from __future__ import annotations

import base64
import ctypes
import os
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass
from urllib.parse import urlparse

from .errors import AppError


MASK = "****"
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*)(basic|bearer)\s+[^\s,;]+"),
    re.compile(r"(?i)(cookie\s*:\s*)[^\r\n]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(api[_-]?token\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(password\s*[=:]\s*)[^\s,;]+"),
]


def mask_sensitive(value: object) -> str:
    text = str(value)
    for pattern in SENSITIVE_PATTERNS:
        def repl(match: re.Match[str]) -> str:
            groups = match.groups()
            if len(groups) >= 2 and groups[1].lower() in {"basic", "bearer"}:
                return f"{groups[0]}{groups[1]} {MASK}"
            return f"{groups[0]}{MASK}"

        text = pattern.sub(repl, text)
    return text


def normalize_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise AppError(
            "Config",
            "INVALID_BASE_URL",
            "Confluence Base URL 형식을 확인하세요.",
            f"Invalid base_url: {base_url}",
            False,
        )
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}".rstrip("/")


def credential_key(base_url: str, email: str) -> str:
    return f"ConfluenceExportDesktop:{normalize_base_url(base_url)}:{email.strip().lower()}"


@dataclass
class CredentialRecord:
    target: str
    username: str
    secret: str


class CredentialStore:
    def write(self, base_url: str, email: str, token: str) -> str:
        raise NotImplementedError

    def read(self, base_url: str, email: str) -> str | None:
        raise NotImplementedError

    def delete(self, base_url: str, email: str) -> None:
        raise NotImplementedError


class MemoryCredentialStore(CredentialStore):
    def __init__(self) -> None:
        self._items: dict[str, CredentialRecord] = {}

    def write(self, base_url: str, email: str, token: str) -> str:
        key = credential_key(base_url, email)
        self._items[key] = CredentialRecord(key, email, token)
        return key

    def read(self, base_url: str, email: str) -> str | None:
        item = self._items.get(credential_key(base_url, email))
        return item.secret if item else None

    def delete(self, base_url: str, email: str) -> None:
        self._items.pop(credential_key(base_url, email), None)


class WindowsCredentialStore(CredentialStore):
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", wintypes.LPVOID),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    def __init__(self) -> None:
        if os.name != "nt":
            raise AppError(
                "Config",
                "WINDOWS_CREDENTIAL_MANAGER_REQUIRED",
                "Windows Credential Manager는 Windows에서만 사용할 수 있습니다.",
                sys.platform,
                False,
            )
        self._advapi32 = ctypes.windll.advapi32
        self._advapi32.CredWriteW.argtypes = [ctypes.POINTER(self.CREDENTIAL), wintypes.DWORD]
        self._advapi32.CredWriteW.restype = wintypes.BOOL
        self._advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(self.CREDENTIAL)),
        ]
        self._advapi32.CredReadW.restype = wintypes.BOOL
        self._advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._advapi32.CredDeleteW.restype = wintypes.BOOL
        self._advapi32.CredFree.argtypes = [wintypes.LPVOID]

    def write(self, base_url: str, email: str, token: str) -> str:
        key = credential_key(base_url, email)
        blob = token.encode("utf-16-le")
        blob_array = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = self.CREDENTIAL()
        cred.Type = self.CRED_TYPE_GENERIC
        cred.TargetName = key
        cred.UserName = email
        cred.CredentialBlob = ctypes.cast(blob_array, ctypes.POINTER(ctypes.c_ubyte))
        cred.CredentialBlobSize = len(blob)
        cred.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        if not self._advapi32.CredWriteW(ctypes.byref(cred), 0):
            raise AppError(
                "Auth",
                "CREDENTIAL_WRITE_FAILED",
                "API Token을 Windows Credential Manager에 저장하지 못했습니다.",
                f"CredWriteW failed: {ctypes.GetLastError()}",
                False,
            )
        return key

    def read(self, base_url: str, email: str) -> str | None:
        key = credential_key(base_url, email)
        pcred = ctypes.POINTER(self.CREDENTIAL)()
        if not self._advapi32.CredReadW(key, self.CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
            return None
        try:
            cred = pcred.contents
            size = cred.CredentialBlobSize
            raw = ctypes.string_at(cred.CredentialBlob, size)
            return raw.decode("utf-16-le")
        finally:
            self._advapi32.CredFree(pcred)

    def delete(self, base_url: str, email: str) -> None:
        key = credential_key(base_url, email)
        self._advapi32.CredDeleteW(key, self.CRED_TYPE_GENERIC, 0)


def basic_auth_header(email: str, token: str) -> str:
    payload = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    return f"Basic {payload}"

