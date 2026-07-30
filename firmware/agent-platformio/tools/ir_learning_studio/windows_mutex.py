#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows named mutex for atomic single-instance enforcement.

Safe to import on all platforms. Only instantiates kernel32 bindings
on Windows (os.name == 'nt'). Non-Windows platforms get UnsupportedPlatformError.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Optional, Callable

# ---- Platform-conditional ctypes (lazy) ----
_kernel32 = None
_CreateMutexW = None
_CloseHandle = None
_GetLastError = None
_WaitForSingleObject = None

def _ensure_windows():
    global _kernel32, _CreateMutexW, _CloseHandle, _GetLastError, _WaitForSingleObject
    if _kernel32 is not None:
        return
    if os.name != "nt":
        return
    import ctypes
    _kernel32 = ctypes.windll.kernel32
    _CreateMutexW = _kernel32.CreateMutexW
    _CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    _CreateMutexW.restype = ctypes.c_void_p
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [ctypes.c_void_p]
    _CloseHandle.restype = ctypes.c_bool
    _GetLastError = _kernel32.GetLastError
    _GetLastError.argtypes = []
    _GetLastError.restype = ctypes.c_uint32
    _WaitForSingleObject = _kernel32.WaitForSingleObject
    _WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _WaitForSingleObject.restype = ctypes.c_uint32

ERROR_ALREADY_EXISTS = 183
DDD_REMOVE_DEFINITION = 2
DDD_EXACT_MATCH_ON_REMOVE = 4


class UnsupportedPlatformError(RuntimeError):
    """Raised when WindowsNamedMutex is used on non-Windows."""


def _compute_project_root_hash(project_root: Path) -> str:
    resolved = project_root.resolve()
    normalized = str(resolved).lower().rstrip("\\/")
    encoded = normalized.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def _mutex_name(project_root_hash: str) -> str:
    return f"Local\\RemoteAC_IRLearningStudio_{project_root_hash}"


class WindowsNamedMutex:
    def __init__(self, project_root: Path, backend: Optional[Callable] = None):
        self._project_root = project_root
        self._root_hash = _compute_project_root_hash(project_root)
        self._mutex_name = _mutex_name(self._root_hash)
        self._handle: Optional[int] = None
        self._owned = False
        self._is_windows = (os.name == "nt")
        self._backend = backend  # For testing

    @property
    def root_hash(self) -> str:
        return self._root_hash

    @property
    def mutex_name(self) -> str:
        return self._mutex_name

    @property
    def is_owned(self) -> bool:
        return self._owned

    def acquire(self) -> bool:
        if self._backend:
            return self._backend(self)
        if not self._is_windows:
            self._owned = True
            return True
        _ensure_windows()
        name_wide = __import__('ctypes').c_wchar_p(self._mutex_name)
        handle = _CreateMutexW(None, False, name_wide)
        if not handle:
            return False
        self._handle = handle
        if _GetLastError() == ERROR_ALREADY_EXISTS:
            _CloseHandle(handle)
            self._handle = None
            self._owned = False
            return False
        self._owned = True
        return True

    def release(self) -> None:
        if self._handle is not None and _kernel32 is not None:
            try:
                _CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
        self._owned = False

    def write_diagnostics(self, diagnostics_path: Optional[Path] = None) -> None:
        if diagnostics_path is None:
            return
        try:
            diag = {"pid": os.getpid(), "projectRoot": str(self._project_root),
                    "projectRootHash": self._root_hash, "mutexName": self._mutex_name,
                    "isOwned": self._owned, "platform": sys.platform}
            diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostics_path.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Another IR Learning Studio instance is already running for {self._project_root}")
        return self

    def __exit__(self, *args):
        self.release()
        return False
