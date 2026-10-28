"""SuperDuper desktop network-condition interface and WinDivert controller."""

from __future__ import annotations

import csv
import ctypes
import io
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QDir, QObject, QSettings, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFileSystemModel,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from package_locator import PackageLocation, resolve_package_directory
from voice_backend import MAX_SPEECH_CHARACTERS, VoiceConfig, VoiceController
from windivert_backend import (
    EngineStats,
    ImpairmentConfig,
    PacketEngine,
    WinDivertError,
    build_filter,
)


@dataclass(frozen=True, slots=True)
class AppDefaults:
    """Default values used by both the interface and Reset action."""

    direction: str = "Both"
    protocol: str = "All traffic"
    latency_ms: int = 120
    jitter_ms: int = 20
    packet_loss_percent: int = 2
    duplication_percent: int = 0
    reorder_percent: int = 0
    reorder_delay_ms: int = 250
    bandwidth_kbps: int = 0
    corruption_percent: int = 0
    corruption_bit_flips: int = 1
    preset: str = "Custom"
    ip_filter: str = ""
    port_filter: str = ""
    process_filter: str = "Any process"
    max_queue_packets: int = 10000
    max_session_minutes: int = 0


DEFAULTS = AppDefaults()
PRESET_VALUES = {
    "All Traffic": ("Both", "All traffic", "", ""),
    "Localhost": ("Both", "All traffic", "127.0.0.1", ""),
    "Web Traffic": ("Both", "TCP", "", "80, 443"),
    "DNS Traffic": ("Both", "UDP", "", "53"),
}
WM_HOTKEY = 0x0312
HOTKEY_ID_TOGGLE = 0x5355
HOTKEY_ID_EMERGENCY = 0x5356
HOTKEY_ID_DAYZ = 0x5357
HOTKEY_ID_DAYZ_CAPTURE = 0x5358
HOTKEY_ID_VOICE_NUMPAD0 = 0x535B
HOTKEY_ID_VOICE_INSERT = 0x535C
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_MULTIPLY = 0x6A
VK_ADD = 0x6B
VK_SUBTRACT = 0x6D
VK_NUMPAD0 = 0x60
VK_INSERT = 0x2D
DAYZ_CANCEL_CYCLES = 3
DAYZ_CANCEL_DELAY_MS = 2000
DAYZ_BETWEEN_CYCLES_MS = 750
DAYZ_MENU_OPEN_DELAY_MS = 350
DAYZ_LOBBY_WAIT_MS = 8000
CONDITIONS_GUIDANCE = (
    "Please double click the Direction, Protocol, Latency, Jitter, or Packet "
    "Loss label that you want to learn about, or click one time on any control "
    "below to begin using it."
)
DIRECTION_GUIDANCE = (
    "Direction controls which way the matching network packets are traveling. "
    "Choose Both when you want SuperDuper to affect packets traveling in both "
    "directions. Inbound means packets arriving at your computer from the "
    "server. These packets can include information the server sends to your "
    "game, such as world updates and other player activity. Outbound means "
    "packets leaving your computer and traveling to the server. These packets "
    "can include information your game sends, such as movement or actions. "
    "For a balanced experiment, choose Both. Choose Inbound when you want to "
    "study only incoming traffic, or Outbound when you want to study only "
    "outgoing traffic. Direction works together with Protocol and Targeting. "
    "A single click on the control below the Direction label opens the list and "
    "lets you choose a setting. Double click the Direction label only when you "
    "want to hear this explanation."
)
PROTOCOL_GUIDANCE = (
    "Protocol chooses the type of matching network traffic SuperDuper affects. "
    "All traffic includes every supported Internet Protocol packet that also "
    "matches your Direction and Targeting settings. TCP is a reliable, ordered "
    "connection used when information must arrive correctly and in sequence. "
    "Web pages, login services, and some game services commonly use TCP. UDP "
    "favors speed and low delay instead of guaranteed delivery. Real-time games "
    "commonly use UDP for movement, position, voice, and rapidly changing world "
    "updates. IPv4 affects only Internet Protocol version four traffic. IPv6 "
    "affects only Internet Protocol version six traffic. Most private networks "
    "still use IPv4, but the correct choice depends on the server connection. "
    "If you do not know which protocol the experiment uses, begin with All "
    "traffic and narrow the Targeting settings carefully. A single click on the "
    "control below the Protocol label opens the list and lets you choose a "
    "setting. Double click the Protocol label only when you want to hear this "
    "explanation."
)
LATENCY_GUIDANCE = (
    "Latency is a fixed amount of extra waiting time added to every matching "
    "packet before SuperDuper allows it to continue. It is measured in "
    "milliseconds. One thousand milliseconds equals one full second. A low "
    "latency value creates a small delay between an action and its response. A "
    "larger value makes movement, inventory actions, and server responses feel "
    "more delayed. Zero milliseconds adds no fixed delay. For a gentle test, "
    "begin around fifty to one hundred twenty milliseconds and increase the "
    "value slowly. Drag the slider for a broad change, use the arrow keys for "
    "one-millisecond steps, or type an exact number in the large value box. "
    "Latency affects only traffic that also matches Direction, Protocol, and "
    "Targeting. Double click the Latency label whenever you want to hear this "
    "explanation."
)
JITTER_GUIDANCE = (
    "Jitter means the delay does not stay perfectly even. SuperDuper randomly "
    "varies the waiting time of matching packets around the Latency setting. It "
    "is measured in milliseconds. With Jitter at zero, the added Latency is "
    "steady. As Jitter increases, packets can arrive at less consistent times. "
    "In a game this may appear as uneven movement, brief stuttering, or updates "
    "that do not arrive in a smooth rhythm. Jitter is different from Latency: "
    "Latency is the basic fixed delay, while Jitter is the changing part of the "
    "delay. Begin at zero and raise it in small steps, such as five or ten "
    "milliseconds, so the result is easy to observe. Drag the slider, use the "
    "arrow keys, or type an exact value in the large value box. Double click "
    "the Jitter label whenever you want to hear this explanation."
)
PACKET_LOSS_GUIDANCE = (
    "Packet Loss is the percentage of matching packets that SuperDuper "
    "intentionally drops instead of sending them onward. Zero percent drops no "
    "matching packets. One percent means approximately one out of every one "
    "hundred matching packets is dropped over time. Because each packet is "
    "chosen randomly, a short test may not show the exact percentage. Small "
    "amounts can cause missing updates, delayed corrections, or rubber-banding. "
    "Large amounts can make a connection unstable or disconnect it. One hundred "
    "percent blocks all matching traffic. Begin with one or two percent and "
    "increase it carefully. Drag the slider, use the arrow keys, or type an "
    "exact percentage in the large value box. Packet Loss applies only to "
    "traffic matching Direction, Protocol, and Targeting. Double click the "
    "Packet Loss label whenever you want to hear this explanation."
)
TARGETING_GUIDANCE = (
    "Please double click the Preset, I P or C I D R, Ports, or Process label "
    "that you want to learn about, or click one time on any control below to "
    "begin using it."
)
PRESET_GUIDANCE = (
    "Preset provides a quick starting configuration for Direction, Protocol, "
    "I P targeting, and Ports. Custom keeps the values you choose yourself. "
    "All Traffic selects both directions, all protocols, any I P address, and "
    "any port. Localhost limits the I P target to this computer, using address "
    "one twenty-seven dot zero dot zero dot one. Web Traffic selects T C P and "
    "the common web ports eighty and four forty-three. D N S Traffic selects U "
    "D P and port fifty-three. Choosing a preset fills the related fields, but "
    "it does not start SuperDuper. If you manually change Direction, Protocol, "
    "I P, Ports, or Process, the preset becomes Custom. Always review every "
    "filled value before pressing Start. Double click the Preset label whenever "
    "you want to hear this explanation."
)
IP_CIDR_GUIDANCE = (
    "I P or C I D R limits the experiment to one network address or a range of "
    "addresses. Enter one server I P address to match traffic going to or "
    "coming from that server. You can also enter a C I D R network, such as an "
    "address followed by a slash and prefix number, to match an entire address "
    "range. Leave the field empty to allow any I P address. SuperDuper does not "
    "automatically discover the Day Zee server address when you join it, so the "
    "user must enter the intended address when a narrow target is required. "
    "Use only an address or range belonging to your authorized private "
    "laboratory. An invalid address is rejected before settings can start. "
    "Double click the I P or C I D R label whenever you want to hear this "
    "explanation."
)
PORTS_GUIDANCE = (
    "Ports limit the experiment to particular network service numbers. Enter "
    "one port, such as twenty-three oh two, or several ports separated by "
    "commas. Enter a range with a hyphen, such as eight thousand hyphen "
    "eighty-one hundred. SuperDuper matches the number as either the source or "
    "destination port. Leave this field empty to allow any port. Ports work "
    "together with Direction, Protocol, and I P targeting. The app does not "
    "automatically copy a Day Zee server port into this field. Every port must be "
    "between one and sixty-five thousand five hundred thirty-five, and a range "
    "must go from the lower number to the higher number. Double click the Ports "
    "label whenever you want to hear this explanation."
)
PROCESS_GUIDANCE = (
    "Process is intended to narrow matching traffic to a selected running "
    "program. The Refresh button reads the current Windows process list and "
    "shows program names with their process identifiers. Any Process means no "
    "program-specific restriction. In this release, live process-to-network "
    "tracking is not implemented, so selecting a specific process prevents "
    "SuperDuper from starting and shows an explanatory message. Keep Any "
    "Process selected for working experiments. The selector is present for a "
    "future implementation and does not automatically identify which process "
    "owns a server connection. Double click the Process label whenever you "
    "want to hear this explanation."
)
ADVANCED_EFFECTS_GUIDANCE = (
    "Please hover over the Duplication, Out of Order Chance, Reorder Hold "
    "Maximum, Bandwidth Limit, Payload Corruption, or Bit Flips per Selected "
    "Packet label, and double click the label to hear what it does and how to "
    "use it. Click any control one time to use it normally."
)
DUPLICATION_GUIDANCE = (
    "Duplication is the percentage chance that SuperDuper sends an extra copy "
    "of a matching packet. Zero percent sends no extra copies. Ten percent "
    "means that about ten out of every one hundred matching packets receive one "
    "additional copy over time, although a short test can vary. Duplicate "
    "packets may cause repeated-looking updates, but the receiving program or "
    "server may ignore them. Begin with one or two percent and increase slowly. "
    "Use the slider, arrow keys, or large value box to set an exact percentage."
)
REORDER_GUIDANCE = (
    "Out of Order Chance is the percentage chance that a matching packet is "
    "held long enough for a later packet to pass it. Zero percent keeps the "
    "normal order. A higher percentage creates more opportunities for updates "
    "to arrive out of sequence. This can produce corrections, uneven movement, "
    "or ignored updates depending on the protocol. It works together with "
    "Reorder Hold Maximum. Begin with a low percentage and a short hold, then "
    "change one value at a time."
)
REORDER_HOLD_GUIDANCE = (
    "Reorder Hold Maximum sets the longest extra hold used for a packet chosen "
    "by Out of Order Chance. It is measured in milliseconds. The actual hold "
    "is randomly selected between zero and this maximum. A larger maximum gives "
    "later packets more time to pass the held packet. This setting does nothing "
    "when Out of Order Chance is zero. Start with a small value, use the slider "
    "or exact value box, and increase it carefully."
)
BANDWIDTH_GUIDANCE = (
    "Bandwidth Limit controls the maximum combined speed of matching traffic "
    "in kilobits per second. Unlimited, or zero, applies no bandwidth shaping. "
    "A lower positive number makes matching packets wait so their average rate "
    "stays near the selected limit. This can slow loading and delay large "
    "updates. Type the desired value or use the arrow controls. Begin with a "
    "generous limit and reduce it gradually. This is kilobits, not kilobytes."
)
CORRUPTION_GUIDANCE = (
    "Payload Corruption is the percentage chance that SuperDuper changes data "
    "bits inside the payload of a matching T C P or U D P packet. Network "
    "headers are protected and checksums are recalculated, but the application "
    "may reject or misread the altered data. SuperDuper requires a narrow I P "
    "or port target and asks for confirmation before starting. Use only "
    "disposable private-lab traffic, begin at one percent, and never use this "
    "during valuable transfers or updates."
)
BIT_FLIPS_GUIDANCE = (
    "Bit Flips per Selected Packet chooses how many different payload bits are "
    "changed whenever Payload Corruption selects a packet. One bit flip is the "
    "gentlest setting. More flips make each selected packet more heavily "
    "damaged and more likely to be rejected. This control has no effect when "
    "Payload Corruption is zero. Keep it at one while beginning an experiment "
    "and increase it only when you understand the result."
)
SAFETY_GUIDANCE = (
    "Please hover over the Maximum Delay Queue or Maximum Session label and "
    "double click the label to hear detailed instructions about its purpose and "
    "use. Click either control one time to adjust it normally."
)
MAX_QUEUE_GUIDANCE = (
    "Maximum Delay Queue limits how many matching packets SuperDuper may hold "
    "in memory while delay, reordering, or bandwidth shaping is active. If the "
    "queue reaches this limit, SuperDuper triggers a safety stop and releases "
    "the held traffic instead of allowing the queue to grow without control. "
    "The default is ten thousand packets. A very small limit may stop a busy "
    "test early; a very large limit can use more memory. Keep the default until "
    "a controlled experiment shows a reason to change it."
)
MAX_SESSION_GUIDANCE = (
    "Maximum Session limits how long SuperDuper may remain active. It is "
    "measured in minutes. No Time Limit means the safety timer is disabled. "
    "When a positive limit expires, SuperDuper stops interception and releases "
    "queued packets. Use a short limit for unattended or first-time tests so an "
    "experiment cannot continue longer than intended. This timer does not shut "
    "down Day Zee or the computer."
)
PROFILES_GUIDANCE = (
    "Hover over the Saved Profile label and double click it if you want to "
    "learn about its purpose, function, and use. Click the profile controls one "
    "time to use them normally."
)
SAVED_PROFILE_GUIDANCE = (
    "Saved Profile stores a named copy of the current Conditions, Targeting, "
    "Advanced Effects, and Safety values. Choose Save Profile, enter a clear "
    "name, and the settings are added to the list. Select a name and choose "
    "Load to place those values back into the controls. Loading does not start "
    "the packet engine. Select a profile and choose Delete to remove it after "
    "confirmation. Day Zee screen coordinates are not part of a profile. Always "
    "review loaded targeting and safety values before pressing Start."
)
DUPE_GUIDANCE = (
    "Select Info to hear the complete setup and calibration instructions. "
    "Numpad minus records the current mouse position as the next step. "
    "Select Clear to delete the entire saved calibration sequence."
)
DUPE_INSTRUCTIONS = (
    "Make sure that you adjust the following settings in SuperDuper before "
    "going into the game to execute the duplication experiment. "
    "Ideal settings for duplication. Direction: Both. Protocol: U D P. "
    "I P slash C I D R: your private server I P. Ports: your private server's "
    "game port. Latency: 250 milliseconds. Jitter: 50 milliseconds. "
    "Packet loss: 1 percent. Duplication: 0 percent. Out-of-order chance: "
    "5 percent. Reorder hold: 250 milliseconds. Bandwidth: Unlimited. "
    "Payload corruption: 0 percent. Maximum queue: 10,000. Maximum session: "
    "5 minutes. Then change only one variable per run. Increase latency from "
    "250, to 500, to 750 milliseconds. Increase jitter from 50, to 100, to "
    "200 milliseconds. Increase loss carefully from 1 percent, to 2 percent, "
    "to 5 percent. Test reordering separately from 5 percent to 10 percent, "
    "with a 250 to 500 millisecond hold. After making the adjustments, select "
    "Apply Settings at the bottom of the app to save them. "
    "When you go into the game, set up calibration in these specific steps. "
    "The asterisk button on the numpad activates and starts the app. "
    "First, enter the game and press Numpad asterisk. Second, press Escape on "
    "your keyboard to open the Exit option. Third, hover the mouse directly "
    "over Exit and press Numpad minus. The app immediately records and saves "
    "that position as the first step. Fourth, hover over Cancel and press "
    "Numpad minus again to record the second step. Fifth, repeat the Exit and "
    "Cancel recordings two more times, for three Exit and Cancel maneuvers in "
    "total. Press Escape before displaying Exit again whenever necessary. "
    "Sixth, record the fourth and final Exit by hovering over Exit and pressing "
    "Numpad minus. Do not record Cancel after this final Exit. Seventh, enter "
    "the Day Zee lobby, hover over Rejoin, and press Numpad minus one last time. "
    "Calibration is now complete. To execute the saved experiment later, enter "
    "the server, activate SuperDuper with Numpad asterisk, and press Numpad "
    "plus. Numpad plus always initiates the saved experimental sequence."
)
DUPE_INSTRUCTIONS_DISPLAY = """IDEAL SETTINGS FOR DUPING

Direction: Both
Protocol: UDP
IP/CIDR: private server IP
Ports: private server's game port
Latency: 250 ms
Jitter: 50 ms
Packet Loss: 1%
Duplication: 0%
Out-of-Order Chance: 5%
Reorder Hold: 250 ms
Bandwidth: Unlimited
Payload Corruption: 0%
Maximum Queue: 10,000
Maximum Session: 5 minutes

Change only one variable per run:
• Latency: 250 → 500 → 750 ms
• Jitter: 50 → 100 → 200 ms
• Packet loss: 1% → 2% → 5%
• Reordering: 5% → 10%, with a 250–500 ms hold

After adjusting the settings, select APPLY SETTINGS.

CALIBRATION

1. Enter DayZ and press Numpad * to activate SuperDuper.
2. Press Escape to display EXIT.
3. Hover over EXIT and press Numpad -.
4. Hover over CANCEL and press Numpad -.
5. Repeat EXIT and CANCEL two more times, for three pairs in total.
6. Hover over EXIT and press Numpad - for the final logout. Do not record CANCEL.
7. In the lobby, hover over REJOIN and press Numpad -.

The completed calibration contains eight ordered positions:
EXIT, CANCEL, EXIT, CANCEL, EXIT, CANCEL, EXIT, REJOIN.

Press Numpad + during an active DayZ session to run the saved sequence.
"""


class EngineBridge(QObject):
    """Safely transfer worker-thread backend events to the Qt UI thread."""

    stats_changed = pyqtSignal(object)
    engine_error = pyqtSignal(str)
    hotkey_triggered = pyqtSignal()
    emergency_stop_triggered = pyqtSignal()
    dayz_sequence_triggered = pyqtSignal()
    dayz_capture_triggered = pyqtSignal()
    voice_hotkey_triggered = pyqtSignal()
    hotkey_registration = pyqtSignal(bool, str)
    voice_ready = pyqtSignal(str)
    voice_error = pyqtSignal(str)


class GlobalHotkeyThread(threading.Thread):
    """Own a Windows message queue for the global Numpad Multiply hotkey."""

    def __init__(
        self,
        on_toggle: Callable[[], None],
        on_emergency_stop: Callable[[], None],
        on_dayz_sequence: Callable[[], None],
        on_dayz_capture: Callable[[], None],
        on_voice_toggle: Callable[[], None],
        on_registration: Callable[[bool, str], None],
    ) -> None:
        super().__init__(name="SuperDuper-Hotkey", daemon=True)
        self._on_toggle = on_toggle
        self._on_emergency_stop = on_emergency_stop
        self._on_dayz_sequence = on_dayz_sequence
        self._on_dayz_capture = on_dayz_capture
        self._on_voice_toggle = on_voice_toggle
        self._on_registration = on_registration
        self._ready = threading.Event()
        self._thread_id = 0
        self.registered = False
        self.emergency_registered = False
        self.dayz_registered = False
        self.dayz_capture_registered = False
        self.voice_numpad_registered = False
        self.voice_insert_registered = False

    def run(self) -> None:
        """Register the hotkey and dispatch its thread-level Windows messages."""

        if os.name != "nt":
            self._ready.set()
            self._on_registration(False, "Global Numpad * hotkey requires Windows")
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        user32.GetMessageW.restype = ctypes.c_int

        self._thread_id = int(kernel32.GetCurrentThreadId())
        self.registered = bool(
            user32.RegisterHotKey(
                None,
                HOTKEY_ID_TOGGLE,
                MOD_NOREPEAT,
                VK_MULTIPLY,
            )
        )
        self.emergency_registered = bool(
            user32.RegisterHotKey(
                None,
                HOTKEY_ID_EMERGENCY,
                MOD_CONTROL | MOD_NOREPEAT,
                VK_MULTIPLY,
            )
        )
        self.dayz_registered = bool(
            user32.RegisterHotKey(
                None,
                HOTKEY_ID_DAYZ,
                MOD_NOREPEAT,
                VK_ADD,
            )
        )
        self.dayz_capture_registered = bool(
            user32.RegisterHotKey(
                None,
                HOTKEY_ID_DAYZ_CAPTURE,
                MOD_NOREPEAT,
                VK_SUBTRACT,
            )
        )
        self.voice_numpad_registered = bool(
            user32.RegisterHotKey(
                None,
                HOTKEY_ID_VOICE_NUMPAD0,
                MOD_NOREPEAT,
                VK_NUMPAD0,
            )
        )
        self.voice_insert_registered = bool(
            user32.RegisterHotKey(
                None,
                HOTKEY_ID_VOICE_INSERT,
                MOD_NOREPEAT,
                VK_INSERT,
            )
        )
        self._ready.set()
        if not any(
            (
                self.registered,
                self.emergency_registered,
                self.dayz_registered,
                self.dayz_capture_registered,
                self.voice_numpad_registered,
                self.voice_insert_registered,
            )
        ):
            error = ctypes.get_last_error()
            self._on_registration(
                False,
                f"Numpad hotkeys unavailable (Windows error {error})",
            )
            return

        enabled_hotkeys = []
        if self.registered:
            enabled_hotkeys.append("Numpad * toggle")
        if self.emergency_registered:
            enabled_hotkeys.append("Ctrl + Numpad * emergency stop")
        if self.dayz_registered:
            enabled_hotkeys.append("Numpad + Dupe sequence")
        if self.dayz_capture_registered:
            enabled_hotkeys.append("Numpad - calibration capture")
        if self.voice_numpad_registered or self.voice_insert_registered:
            enabled_hotkeys.append("Numpad 0/INS voice mute")
        hotkey_status = ", ".join(enabled_hotkeys) + " enabled"
        self._on_registration(
            any(
                (
                    self.registered,
                    self.emergency_registered,
                    self.dayz_registered,
                    self.dayz_capture_registered,
                    self.voice_numpad_registered,
                    self.voice_insert_registered,
                )
            ),
            hotkey_status,
        )
        message = wintypes.MSG()
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID_TOGGLE:
                    self._on_toggle()
                elif message.message == WM_HOTKEY and message.wParam == HOTKEY_ID_EMERGENCY:
                    self._on_emergency_stop()
                elif message.message == WM_HOTKEY and message.wParam == HOTKEY_ID_DAYZ:
                    self._on_dayz_sequence()
                elif message.message == WM_HOTKEY and message.wParam == HOTKEY_ID_DAYZ_CAPTURE:
                    self._on_dayz_capture()
                elif message.message == WM_HOTKEY and message.wParam in (
                    HOTKEY_ID_VOICE_NUMPAD0,
                    HOTKEY_ID_VOICE_INSERT,
                ):
                    self._on_voice_toggle()
        finally:
            if self.registered:
                user32.UnregisterHotKey(None, HOTKEY_ID_TOGGLE)
            if self.emergency_registered:
                user32.UnregisterHotKey(None, HOTKEY_ID_EMERGENCY)
            if self.dayz_registered:
                user32.UnregisterHotKey(None, HOTKEY_ID_DAYZ)
            if self.dayz_capture_registered:
                user32.UnregisterHotKey(None, HOTKEY_ID_DAYZ_CAPTURE)
            if self.voice_numpad_registered:
                user32.UnregisterHotKey(None, HOTKEY_ID_VOICE_NUMPAD0)
            if self.voice_insert_registered:
                user32.UnregisterHotKey(None, HOTKEY_ID_VOICE_INSERT)
            self.registered = False
            self.emergency_registered = False
            self.dayz_registered = False
            self.dayz_capture_registered = False
            self.voice_numpad_registered = False
            self.voice_insert_registered = False

    def wait_until_ready(self, timeout: float = 2.0) -> bool:
        """Wait until Windows accepts or rejects the registration request."""

        return self._ready.wait(timeout)

    def stop(self) -> None:
        """Post WM_QUIT to the owning thread and wait for clean teardown."""

        if self._thread_id and self.is_alive() and os.name == "nt":
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostThreadMessageW.argtypes = [
                wintypes.DWORD,
                ctypes.c_uint,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.PostThreadMessageW.restype = wintypes.BOOL
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            if threading.current_thread() is not self:
                self.join()


class TitaniumButton(QPushButton):
    """Pill-shaped button painted with a titanium-white metallic finish."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setFont(QFont("Segoe UI Semibold", 9))

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bounds = self.rect().adjusted(1, 1, -1, -1)
        radius = bounds.height() / 2
        gradient = QLinearGradient(0, bounds.top(), 0, bounds.bottom())

        if not self.isEnabled():
            gradient.setColorAt(0.0, QColor("#CBCDD0"))
            gradient.setColorAt(1.0, QColor("#8E9297"))
            text_color = QColor("#5A5D61")
        elif self.isDown():
            gradient.setColorAt(0.0, QColor("#AEB2B7"))
            gradient.setColorAt(0.5, QColor("#F2F3F4"))
            gradient.setColorAt(1.0, QColor("#FFFFFF"))
            text_color = QColor("#4B0A18")
        else:
            gradient.setColorAt(0.0, QColor("#FFFFFF"))
            gradient.setColorAt(0.42, QColor("#E9EBED"))
            gradient.setColorAt(1.0, QColor("#A9ADB2"))
            text_color = QColor("#4B0A18")

        painter.setPen(QColor("#FFFFFF"))
        painter.setBrush(gradient)
        painter.drawRoundedRect(bounds, radius, radius)

        if self.hasFocus():
            focus_bounds = bounds.adjusted(3, 3, -3, -3)
            painter.setPen(QColor("#7A0D27"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                focus_bounds,
                focus_bounds.height() / 2,
                focus_bounds.height() / 2,
            )

        painter.setPen(text_color)
        painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, self.text())


class InfoCenterDialog(QDialog):
    """Editable, recursive information tree with one protected root folder."""

    INTERNAL_FOLDERS = {"build", "dist", "__pycache__"}

    def __init__(
        self,
        package_directory: Path,
        *,
        read_text_aloud: Callable[[str, str], bool],
        stop_narration: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.package_directory = package_directory.resolve()
        self._read_text_aloud = read_text_aloud
        self._stop_narration = stop_narration
        self._reading_document = False
        self._arrow_glow_on = False
        self.protected_directory = (self.package_directory / "INFO-CENTER").resolve()
        self.protected_directory.mkdir(parents=True, exist_ok=True)
        self.setWindowTitle("SuperDuper INFO-CENTER")
        self.setModal(True)
        self.setMinimumSize(620, 500)
        self.resize(700, 560)

        self.back_button = QPushButton("←")
        self.back_button.setObjectName("infoCenterBack")
        self.back_button.setFixedSize(54, 42)
        self.back_button.setToolTip("Return to folders and stop APP Voice")
        self.back_button.clicked.connect(self._return_to_folders)
        self.back_glow = QGraphicsDropShadowEffect(self.back_button)
        self.back_glow.setOffset(0, 0)
        self.back_button.setGraphicsEffect(self.back_glow)
        self.back_button.hide()
        heading = QLabel("INFO-CENTER")
        heading.setObjectName("infoCenterHeading")
        header = QHBoxLayout()
        header.setContentsMargins(0, 5, 0, 0)
        header.addWidget(self.back_button)
        header.addWidget(heading, 1)
        description = QLabel(
            "Expand folders with their arrows. Select a folder before pasting "
            "new folders or text documents into it."
        )
        description.setWordWrap(True)

        self.model = QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setNameFilters(["*.txt"])
        self.model.setNameFilterDisables(False)
        self.model.directoryLoaded.connect(self._hide_internal_folders)

        self.tree = QTreeView()
        self.tree.setObjectName("infoCenterTree")
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.setRootPath(str(self.package_directory)))
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(22)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.doubleClicked.connect(self._open_selected_item)
        for column in range(1, 4):
            self.tree.hideColumn(column)

        self.document_title = QLabel()
        self.document_title.setObjectName("infoCenterDocumentTitle")
        self.document_text = QTextEdit()
        self.document_text.setObjectName("infoCenterDocumentText")
        self.document_text.setReadOnly(True)
        document_page = QWidget()
        document_layout = QVBoxLayout(document_page)
        document_layout.setContentsMargins(0, 0, 0, 0)
        document_layout.addWidget(self.document_title)
        document_layout.addWidget(self.document_text, 1)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.tree)
        self.content_stack.addWidget(document_page)

        self.arrow_timer = QTimer(self)
        self.arrow_timer.setInterval(520)
        self.arrow_timer.timeout.connect(self._pulse_back_arrow)

        close_button = TitaniumButton("CLOSE")
        close_button.clicked.connect(self._close_dialog)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 20, 18, 16)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(description)
        layout.addWidget(self.content_stack, 1)
        layout.addWidget(close_button)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #780B25;
                color: #FFFFFF;
            }
            QLabel {
                color: #F5DDE3;
            }
            QLabel#infoCenterHeading {
                color: #FFFFFF;
                font-family: "Segoe UI Black";
                font-size: 16pt;
                letter-spacing: 2px;
            }
            QLabel#infoCenterDocumentTitle {
                color: #FFFFFF;
                font-family: "Segoe UI Semibold";
                font-size: 12pt;
                padding: 3px 2px;
            }
            QTextEdit#infoCenterDocumentText {
                background-color: #420615;
                border: 1px solid #A93650;
                border-radius: 10px;
                color: #FFFFFF;
                font-family: "Segoe UI";
                font-size: 11pt;
                padding: 10px;
            }
            QPushButton#infoCenterBack {
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-size: 30pt;
                font-weight: 900;
            }
            QTreeView#infoCenterTree {
                background-color: #420615;
                alternate-background-color: #500819;
                border: 1px solid #A93650;
                border-radius: 10px;
                color: #FFFFFF;
                font-size: 10pt;
                padding: 6px;
                selection-background-color: #9B2340;
            }
            QTreeView#infoCenterTree::item {
                min-height: 25px;
            }
            QMenu {
                background-color: #5B091D;
                border: 1px solid #A93650;
                color: #FFFFFF;
            }
            QMenu::item:selected {
                background-color: #9B2340;
            }
            """
        )
        QTimer.singleShot(0, lambda: self._hide_internal_folders(str(self.package_directory)))

    def _selected_path(self) -> Path | None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return None
        return Path(self.model.filePath(index)).resolve()

    def _selected_directory(self) -> Path:
        selected = self._selected_path()
        if selected is None:
            return self.package_directory
        return selected if selected.is_dir() else selected.parent

    def _is_within_package(self, path: Path) -> bool:
        resolved = path.resolve()
        return resolved == self.package_directory or self.package_directory in resolved.parents

    def _is_protected(self, path: Path) -> bool:
        return path.resolve() == self.protected_directory

    @classmethod
    def _hide_at_package_root(cls, name: str, is_directory: bool) -> bool:
        normalized = name.casefold()
        if is_directory:
            return normalized in cls.INTERNAL_FOLDERS or normalized.startswith("backup-")
        return Path(name).suffix.casefold() == ".txt"

    def _hide_internal_folders(self, loaded_path: str) -> None:
        if Path(loaded_path).resolve() != self.package_directory:
            return
        root_index = self.model.index(str(self.package_directory))
        for row in range(self.model.rowCount(root_index)):
            index = self.model.index(row, 0, root_index)
            name = self.model.fileName(index)
            hidden = self._hide_at_package_root(
                name,
                self.model.isDir(index),
            )
            self.tree.setRowHidden(row, root_index, hidden)

    def _show_context_menu(self, position) -> None:
        index = self.tree.indexAt(position)
        if index.isValid():
            self.tree.setCurrentIndex(index)
        selected = self._selected_path()
        menu = QMenu(self)
        new_folder_action = menu.addAction("New Folder")
        paste_action = menu.addAction("Paste")
        refresh_action = menu.addAction("Refresh")
        open_action = menu.addAction("Open in File Explorer")
        rename_action = None
        delete_action = None
        delete_is_folder = False
        if (
            selected is not None
            and selected != self.package_directory
            and not self._is_protected(selected)
        ):
            rename_action = menu.addAction("Rename")
            if selected.is_dir():
                delete_action = menu.addAction("Delete Folder")
                delete_is_folder = True
            elif selected.is_file() and selected.suffix.casefold() == ".txt":
                delete_action = menu.addAction("Delete Text File")
        chosen = menu.exec(self.tree.viewport().mapToGlobal(position))
        if chosen == new_folder_action:
            self._create_folder()
        elif chosen == paste_action:
            self._paste_clipboard()
        elif chosen == refresh_action:
            self._refresh()
        elif chosen == open_action:
            self._open_in_explorer()
        elif rename_action is not None and chosen == rename_action:
            self._rename_selected()
        elif delete_action is not None and chosen == delete_action:
            self._delete_selected_item(delete_is_folder)

    def _create_folder(self) -> None:
        parent = self._selected_directory()
        name, accepted = QInputDialog.getText(
            self,
            "New Folder",
            "Folder name:",
        )
        if not accepted:
            return
        clean_name = name.strip()
        if (
            not clean_name
            or clean_name in {".", ".."}
            or any(character in clean_name for character in '<>:"/\\|?*')
        ):
            QMessageBox.warning(self, "Invalid Name", "Enter a valid folder name.")
            return
        destination = parent / clean_name
        try:
            destination.mkdir()
        except OSError as exc:
            QMessageBox.warning(self, "Folder Not Created", str(exc))

    @staticmethod
    def _unique_destination(parent: Path, source_name: str) -> Path:
        destination = parent / source_name
        if not destination.exists():
            return destination
        stem = Path(source_name).stem
        suffix = Path(source_name).suffix
        number = 2
        while True:
            candidate = parent / f"{stem} - Copy {number}{suffix}"
            if not candidate.exists():
                return candidate
            number += 1

    def _paste_clipboard(self) -> None:
        destination_parent = self._selected_directory()
        urls = QApplication.clipboard().mimeData().urls()
        sources = [Path(url.toLocalFile()).resolve() for url in urls if url.isLocalFile()]
        if not sources:
            QMessageBox.information(
                self,
                "Nothing to Paste",
                "Copy a folder or .txt document in File Explorer first.",
            )
            return
        copied = 0
        skipped: list[str] = []
        for source in sources:
            if not source.exists():
                skipped.append(source.name)
                continue
            if source.is_file() and source.suffix.casefold() != ".txt":
                skipped.append(source.name)
                continue
            if source.is_dir() and (
                destination_parent == source or source in destination_parent.parents
            ):
                skipped.append(source.name)
                continue
            destination = self._unique_destination(destination_parent, source.name)
            try:
                if source.is_dir():
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
                copied += 1
            except OSError:
                skipped.append(source.name)
        self._refresh()
        message = f"{copied} item(s) pasted."
        if skipped:
            message += "\nSkipped: " + ", ".join(skipped)
        QMessageBox.information(self, "Paste Complete", message)

    def _rename_selected(self) -> None:
        selected = self._selected_path()
        if (
            selected is None
            or self._is_protected(selected)
            or not self._is_within_package(selected)
        ):
            return
        name, accepted = QInputDialog.getText(
            self,
            "Rename",
            "New name:",
            text=selected.name,
        )
        if not accepted or not name.strip() or name.strip() == selected.name:
            return
        destination = selected.with_name(name.strip())
        if destination.exists():
            QMessageBox.warning(self, "Rename Failed", "That name already exists.")
            return
        try:
            selected.rename(destination)
        except OSError as exc:
            QMessageBox.warning(self, "Rename Failed", str(exc))

    def _delete_selected_item(self, is_folder: bool) -> None:
        selected = self._selected_path()
        if selected is None or (is_folder and not selected.is_dir()):
            return
        if not is_folder and (not selected.is_file() or selected.suffix.casefold() != ".txt"):
            return
        if self._is_protected(selected):
            QMessageBox.warning(
                self,
                "Protected Folder",
                "The INFO-CENTER folder cannot be deleted.",
            )
            return
        if selected == self.package_directory or not self._is_within_package(selected):
            return
        prompt = (
            "Move this folder and all of its contents to the Recycle Bin?"
            if is_folder
            else "Move this text file to the Recycle Bin?"
        )
        answer = QMessageBox.question(
            self,
            "Delete Folder" if is_folder else "Delete Text File",
            f"{prompt}\n\n{selected.name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self._move_to_recycle_bin(selected):
            QMessageBox.warning(
                self,
                "Delete Failed",
                "Windows could not move the selected item to the Recycle Bin.",
            )

    @staticmethod
    def _move_to_recycle_bin(path: Path) -> bool:
        if os.name != "nt":
            return False

        class SHFileOperation(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", ctypes.c_uint),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFileOperation)]
        shell32.SHFileOperationW.restype = ctypes.c_int
        operation = SHFileOperation()
        operation.wFunc = 0x0003
        operation.pFrom = f"{path}\0\0"
        operation.fFlags = 0x0040 | 0x0010 | 0x0400
        result = shell32.SHFileOperationW(ctypes.byref(operation))
        return result == 0 and not operation.fAnyOperationsAborted

    def _open_selected_item(self, index) -> None:
        path = Path(self.model.filePath(index)).resolve()
        if path.is_file() and path.suffix.casefold() == ".txt":
            self._read_text_file_aloud(path)

    def _read_text_file_aloud(self, path: Path) -> None:
        if not self._is_within_package(path):
            return
        try:
            with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
                text = stream.read()
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Text File Could Not Be Read",
                str(exc),
            )
            return
        narration = text[:MAX_SPEECH_CHARACTERS].strip()
        if not narration:
            QMessageBox.information(
                self,
                "Empty Text File",
                f"{path.name} does not contain any text to read.",
            )
            return
        self.document_title.setText(path.name)
        self.document_text.setPlainText(text)
        self.content_stack.setCurrentIndex(1)
        self.back_button.show()
        self._reading_document = True
        self._arrow_glow_on = False
        self._pulse_back_arrow()
        self.arrow_timer.start()
        if not self._read_text_aloud(path.name, narration):
            QMessageBox.information(
                self,
                "APP Voice Is Muted",
                "Enable APP Voice with the lips or Numpad 0 / INS, then "
                "double click the text file again.",
            )

    def _pulse_back_arrow(self) -> None:
        self._arrow_glow_on = not self._arrow_glow_on
        glow = "#FFFFFF" if self._arrow_glow_on else "#FF8EAA"
        self.back_glow.setColor(QColor(glow))
        self.back_glow.setBlurRadius(24 if self._arrow_glow_on else 9)
        self.back_button.setStyleSheet(
            "QPushButton#infoCenterBack {"
            "background: transparent; border: none;"
            f"color: {glow}; font-size: 30pt; font-weight: 900;"
            "}"
        )

    def _return_to_folders(self) -> None:
        if self._reading_document:
            self._stop_narration()
        self._reading_document = False
        self.arrow_timer.stop()
        self.back_button.hide()
        self.content_stack.setCurrentIndex(0)
        self.document_title.clear()
        self.document_text.clear()

    def _close_dialog(self) -> None:
        if self._reading_document:
            self._stop_narration()
            self._reading_document = False
        self.accept()

    def reject(self) -> None:
        if self._reading_document:
            self._stop_narration()
            self._reading_document = False
        super().reject()

    def _open_in_explorer(self) -> None:
        directory = self._selected_directory()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _refresh(self) -> None:
        self.protected_directory.mkdir(parents=True, exist_ok=True)
        root_path = str(self.package_directory)
        self.model.setRootPath("")
        self.tree.setRootIndex(self.model.setRootPath(root_path))
        QTimer.singleShot(0, lambda: self._hide_internal_folders(root_path))


class NarratedLabel(QLabel):
    """Control label that requests spoken help after a double-click."""

    guidance_requested = pyqtSignal()

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        """Request narration without interfering with the control below."""

        self.guidance_requested.emit()
        event.accept()


class ValueSlider(QWidget):
    """Slider with a large editable value field for precise one-unit control."""

    def __init__(
        self,
        title: str,
        suffix: str,
        minimum: int,
        maximum: int,
        narrated: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.suffix = suffix
        self.title_label = NarratedLabel(title) if narrated else QLabel(title)
        self.value_label = QSpinBox()
        self.value_label.setObjectName("precisionValue")
        self.value_label.setRange(minimum, maximum)
        self.value_label.setSuffix(suffix)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.value_label.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.value_label.setKeyboardTracking(False)
        self.value_label.setAccelerated(False)
        self.value_label.setMinimumWidth(180)
        self.value_label.setFixedHeight(48)
        self.value_label.setToolTip(
            "Type an exact value here, or use the arrow keys for one-unit changes."
        )

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setTracking(True)
        self.slider.setToolTip(
            "Drag for broad adjustment. Use the large value field for an exact value."
        )
        self.slider.valueChanged.connect(self._show_value)
        self.value_label.valueChanged.connect(self.slider.setValue)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.addWidget(self.title_label)
        heading.addStretch()
        heading.addWidget(self.value_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(heading)
        layout.addWidget(self.slider)
        self._show_value(minimum)

    def _show_value(self, value: int) -> None:
        if self.value_label.value() != value:
            self.value_label.blockSignals(True)
            self.value_label.setValue(value)
            self.value_label.blockSignals(False)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, value: int) -> None:
        self.slider.setValue(value)


class SuperDuperWindow(QMainWindow):
    """Main application window and persistent configuration controller."""

    SETTINGS_ORGANIZATION = "SuperDuper"
    SETTINGS_APPLICATION = "SuperDuper"

    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(
            self.SETTINGS_ORGANIZATION,
            self.SETTINGS_APPLICATION,
        )
        self._applying_preset = False
        self.package_location: PackageLocation = resolve_package_directory()
        self.bridge = EngineBridge()
        self.engine = PacketEngine(
            self.package_location.path / "WinDivert.dll",
            on_stats=self.bridge.stats_changed.emit,
            on_error=self.bridge.engine_error.emit,
        )
        self.bridge.stats_changed.connect(self.show_engine_stats)
        self.bridge.engine_error.connect(self.show_engine_error)
        self.bridge.hotkey_triggered.connect(self.toggle_engine_from_hotkey)
        self.bridge.emergency_stop_triggered.connect(self.emergency_stop)
        self.bridge.dayz_sequence_triggered.connect(self.start_dayz_sequence)
        self.bridge.dayz_capture_triggered.connect(self.capture_dayz_calibration_point)
        self.bridge.voice_hotkey_triggered.connect(self.toggle_voice_hotkey)
        self.bridge.hotkey_registration.connect(self.show_hotkey_registration)
        self.bridge.voice_ready.connect(self.show_voice_ready)
        self.bridge.voice_error.connect(self.show_voice_error)
        self.voice = VoiceController(
            VoiceConfig(volume=85, rate=-1, preferred_gender="Female"),
            on_ready=self.bridge.voice_ready.emit,
            on_error=self.bridge.voice_error.emit,
        )
        self.hotkey_thread = GlobalHotkeyThread(
            self.bridge.hotkey_triggered.emit,
            self.bridge.emergency_stop_triggered.emit,
            self.bridge.dayz_sequence_triggered.emit,
            self.bridge.dayz_capture_triggered.emit,
            self.bridge.voice_hotkey_triggered.emit,
            self.bridge.hotkey_registration.emit,
        )
        self._dayz_sequence_active = False
        self._dayz_sequence_generation = 0
        self._dayz_cycle = 0
        self._dayz_cancel_cycles = DAYZ_CANCEL_CYCLES
        self._dayz_playback_points: list[tuple[int, int]] = []
        self._dayz_calibration_target = ""
        self.setWindowTitle("SuperDuper")
        self.setObjectName("mainWindow")
        self._build_interface()
        self.voice.set_muted(False)
        self._apply_styles()
        self._load_settings()
        self.refresh_processes(announce=False)
        self.update_filter_preview()
        self.status.setText(f"Ready — {self.package_location.source}")

    def _build_interface(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        title = QLabel("SUPERDUPER")
        title.setObjectName("title")
        subtitle = QLabel("NETWORK CONDITION STUDIO")
        subtitle.setObjectName("subtitle")

        title_row = QVBoxLayout()
        title_row.setSpacing(0)
        title_row.addWidget(title)
        title_row.addWidget(subtitle)

        self.info_center_button = TitaniumButton("INFO-CENTER")
        self.info_center_button.setFixedSize(180, 34)
        self.info_center_button.setToolTip("Open the editable information center")
        self.info_center_button.clicked.connect(self.show_info_center)

        self.mute_button = QPushButton()
        self.mute_button.setObjectName("muteButton")
        self.mute_button.setCheckable(True)
        self.mute_button.setChecked(False)
        self.mute_button.setFixedSize(72, 62)
        self.mute_button.setIcon(QIcon(str(self.package_location.path / "lips.png")))
        self.mute_button.setIconSize(QSize(60, 40))
        self.mute_button.setToolTip("Voice enabled — click to mute spoken guidance")
        self.mute_button.setAccessibleName("Mute or unmute spoken guidance")
        self.mute_button.clicked.connect(self.toggle_voice_muted)

        header_row = QGridLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addLayout(
            title_row,
            0,
            0,
            1,
            3,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        header_row.addWidget(
            self.info_center_button,
            0,
            0,
            1,
            3,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        )
        header_row.addWidget(
            self.mute_button,
            0,
            0,
            1,
            3,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Both", "Outbound", "Inbound"])
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["All traffic", "TCP", "UDP", "IPv4", "IPv6"])
        self.direction_label = NarratedLabel("DIRECTION")
        self.protocol_label = NarratedLabel("PROTOCOL")
        self.direction_label.setObjectName("conditionsLabel")
        self.protocol_label.setObjectName("conditionsLabel")
        self.direction_label.setToolTip("Double click this label for spoken DIRECTION help")
        self.protocol_label.setToolTip("Double click this label for spoken PROTOCOL help")
        self.direction_label.guidance_requested.connect(self.speak_direction_guidance)
        self.protocol_label.guidance_requested.connect(self.speak_protocol_guidance)

        selectors = QGridLayout()
        selectors.setHorizontalSpacing(12)
        selectors.setVerticalSpacing(4)
        selectors.addWidget(self.direction_label, 0, 0)
        selectors.addWidget(self.protocol_label, 0, 1)
        selectors.addWidget(self.direction_combo, 1, 0)
        selectors.addWidget(self.protocol_combo, 1, 1)

        self.latency = ValueSlider("LATENCY", " ms", 0, 15000, narrated=True)
        self.jitter = ValueSlider("JITTER", " ms", 0, 2000, narrated=True)
        self.packet_loss = ValueSlider(
            "PACKET LOSS",
            "%",
            0,
            100,
            narrated=True,
        )
        for condition_label in (
            self.latency.title_label,
            self.jitter.title_label,
            self.packet_loss.title_label,
        ):
            condition_label.setObjectName("conditionsLabel")
        self.latency.title_label.setToolTip("Double click this label for spoken LATENCY help")
        self.jitter.title_label.setToolTip("Double click this label for spoken JITTER help")
        self.packet_loss.title_label.setToolTip(
            "Double click this label for spoken PACKET LOSS help"
        )
        self.latency.title_label.guidance_requested.connect(self.speak_latency_guidance)
        self.jitter.title_label.guidance_requested.connect(self.speak_jitter_guidance)
        self.packet_loss.title_label.guidance_requested.connect(self.speak_packet_loss_guidance)

        conditions_tab = QWidget()
        conditions_layout = QVBoxLayout(conditions_tab)
        conditions_layout.setContentsMargins(12, 8, 12, 8)
        conditions_layout.setSpacing(5)
        conditions_layout.addLayout(selectors)
        conditions_layout.addWidget(self.latency)
        conditions_layout.addWidget(self.jitter)
        conditions_layout.addWidget(self.packet_loss)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(
            ["Custom", "All Traffic", "Localhost", "Web Traffic", "DNS Traffic"]
        )
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("Any IP, address, or CIDR")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("Any port; e.g. 443, 8000-8100")
        self.process_combo = QComboBox()
        self.process_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.process_combo.setMinimumContentsLength(18)
        self.refresh_button = TitaniumButton("REFRESH")
        self.refresh_button.setMinimumHeight(30)
        self.refresh_button.clicked.connect(self.refresh_processes)
        self.preset_label = NarratedLabel("PRESET")
        self.ip_cidr_label = NarratedLabel("IP / CIDR")
        self.ports_label = NarratedLabel("PORTS")
        self.process_label = NarratedLabel("PROCESS")
        for label, help_name in (
            (self.preset_label, "PRESET"),
            (self.ip_cidr_label, "IP / CIDR"),
            (self.ports_label, "PORTS"),
            (self.process_label, "PROCESS"),
        ):
            label.setObjectName("targetingLabel")
            label.setToolTip(f"Double click this label for spoken {help_name} help")
        self.preset_label.guidance_requested.connect(self.speak_preset_guidance)
        self.ip_cidr_label.guidance_requested.connect(self.speak_ip_cidr_guidance)
        self.ports_label.guidance_requested.connect(self.speak_ports_guidance)
        self.process_label.guidance_requested.connect(self.speak_process_guidance)

        target_grid = QGridLayout()
        target_grid.setHorizontalSpacing(10)
        target_grid.setVerticalSpacing(3)
        target_grid.addWidget(self.preset_label, 0, 0)
        target_grid.addWidget(self.ip_cidr_label, 0, 1)
        target_grid.addWidget(self.preset_combo, 1, 0)
        target_grid.addWidget(self.ip_edit, 1, 1)
        target_grid.addWidget(self.ports_label, 2, 0)
        target_grid.addWidget(self.process_label, 2, 1)
        target_grid.addWidget(self.port_edit, 3, 0)
        process_row = QHBoxLayout()
        process_row.setSpacing(6)
        process_row.addWidget(self.process_combo, 1)
        process_row.addWidget(self.refresh_button)
        target_grid.addLayout(process_row, 3, 1)

        self.filter_preview = QLabel()
        self.filter_preview.setObjectName("filterPreview")
        self.filter_preview.setWordWrap(True)
        target_layout = QVBoxLayout()
        target_layout.setContentsMargins(12, 8, 12, 8)
        target_layout.setSpacing(5)
        target_layout.addLayout(target_grid)
        target_layout.addWidget(self.filter_preview, 1)
        targeting_tab = QWidget()
        targeting_tab.setLayout(target_layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(conditions_tab, "CONDITIONS")
        self.tabs.addTab(targeting_tab, "TARGETING")

        self.duplication = ValueSlider("DUPLICATION", "%", 0, 100, narrated=True)
        self.reorder = ValueSlider("OUT-OF-ORDER CHANCE", "%", 0, 100, narrated=True)
        self.reorder_delay = ValueSlider("REORDER HOLD (MAXIMUM)", " ms", 0, 10000, narrated=True)
        self.bandwidth_spin = QSpinBox()
        self.bandwidth_spin.setRange(0, 1000000)
        self.bandwidth_spin.setSingleStep(100)
        self.bandwidth_spin.setSuffix(" Kbit/s")
        self.bandwidth_spin.setSpecialValueText("Unlimited")
        self.corruption = ValueSlider("PAYLOAD CORRUPTION", "%", 0, 25, narrated=True)
        self.corruption_bits = QSpinBox()
        self.corruption_bits.setRange(1, 8)
        self.corruption_bits.setSuffix(" bit flips")
        self.bandwidth_label = NarratedLabel("BANDWIDTH LIMIT")
        self.bit_flips_label = NarratedLabel("BIT FLIPS PER SELECTED PACKET")
        for effect_label in (
            self.duplication.title_label,
            self.reorder.title_label,
            self.reorder_delay.title_label,
            self.bandwidth_label,
            self.corruption.title_label,
            self.bit_flips_label,
        ):
            effect_label.setObjectName("sectionLabel")
        for label, method in (
            (self.duplication.title_label, self.speak_duplication_guidance),
            (self.reorder.title_label, self.speak_reorder_guidance),
            (self.reorder_delay.title_label, self.speak_reorder_hold_guidance),
            (self.bandwidth_label, self.speak_bandwidth_guidance),
            (self.corruption.title_label, self.speak_corruption_guidance),
            (self.bit_flips_label, self.speak_bit_flips_guidance),
        ):
            label.setToolTip("Double click this label for spoken help")
            label.guidance_requested.connect(method)
        effects_note = QLabel(
            "Selected packets receive a random hold up to the reorder maximum, "
            "allowing later packets to pass them. Bandwidth 0 means unlimited."
        )
        effects_note.setObjectName("filterPreview")
        effects_note.setWordWrap(True)
        effects_tab = QWidget()
        effects_layout = QVBoxLayout(effects_tab)
        effects_layout.setContentsMargins(12, 8, 12, 8)
        effects_layout.setSpacing(5)
        effects_layout.addWidget(self.duplication)
        effects_layout.addWidget(self.reorder)
        effects_layout.addWidget(self.reorder_delay)
        effects_layout.addWidget(self.bandwidth_label)
        effects_layout.addWidget(self.bandwidth_spin)
        effects_layout.addWidget(self.corruption)
        effects_layout.addWidget(self.bit_flips_label)
        effects_layout.addWidget(self.corruption_bits)
        effects_layout.addWidget(effects_note)
        self.tabs.addTab(effects_tab, "ADVANCED EFFECTS")

        self.max_queue_spin = QSpinBox()
        self.max_queue_spin.setRange(100, 100000)
        self.max_queue_spin.setSingleStep(100)
        self.max_queue_spin.setSuffix(" packets")
        self.max_session_spin = QSpinBox()
        self.max_session_spin.setRange(0, 1440)
        self.max_session_spin.setSuffix(" min")
        self.max_session_spin.setSpecialValueText("No time limit")
        self.max_queue_label = NarratedLabel("MAXIMUM DELAY QUEUE")
        self.max_session_label = NarratedLabel("MAXIMUM SESSION")
        self.max_queue_label.setObjectName("sectionLabel")
        self.max_session_label.setObjectName("sectionLabel")
        self.max_queue_label.guidance_requested.connect(self.speak_max_queue_guidance)
        self.max_session_label.guidance_requested.connect(self.speak_max_session_guidance)
        safety_form = QGridLayout()
        safety_form.setHorizontalSpacing(12)
        safety_form.setVerticalSpacing(6)
        safety_form.addWidget(self.max_queue_label, 0, 0)
        safety_form.addWidget(self.max_session_label, 0, 1)
        safety_form.addWidget(self.max_queue_spin, 1, 0)
        safety_form.addWidget(self.max_session_spin, 1, 1)
        hotkey_help = QLabel(
            "Numpad * toggles Start/Stop from anywhere in Windows.\n"
            "Ctrl + Numpad * is a Stop-only emergency hotkey."
        )
        hotkey_help.setObjectName("filterPreview")
        safety_tab = QWidget()
        safety_layout = QVBoxLayout(safety_tab)
        safety_layout.setContentsMargins(12, 10, 12, 10)
        safety_layout.addLayout(safety_form)
        safety_layout.addWidget(hotkey_help)
        safety_layout.addStretch()
        self.tabs.addTab(safety_tab, "SAFETY")

        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Select a saved profile...")
        self.save_profile_button = TitaniumButton("SAVE PROFILE")
        self.load_profile_button = TitaniumButton("LOAD")
        self.delete_profile_button = TitaniumButton("DELETE")
        self.save_profile_button.clicked.connect(self.save_profile_prompt)
        self.load_profile_button.clicked.connect(self.load_selected_profile)
        self.delete_profile_button.clicked.connect(self.delete_profile_prompt)
        profile_buttons = QHBoxLayout()
        profile_buttons.setSpacing(8)
        profile_buttons.addWidget(self.save_profile_button, 2)
        profile_buttons.addWidget(self.load_profile_button, 1)
        profile_buttons.addWidget(self.delete_profile_button, 1)
        profile_tab = QWidget()
        profile_layout = QVBoxLayout(profile_tab)
        profile_layout.setContentsMargins(12, 12, 12, 12)
        profile_layout.setSpacing(10)
        self.saved_profile_label = NarratedLabel("SAVED PROFILE")
        self.saved_profile_label.setObjectName("sectionLabel")
        self.saved_profile_label.guidance_requested.connect(self.speak_saved_profile_guidance)
        profile_layout.addWidget(self.saved_profile_label)
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addLayout(profile_buttons)
        profile_note = QLabel(
            "Profiles save conditions, targeting, and safety limits together.\n"
            "Loading a profile does not start interception."
        )
        profile_note.setObjectName("filterPreview")
        profile_layout.addWidget(profile_note)
        profile_layout.addStretch()
        self.tabs.addTab(profile_tab, "PROFILES")

        self.dayz_exit_label = QLabel("Exit: not calibrated")
        self.dayz_cancel_label = QLabel("Cancel/Continue: not calibrated")
        self.dayz_play_label = QLabel("Lobby Play: not calibrated")
        self.final_logout_label = QLabel("FINAL LOGOUT COMPLETION")
        for dayz_label in (
            self.dayz_exit_label,
            self.dayz_cancel_label,
            self.dayz_play_label,
            self.final_logout_label,
        ):
            dayz_label.setObjectName("sectionLabel")
        self.dayz_play_label.setWordWrap(True)
        self.dayz_clear_button = TitaniumButton("CLEAR")
        self.dayz_clear_button.setFixedSize(58, 58)
        self.dayz_clear_button.setFont(QFont("Segoe UI Semibold", 7))
        self.dayz_clear_button.setToolTip("Delete every saved DUPE calibration position")
        self.dayz_clear_button.clicked.connect(self.clear_dayz_calibration)
        self.dayz_info_button = TitaniumButton("INFO")
        self.dayz_info_button.setFixedSize(58, 58)
        self.dayz_info_button.setFont(QFont("Segoe UI Semibold", 7))
        self.dayz_info_button.setToolTip("Show and speak the DUPE instructions")
        self.dayz_info_button.clicked.connect(self.show_dupe_instructions)
        self.dayz_logout_wait_spin = QSpinBox()
        self.dayz_logout_wait_spin.setRange(1, 60)
        self.dayz_logout_wait_spin.setValue(15)
        self.dayz_logout_wait_spin.setSuffix(" sec")
        self.dayz_abort_button = TitaniumButton("ABORT SEQUENCE")
        self.dayz_abort_button.clicked.connect(lambda: self.abort_dayz_sequence())
        self.dayz_abort_button.setEnabled(False)
        dayz_grid = QGridLayout()
        dayz_grid.setHorizontalSpacing(8)
        dayz_grid.setVerticalSpacing(5)
        dayz_grid.addWidget(self.dayz_exit_label, 0, 0, 1, 2)
        dayz_grid.addWidget(self.dayz_cancel_label, 1, 0, 1, 2)
        dayz_grid.addWidget(self.dayz_play_label, 2, 0, 1, 2)
        dayz_grid.addWidget(self.final_logout_label, 3, 0)
        dayz_grid.addWidget(self.dayz_logout_wait_spin, 3, 1)
        self.dayz_note = QTextEdit()
        self.dayz_note.setPlainText(
            "CALIBRATION\n"
            "In DayZ, hover over each required button and press Numpad - to "
            "record its exact position and order. Record Exit and Cancel three "
            "times, then final Exit, then Rejoin. CLEAR deletes the full list.\n\n"
            "RUN DUPE\n"
            "Start SuperDuper, return to DayZ, and press Numpad + once. It runs "
            "three Exit → 2-second wait → Cancel cycles, completes a fourth "
            "logout, waits for the configured logout time plus 8 lobby seconds, "
            "then clicks Play.\n"
            "Select INFO for complete spoken and written instructions."
        )
        self.dayz_note.setReadOnly(True)
        self.dayz_note.setObjectName("filterPreview")
        dayz_tab = QWidget()
        dayz_layout = QVBoxLayout(dayz_tab)
        dayz_layout.setContentsMargins(12, 8, 12, 8)
        dayz_layout.setSpacing(6)
        clear_button_row = QHBoxLayout()
        clear_button_row.setContentsMargins(0, 8, 0, 0)
        clear_button_row.addStretch(8)
        dayz_button_column = QVBoxLayout()
        dayz_button_column.setContentsMargins(0, 0, 0, 0)
        dayz_button_column.setSpacing(6)
        dayz_button_column.addWidget(self.dayz_clear_button)
        dayz_button_column.addWidget(self.dayz_info_button)
        clear_button_row.addLayout(dayz_button_column)
        clear_button_row.addStretch(1)
        dayz_layout.addLayout(clear_button_row)
        dayz_layout.addLayout(dayz_grid)
        dayz_layout.addWidget(self.dayz_note)
        dayz_layout.addWidget(self.dayz_abort_button)
        self.tabs.addTab(dayz_tab, "DUPE")
        self.tabs.tabBarClicked.connect(self.speak_tab_guidance)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.addWidget(self.tabs)

        self.status = QLabel("Ready — configure a profile")
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.reset_button = TitaniumButton("RESET")
        self.apply_button = TitaniumButton("APPLY SETTINGS")
        self.start_button = TitaniumButton("START")
        self.reset_button.clicked.connect(self.reset_settings)
        self.apply_button.clicked.connect(self.apply_settings)
        self.start_button.clicked.connect(self.toggle_engine)
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        self.ip_edit.textChanged.connect(self.update_filter_preview)
        self.port_edit.textChanged.connect(self.update_filter_preview)
        self.direction_combo.currentTextChanged.connect(self.update_filter_preview)
        self.protocol_combo.currentTextChanged.connect(self.update_filter_preview)
        self.process_combo.currentTextChanged.connect(self.update_filter_preview)
        self.ip_edit.textEdited.connect(self.mark_targeting_custom)
        self.port_edit.textEdited.connect(self.mark_targeting_custom)
        self.direction_combo.activated.connect(self.mark_targeting_custom)
        self.protocol_combo.activated.connect(self.mark_targeting_custom)
        self.process_combo.activated.connect(self.mark_targeting_custom)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self.reset_button, 1)
        button_row.addWidget(self.apply_button, 2)
        button_row.addWidget(self.start_button, 1)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(9)
        layout.addLayout(header_row)
        layout.addWidget(panel, 1)
        layout.addWidget(self.status)
        layout.addLayout(button_row)

    def show_info_center(self) -> None:
        """Open the protected, editable INFO-CENTER folder browser."""

        dialog = InfoCenterDialog(
            self.package_location.path,
            read_text_aloud=self.read_info_center_text_aloud,
            stop_narration=self.voice.stop_speaking,
            parent=self,
        )
        dialog_geometry = dialog.frameGeometry()
        dialog_geometry.moveCenter(self.frameGeometry().center())
        dialog.move(dialog_geometry.topLeft())
        dialog.exec()

    def read_info_center_text_aloud(self, file_name: str, text: str) -> bool:
        """Narrate one INFO-CENTER text document through APP Voice."""

        if not self.voice.speak(text):
            self.status.setText(f"Cannot read {file_name} — APP Voice is currently muted")
            return False
        self.status.setText(f"APP Voice is reading {file_name}")
        return True

    def toggle_voice_muted(self, muted: bool) -> None:
        """Enable or mute the asynchronous Windows speech service."""

        self.voice.set_muted(muted)
        if muted:
            self.mute_button.setToolTip("Voice muted — click to enable the soft spoken assistant")
            self.status.setText("Voice muted")
        else:
            self.mute_button.setToolTip("Voice enabled — click to mute spoken guidance")
            self.status.setText("Voice enabled — preparing the female voice")
            self.voice.speak("SuperDuper voice is ready.")

    def toggle_voice_hotkey(self) -> None:
        """Toggle voice and synchronize the lips button from Numpad 0/INS."""

        muted = not self.mute_button.isChecked()
        self.mute_button.setChecked(muted)
        self.toggle_voice_muted(muted)
        self.status.setText(
            "Voice muted by Numpad 0/INS" if muted else "Voice enabled by Numpad 0/INS"
        )

    def speak_tab_guidance(self, index: int) -> None:
        """Speak the selected tab's help when that tab has narrated guidance."""

        tab_name = self.tabs.tabText(index)
        guidance = {
            "CONDITIONS": CONDITIONS_GUIDANCE,
            "TARGETING": TARGETING_GUIDANCE,
            "ADVANCED EFFECTS": ADVANCED_EFFECTS_GUIDANCE,
            "SAFETY": SAFETY_GUIDANCE,
            "PROFILES": PROFILES_GUIDANCE,
            "DUPE": DUPE_GUIDANCE,
        }.get(tab_name)
        if guidance is None:
            return
        if self.voice.speak(guidance):
            self.status.setText(f"Voice is explaining the {tab_name} controls")
        else:
            self.status.setText(f"Voice is muted — click the lips, then click {tab_name} again")

    def speak_direction_guidance(self) -> None:
        """Explain DIRECTION only after its explicit double-click gesture."""

        if self.voice.speak(DIRECTION_GUIDANCE):
            self.status.setText("Voice is explaining DIRECTION")
        else:
            self.status.setText("Voice is muted — click the lips, then double click DIRECTION")

    def speak_protocol_guidance(self) -> None:
        """Explain PROTOCOL only after its explicit double-click gesture."""

        if self.voice.speak(PROTOCOL_GUIDANCE):
            self.status.setText("Voice is explaining PROTOCOL")
        else:
            self.status.setText("Voice is muted — click the lips, then double click PROTOCOL")

    def speak_latency_guidance(self) -> None:
        """Explain LATENCY only after its label is double-clicked."""

        if self.voice.speak(LATENCY_GUIDANCE):
            self.status.setText("Voice is explaining LATENCY")
        else:
            self.status.setText("Voice is muted — click the lips, then double click LATENCY")

    def speak_jitter_guidance(self) -> None:
        """Explain JITTER only after its label is double-clicked."""

        if self.voice.speak(JITTER_GUIDANCE):
            self.status.setText("Voice is explaining JITTER")
        else:
            self.status.setText("Voice is muted — click the lips, then double click JITTER")

    def speak_packet_loss_guidance(self) -> None:
        """Explain PACKET LOSS only after its label is double-clicked."""

        if self.voice.speak(PACKET_LOSS_GUIDANCE):
            self.status.setText("Voice is explaining PACKET LOSS")
        else:
            self.status.setText("Voice is muted — click the lips, then double click PACKET LOSS")

    def speak_preset_guidance(self) -> None:
        """Explain PRESET only after its label is double-clicked."""

        self._speak_labeled_guidance("PRESET", PRESET_GUIDANCE)

    def speak_ip_cidr_guidance(self) -> None:
        """Explain IP / CIDR only after its label is double-clicked."""

        self._speak_labeled_guidance("IP / CIDR", IP_CIDR_GUIDANCE)

    def speak_ports_guidance(self) -> None:
        """Explain PORTS only after its label is double-clicked."""

        self._speak_labeled_guidance("PORTS", PORTS_GUIDANCE)

    def speak_process_guidance(self) -> None:
        """Explain PROCESS only after its label is double-clicked."""

        self._speak_labeled_guidance("PROCESS", PROCESS_GUIDANCE)

    def speak_duplication_guidance(self) -> None:
        self._speak_labeled_guidance("DUPLICATION", DUPLICATION_GUIDANCE)

    def speak_reorder_guidance(self) -> None:
        self._speak_labeled_guidance("OUT-OF-ORDER CHANCE", REORDER_GUIDANCE)

    def speak_reorder_hold_guidance(self) -> None:
        self._speak_labeled_guidance(
            "REORDER HOLD (MAXIMUM)",
            REORDER_HOLD_GUIDANCE,
        )

    def speak_bandwidth_guidance(self) -> None:
        self._speak_labeled_guidance("BANDWIDTH LIMIT", BANDWIDTH_GUIDANCE)

    def speak_corruption_guidance(self) -> None:
        self._speak_labeled_guidance(
            "PAYLOAD CORRUPTION",
            CORRUPTION_GUIDANCE,
        )

    def speak_bit_flips_guidance(self) -> None:
        self._speak_labeled_guidance(
            "BIT FLIPS PER SELECTED PACKET",
            BIT_FLIPS_GUIDANCE,
        )

    def speak_max_queue_guidance(self) -> None:
        self._speak_labeled_guidance(
            "MAXIMUM DELAY QUEUE",
            MAX_QUEUE_GUIDANCE,
        )

    def speak_max_session_guidance(self) -> None:
        self._speak_labeled_guidance("MAXIMUM SESSION", MAX_SESSION_GUIDANCE)

    def speak_saved_profile_guidance(self) -> None:
        self._speak_labeled_guidance("SAVED PROFILE", SAVED_PROFILE_GUIDANCE)

    def show_dupe_instructions(self) -> None:
        """Replace the DUPE information panel and narrate its complete guide."""

        self.dayz_note.clear()
        self.dayz_note.setPlainText(DUPE_INSTRUCTIONS_DISPLAY)
        self.dayz_note.verticalScrollBar().setValue(0)
        if self.voice.speak(DUPE_INSTRUCTIONS):
            self.status.setText("Voice is reading the DUPE instructions")
        else:
            self.status.setText("DUPE instructions displayed — voice is currently muted")

    def _speak_labeled_guidance(self, label: str, guidance: str) -> None:
        """Speak one label guide while preserving consistent mute feedback."""

        if self.voice.speak(guidance):
            self.status.setText(f"Voice is explaining {label}")
        else:
            self.status.setText(f"Voice is muted — click the lips, then double click {label}")

    def show_voice_ready(self, description: str) -> None:
        """Report the installed Windows voice selected by the worker."""

        if not self.voice.muted:
            self.status.setText(f"Voice ready — {description}")

    def show_voice_error(self, message: str) -> None:
        """Return the control to muted state if Windows speech cannot start."""

        self.mute_button.setChecked(True)
        self.mute_button.setToolTip("Voice unavailable — click to try Windows speech again")
        self.status.setText(message)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#central {
                background-color: #720D26;
                color: #FFF8FA;
                font-family: "Segoe UI";
                font-size: 9pt;
            }
            QLabel#title {
                color: #FFFFFF;
                font-family: "Segoe UI Black";
                font-size: 20pt;
                letter-spacing: 3px;
            }
            QLabel#subtitle {
                color: #E9C7D0;
                font-size: 7pt;
                letter-spacing: 2px;
            }
            QLabel#conditionsLabel {
                color: #FFFFFF;
                font-weight: 600;
            }
            QLabel#targetingLabel {
                color: #FFFFFF;
                font-weight: 600;
            }
            QLabel#sectionLabel {
                color: #FFFFFF;
                font-weight: 600;
            }
            QFrame#panel {
                background-color: #5B091D;
                border: 1px solid #A93650;
                border-radius: 15px;
            }
            QPushButton#muteButton {
                background-color: transparent;
                border: none;
                padding: 0;
            }
            QPushButton#muteButton:hover {
                background-color: transparent;
                border: none;
            }
            QPushButton#muteButton:pressed {
                background-color: transparent;
                border: none;
            }
            QPushButton#muteButton:checked {
                background-color: transparent;
                border: none;
            }
            QComboBox {
                background-color: #420615;
                border: 1px solid #B94A63;
                border-radius: 9px;
                color: #FFFFFF;
                min-height: 28px;
                padding: 0 10px;
            }
            QSpinBox {
                background-color: #420615;
                border: 1px solid #B94A63;
                border-radius: 9px;
                color: #FFFFFF;
                min-height: 28px;
                padding: 0 10px;
            }
            QSpinBox#precisionValue {
                background-color: transparent;
                border: none;
                border-radius: 0;
                color: #FFFFFF;
                font-family: "Segoe UI Semibold";
                font-size: 27pt;
                min-height: 44px;
                padding: 0;
            }
            QSpinBox#precisionValue:focus {
                background-color: #420615;
                border: 1px solid #F0B4C2;
                border-radius: 8px;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #5B091D;
                color: #FFFFFF;
                selection-background-color: #8E1732;
            }
            QLineEdit {
                background-color: #420615;
                border: 1px solid #B94A63;
                border-radius: 9px;
                color: #FFFFFF;
                min-height: 28px;
                padding: 0 10px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #F0B4C2;
            }
            QSlider::groove:horizontal {
                background: #31040F;
                border-radius: 3px;
                height: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #D4D7DA;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #AEB2B7;
                border-radius: 8px;
                height: 16px;
                margin: -5px 0;
                width: 16px;
            }
            QLabel#status {
                color: #F5DDE3;
                font-size: 8pt;
            }
            QTabWidget::pane {
                border: 0;
            }
            QTabBar::tab {
                background: #420615;
                color: #DDB8C1;
                border-radius: 8px;
                min-width: 105px;
                min-height: 24px;
                margin-right: 5px;
            }
            QTabBar::tab:selected {
                background: #9B2340;
                color: #FFFFFF;
            }
            QLabel#filterPreview, QTextEdit#filterPreview {
                background: #420615;
                border: 1px solid #8F2A43;
                border-radius: 8px;
                color: #F5DDE3;
                padding: 6px;
                font-size: 8pt;
            }
            """
        )

    def _load_settings(self) -> None:
        direction = str(self.settings.value("direction", DEFAULTS.direction))
        protocol = str(self.settings.value("protocol", DEFAULTS.protocol))
        preset = str(self.settings.value("preset", DEFAULTS.preset))
        self._select_combo_text(self.direction_combo, direction, DEFAULTS.direction)
        self._select_combo_text(self.protocol_combo, protocol, DEFAULTS.protocol)
        self._select_combo_text(self.preset_combo, preset, DEFAULTS.preset)
        self.ip_edit.setText(str(self.settings.value("ip_filter", DEFAULTS.ip_filter)))
        self.port_edit.setText(str(self.settings.value("port_filter", DEFAULTS.port_filter)))
        self.latency.set_value(self._bounded_setting("latency_ms", DEFAULTS.latency_ms, 0, 15000))
        self.jitter.set_value(self._bounded_setting("jitter_ms", DEFAULTS.jitter_ms, 0, 2000))
        self.packet_loss.set_value(
            self._bounded_setting(
                "packet_loss_percent",
                DEFAULTS.packet_loss_percent,
                0,
                100,
            )
        )
        self.duplication.set_value(
            self._bounded_setting(
                "duplication_percent",
                DEFAULTS.duplication_percent,
                0,
                100,
            )
        )
        self.reorder.set_value(
            self._bounded_setting(
                "reorder_percent",
                DEFAULTS.reorder_percent,
                0,
                100,
            )
        )
        self.reorder_delay.set_value(
            self._bounded_setting(
                "reorder_delay_ms",
                DEFAULTS.reorder_delay_ms,
                0,
                10000,
            )
        )
        self.bandwidth_spin.setValue(
            self._bounded_setting(
                "bandwidth_kbps",
                DEFAULTS.bandwidth_kbps,
                0,
                1000000,
            )
        )
        self.corruption.set_value(
            self._bounded_setting(
                "corruption_percent",
                DEFAULTS.corruption_percent,
                0,
                25,
            )
        )
        self.corruption_bits.setValue(
            self._bounded_setting(
                "corruption_bit_flips",
                DEFAULTS.corruption_bit_flips,
                1,
                8,
            )
        )
        self.max_queue_spin.setValue(
            self._bounded_setting(
                "max_queue_packets",
                DEFAULTS.max_queue_packets,
                100,
                100000,
            )
        )
        self.max_session_spin.setValue(
            self._bounded_setting(
                "max_session_minutes",
                DEFAULTS.max_session_minutes,
                0,
                1440,
            )
        )
        self.dayz_logout_wait_spin.setValue(
            self._bounded_setting("dayz_logout_wait_seconds", 15, 1, 60)
        )
        self._refresh_dayz_coordinate_labels()
        self._normalize_loaded_preset()
        self._load_profile_names()

    def _normalize_loaded_preset(self) -> None:
        """Correct legacy settings whose preset label no longer matches its values."""

        preset = self.preset_combo.currentText()
        expected = PRESET_VALUES.get(preset)
        actual = (
            self.direction_combo.currentText(),
            self.protocol_combo.currentText(),
            self.ip_edit.text().strip(),
            self.port_edit.text().strip(),
        )
        if expected is not None and actual != expected:
            self.preset_combo.setCurrentText("Custom")

    def _bounded_setting(
        self,
        key: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            value = int(self.settings.value(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _select_combo_text(combo: QComboBox, value: str, fallback: str) -> None:
        index = combo.findText(value)
        if index < 0:
            index = combo.findText(fallback)
        combo.setCurrentIndex(max(0, index))

    def apply_settings(self) -> None:
        """Persist the current configuration and report exactly what was saved."""

        valid, message = self.validate_targeting()
        if not valid:
            self.tabs.setCurrentIndex(1)
            self.status.setText(f"Cannot save: {message}")
            return
        self.settings.setValue("direction", self.direction_combo.currentText())
        self.settings.setValue("protocol", self.protocol_combo.currentText())
        self.settings.setValue("preset", self.preset_combo.currentText())
        self.settings.setValue("ip_filter", self.ip_edit.text().strip())
        self.settings.setValue("port_filter", self.port_edit.text().strip())
        self.settings.setValue("process_filter", self.process_combo.currentText())
        self.settings.setValue("latency_ms", self.latency.value())
        self.settings.setValue("jitter_ms", self.jitter.value())
        self.settings.setValue("packet_loss_percent", self.packet_loss.value())
        self.settings.setValue("duplication_percent", self.duplication.value())
        self.settings.setValue("reorder_percent", self.reorder.value())
        self.settings.setValue("reorder_delay_ms", self.reorder_delay.value())
        self.settings.setValue("bandwidth_kbps", self.bandwidth_spin.value())
        self.settings.setValue("corruption_percent", self.corruption.value())
        self.settings.setValue("corruption_bit_flips", self.corruption_bits.value())
        self.settings.setValue("max_queue_packets", self.max_queue_spin.value())
        self.settings.setValue("max_session_minutes", self.max_session_spin.value())
        self.settings.setValue("dayz_logout_wait_seconds", self.dayz_logout_wait_spin.value())
        self.settings.sync()
        self.status.setText(
            "Saved — "
            f"{self.latency.value()} ms latency, "
            f"{self.jitter.value()} ms jitter, "
            f"{self.packet_loss.value()}% loss"
        )

    def reset_settings(self) -> None:
        """Restore the documented defaults without silently persisting them."""

        self._select_combo_text(
            self.direction_combo,
            DEFAULTS.direction,
            DEFAULTS.direction,
        )
        self._select_combo_text(
            self.protocol_combo,
            DEFAULTS.protocol,
            DEFAULTS.protocol,
        )
        self.latency.set_value(DEFAULTS.latency_ms)
        self.jitter.set_value(DEFAULTS.jitter_ms)
        self.packet_loss.set_value(DEFAULTS.packet_loss_percent)
        self.duplication.set_value(DEFAULTS.duplication_percent)
        self.reorder.set_value(DEFAULTS.reorder_percent)
        self.reorder_delay.set_value(DEFAULTS.reorder_delay_ms)
        self.bandwidth_spin.setValue(DEFAULTS.bandwidth_kbps)
        self.corruption.set_value(DEFAULTS.corruption_percent)
        self.corruption_bits.setValue(DEFAULTS.corruption_bit_flips)
        self.max_queue_spin.setValue(DEFAULTS.max_queue_packets)
        self.max_session_spin.setValue(DEFAULTS.max_session_minutes)
        self.dayz_logout_wait_spin.setValue(15)
        self._select_combo_text(self.preset_combo, DEFAULTS.preset, DEFAULTS.preset)
        self.ip_edit.clear()
        self.port_edit.clear()
        self._select_combo_text(
            self.process_combo,
            DEFAULTS.process_filter,
            DEFAULTS.process_filter,
        )
        self.status.setText("Defaults restored — press Apply Settings to save")

    def apply_preset(self, preset: str) -> None:
        """Apply a documented preset to the editable targeting controls."""

        values = PRESET_VALUES.get(preset)
        if values is not None:
            self._applying_preset = True
            try:
                direction, protocol, ip_filter, port_filter = values
                self._select_combo_text(self.direction_combo, direction, "Both")
                self._select_combo_text(self.protocol_combo, protocol, "All traffic")
                self.ip_edit.setText(ip_filter)
                self.port_edit.setText(port_filter)
            finally:
                self._applying_preset = False
        self.update_filter_preview()

    def mark_targeting_custom(self, *_args: object) -> None:
        """Mark a preset as customized after a user-initiated targeting edit."""

        if not self._applying_preset and self.preset_combo.currentText() != "Custom":
            self.preset_combo.setCurrentText("Custom")

    def refresh_processes(self, checked: bool = False, announce: bool = True) -> None:
        """Refresh the selector using a read-only Windows PowerShell query."""

        del checked
        previous = str(self.settings.value("process_filter", DEFAULTS.process_filter))
        if self.process_combo.currentText():
            previous = self.process_combo.currentText()
        entries = self.discover_processes()
        self.process_combo.blockSignals(True)
        self.process_combo.clear()
        self.process_combo.addItem("Any process")
        self.process_combo.addItems(entries)
        self._select_combo_text(self.process_combo, previous, "Any process")
        self.process_combo.blockSignals(False)
        self.update_filter_preview()
        if announce:
            self.status.setText(f"Process list refreshed — {len(entries)} running")

    @staticmethod
    def discover_processes() -> list[str]:
        """Return unique executable/PID labels without opening process handles."""

        startup_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-Process | Select-Object ProcessName,Id | ConvertTo-Csv -NoTypeInformation",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
                creationflags=startup_flags,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        labels: set[str] = set()
        rows = csv.DictReader(io.StringIO(result.stdout))
        for row in rows:
            name = (row.get("ProcessName") or "").strip()
            process_id = (row.get("Id") or "").strip()
            if name and process_id.isdigit():
                labels.add(f"{name}.exe (PID {process_id})")
        return sorted(labels, key=str.casefold)

    def validate_targeting(self) -> tuple[bool, str]:
        """Validate IP/CIDR and comma-separated port/range expressions."""

        ip_text = self.ip_edit.text().strip()
        if ip_text:
            try:
                ipaddress.ip_network(ip_text, strict=False)
            except ValueError:
                return False, "enter a valid IP address or CIDR range"

        port_text = self.port_edit.text().strip()
        if port_text:
            for item in port_text.split(","):
                token = item.strip()
                if not token:
                    return False, "remove the empty port entry"
                bounds = token.split("-", 1)
                if not all(part.strip().isdigit() for part in bounds):
                    return False, f"'{token}' is not a valid port or range"
                numbers = [int(part.strip()) for part in bounds]
                if any(number < 1 or number > 65535 for number in numbers):
                    return False, "ports must be between 1 and 65535"
                if len(numbers) == 2 and numbers[0] > numbers[1]:
                    return False, f"port range '{token}' is reversed"
        return True, ""

    def update_filter_preview(self, *_args: object) -> None:
        """Display a readable summary of the currently selected target."""

        if not hasattr(self, "filter_preview"):
            return
        valid, message = self.validate_targeting()
        if not valid:
            self.filter_preview.setText(f"INVALID FILTER — {message}")
            return
        ip_scope = self.ip_edit.text().strip() or "any IP"
        ports = self.port_edit.text().strip() or "any port"
        process = self.process_combo.currentText() or "Any process"
        self.filter_preview.setText(
            f"{self.direction_combo.currentText()} · "
            f"{self.protocol_combo.currentText()} · {ip_scope} · {ports}\n"
            f"Process: {process}"
        )

    def _read_profiles(self) -> dict[str, dict[str, object]]:
        """Return validated profile objects stored in Windows settings."""

        raw = str(self.settings.value("named_profiles", "{}"))
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            name: values
            for name, values in parsed.items()
            if isinstance(name, str) and isinstance(values, dict)
        }

    def _write_profiles(self, profiles: dict[str, dict[str, object]]) -> None:
        """Persist all named profiles as deterministic JSON."""

        self.settings.setValue(
            "named_profiles",
            json.dumps(profiles, sort_keys=True, separators=(",", ":")),
        )
        self.settings.sync()

    def _load_profile_names(self, selected_name: str = "") -> None:
        """Refresh the profile selector while preserving a requested selection."""

        profiles = self._read_profiles()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("Select a saved profile...")
        self.profile_combo.addItems(sorted(profiles, key=str.casefold))
        self._select_combo_text(
            self.profile_combo,
            selected_name,
            "Select a saved profile...",
        )
        self.profile_combo.blockSignals(False)

    def current_profile_data(self) -> dict[str, object]:
        """Create a serializable snapshot of every configurable control."""

        return {
            "direction": self.direction_combo.currentText(),
            "protocol": self.protocol_combo.currentText(),
            "latency_ms": self.latency.value(),
            "jitter_ms": self.jitter.value(),
            "packet_loss_percent": self.packet_loss.value(),
            "duplication_percent": self.duplication.value(),
            "reorder_percent": self.reorder.value(),
            "reorder_delay_ms": self.reorder_delay.value(),
            "bandwidth_kbps": self.bandwidth_spin.value(),
            "corruption_percent": self.corruption.value(),
            "corruption_bit_flips": self.corruption_bits.value(),
            "preset": self.preset_combo.currentText(),
            "ip_filter": self.ip_edit.text().strip(),
            "port_filter": self.port_edit.text().strip(),
            "process_filter": self.process_combo.currentText(),
            "max_queue_packets": self.max_queue_spin.value(),
            "max_session_minutes": self.max_session_spin.value(),
        }

    def save_named_profile(self, name: str) -> None:
        """Validate a name and save the current settings under that name."""

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Profile name cannot be empty")
        if len(clean_name) > 40:
            raise ValueError("Profile name cannot exceed 40 characters")
        if any(ord(character) < 32 for character in clean_name):
            raise ValueError("Profile name cannot contain control characters")
        valid, message = self.validate_targeting()
        if not valid:
            raise ValueError(message)
        profiles = self._read_profiles()
        profiles[clean_name] = self.current_profile_data()
        self._write_profiles(profiles)
        self._load_profile_names(clean_name)
        self.status.setText(f"Profile saved — {clean_name}")

    def save_profile_prompt(self) -> None:
        """Ask for a profile name and save it after validation."""

        name, accepted = QInputDialog.getText(
            self,
            "Save Profile",
            "Profile name:",
        )
        if not accepted:
            return
        try:
            self.save_named_profile(name)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Save Profile", str(exc))

    def apply_profile_data(self, data: dict[str, object]) -> None:
        """Apply a validated stored profile without starting interception."""

        direction = str(data.get("direction", DEFAULTS.direction))
        protocol = str(data.get("protocol", DEFAULTS.protocol))
        preset = str(data.get("preset", DEFAULTS.preset))
        self._select_combo_text(self.direction_combo, direction, DEFAULTS.direction)
        self._select_combo_text(self.protocol_combo, protocol, DEFAULTS.protocol)
        self.ip_edit.setText(str(data.get("ip_filter", DEFAULTS.ip_filter)))
        self.port_edit.setText(str(data.get("port_filter", DEFAULTS.port_filter)))
        process = str(data.get("process_filter", DEFAULTS.process_filter))
        self._select_combo_text(
            self.process_combo,
            process,
            DEFAULTS.process_filter,
        )
        self.latency.set_value(
            self._bounded_profile_value(data, "latency_ms", DEFAULTS.latency_ms, 0, 15000)
        )
        self.jitter.set_value(
            self._bounded_profile_value(data, "jitter_ms", DEFAULTS.jitter_ms, 0, 2000)
        )
        self.packet_loss.set_value(
            self._bounded_profile_value(
                data,
                "packet_loss_percent",
                DEFAULTS.packet_loss_percent,
                0,
                100,
            )
        )
        self.duplication.set_value(
            self._bounded_profile_value(
                data,
                "duplication_percent",
                DEFAULTS.duplication_percent,
                0,
                100,
            )
        )
        self.reorder.set_value(
            self._bounded_profile_value(
                data,
                "reorder_percent",
                DEFAULTS.reorder_percent,
                0,
                100,
            )
        )
        self.reorder_delay.set_value(
            self._bounded_profile_value(
                data,
                "reorder_delay_ms",
                DEFAULTS.reorder_delay_ms,
                0,
                10000,
            )
        )
        self.bandwidth_spin.setValue(
            self._bounded_profile_value(
                data,
                "bandwidth_kbps",
                DEFAULTS.bandwidth_kbps,
                0,
                1000000,
            )
        )
        self.corruption.set_value(
            self._bounded_profile_value(
                data,
                "corruption_percent",
                DEFAULTS.corruption_percent,
                0,
                25,
            )
        )
        self.corruption_bits.setValue(
            self._bounded_profile_value(
                data,
                "corruption_bit_flips",
                DEFAULTS.corruption_bit_flips,
                1,
                8,
            )
        )
        self.max_queue_spin.setValue(
            self._bounded_profile_value(
                data,
                "max_queue_packets",
                DEFAULTS.max_queue_packets,
                100,
                100000,
            )
        )
        self.max_session_spin.setValue(
            self._bounded_profile_value(
                data,
                "max_session_minutes",
                DEFAULTS.max_session_minutes,
                0,
                1440,
            )
        )
        self._select_combo_text(self.preset_combo, preset, DEFAULTS.preset)
        self._normalize_loaded_preset()
        valid, message = self.validate_targeting()
        if not valid:
            raise ValueError(f"Stored profile is invalid: {message}")
        self.update_filter_preview()

    @staticmethod
    def _bounded_profile_value(
        data: dict[str, object],
        key: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        """Safely read and clamp an integer from untrusted profile JSON."""

        try:
            value = int(data.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def load_selected_profile(self) -> None:
        """Load the profile selected in the Profiles tab."""

        name = self.profile_combo.currentText()
        profiles = self._read_profiles()
        data = profiles.get(name)
        if data is None:
            self.status.setText("Select a saved profile to load")
            return
        try:
            self.apply_profile_data(data)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.status.setText(f"Profile loaded — {name}")

    def delete_profile_prompt(self) -> None:
        """Confirm and delete the selected named profile."""

        name = self.profile_combo.currentText()
        profiles = self._read_profiles()
        if name not in profiles:
            self.status.setText("Select a saved profile to delete")
            return
        answer = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete the profile '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.delete_named_profile(name)

    def delete_named_profile(self, name: str) -> bool:
        """Delete one profile, returning whether it existed."""

        profiles = self._read_profiles()
        if name not in profiles:
            return False
        del profiles[name]
        self._write_profiles(profiles)
        self._load_profile_names()
        self.status.setText(f"Profile deleted — {name}")
        return True

    def _dayz_coordinate(self, name: str) -> tuple[int, int] | None:
        """Read one calibrated screen coordinate from persistent settings."""

        try:
            x = int(self.settings.value(f"dayz_{name}_x", -1))
            y = int(self.settings.value(f"dayz_{name}_y", -1))
        except (TypeError, ValueError):
            return None
        return (x, y) if x >= 0 and y >= 0 else None

    def _dayz_calibration_sequence(self) -> list[tuple[int, int]]:
        """Read the ordered Numpad-minus calibration positions."""

        raw_value = self.settings.value("dayz_calibration_sequence", "[]")
        try:
            decoded = json.loads(str(raw_value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(decoded, list):
            return []
        points: list[tuple[int, int]] = []
        for item in decoded:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not all(isinstance(value, int) for value in item)
                or item[0] < 0
                or item[1] < 0
            ):
                return []
            points.append((item[0], item[1]))
        return points

    def _save_dayz_calibration_sequence(self, points: list[tuple[int, int]]) -> None:
        """Persist an ordered calibration list in one atomic settings value."""

        self.settings.setValue(
            "dayz_calibration_sequence",
            json.dumps([[x, y] for x, y in points], separators=(",", ":")),
        )
        self.settings.sync()

    def _refresh_dayz_coordinate_labels(self) -> None:
        points = self._dayz_calibration_sequence()
        default_steps = (
            "EXIT 1",
            "CANCEL 1",
            "EXIT 2",
            "CANCEL 2",
            "EXIT 3",
            "CANCEL 3",
            "FINAL EXIT",
            "REJOIN",
        )
        self.dayz_exit_label.setText(f"Calibration sequence: {len(points)} position(s) saved")
        if len(points) < len(default_steps):
            next_step = default_steps[len(points)]
        else:
            next_step = "additional ordered position"
        self.dayz_cancel_label.setText(f"Next Numpad - capture: {next_step}")
        if points:
            coordinate_text = " → ".join(
                f"{index}:{x},{y}" for index, (x, y) in enumerate(points, start=1)
            )
        else:
            coordinate_text = "not calibrated"
        self.dayz_play_label.setText(f"Saved order: {coordinate_text}")

    def capture_dayz_calibration_point(self) -> None:
        """Append the current pointer position when Numpad minus is pressed."""

        if self._dayz_sequence_active:
            self.status.setText("Calibration not recorded — Dupe sequence is currently running")
            return
        if os.name != "nt":
            self.status.setText("Numpad - calibration capture requires Windows")
            return
        title = self.foreground_window_title()
        if "dayz" not in title.casefold():
            self.status.setText("Calibration not recorded — DayZ must be the foreground window")
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        point = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            self.status.setText("Calibration not recorded — pointer position unavailable")
            return
        points = self._dayz_calibration_sequence()
        points.append((int(point.x), int(point.y)))
        self._save_dayz_calibration_sequence(points)
        self._refresh_dayz_coordinate_labels()
        self.status.setText(f"Calibration position {len(points)} saved — {point.x}, {point.y}")

    def clear_dayz_calibration(self) -> None:
        """Delete the ordered sequence and all legacy DUPE positions."""

        if self._dayz_sequence_active:
            self.abort_dayz_sequence("Dupe sequence aborted — calibration positions cleared")
        self._dayz_calibration_target = ""
        self.settings.remove("dayz_calibration_sequence")
        for name in ("exit", "cancel", "play"):
            self.settings.remove(f"dayz_{name}_x")
            self.settings.remove(f"dayz_{name}_y")
        self.settings.sync()
        self._refresh_dayz_coordinate_labels()
        self.status.setText("Calibration cleared — all recorded positions removed")

    def cancel_dayz_calibration(self) -> None:
        """Disarm a pending two-press calibration without saving a coordinate."""

        if not self._dayz_calibration_target:
            return
        self._dayz_calibration_target = ""
        self._refresh_dayz_coordinate_labels()

    @staticmethod
    def foreground_window_title() -> str:
        """Return the current foreground window title without changing focus."""

        if os.name != "nt":
            return ""
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        handle = user32.GetForegroundWindow()
        if not handle:
            return ""
        length = user32.GetWindowTextLengthW(handle)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, len(buffer))
        return buffer.value

    def _click_dayz_coordinate(self, name: str) -> bool:
        """Click a calibrated coordinate only while a DayZ window is foreground."""

        point = self._dayz_coordinate(name)
        if point is None:
            self.abort_dayz_sequence(f"{name.title()} position is not calibrated")
            return False
        return self._click_dayz_point(point, name.title())

    def _click_dayz_point(self, point: tuple[int, int], label: str) -> bool:
        """Click one saved sequence point only while DayZ is foreground."""

        title = self.foreground_window_title()
        if "dayz" not in title.casefold():
            self.abort_dayz_sequence(
                f"DayZ lost foreground focus (active window: {title or 'unknown'})"
            )
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.mouse_event.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        ]
        user32.mouse_event.restype = None
        if not user32.SetCursorPos(point[0], point[1]):
            self.abort_dayz_sequence("Windows could not move the mouse pointer")
            return False
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        self.status.setText(f"Dupe sequence — clicked {label}")
        return True

    def _open_dayz_exit_menu(self) -> bool:
        """Press Escape only while DayZ owns the foreground window."""

        title = self.foreground_window_title()
        if "dayz" not in title.casefold():
            self.abort_dayz_sequence(
                f"DayZ lost foreground focus (active window: {title or 'unknown'})"
            )
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.keybd_event.argtypes = [
            wintypes.BYTE,
            wintypes.BYTE,
            wintypes.DWORD,
            ctypes.c_size_t,
        ]
        user32.keybd_event.restype = None
        user32.keybd_event(0x1B, 0, 0, 0)
        user32.keybd_event(0x1B, 0, 0x0002, 0)
        return True

    def start_dayz_sequence(self) -> None:
        """Run the calibrated four-logout sequence from Numpad +."""

        if self._dayz_sequence_active:
            self.status.setText("Dupe sequence is already active")
            return
        if self._dayz_calibration_target:
            self.status.setText("Cannot run Dupe sequence — finish calibration first")
            return
        if not self.engine.running:
            self.status.setText("Cannot run Dupe sequence — start SuperDuper first")
            return
        points = self._dayz_calibration_sequence()
        if len(points) < 4 or len(points) % 2:
            self.status.setText(
                "Cannot run Dupe sequence — record complete Exit/Cancel pairs, "
                "then final Exit and Rejoin"
            )
            return
        if "dayz" not in self.foreground_window_title().casefold():
            self.status.setText("Cannot run Dupe sequence — DayZ must be foreground")
            return
        self._dayz_sequence_active = True
        self._dayz_sequence_generation += 1
        self._dayz_cycle = 1
        self._dayz_playback_points = points
        self._dayz_cancel_cycles = (len(points) - 2) // 2
        self.dayz_abort_button.setEnabled(True)
        self.status.setText(
            f"Dupe sequence — starting cancel cycle 1 of {self._dayz_cancel_cycles}"
        )
        self._dayz_begin_cancel_cycle(self._dayz_sequence_generation)

    def _dayz_schedule(
        self, delay_ms: int, generation: int, callback: Callable[[int], None]
    ) -> None:
        QTimer.singleShot(delay_ms, lambda: callback(generation))

    def _dayz_begin_cancel_cycle(self, generation: int) -> None:
        if generation != self._dayz_sequence_generation or not self._dayz_sequence_active:
            return
        self.status.setText(
            f"Dupe sequence — logout {self._dayz_cycle} of {self._dayz_cancel_cycles} initiated"
        )
        if self._open_dayz_exit_menu():
            self._dayz_schedule(DAYZ_MENU_OPEN_DELAY_MS, generation, self._dayz_click_cycle_exit)

    def _dayz_click_cycle_exit(self, generation: int) -> None:
        if generation != self._dayz_sequence_generation or not self._dayz_sequence_active:
            return
        point_index = (self._dayz_cycle - 1) * 2
        if self._click_dayz_point(
            self._dayz_playback_points[point_index],
            f"Exit {self._dayz_cycle}",
        ):
            self._dayz_schedule(DAYZ_CANCEL_DELAY_MS, generation, self._dayz_cancel_cycle)

    def _dayz_cancel_cycle(self, generation: int) -> None:
        if generation != self._dayz_sequence_generation or not self._dayz_sequence_active:
            return
        point_index = (self._dayz_cycle - 1) * 2 + 1
        if not self._click_dayz_point(
            self._dayz_playback_points[point_index],
            f"Cancel {self._dayz_cycle}",
        ):
            return
        self.status.setText(
            f"Dupe sequence — logout {self._dayz_cycle} of {self._dayz_cancel_cycles} cancelled"
        )
        if self._dayz_cycle < self._dayz_cancel_cycles:
            self._dayz_cycle += 1
            self._dayz_schedule(DAYZ_BETWEEN_CYCLES_MS, generation, self._dayz_begin_cancel_cycle)
        else:
            self._dayz_schedule(DAYZ_BETWEEN_CYCLES_MS, generation, self._dayz_begin_final_logout)

    def _dayz_begin_final_logout(self, generation: int) -> None:
        if generation != self._dayz_sequence_generation or not self._dayz_sequence_active:
            return
        self.status.setText("Dupe sequence — final logout initiated (not cancelled)")
        if self._open_dayz_exit_menu():
            self._dayz_schedule(DAYZ_MENU_OPEN_DELAY_MS, generation, self._dayz_click_final_exit)

    def _dayz_click_final_exit(self, generation: int) -> None:
        if generation != self._dayz_sequence_generation or not self._dayz_sequence_active:
            return
        if self._click_dayz_point(
            self._dayz_playback_points[-2],
            "Final Exit",
        ):
            delay_ms = self.dayz_logout_wait_spin.value() * 1000 + DAYZ_LOBBY_WAIT_MS
            self._dayz_schedule(delay_ms, generation, self._dayz_rejoin)

    def _dayz_rejoin(self, generation: int) -> None:
        if generation != self._dayz_sequence_generation or not self._dayz_sequence_active:
            return
        if not self._click_dayz_point(
            self._dayz_playback_points[-1],
            "Rejoin",
        ):
            return
        self._dayz_sequence_active = False
        self.dayz_abort_button.setEnabled(False)
        self.status.setText("Dupe sequence complete — Rejoin clicked after lobby wait")

    def abort_dayz_sequence(self, reason: str = "Dupe sequence aborted") -> None:
        """Invalidate pending timers so no later automated click can occur."""

        self._dayz_sequence_active = False
        self._dayz_sequence_generation += 1
        self.dayz_abort_button.setEnabled(False)
        self.status.setText(reason)

    def toggle_engine(self) -> None:
        """Start or safely stop the real WinDivert packet engine."""

        if self.engine.running:
            self.engine.stop()
            self.start_button.setText("START")
            self.set_controls_enabled(True)
            self.status.setText("Stopped — queued packets released")
            return

        valid, message = self.validate_targeting()
        if not valid:
            self.tabs.setCurrentIndex(1)
            self.status.setText(f"Cannot start: {message}")
            return
        if self.process_combo.currentText() != "Any process":
            self.tabs.setCurrentIndex(1)
            self.status.setText(
                "Cannot start: live process-to-endpoint tracking is not enabled yet"
            )
            return
        if self.corruption.value() > 0 and not (
            self.ip_edit.text().strip() or self.port_edit.text().strip()
        ):
            self.tabs.setCurrentIndex(2)
            self.status.setText("Cannot start corruption: enter a narrow IP/CIDR or port filter")
            return
        if os.name != "nt":
            self.status.setText("Cannot start: live interception requires Windows")
            return
        if not bool(ctypes.windll.shell32.IsUserAnAdmin()):
            self.request_administrator_restart()
            return
        if self.corruption.value() > 0:
            answer = QMessageBox.warning(
                self,
                "Confirm Payload Corruption",
                "Payload corruption can break sessions or damage active transfers.\n\n"
                "Only matching TCP/UDP payload bytes will be changed; headers are "
                "protected and checksums are recalculated. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status.setText("Start cancelled — corruption was not confirmed")
                return
        try:
            filter_text = build_filter(
                self.direction_combo.currentText(),
                self.protocol_combo.currentText(),
                self.ip_edit.text(),
                self.port_edit.text(),
            )
            config = ImpairmentConfig(
                filter_text=filter_text,
                latency_ms=self.latency.value(),
                jitter_ms=self.jitter.value(),
                packet_loss_percent=self.packet_loss.value(),
                duplication_percent=self.duplication.value(),
                reorder_percent=self.reorder.value(),
                reorder_delay_ms=self.reorder_delay.value(),
                bandwidth_kbps=self.bandwidth_spin.value(),
                corruption_percent=self.corruption.value(),
                corruption_bit_flips=self.corruption_bits.value(),
                max_queue_packets=self.max_queue_spin.value(),
                max_session_seconds=self.max_session_spin.value() * 60,
            )
            self.engine.start(config)
        except (OSError, ValueError, WinDivertError) as exc:
            self.status.setText(f"Cannot start: {exc}")
            return
        self.start_button.setText("STOP")
        self.set_controls_enabled(False)
        self.start_button.setEnabled(True)
        self.status.setText("ACTIVE — 0 captured · 0 sent · 0 dropped")

    def toggle_engine_from_hotkey(self) -> None:
        """Toggle from Numpad * and announce only a successful activation."""

        was_running = self.engine.running
        self.toggle_engine()
        if not was_running and self.engine.running:
            self.voice.speak("Activated.")
        elif was_running and not self.engine.running:
            self.voice.speak("Deactivated.")

    def request_administrator_restart(self) -> None:
        """Request elevation only when live interception is actually started."""

        answer = QMessageBox.question(
            self,
            "Administrator Permission Required",
            "Live traffic interception requires administrator permission.\n\n"
            "Restart SuperDuper as Administrator now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("Start cancelled — administrator permission required")
            return

        self.apply_settings()
        executable = sys.executable
        parameters = None
        if not getattr(sys, "frozen", False):
            parameters = subprocess.list2cmdline([os.path.abspath(__file__)])

        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.ShellExecuteW.argtypes = [
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            ctypes.c_int,
        ]
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        result = shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            parameters,
            str(self.package_location.path),
            1,
        )
        if int(result or 0) <= 32:
            self.status.setText("Elevation was cancelled or could not be started")
            return
        self.close()

    def emergency_stop(self) -> None:
        """Stop interception without ever treating the hotkey as Start."""

        self.cancel_dayz_calibration()
        self.abort_dayz_sequence("Emergency stop — Dupe sequence aborted")
        if not self.engine.running:
            self.status.setText("Emergency stop — engine already inactive")
            return
        self.engine.stop()
        self.start_button.setText("START")
        self.set_controls_enabled(True)
        self.status.setText("EMERGENCY STOP — queued packets released")

    def set_controls_enabled(self, enabled: bool) -> None:
        """Prevent a running session's settings from changing underneath it."""

        for control in (
            self.reset_button,
            self.apply_button,
            self.direction_combo,
            self.protocol_combo,
            self.latency,
            self.jitter,
            self.packet_loss,
            self.preset_combo,
            self.ip_edit,
            self.port_edit,
            self.process_combo,
            self.refresh_button,
            self.duplication,
            self.reorder,
            self.reorder_delay,
            self.bandwidth_spin,
            self.corruption,
            self.corruption_bits,
            self.max_queue_spin,
            self.max_session_spin,
            self.profile_combo,
            self.save_profile_button,
            self.load_profile_button,
            self.delete_profile_button,
            self.dayz_logout_wait_spin,
            self.dayz_clear_button,
        ):
            control.setEnabled(enabled)

    def show_engine_stats(self, stats: EngineStats) -> None:
        """Render cumulative packet counters received from the backend."""

        if self.engine.running:
            self.status.setText(
                f"ACTIVE — {stats.captured} captured · "
                f"{stats.sent} sent · {stats.dropped} dropped · "
                f"{stats.duplicated} duplicated · "
                f"{stats.reordered} reordered · {stats.throttled} shaped"
                f" · {stats.corrupted} corrupted"
            )

    def show_engine_error(self, message: str) -> None:
        """Stop a failed session so diverted traffic cannot remain queued."""

        if self.engine.running:
            self.engine.stop()
        self.start_button.setText("START")
        self.set_controls_enabled(True)
        self.status.setText(f"Engine stopped: {message}")

    def register_global_hotkey(self) -> bool:
        """Register the dedicated Numpad Multiply key as the global toggle."""

        if not self.hotkey_thread.ident:
            self.hotkey_thread.start()
        if not self.hotkey_thread.wait_until_ready():
            self.status.setText("Numpad * hotkey registration timed out")
            return False
        return (
            self.hotkey_thread.registered
            or self.hotkey_thread.emergency_registered
            or self.hotkey_thread.dayz_registered
            or self.hotkey_thread.dayz_capture_registered
            or self.hotkey_thread.voice_numpad_registered
            or self.hotkey_thread.voice_insert_registered
        )

    def unregister_global_hotkey(self) -> None:
        """Release the Windows hotkey registration when the application exits."""

        self.hotkey_thread.stop()

    def show_hotkey_registration(self, registered: bool, message: str) -> None:
        """Report whether Windows accepted the dedicated Numpad hotkey."""

        if registered:
            self.status.setText(f"Ready — {self.package_location.source} · {message}")
        else:
            self.status.setText(message)

    def showEvent(self, event: QShowEvent) -> None:
        """Register the global hotkey once the native window handle exists."""

        super().showEvent(event)
        self.register_global_hotkey()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release held packets and the driver handle before the window exits."""

        self.cancel_dayz_calibration()
        self.abort_dayz_sequence("Application closing — Dupe sequence aborted")
        self.unregister_global_hotkey()
        self.voice.shutdown()
        if self.engine.running:
            self.engine.stop()
        event.accept()

    def size_to_physical_inches(self, width_inches: float, height_inches: float) -> None:
        """Size the client window from the active display's logical DPI."""

        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            width_px, height_px = 768, 672
        else:
            width_px = round(width_inches * screen.logicalDotsPerInchX())
            height_px = round(height_inches * screen.logicalDotsPerInchY())
        self.setFixedSize(max(768, width_px), max(672, height_px))


def main() -> int:
    """Create and run the SuperDuper application."""

    app = QApplication(sys.argv)
    app.setApplicationName("SuperDuper")
    app.setOrganizationName("SuperDuper")
    window = SuperDuperWindow()
    window.size_to_physical_inches(width_inches=8.0, height_inches=7.0)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
