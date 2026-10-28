"""Locate and authenticate a SuperDuper package on the configured Desktop."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APPLICATION_ID = "com.superduper.network-condition-studio"
MARKER_NAME = "superduper.package.json"
SCHEMA_VERSION = 1
FOLDERID_DESKTOP = uuid.UUID("b4bfcc3a-db2c-424c-b029-7fe99a87c641")
PACKAGE_VERSION = "0.1.0"
WINDIVERT_VERSION = "2.2.2"
OFFICIAL_REQUIRED_FILES = {
    "WinDivert.dll": "c1e060ee19444a259b2162f8af0f3fe8c4428a1c6f694dce20de194ac8d7d9a2",
    "WinDivert64.sys": ("8da085332782708d8767bcace5327a6ec7283c17cfb85e40b03cd2323a90ddc2"),
    "WinDivert-LICENSE.txt": ("14a0cb5214d536e4fdae6aa3f5696f981eeda106cd026e9794bba489ee79d628"),
}
OFFICIAL_APPLICATION_MARKERS = {
    "SuperDuper.py": ("77da58cac4579109a6593efb05305656a6d6a519fe98dc5fa9d6e4422b9ddd1a"),
    "windivert_backend.py": ("1f84913c91484d109cd4e032d5fc94828471be7cf7e7f552dbaf8e86824976d3"),
    "SuperDuper.ico": ("afba0b42a49b57a83f44b013b9a98f33273b72250e41ce83b376b99ed60b3227"),
}


class PackageNotFoundError(RuntimeError):
    """Raised when neither an authentic external nor bundled package exists."""


@dataclass(frozen=True, slots=True)
class PackageLocation:
    """A validated package directory and the method used to locate it."""

    path: Path
    source: str


def configured_desktop() -> Path:
    """Return Windows' configured Desktop, including known-folder redirection."""

    if os.name != "nt":
        return Path.home() / "Desktop"
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    guid_buffer = (ctypes.c_ubyte * 16).from_buffer_copy(FOLDERID_DESKTOP.bytes_le)
    output = ctypes.c_wchar_p()
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(guid_buffer),
        0,
        None,
        ctypes.byref(output),
    )
    if result != 0 or not output.value:
        raise PackageNotFoundError(
            f"Windows could not resolve the configured Desktop (HRESULT {result:#x})"
        )
    try:
        return Path(output.value).resolve()
    finally:
        ole32.CoTaskMemFree(ctypes.cast(output, ctypes.c_void_p))


def sha256_file(path: Path) -> str:
    """Hash a file without loading the complete binary into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_marker(directory: Path) -> dict[str, Any] | None:
    """Read a candidate marker, returning None for malformed content."""

    try:
        data = json.loads((directory / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def validate_package(directory: Path, require_application_markers: bool) -> bool:
    """Authenticate identity, schema, required files, and official binary hashes."""

    marker = read_marker(directory)
    if marker is None:
        return False
    if marker.get("application_id") != APPLICATION_ID:
        return False
    if marker.get("schema_version") != SCHEMA_VERSION:
        return False
    if marker.get("package_version") != PACKAGE_VERSION:
        return False
    if marker.get("windivert_version") != WINDIVERT_VERSION:
        return False
    required = marker.get("required_files")
    if required != OFFICIAL_REQUIRED_FILES:
        return False
    for name, expected_hash in required.items():
        if not isinstance(name, str) or not isinstance(expected_hash, str):
            return False
        candidate = directory / name
        try:
            if not candidate.is_file() or sha256_file(candidate) != expected_hash.lower():
                return False
        except OSError:
            return False
    if require_application_markers:
        markers = marker.get("application_markers")
        if markers != OFFICIAL_APPLICATION_MARKERS:
            return False
        for name, expected_hash in OFFICIAL_APPLICATION_MARKERS.items():
            candidate = directory / name
            try:
                if not candidate.is_file() or sha256_file(candidate) != expected_hash:
                    return False
            except OSError:
                return False
    return True


def candidate_ancestors(start: Path, desktop: Path) -> list[Path]:
    """Return nearby candidates without walking above the configured Desktop."""

    candidates: list[Path] = []
    current = start.resolve()
    while current == desktop or desktop in current.parents:
        candidates.append(current)
        if current == desktop:
            break
        current = current.parent
    return candidates


def search_desktop(desktop: Path) -> list[Path]:
    """Find marker-bearing directories anywhere beneath the configured Desktop."""

    candidates: list[Path] = []
    for root, directories, files in os.walk(desktop, followlinks=False):
        directories[:] = [name for name in directories if not name.startswith(".")]
        if MARKER_NAME in files:
            candidates.append(Path(root).resolve())
    return sorted(
        candidates,
        key=lambda path: (len(path.relative_to(desktop).parts), str(path).casefold()),
    )


def bundled_directory() -> Path:
    """Return PyInstaller's extraction directory or the source directory."""

    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle).resolve()
    return Path(__file__).resolve().parent


def resolve_package_directory() -> PackageLocation:
    """Resolve a genuine external package first, then an authenticated bundle."""

    desktop = configured_desktop()
    module_directory = Path(__file__).resolve().parent
    if validate_package(module_directory, require_application_markers=True):
        return PackageLocation(module_directory, "active source package")
    executable_directory = Path(sys.executable).resolve().parent
    seen: set[Path] = set()
    external_candidates = candidate_ancestors(executable_directory, desktop)
    external_candidates.extend(search_desktop(desktop))
    for candidate in external_candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if validate_package(candidate, require_application_markers=True):
            return PackageLocation(candidate, "configured Desktop package")

    bundle = bundled_directory()
    if validate_package(bundle, require_application_markers=False):
        return PackageLocation(bundle, "bundled package")
    raise PackageNotFoundError(
        f"No authentic SuperDuper package was found beneath {desktop} "
        "and the bundled resources failed integrity validation"
    )
