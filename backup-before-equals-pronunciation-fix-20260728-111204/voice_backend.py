"""Queued Windows text-to-speech support for the SuperDuper interface."""

from __future__ import annotations

import locale
import queue
import re
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

MAX_SPEECH_CHARACTERS = 5000
_INFORMATION_TECHNOLOGY_CONTEXT = re.compile(
    r"\bIT(?=\s+(?i:administrator|department|infrastructure|professional|"
    r"security|service|staff|support|system|team|technician|worker)s?\b)"
)
_UPPERCASE_PRONOUN_IT = re.compile(r"\bIT\b")


def prepare_text_for_speech(text: str) -> str:
    """Resolve ambiguous uppercase IT without changing displayed documents."""

    prepared = _INFORMATION_TECHNOLOGY_CONTEXT.sub(
        "information technology",
        str(text),
    )
    return _UPPERCASE_PRONOUN_IT.sub("it", prepared)


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    """Friendly defaults for a gentle but clearly audible application voice."""

    volume: int = 85
    rate: int = -1
    preferred_gender: str = "Female"

    def __post_init__(self) -> None:
        if not 0 <= self.volume <= 100:
            raise ValueError("Voice volume must be between 0 and 100")
        if not -10 <= self.rate <= 10:
            raise ValueError("Voice rate must be between -10 and 10")


class SpeechVoice(Protocol):
    """Small interface that keeps the controller independently testable."""

    description: str

    def speak(self, text: str) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class _SapiVoice:
    """Windows SAPI adapter. All COM work remains on its worker thread."""

    def __init__(self, config: VoiceConfig) -> None:
        import pythoncom
        import win32com.client

        self._pythoncom = pythoncom
        pythoncom.CoInitialize()
        try:
            self._voice = win32com.client.Dispatch("SAPI.SpVoice")
            token = self._choose_token(config.preferred_gender)
            if token is not None:
                self._voice.Voice = token
            self._voice.Volume = config.volume
            self._voice.Rate = config.rate
            self.description = self._voice.Voice.GetDescription()
        except Exception:
            pythoncom.CoUninitialize()
            raise

    def _choose_token(self, preferred_gender: str):
        voices = self._voice.GetVoices()
        tokens = [voices.Item(index) for index in range(voices.Count)]
        if not tokens:
            return None
        preferred_language = _windows_language_hex()
        gender_matches = [
            token
            for token in tokens
            if _token_attribute(token, "Gender").casefold() == preferred_gender.casefold()
        ]
        for token in gender_matches:
            if preferred_language in _token_attribute(token, "Language").split(";"):
                return token
        return gender_matches[0] if gender_matches else tokens[0]

    def speak(self, text: str) -> None:
        self._voice.Speak(text, 1)

    def stop(self) -> None:
        self._voice.Speak("", 3)

    def close(self) -> None:
        self.stop()
        self._voice = None
        self._pythoncom.CoUninitialize()


def _token_attribute(token, name: str) -> str:
    try:
        return str(token.GetAttribute(name))
    except Exception:
        return ""


def _windows_language_hex() -> str:
    """Return the current Windows language as SAPI's lower-case hex LCID."""

    try:
        language_code = locale.getlocale()[0] or ""
        for number, name in locale.windows_locale.items():
            if name.casefold() == language_code.casefold():
                return f"{number:x}"
    except Exception:
        pass
    return ""


class VoiceController:
    """Own a non-blocking speech queue that is muted until explicitly enabled."""

    _STOP = object()
    _MUTE = object()

    def __init__(
        self,
        config: VoiceConfig | None = None,
        *,
        on_ready: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        voice_factory: Callable[[VoiceConfig], SpeechVoice] | None = None,
    ) -> None:
        self.config = config or VoiceConfig()
        self._on_ready = on_ready or (lambda _description: None)
        self._on_error = on_error or (lambda _message: None)
        self._voice_factory = voice_factory or _SapiVoice
        self._queue: queue.Queue[str | object] = queue.Queue()
        self._lock = threading.Lock()
        self._muted = True
        self._closed = False
        self._worker: threading.Thread | None = None

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            if self._closed:
                return
            self._muted = muted
            if not muted and self._worker is None:
                self._worker = threading.Thread(
                    target=self._run,
                    name="SuperDuper-Voice",
                    daemon=True,
                )
                self._worker.start()
            worker = self._worker
        if muted:
            self._discard_pending_speech()
            if worker is not None:
                self._queue.put(self._MUTE)

    def speak(self, text: str) -> bool:
        """Queue a concise announcement; return False when muted or unavailable."""

        clean_text = " ".join(prepare_text_for_speech(text).split()).strip()
        if not clean_text:
            return False
        with self._lock:
            if self._muted or self._closed:
                return False
        self._queue.put(clean_text[:MAX_SPEECH_CHARACTERS])
        return True

    def stop_speaking(self) -> None:
        """Stop current and queued speech without changing the mute setting."""

        with self._lock:
            if self._closed:
                return
            worker = self._worker
        self._discard_pending_speech()
        if worker is not None:
            self._queue.put(self._MUTE)

    def shutdown(self, timeout: float = 3.0) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._muted = True
            worker = self._worker
        self._discard_pending_speech()
        if worker is not None:
            self._queue.put(self._STOP)
            worker.join(timeout=max(0.0, timeout))

    def _discard_pending_speech(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                return

    def _run(self) -> None:
        voice: SpeechVoice | None = None
        try:
            voice = self._voice_factory(self.config)
            self._on_ready(voice.description)
            while True:
                item = self._queue.get()
                try:
                    if item is self._STOP:
                        voice.stop()
                        return
                    if item is self._MUTE:
                        voice.stop()
                        continue
                    if not self.muted:
                        voice.speak(str(item))
                finally:
                    self._queue.task_done()
        except Exception as exc:
            with self._lock:
                self._muted = True
            self._on_error(f"Voice could not start: {exc}")
        finally:
            if voice is not None:
                with suppress(Exception):
                    voice.close()
            with self._lock:
                self._worker = None
