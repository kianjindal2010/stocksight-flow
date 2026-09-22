from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Callable


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_byte]]:
    buffer = (ctypes.c_byte * len(value)).from_buffer_copy(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect(value: bytes) -> bytes:
    if os.name != "nt":
        raise OSError("Windows credential protection is unavailable")
    source, source_buffer = _blob(value)
    result = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)
        del source_buffer


def _unprotect(value: bytes) -> bytes:
    if os.name != "nt":
        raise OSError("Windows credential protection is unavailable")
    source, source_buffer = _blob(value)
    result = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)
        del source_buffer


class DesktopSessionStore:
    """Persists one Appwrite session for the current Windows account.

    The token is encrypted with Windows DPAPI, so another Windows user cannot
    read or reuse it. A failure deliberately behaves like a signed-out state.
    """

    def __init__(
        self,
        path: Path | None = None,
        protector: Callable[[bytes], bytes] = _protect,
        unprotector: Callable[[bytes], bytes] = _unprotect,
    ) -> None:
        local_app_data = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        self.path = path or local_app_data / "StockSight Learner" / "session.dat"
        self._protector = protector
        self._unprotector = unprotector

    def load(self) -> str:
        try:
            encrypted = base64.urlsafe_b64decode(self.path.read_bytes())
            return self._unprotector(encrypted).decode("utf-8")
        except (OSError, ValueError, UnicodeError):
            return ""

    def save(self, token: str) -> None:
        if not token:
            self.clear()
            return
        try:
            encrypted = self._protector(token.encode("utf-8"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(base64.urlsafe_b64encode(encrypted))
        except OSError:
            # Authentication must still work if the local credential store is
            # temporarily unavailable; it simply will not survive a restart.
            return

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            return
