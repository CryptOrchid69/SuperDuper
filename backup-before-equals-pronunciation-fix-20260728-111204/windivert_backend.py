"""Thread-safe WinDivert 2.2 packet-delay backend for SuperDuper."""

from __future__ import annotations

import ctypes
import heapq
import ipaddress
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MAX_PACKET_SIZE = 0xFFFF
WINDIVERT_LAYER_NETWORK = 0
WINDIVERT_SHUTDOWN_RECV = 0x1
WINDIVERT_SHUTDOWN_BOTH = 0x3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class WinDivertError(RuntimeError):
    """Raised when WinDivert cannot be loaded, opened, or used safely."""


@dataclass(frozen=True, slots=True)
class ImpairmentConfig:
    """Immutable settings consumed by a running packet engine."""

    filter_text: str
    latency_ms: int
    jitter_ms: int
    packet_loss_percent: int
    duplication_percent: int = 0
    reorder_percent: int = 0
    reorder_delay_ms: int = 0
    bandwidth_kbps: int = 0
    corruption_percent: int = 0
    corruption_bit_flips: int = 1
    max_queue_packets: int = 10000
    max_session_seconds: int = 0

    def __post_init__(self) -> None:
        """Reject unsafe values even when callers bypass the interface."""
        if not self.filter_text or not self.filter_text.isascii():
            raise ValueError("filter_text must be non-empty ASCII")
        if not 0 <= self.latency_ms <= 15000:
            raise ValueError("latency_ms must be between 0 and 15000")
        if not 0 <= self.jitter_ms <= 2000:
            raise ValueError("jitter_ms must be between 0 and 2000")
        if not 0 <= self.packet_loss_percent <= 100:
            raise ValueError("packet_loss_percent must be between 0 and 100")
        if not 0 <= self.duplication_percent <= 100:
            raise ValueError("duplication_percent must be between 0 and 100")
        if not 0 <= self.reorder_percent <= 100:
            raise ValueError("reorder_percent must be between 0 and 100")
        if not 0 <= self.reorder_delay_ms <= 10000:
            raise ValueError("reorder_delay_ms must be between 0 and 10000")
        if not 0 <= self.bandwidth_kbps <= 1000000:
            raise ValueError("bandwidth_kbps must be between 0 and 1000000")
        if not 0 <= self.corruption_percent <= 25:
            raise ValueError("corruption_percent must be between 0 and 25")
        if not 1 <= self.corruption_bit_flips <= 8:
            raise ValueError("corruption_bit_flips must be between 1 and 8")
        if not 100 <= self.max_queue_packets <= 100000:
            raise ValueError("max_queue_packets must be between 100 and 100000")
        if not 0 <= self.max_session_seconds <= 86400:
            raise ValueError("max_session_seconds must be between 0 and 86400")


@dataclass(frozen=True, slots=True)
class EngineStats:
    """Cumulative counters emitted while an engine session is active."""

    captured: int = 0
    sent: int = 0
    dropped: int = 0
    duplicated: int = 0
    reordered: int = 0
    throttled: int = 0
    corrupted: int = 0
    errors: int = 0


class WinDivertApi:
    """Minimal, typed ctypes wrapper around the official WinDivert API."""

    def __init__(self, dll_path: Path) -> None:
        if not dll_path.is_file():
            raise WinDivertError(f"WinDivert.dll was not found at {dll_path}")
        if os.name != "nt":
            raise WinDivertError("WinDivert is available only on Windows")
        self.dll = ctypes.WinDLL(str(dll_path), use_last_error=True)
        self.dll.WinDivertOpen.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int16,
            ctypes.c_uint64,
        ]
        self.dll.WinDivertOpen.restype = ctypes.c_void_p
        self.dll.WinDivertRecv.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.c_void_p,
        ]
        self.dll.WinDivertRecv.restype = ctypes.c_bool
        self.dll.WinDivertSend.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.c_void_p,
        ]
        self.dll.WinDivertSend.restype = ctypes.c_bool
        self.dll.WinDivertShutdown.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.dll.WinDivertShutdown.restype = ctypes.c_bool
        self.dll.WinDivertClose.argtypes = [ctypes.c_void_p]
        self.dll.WinDivertClose.restype = ctypes.c_bool
        self.dll.WinDivertHelperCompileFilter.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self.dll.WinDivertHelperCompileFilter.restype = ctypes.c_bool
        self.dll.WinDivertHelperCalcChecksums.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint64,
        ]
        self.dll.WinDivertHelperCalcChecksums.restype = ctypes.c_uint

    def validate_filter(self, filter_text: str) -> None:
        """Compile a filter without opening the driver or intercepting traffic."""

        error_text = ctypes.c_char_p()
        error_position = ctypes.c_uint()
        ok = self.dll.WinDivertHelperCompileFilter(
            filter_text.encode("ascii"),
            WINDIVERT_LAYER_NETWORK,
            None,
            0,
            ctypes.byref(error_text),
            ctypes.byref(error_position),
        )
        if not ok:
            detail = (
                error_text.value.decode("ascii", errors="replace")
                if error_text.value
                else "unknown compiler error"
            )
            raise WinDivertError(f"Invalid filter at character {error_position.value}: {detail}")

    def open(self, filter_text: str) -> int:
        self.validate_filter(filter_text)
        ctypes.set_last_error(0)
        handle = self.dll.WinDivertOpen(
            filter_text.encode("ascii"),
            WINDIVERT_LAYER_NETWORK,
            0,
            0,
        )
        if handle in (None, INVALID_HANDLE_VALUE):
            error = ctypes.get_last_error()
            if error == 5:
                raise WinDivertError("Administrator privileges are required")
            if error == 87:
                raise WinDivertError("WinDivert rejected the generated filter")
            raise WinDivertError(f"WinDivertOpen failed with Windows error {error}")
        return int(handle)

    def recv(self, handle: int) -> tuple[bytes, bytes] | None:
        packet = ctypes.create_string_buffer(MAX_PACKET_SIZE)
        address = ctypes.create_string_buffer(80)
        received = ctypes.c_uint()
        ok = self.dll.WinDivertRecv(
            handle,
            packet,
            MAX_PACKET_SIZE,
            ctypes.byref(received),
            address,
        )
        if not ok:
            return None
        return packet.raw[: received.value], address.raw

    def send(self, handle: int, packet: bytes, address: bytes) -> bool:
        packet_buffer = ctypes.create_string_buffer(packet, len(packet))
        address_buffer = ctypes.create_string_buffer(address, len(address))
        sent = ctypes.c_uint()
        return bool(
            self.dll.WinDivertSend(
                handle,
                packet_buffer,
                len(packet),
                ctypes.byref(sent),
                address_buffer,
            )
        ) and sent.value == len(packet)

    def recalculate_checksums(self, packet: bytes, address: bytes) -> bytes | None:
        """Return a checksum-corrected packet, or None if WinDivert rejects it."""

        packet_buffer = ctypes.create_string_buffer(packet, len(packet))
        address_buffer = ctypes.create_string_buffer(address, len(address))
        checksum_count = self.dll.WinDivertHelperCalcChecksums(
            packet_buffer,
            len(packet),
            address_buffer,
            0,
        )
        if checksum_count == 0:
            return None
        return packet_buffer.raw[: len(packet)]

    def shutdown(self, handle: int, how: int = WINDIVERT_SHUTDOWN_BOTH) -> None:
        self.dll.WinDivertShutdown(handle, how)

    def close(self, handle: int) -> None:
        self.dll.WinDivertClose(handle)


class PacketEngine:
    """Capture, delay/drop, and re-inject matching packets on worker threads."""

    def __init__(
        self,
        dll_path: Path,
        on_stats: Callable[[EngineStats], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._dll_path = dll_path
        self._on_stats = on_stats or (lambda _stats: None)
        self._on_error = on_error or (lambda _message: None)
        self._api: WinDivertApi | None = None
        self._handle: int | None = None
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._queue: list[tuple[float, int, bytes, bytes]] = []
        self._sequence = 0
        self._bandwidth_next_due = 0.0
        self._stats = EngineStats()
        self._stats_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._capture_thread: threading.Thread | None = None
        self._sender_thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._config: ImpairmentConfig | None = None

    @property
    def running(self) -> bool:
        return self._handle is not None

    def start(self, config: ImpairmentConfig) -> None:
        with self._lifecycle_lock:
            if self.running:
                raise WinDivertError("The packet engine is already running")
            api = WinDivertApi(self._dll_path)
            handle = api.open(config.filter_text)
            self._api = api
            self._handle = handle
            self._config = config
            self._stop.clear()
            self._queue.clear()
            self._sequence = 0
            self._bandwidth_next_due = 0.0
            self._stats = EngineStats()
            self._capture_thread = threading.Thread(
                target=self._capture_loop,
                name="SuperDuper-Capture",
                daemon=True,
            )
            self._sender_thread = threading.Thread(
                target=self._sender_loop,
                name="SuperDuper-Sender",
                daemon=True,
            )
            self._watchdog_thread = (
                threading.Thread(
                    target=self._watchdog_loop,
                    name="SuperDuper-Watchdog",
                    daemon=True,
                )
                if config.max_session_seconds > 0
                else None
            )
            try:
                self._capture_thread.start()
                self._sender_thread.start()
                if self._watchdog_thread is not None:
                    self._watchdog_thread.start()
            except RuntimeError:
                self._stop.set()
                api.shutdown(handle, WINDIVERT_SHUTDOWN_BOTH)
                with self._condition:
                    self._condition.notify_all()
                for worker in (
                    self._capture_thread,
                    self._sender_thread,
                    self._watchdog_thread,
                ):
                    if worker is not None and worker.is_alive():
                        worker.join()
                api.close(handle)
                self._clear_session()
                raise

    def stop(self) -> None:
        with self._lifecycle_lock:
            handle = self._handle
            api = self._api
            if handle is None or api is None:
                return
            self._stop.set()
            api.shutdown(handle, WINDIVERT_SHUTDOWN_RECV)
            with self._condition:
                self._condition.notify_all()
            current = threading.current_thread()
            for worker in (
                self._capture_thread,
                self._sender_thread,
                self._watchdog_thread,
            ):
                if worker is not None and worker is not current:
                    worker.join()
            self._flush_queue(handle, api)
            api.shutdown(handle, WINDIVERT_SHUTDOWN_BOTH)
            api.close(handle)
            self._clear_session()

    def _clear_session(self) -> None:
        """Clear handle and worker references after the native handle closes."""
        self._handle = None
        self._api = None
        self._config = None
        self._capture_thread = None
        self._sender_thread = None
        self._watchdog_thread = None

    def _capture_loop(self) -> None:
        assert self._api is not None and self._handle is not None
        assert self._config is not None
        try:
            while not self._stop.is_set():
                item = self._api.recv(self._handle)
                if item is None:
                    if not self._stop.is_set():
                        self._record_error("Packet reception stopped unexpectedly")
                    break
                packet, address = item
                self._increment_stat("captured")
                if random.random() * 100 < self._config.packet_loss_percent:
                    self._increment_stat("dropped")
                    continue
                if random.random() * 100 < self._config.corruption_percent:
                    corrupted_packet, changed = corrupt_packet_payload(
                        packet,
                        self._config.corruption_bit_flips,
                    )
                    if changed:
                        corrected_packet = self._api.recalculate_checksums(
                            corrupted_packet,
                            address,
                        )
                        if corrected_packet is None:
                            self._record_error(
                                "A corrupted packet checksum could not be recalculated"
                            )
                        else:
                            packet = corrected_packet
                            self._increment_stat("corrupted")
                jitter = random.uniform(
                    -self._config.jitter_ms,
                    self._config.jitter_ms,
                )
                delay_seconds = max(
                    0.0,
                    (self._config.latency_ms + jitter) / 1000.0,
                )
                now = time.monotonic()
                due = now + delay_seconds
                duplicate = random.random() * 100 < self._config.duplication_percent
                reorder = random.random() * 100 < self._config.reorder_percent
                copies = 2 if duplicate else 1
                queue_overflow = False
                with self._condition:
                    if len(self._queue) + copies > self._config.max_queue_packets:
                        queue_overflow = True
                    else:
                        for copy_index in range(copies):
                            packet_due = due
                            if self._config.bandwidth_kbps > 0:
                                packet_due = max(
                                    packet_due,
                                    self._bandwidth_next_due,
                                )
                                transmission_seconds = (
                                    len(packet) * 8 / (self._config.bandwidth_kbps * 1000)
                                )
                                self._bandwidth_next_due = packet_due + transmission_seconds
                            if reorder:
                                packet_due += random.uniform(
                                    0,
                                    self._config.reorder_delay_ms / 1000,
                                )
                            if copy_index:
                                packet_due += 0.001
                            self._sequence += 1
                            heapq.heappush(
                                self._queue,
                                (packet_due, self._sequence, packet, address),
                            )
                        self._condition.notify()
                if duplicate and not queue_overflow:
                    self._increment_stat("duplicated")
                if reorder and not queue_overflow:
                    self._increment_stat("reordered")
                if self._config.bandwidth_kbps > 0 and not queue_overflow:
                    self._increment_stat("throttled")
                if queue_overflow:
                    if self._api.send(self._handle, packet, address):
                        self._increment_stat("sent")
                    else:
                        self._increment_stat("errors")
                    self._trip_failsafe(
                        f"Safety stop: queue reached {self._config.max_queue_packets} packets",
                    )
                    break
        except Exception as exc:
            self._record_error(str(exc))

    def _sender_loop(self) -> None:
        assert self._api is not None and self._handle is not None
        while not self._stop.is_set():
            with self._condition:
                while not self._queue and not self._stop.is_set():
                    self._condition.wait(timeout=0.5)
                if self._stop.is_set():
                    break
                due, _sequence, packet, address = self._queue[0]
                remaining = due - time.monotonic()
                if remaining > 0:
                    self._condition.wait(timeout=remaining)
                    continue
                heapq.heappop(self._queue)
            if self._api.send(self._handle, packet, address):
                self._increment_stat("sent")
            else:
                self._record_error("A packet could not be re-injected")

    def _watchdog_loop(self) -> None:
        """Stop the session when its configured maximum duration expires."""

        assert self._config is not None
        if self._stop.wait(timeout=self._config.max_session_seconds):
            return
        self._trip_failsafe(
            f"Safety stop: {self._config.max_session_seconds}-second limit reached",
        )

    def _trip_failsafe(self, message: str) -> None:
        """Stop capture promptly and ask the UI thread to complete cleanup."""

        if self._stop.is_set():
            return
        self._stop.set()
        if self._api is not None and self._handle is not None:
            self._api.shutdown(self._handle, WINDIVERT_SHUTDOWN_RECV)
        with self._condition:
            self._condition.notify_all()
        self._record_error(message)

    def _flush_queue(self, handle: int, api: WinDivertApi) -> None:
        """Fail open by immediately returning every queued packet on Stop."""

        with self._condition:
            queued = list(self._queue)
            self._queue.clear()
        queued.sort()
        for _due, _sequence, packet, address in queued:
            if api.send(handle, packet, address):
                self._increment_stat("sent")
            else:
                self._increment_stat("errors")

    def _record_error(self, message: str) -> None:
        self._increment_stat("errors")
        self._on_error(message)

    def _increment_stat(self, field: str) -> None:
        """Atomically increment one named counter and publish a snapshot."""
        with self._stats_lock:
            values = {
                "captured": self._stats.captured,
                "sent": self._stats.sent,
                "dropped": self._stats.dropped,
                "duplicated": self._stats.duplicated,
                "reordered": self._stats.reordered,
                "throttled": self._stats.throttled,
                "corrupted": self._stats.corrupted,
                "errors": self._stats.errors,
            }
            values[field] += 1
            self._stats = EngineStats(**values)
            snapshot = self._stats
        self._on_stats(snapshot)


def packet_payload_bounds(packet: bytes) -> tuple[int, int] | None:
    """Locate a direct TCP/UDP payload without modifying network headers."""

    if not packet:
        return None
    version = packet[0] >> 4
    if version == 4:
        if len(packet) < 20:
            return None
        network_header = (packet[0] & 0x0F) * 4
        if network_header < 20 or len(packet) < network_header:
            return None
        protocol = packet[9]
        packet_end = min(len(packet), int.from_bytes(packet[2:4], "big"))
    elif version == 6:
        if len(packet) < 40:
            return None
        network_header = 40
        protocol = packet[6]
        packet_end = min(
            len(packet),
            40 + int.from_bytes(packet[4:6], "big"),
        )
    else:
        return None

    if protocol == 6:
        if packet_end < network_header + 20:
            return None
        transport_header = (packet[network_header + 12] >> 4) * 4
        if transport_header < 20:
            return None
    elif protocol == 17:
        transport_header = 8
    else:
        return None

    payload_start = network_header + transport_header
    if payload_start >= packet_end:
        return None
    return payload_start, packet_end


def corrupt_packet_payload(packet: bytes, bit_flips: int) -> tuple[bytes, bool]:
    """Flip unique payload bits while preserving every protocol header byte."""

    if not 1 <= bit_flips <= 8:
        raise ValueError("bit_flips must be between 1 and 8")
    bounds = packet_payload_bounds(packet)
    if bounds is None:
        return packet, False
    payload_start, payload_end = bounds
    available_bits = (payload_end - payload_start) * 8
    positions = random.sample(range(available_bits), min(bit_flips, available_bits))
    changed_packet = bytearray(packet)
    for position in positions:
        byte_index = payload_start + position // 8
        changed_packet[byte_index] ^= 1 << (position % 8)
    return bytes(changed_packet), True


def build_filter(
    direction: str,
    protocol: str,
    ip_filter: str,
    port_filter: str,
) -> str:
    """Translate validated interface fields into WinDivert filter syntax."""

    valid_directions = {"Both", "Outbound", "Inbound"}
    valid_protocols = {"All traffic", "TCP", "UDP", "IPv4", "IPv6"}
    if direction not in valid_directions:
        raise ValueError(f"Unsupported direction: {direction}")
    if protocol not in valid_protocols:
        raise ValueError(f"Unsupported protocol: {protocol}")

    clauses: list[str] = []
    if direction == "Outbound":
        clauses.append("outbound")
    elif direction == "Inbound":
        clauses.append("inbound")

    protocol_map = {"TCP": "tcp", "UDP": "udp", "IPv4": "ip", "IPv6": "ipv6"}
    if protocol in protocol_map:
        clauses.append(protocol_map[protocol])

    ip_text = ip_filter.strip()
    if ip_text:
        network = ipaddress.ip_network(ip_text, strict=False)
        family = "ip" if network.version == 4 else "ipv6"
        if protocol == "IPv4" and network.version != 4:
            raise ValueError("IPv6 target cannot be combined with IPv4 protocol")
        if protocol == "IPv6" and network.version != 6:
            raise ValueError("IPv4 target cannot be combined with IPv6 protocol")
        first, last = network.network_address, network.broadcast_address
        if first == last:
            clauses.append(f"({family}.SrcAddr == {first} or {family}.DstAddr == {first})")
        else:
            clauses.append(
                f"((({family}.SrcAddr >= {first}) and ({family}.SrcAddr <= {last})) "
                f"or (({family}.DstAddr >= {first}) and ({family}.DstAddr <= {last})))"
            )

    port_text = port_filter.strip()
    if port_text:
        ports = [item.strip() for item in port_text.split(",")]

        def port_terms(prefix: str) -> str:
            terms: list[str] = []
            for token in ports:
                if "-" in token:
                    low, high = token.split("-", 1)
                    terms.append(f"(({prefix}.SrcPort >= {low}) and ({prefix}.SrcPort <= {high}))")
                    terms.append(f"(({prefix}.DstPort >= {low}) and ({prefix}.DstPort <= {high}))")
                else:
                    terms.append(f"{prefix}.SrcPort == {token}")
                    terms.append(f"{prefix}.DstPort == {token}")
            return " or ".join(terms)

        if protocol == "TCP":
            clauses.append(f"({port_terms('tcp')})")
        elif protocol == "UDP":
            clauses.append(f"({port_terms('udp')})")
        else:
            clauses.append(f"((tcp and ({port_terms('tcp')})) or (udp and ({port_terms('udp')})))")
    return " and ".join(clauses) if clauses else "true"
