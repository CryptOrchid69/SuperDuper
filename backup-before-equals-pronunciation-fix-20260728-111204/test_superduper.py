"""Non-destructive unit tests for SuperDuper; no packets are intercepted."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from shutil import copy2
from typing import ClassVar
from unittest.mock import patch

import SuperDuper as superduper_module
import package_locator as package_locator_module
from package_locator import (
    MARKER_NAME,
    configured_desktop,
    resolve_package_directory,
    validate_package,
)
from windivert_backend import (
    ImpairmentConfig,
    PacketEngine,
    WinDivertApi,
    build_filter,
    corrupt_packet_payload,
    packet_payload_bounds,
)
from voice_backend import (
    MAX_SPEECH_CHARACTERS,
    VoiceConfig,
    VoiceController,
    prepare_text_for_speech,
)
from SuperDuper import (
    CONDITIONS_GUIDANCE,
    DIRECTION_GUIDANCE,
    InfoCenterDialog,
    JITTER_GUIDANCE,
    IP_CIDR_GUIDANCE,
    LATENCY_GUIDANCE,
    PACKET_LOSS_GUIDANCE,
    PORTS_GUIDANCE,
    PRESET_GUIDANCE,
    PROCESS_GUIDANCE,
    PROTOCOL_GUIDANCE,
    TARGETING_GUIDANCE,
    SuperDuperWindow,
)

PROJECT_DIR = Path(__file__).resolve().parent


class FakeSpeechVoice:
    """Silent stand-in used to verify voice queuing without playing audio."""

    description = "Test Female Voice"

    def __init__(self, _config: VoiceConfig) -> None:
        self.spoken: list[str] = []
        self.stopped = threading.Event()
        self.closed = threading.Event()

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped.set()

    def close(self) -> None:
        self.closed.set()


class VoiceControllerTests(unittest.TestCase):
    def test_uppercase_pronoun_it_is_not_spoken_as_initials(self) -> None:
        text = "INSTALL IT. IT WORKS. IT workers maintain IT systems."
        self.assertEqual(
            prepare_text_for_speech(text),
            (
                "INSTALL it. it WORKS. information technology workers "
                "maintain information technology systems."
            ),
        )

    def test_voice_config_rejects_invalid_volume_and_rate(self) -> None:
        with self.assertRaises(ValueError):
            VoiceConfig(volume=101)
        with self.assertRaises(ValueError):
            VoiceConfig(rate=-11)

    def test_muted_controller_does_not_queue_speech(self) -> None:
        controller = VoiceController(voice_factory=FakeSpeechVoice)
        self.assertTrue(controller.muted)
        self.assertFalse(controller.speak("This must remain silent"))
        controller.shutdown()

    def test_unmuted_controller_speaks_on_worker_and_closes(self) -> None:
        voices: list[FakeSpeechVoice] = []
        ready = threading.Event()

        def factory(config: VoiceConfig) -> FakeSpeechVoice:
            voice = FakeSpeechVoice(config)
            voices.append(voice)
            return voice

        controller = VoiceController(
            voice_factory=factory,
            on_ready=lambda _description: ready.set(),
        )
        controller.set_muted(False)
        self.assertTrue(controller.speak(" Voice   is ready. "))
        self.assertTrue(ready.wait(1.0))
        deadline = time.monotonic() + 1.0
        while voices[0].spoken != ["Voice is ready."] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(voices[0].spoken, ["Voice is ready."])
        controller.shutdown()
        self.assertTrue(voices[0].stopped.wait(1.0))
        self.assertTrue(voices[0].closed.wait(1.0))

    def test_muting_stops_active_voice_and_discards_pending_speech(self) -> None:
        voices: list[FakeSpeechVoice] = []
        ready = threading.Event()

        def factory(config: VoiceConfig) -> FakeSpeechVoice:
            voice = FakeSpeechVoice(config)
            voices.append(voice)
            return voice

        controller = VoiceController(
            voice_factory=factory,
            on_ready=lambda _description: ready.set(),
        )
        controller.set_muted(False)
        self.assertTrue(ready.wait(1.0))
        controller.set_muted(True)
        self.assertTrue(voices[0].stopped.wait(1.0))
        self.assertFalse(controller.speak("Muted speech"))
        controller.shutdown()

    def test_stop_speaking_interrupts_voice_without_muting(self) -> None:
        voices: list[FakeSpeechVoice] = []
        ready = threading.Event()

        def factory(config: VoiceConfig) -> FakeSpeechVoice:
            voice = FakeSpeechVoice(config)
            voices.append(voice)
            return voice

        controller = VoiceController(
            voice_factory=factory,
            on_ready=lambda _description: ready.set(),
        )
        controller.set_muted(False)
        self.assertTrue(ready.wait(1.0))
        controller.stop_speaking()
        self.assertTrue(voices[0].stopped.wait(1.0))
        self.assertFalse(controller.muted)
        controller.shutdown()

    def test_conditions_and_combo_guidance_match_requested_scope(self) -> None:
        for phrase in (
            CONDITIONS_GUIDANCE,
            DIRECTION_GUIDANCE,
            PROTOCOL_GUIDANCE,
            LATENCY_GUIDANCE,
            JITTER_GUIDANCE,
            PACKET_LOSS_GUIDANCE,
            TARGETING_GUIDANCE,
            PRESET_GUIDANCE,
            IP_CIDR_GUIDANCE,
            PORTS_GUIDANCE,
            PROCESS_GUIDANCE,
        ):
            self.assertLess(len(phrase), MAX_SPEECH_CHARACTERS)
        self.assertIn("double click", CONDITIONS_GUIDANCE)
        self.assertIn("label", CONDITIONS_GUIDANCE)
        self.assertIn("one time", CONDITIONS_GUIDANCE)
        self.assertIn("Inbound", DIRECTION_GUIDANCE)
        self.assertIn("Outbound", DIRECTION_GUIDANCE)
        for term in ("All traffic", "TCP", "UDP", "IPv4", "IPv6"):
            self.assertIn(term, PROTOCOL_GUIDANCE)
        self.assertIn("milliseconds", LATENCY_GUIDANCE)
        self.assertIn("fixed delay", JITTER_GUIDANCE)
        self.assertIn("percentage", PACKET_LOSS_GUIDANCE)
        self.assertIn("Custom", PRESET_GUIDANCE)
        self.assertIn("automatically discover", IP_CIDR_GUIDANCE)
        self.assertIn("hyphen", PORTS_GUIDANCE)
        self.assertIn("not implemented", PROCESS_GUIDANCE)

    def test_conditions_click_speaks_every_time_when_unmuted(self) -> None:
        class Tabs:
            @staticmethod
            def tabText(index: int) -> str:
                return "CONDITIONS" if index == 0 else "TARGETING"

        class Voice:
            def __init__(self) -> None:
                self.phrases: list[str] = []

            def speak(self, text: str) -> bool:
                self.phrases.append(text)
                return True

        class Status:
            text = ""

            def setText(self, text: str) -> None:
                self.text = text

        window = type("WindowDouble", (), {})()
        window.tabs = Tabs()
        window.voice = Voice()
        window.status = Status()
        SuperDuperWindow.speak_tab_guidance(window, 0)
        SuperDuperWindow.speak_tab_guidance(window, 0)
        SuperDuperWindow.speak_tab_guidance(window, 1)
        self.assertEqual(
            window.voice.phrases,
            [CONDITIONS_GUIDANCE, CONDITIONS_GUIDANCE, TARGETING_GUIDANCE],
        )
        self.assertIn("TARGETING", window.status.text)

    def test_direction_and_protocol_guidance_are_separate_requests(self) -> None:
        class Voice:
            def __init__(self) -> None:
                self.phrases: list[str] = []

            def speak(self, text: str) -> bool:
                self.phrases.append(text)
                return True

        class Status:
            def setText(self, _text: str) -> None:
                pass

        window = type("WindowDouble", (), {})()
        window.voice = Voice()
        window.status = Status()
        SuperDuperWindow.speak_direction_guidance(window)
        SuperDuperWindow.speak_protocol_guidance(window)
        self.assertEqual(
            window.voice.phrases,
            [DIRECTION_GUIDANCE, PROTOCOL_GUIDANCE],
        )

    def test_condition_slider_guidance_requests_are_separate(self) -> None:
        class Voice:
            def __init__(self) -> None:
                self.phrases: list[str] = []

            def speak(self, text: str) -> bool:
                self.phrases.append(text)
                return True

        class Status:
            def setText(self, _text: str) -> None:
                pass

        window = type("WindowDouble", (), {})()
        window.voice = Voice()
        window.status = Status()
        SuperDuperWindow.speak_latency_guidance(window)
        SuperDuperWindow.speak_jitter_guidance(window)
        SuperDuperWindow.speak_packet_loss_guidance(window)
        self.assertEqual(
            window.voice.phrases,
            [LATENCY_GUIDANCE, JITTER_GUIDANCE, PACKET_LOSS_GUIDANCE],
        )

    def test_targeting_guidance_requests_are_separate(self) -> None:
        class Voice:
            def __init__(self) -> None:
                self.phrases: list[str] = []

            def speak(self, text: str) -> bool:
                self.phrases.append(text)
                return True

        class Status:
            def setText(self, _text: str) -> None:
                pass

        window = type("WindowDouble", (), {})()
        window.voice = Voice()
        window.status = Status()
        window._speak_labeled_guidance = lambda label, guidance: (
            SuperDuperWindow._speak_labeled_guidance(
                window,
                label,
                guidance,
            )
        )
        SuperDuperWindow.speak_preset_guidance(window)
        SuperDuperWindow.speak_ip_cidr_guidance(window)
        SuperDuperWindow.speak_ports_guidance(window)
        SuperDuperWindow.speak_process_guidance(window)
        self.assertEqual(
            window.voice.phrases,
            [
                PRESET_GUIDANCE,
                IP_CIDR_GUIDANCE,
                PORTS_GUIDANCE,
                PROCESS_GUIDANCE,
            ],
        )

    def test_remaining_tab_guidance_is_complete_and_queue_safe(self) -> None:
        names = (
            "ADVANCED_EFFECTS_GUIDANCE",
            "DUPLICATION_GUIDANCE",
            "REORDER_GUIDANCE",
            "REORDER_HOLD_GUIDANCE",
            "BANDWIDTH_GUIDANCE",
            "CORRUPTION_GUIDANCE",
            "BIT_FLIPS_GUIDANCE",
            "SAFETY_GUIDANCE",
            "MAX_QUEUE_GUIDANCE",
            "MAX_SESSION_GUIDANCE",
            "PROFILES_GUIDANCE",
            "SAVED_PROFILE_GUIDANCE",
            "DUPE_GUIDANCE",
        )
        phrases = [getattr(superduper_module, name) for name in names]
        self.assertTrue(all(0 < len(text) < MAX_SPEECH_CHARACTERS for text in phrases))
        self.assertTrue(all("DayZ" not in text for text in phrases))
        self.assertIn("Numpad minus", superduper_module.DUPE_GUIDANCE)
        self.assertLess(
            len(superduper_module.DUPE_INSTRUCTIONS),
            MAX_SPEECH_CHARACTERS,
        )
        self.assertIn("double click", superduper_module.SAFETY_GUIDANCE)
        self.assertIn("does not start", superduper_module.SAVED_PROFILE_GUIDANCE)

    def test_numpad_insert_hotkey_synchronizes_mute_button(self) -> None:
        class Button:
            def __init__(self) -> None:
                self.checked = False

            def isChecked(self) -> bool:
                return self.checked

            def setChecked(self, checked: bool) -> None:
                self.checked = checked

            def setToolTip(self, _text: str) -> None:
                pass

        class Voice:
            def __init__(self) -> None:
                self.mute_states: list[bool] = []

            def set_muted(self, muted: bool) -> None:
                self.mute_states.append(muted)

            def speak(self, _text: str) -> bool:
                return True

        class Status:
            text = ""

            def setText(self, text: str) -> None:
                self.text = text

        window = type("WindowDouble", (), {})()
        window.mute_button = Button()
        window.voice = Voice()
        window.status = Status()
        window.toggle_voice_muted = lambda muted: SuperDuperWindow.toggle_voice_muted(window, muted)
        SuperDuperWindow.toggle_voice_hotkey(window)
        SuperDuperWindow.toggle_voice_hotkey(window)
        self.assertEqual(window.voice.mute_states, [True, False])
        self.assertFalse(window.mute_button.checked)
        self.assertIn("enabled", window.status.text)

    def test_numpad_star_announces_only_successful_activation(self) -> None:
        class Engine:
            running = False

        class Voice:
            def __init__(self) -> None:
                self.phrases: list[str] = []

            def speak(self, text: str) -> bool:
                self.phrases.append(text)
                return True

        window = type("WindowDouble", (), {})()
        window.engine = Engine()
        window.voice = Voice()

        window.toggle_engine = lambda: setattr(window.engine, "running", True)
        SuperDuperWindow.toggle_engine_from_hotkey(window)
        self.assertEqual(window.voice.phrases, ["Activated."])

        window.voice.phrases.clear()
        window.engine.running = False
        window.toggle_engine = lambda: None
        SuperDuperWindow.toggle_engine_from_hotkey(window)
        self.assertEqual(window.voice.phrases, [])

        window.engine.running = True
        window.toggle_engine = lambda: setattr(window.engine, "running", False)
        SuperDuperWindow.toggle_engine_from_hotkey(window)
        self.assertEqual(window.voice.phrases, ["Deactivated."])

    def test_clear_removes_all_six_calibration_values(self) -> None:
        class Settings:
            def __init__(self) -> None:
                self.values = {
                    f"dayz_{name}_{axis}": 100
                    for name in ("exit", "cancel", "play")
                    for axis in ("x", "y")
                }
                self.values["dayz_calibration_sequence"] = "[[10,20],[30,40]]"
                self.synced = False

            def remove(self, key: str) -> None:
                self.values.pop(key, None)

            def sync(self) -> None:
                self.synced = True

        class Status:
            text = ""

            def setText(self, text: str) -> None:
                self.text = text

        window = type("WindowDouble", (), {})()
        window._dayz_sequence_active = False
        window._dayz_calibration_target = "exit"
        window.settings = Settings()
        window.status = Status()
        refreshed: list[bool] = []
        window._refresh_dayz_coordinate_labels = lambda: refreshed.append(True)
        SuperDuperWindow.clear_dayz_calibration(window)
        self.assertEqual(window.settings.values, {})
        self.assertTrue(window.settings.synced)
        self.assertEqual(refreshed, [True])
        self.assertEqual(window._dayz_calibration_target, "")
        self.assertIn("Calibration cleared", window.status.text)

    def test_ordered_calibration_round_trip_preserves_repeated_points(self) -> None:
        class Settings:
            values: dict[str, str] = {}

            def value(self, key: str, default: str) -> str:
                return self.values.get(key, default)

            def setValue(self, key: str, value: str) -> None:
                self.values[key] = value

            def sync(self) -> None:
                pass

        window = type("WindowDouble", (), {})()
        window.settings = Settings()
        points = [(100, 200), (300, 400), (100, 200), (300, 400)]
        SuperDuperWindow._save_dayz_calibration_sequence(window, points)
        loaded = SuperDuperWindow._dayz_calibration_sequence(window)
        self.assertEqual(loaded, points)

    def test_dupe_timing_keeps_two_second_cancel_and_eight_second_lobby_wait(
        self,
    ) -> None:
        self.assertEqual(superduper_module.DAYZ_CANCEL_DELAY_MS, 2000)
        self.assertEqual(superduper_module.DAYZ_LOBBY_WAIT_MS, 8000)

        class Spin:
            @staticmethod
            def value() -> int:
                return 8

        window = type("WindowDouble", (), {})()
        window._dayz_sequence_active = True
        window._dayz_sequence_generation = 7
        window._dayz_playback_points = [(1, 2), (3, 4), (5, 6), (7, 8)]
        window.dayz_logout_wait_spin = Spin()
        window._click_dayz_point = lambda point, label: point == (5, 6) and label == "Final Exit"
        scheduled: list[tuple[int, object]] = []
        window._dayz_schedule = lambda delay, generation, callback: scheduled.append(
            (delay, callback)
        )
        window._dayz_rejoin = lambda _generation: None
        SuperDuperWindow._dayz_click_final_exit(window, 7)
        self.assertEqual(scheduled[0][0], 16000)

    def test_info_center_protects_only_its_named_root_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary).resolve()
            protected = package / "INFO-CENTER"
            protected.mkdir()
            ordinary = package / "Ordinary"
            ordinary.mkdir()
            dialog = type("InfoCenterDouble", (), {})()
            dialog.package_directory = package
            dialog.protected_directory = protected
            self.assertTrue(InfoCenterDialog._is_protected(dialog, protected))
            self.assertFalse(InfoCenterDialog._is_protected(dialog, ordinary))
            self.assertTrue(InfoCenterDialog._is_within_package(dialog, ordinary))

    def test_info_center_hides_package_text_files_but_not_user_folders(self) -> None:
        self.assertTrue(InfoCenterDialog._hide_at_package_root("READ ME.txt", False))
        self.assertTrue(InfoCenterDialog._hide_at_package_root("backup-before-update", True))
        self.assertFalse(InfoCenterDialog._hide_at_package_root("INFO-CENTER", True))
        self.assertFalse(InfoCenterDialog._hide_at_package_root("My Research", True))

    def test_info_center_copy_names_never_overwrite_existing_items(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            (parent / "Guide.txt").write_text("original", encoding="utf-8")
            destination = InfoCenterDialog._unique_destination(parent, "Guide.txt")
            self.assertEqual(destination.name, "Guide - Copy 2.txt")

    def test_info_center_text_double_click_uses_bounded_voice_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            text_path = Path(temporary) / "Lesson.txt"
            text_path.write_text(
                "A" * (MAX_SPEECH_CHARACTERS + 100),
                encoding="utf-8",
            )
            spoken: list[tuple[str, str]] = []
            dialog = type("InfoCenterDouble", (), {})()
            dialog._is_within_package = lambda _path: True
            dialog._read_text_aloud = lambda name, text: spoken.append((name, text)) or True
            dialog.document_title = type(
                "LabelDouble",
                (),
                {"setText": lambda _self, _text: None},
            )()
            dialog.document_text = type(
                "TextDouble",
                (),
                {"setPlainText": lambda _self, _text: None},
            )()
            dialog.content_stack = type(
                "StackDouble",
                (),
                {"setCurrentIndex": lambda _self, _index: None},
            )()
            dialog.back_button = type(
                "ButtonDouble",
                (),
                {
                    "show": lambda _self: None,
                    "setStyleSheet": lambda _self, _style: None,
                },
            )()
            dialog.back_glow = type(
                "GlowDouble",
                (),
                {
                    "setColor": lambda _self, _color: None,
                    "setBlurRadius": lambda _self, _radius: None,
                },
            )()
            dialog.arrow_timer = type(
                "TimerDouble",
                (),
                {"start": lambda _self: None},
            )()
            dialog._arrow_glow_on = False
            dialog._pulse_back_arrow = lambda: None
            InfoCenterDialog._read_text_file_aloud(dialog, text_path)
            self.assertEqual(spoken[0][0], "Lesson.txt")
            self.assertEqual(len(spoken[0][1]), MAX_SPEECH_CHARACTERS)


class FilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api = WinDivertApi(PROJECT_DIR / "WinDivert.dll")

    def assert_compiles(self, expression: str) -> None:
        self.api.validate_filter(expression)

    def test_all_traffic(self) -> None:
        expression = build_filter("Both", "All traffic", "", "")
        self.assertEqual(expression, "true")
        self.assert_compiles(expression)

    def test_tcp_port_list_and_range(self) -> None:
        expression = build_filter(
            "Outbound",
            "TCP",
            "192.168.1.0/24",
            "80, 443, 8000-8100",
        )
        self.assert_compiles(expression)

    def test_udp_ipv6_target(self) -> None:
        expression = build_filter("Inbound", "UDP", "2001:db8::/64", "53")
        self.assert_compiles(expression)

    def test_mismatched_address_family(self) -> None:
        with self.assertRaises(ValueError):
            build_filter("Both", "IPv4", "2001:db8::1", "")

    def test_unknown_filter_options_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_filter("Sideways", "TCP", "", "")
        with self.assertRaises(ValueError):
            build_filter("Both", "SCTP", "", "")

    def test_impairment_config_rejects_out_of_range_values(self) -> None:
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", -1, 0, 0)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 2001, 0)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 0, 101)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 0, 0, duplication_percent=101)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 0, 0, reorder_percent=-1)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 0, 0, reorder_delay_ms=10001)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 0, 0, bandwidth_kbps=1000001)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 0, 0, corruption_percent=26)
        with self.assertRaises(ValueError):
            ImpairmentConfig("true", 0, 0, 0, corruption_bit_flips=9)


class CorruptionTests(unittest.TestCase):
    @staticmethod
    def ipv4_tcp_packet(payload: bytes = b"laboratory") -> bytes:
        total_length = 20 + 20 + len(payload)
        ip_header = bytearray(20)
        ip_header[0] = 0x45
        ip_header[2:4] = total_length.to_bytes(2, "big")
        ip_header[9] = 6
        tcp_header = bytearray(20)
        tcp_header[12] = 0x50
        return bytes(ip_header + tcp_header + payload)

    def test_payload_bounds_reject_headers_and_header_only_packets(self) -> None:
        packet = self.ipv4_tcp_packet(b"")
        self.assertIsNone(packet_payload_bounds(packet))
        self.assertIsNone(packet_payload_bounds(b"not an IP packet"))

    def test_corruption_changes_only_payload_bits(self) -> None:
        packet = self.ipv4_tcp_packet()
        with patch("windivert_backend.random.sample", return_value=[0, 9, 18]):
            changed, did_change = corrupt_packet_payload(packet, 3)
        self.assertTrue(did_change)
        self.assertEqual(changed[:40], packet[:40])
        self.assertNotEqual(changed[40:], packet[40:])
        changed_bits = sum(
            (left ^ right).bit_count() for left, right in zip(packet, changed, strict=True)
        )
        self.assertEqual(changed_bits, 3)

    def test_unsupported_protocol_is_not_modified(self) -> None:
        packet = bytearray(self.ipv4_tcp_packet())
        packet[9] = 1
        changed, did_change = corrupt_packet_payload(bytes(packet), 1)
        self.assertFalse(did_change)
        self.assertEqual(changed, bytes(packet))


class PackageLocatorTests(unittest.TestCase):
    @staticmethod
    def _copy_authentic_package(destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for name in (
            MARKER_NAME,
            "WinDivert.dll",
            "WinDivert64.sys",
            "WinDivert-LICENSE.txt",
            "SuperDuper.py",
            "windivert_backend.py",
            "SuperDuper.ico",
        ):
            copy2(PROJECT_DIR / name, destination / name)

    def test_configured_desktop_and_real_package_are_resolved(self) -> None:
        desktop = configured_desktop()
        location = resolve_package_directory()
        self.assertTrue(desktop.is_dir())
        self.assertEqual(location.path, PROJECT_DIR)
        self.assertTrue(validate_package(location.path, True))

    def test_tampered_binary_fails_integrity_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary)
            self._copy_authentic_package(candidate)
            self.assertTrue(validate_package(candidate, True))
            with (candidate / "WinDivert.dll").open("ab") as stream:
                stream.write(b"tampered")
            self.assertFalse(validate_package(candidate, True))

    def test_manifest_cannot_remove_required_official_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary)
            self._copy_authentic_package(candidate)
            marker_path = candidate / MARKER_NAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            del marker["required_files"]["WinDivert64.sys"]
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            self.assertFalse(validate_package(candidate, True))

    def test_manifest_cannot_redefine_application_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary)
            self._copy_authentic_package(candidate)
            marker_path = candidate / MARKER_NAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["application_markers"] = ["unrelated.txt", "another.txt"]
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            self.assertFalse(validate_package(candidate, True))

    def test_tampered_application_marker_fails_integrity_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary)
            self._copy_authentic_package(candidate)
            with (candidate / "SuperDuper.py").open("a", encoding="utf-8") as stream:
                stream.write("\n# counterfeit change\n")
            self.assertFalse(validate_package(candidate, True))

    def test_separate_desktop_executable_finds_nested_authentic_package(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            desktop = Path(temporary) / "Configured Desktop"
            package = desktop / "SuperDuper-Enhanced"
            self._copy_authentic_package(package)
            separate_executable = desktop / "SuperDuper.exe"
            separate_executable.write_bytes(b"standalone executable placeholder")
            unrelated_module = Path(temporary) / "bundle" / "package_locator.py"
            unrelated_module.parent.mkdir()
            unrelated_module.write_text("# isolated bundle", encoding="utf-8")
            invalid_bundle = Path(temporary) / "invalid-bundle"
            invalid_bundle.mkdir()

            with (
                patch.object(
                    package_locator_module,
                    "configured_desktop",
                    return_value=desktop,
                ),
                patch.object(
                    package_locator_module,
                    "__file__",
                    str(unrelated_module),
                ),
                patch.object(
                    package_locator_module.sys,
                    "executable",
                    str(separate_executable),
                ),
                patch.object(
                    package_locator_module,
                    "bundled_directory",
                    return_value=invalid_bundle,
                ),
            ):
                location = package_locator_module.resolve_package_directory()

            self.assertEqual(location.path, package.resolve())
            self.assertEqual(location.source, "configured Desktop package")


class FakeWinDivertApi:
    """In-memory driver double used to test lifecycle and fail-open flushing."""

    instances: ClassVar[list[FakeWinDivertApi]] = []

    def __init__(self, _dll_path: Path) -> None:
        self.closed = False
        self.receive_shutdown = threading.Event()
        self.sent: list[bytes] = []
        self._delivered = False
        self.__class__.instances.append(self)

    def open(self, _filter_text: str) -> int:
        return 123

    def recv(self, _handle: int) -> tuple[bytes, bytes] | None:
        if not self._delivered:
            self._delivered = True
            return b"packet", bytes(80)
        self.receive_shutdown.wait(timeout=2)
        return None

    def send(self, _handle: int, packet: bytes, _address: bytes) -> bool:
        self.sent.append(packet)
        return True

    def recalculate_checksums(self, packet: bytes, _address: bytes) -> bytes:
        return packet

    def shutdown(self, _handle: int, how: int = 3) -> None:
        if how & 1:
            self.receive_shutdown.set()

    def close(self, _handle: int) -> None:
        self.closed = True


class BurstFakeWinDivertApi(FakeWinDivertApi):
    """Deliver enough packets immediately to exercise the queue limit."""

    def __init__(self, dll_path: Path) -> None:
        super().__init__(dll_path)
        self._delivered_count = 0

    def recv(self, _handle: int) -> tuple[bytes, bytes] | None:
        if self._delivered_count < 101:
            self._delivered_count += 1
            return f"packet-{self._delivered_count}".encode(), bytes(80)
        self.receive_shutdown.wait(timeout=2)
        return None


class PayloadFakeWinDivertApi(FakeWinDivertApi):
    """Deliver one valid TCP payload packet for corruption integration tests."""

    def recv(self, _handle: int) -> tuple[bytes, bytes] | None:
        if not self._delivered:
            self._delivered = True
            return CorruptionTests.ipv4_tcp_packet(), bytes(80)
        self.receive_shutdown.wait(timeout=2)
        return None


class EngineLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeWinDivertApi.instances.clear()

    def test_stop_flushes_delayed_packet_before_close(self) -> None:
        config = ImpairmentConfig(
            filter_text="true",
            latency_ms=15000,
            jitter_ms=0,
            packet_loss_percent=0,
        )
        with patch("windivert_backend.WinDivertApi", FakeWinDivertApi):
            engine = PacketEngine(PROJECT_DIR / "WinDivert.dll")
            engine.start(config)
            deadline = time.monotonic() + 2
            while not engine._queue and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(engine._queue)
            engine.stop()
        fake = FakeWinDivertApi.instances[-1]
        self.assertEqual(fake.sent, [b"packet"])
        self.assertTrue(fake.closed)
        self.assertFalse(engine.running)

    def test_duplication_queues_and_releases_a_real_second_packet(self) -> None:
        snapshots = []
        config = ImpairmentConfig(
            filter_text="true",
            latency_ms=15000,
            jitter_ms=0,
            packet_loss_percent=0,
            duplication_percent=100,
        )
        with patch("windivert_backend.WinDivertApi", FakeWinDivertApi):
            engine = PacketEngine(
                PROJECT_DIR / "WinDivert.dll",
                on_stats=snapshots.append,
            )
            engine.start(config)
            deadline = time.monotonic() + 2
            while len(engine._queue) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(len(engine._queue), 2)
            engine.stop()
        fake = FakeWinDivertApi.instances[-1]
        self.assertEqual(fake.sent, [b"packet", b"packet"])
        self.assertEqual(snapshots[-1].duplicated, 1)

    def test_reordering_adds_the_configured_variable_hold(self) -> None:
        config = ImpairmentConfig(
            filter_text="true",
            latency_ms=15000,
            jitter_ms=0,
            packet_loss_percent=0,
            reorder_percent=100,
            reorder_delay_ms=500,
        )
        with (
            patch("windivert_backend.WinDivertApi", FakeWinDivertApi),
            patch("windivert_backend.random.uniform", side_effect=[0, 0.4]),
        ):
            engine = PacketEngine(PROJECT_DIR / "WinDivert.dll")
            started = time.monotonic()
            engine.start(config)
            deadline = time.monotonic() + 2
            while not engine._queue and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(engine._queue)
            self.assertGreaterEqual(engine._queue[0][0] - started, 15.39)
            engine.stop()

    def test_bandwidth_limit_serializes_packet_release_budget(self) -> None:
        config = ImpairmentConfig(
            filter_text="true",
            latency_ms=15000,
            jitter_ms=0,
            packet_loss_percent=0,
            bandwidth_kbps=1,
        )
        with patch("windivert_backend.WinDivertApi", FakeWinDivertApi):
            engine = PacketEngine(PROJECT_DIR / "WinDivert.dll")
            engine.start(config)
            deadline = time.monotonic() + 2
            while not engine._queue and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(engine._queue)
            first_due = engine._queue[0][0]
            self.assertAlmostEqual(
                engine._bandwidth_next_due - first_due,
                len(b"packet") * 8 / 1000,
                places=3,
            )
            engine.stop()

    def test_corruption_mutates_payload_before_queued_reinjection(self) -> None:
        snapshots = []
        original = CorruptionTests.ipv4_tcp_packet()
        config = ImpairmentConfig(
            filter_text="tcp and tcp.DstPort == 443",
            latency_ms=15000,
            jitter_ms=0,
            packet_loss_percent=0,
            corruption_percent=25,
            corruption_bit_flips=2,
        )
        with (
            patch("windivert_backend.WinDivertApi", PayloadFakeWinDivertApi),
            patch("windivert_backend.random.random", return_value=0),
            patch("windivert_backend.random.sample", return_value=[0, 9]),
        ):
            engine = PacketEngine(
                PROJECT_DIR / "WinDivert.dll",
                on_stats=snapshots.append,
            )
            engine.start(config)
            deadline = time.monotonic() + 2
            while not engine._queue and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(engine._queue)
            queued_packet = engine._queue[0][2]
            self.assertEqual(queued_packet[:40], original[:40])
            self.assertNotEqual(queued_packet[40:], original[40:])
            engine.stop()
        self.assertEqual(snapshots[-1].corrupted, 1)

    def test_queue_limit_triggers_fail_safe_and_releases_packets(self) -> None:
        errors: list[str] = []
        error_event = threading.Event()

        def record_error(message: str) -> None:
            errors.append(message)
            error_event.set()

        config = ImpairmentConfig(
            filter_text="true",
            latency_ms=15000,
            jitter_ms=0,
            packet_loss_percent=0,
            max_queue_packets=100,
        )
        with patch("windivert_backend.WinDivertApi", BurstFakeWinDivertApi):
            engine = PacketEngine(
                PROJECT_DIR / "WinDivert.dll",
                on_error=record_error,
            )
            engine.start(config)
            self.assertTrue(error_event.wait(timeout=2))
            engine.stop()
        fake = BurstFakeWinDivertApi.instances[-1]
        self.assertIn("queue reached 100 packets", errors[-1])
        self.assertEqual(len(fake.sent), 101)
        self.assertTrue(fake.closed)

    def test_session_timeout_triggers_fail_safe(self) -> None:
        errors: list[str] = []
        error_event = threading.Event()

        def record_error(message: str) -> None:
            errors.append(message)
            error_event.set()

        config = ImpairmentConfig(
            filter_text="true",
            latency_ms=0,
            jitter_ms=0,
            packet_loss_percent=0,
            max_session_seconds=1,
        )
        with patch("windivert_backend.WinDivertApi", FakeWinDivertApi):
            engine = PacketEngine(
                PROJECT_DIR / "WinDivert.dll",
                on_error=record_error,
            )
            engine.start(config)
            self.assertTrue(error_event.wait(timeout=2))
            engine.stop()
        self.assertIn("1-second limit reached", errors[-1])
        self.assertFalse(engine.running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
