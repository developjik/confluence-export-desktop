from __future__ import annotations

from dataclasses import asdict, dataclass


ALLOWED_CATEGORIES = {
    "Auth",
    "Network",
    "Confluence API",
    "Exporter",
    "File System",
    "Config",
    "Validation",
    "Conflict",
    "Unknown",
}


@dataclass(frozen=True)
class AppError(Exception):
    category: str
    code: str
    user_message: str
    technical_message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        if self.category not in ALLOWED_CATEGORIES:
            object.__setattr__(self, "category", "Unknown")

    def __str__(self) -> str:
        return f"{self.category}:{self.code}: {self.user_message}"

    def to_dict(self) -> dict:
        return asdict(self)


def classify_exception(exc: Exception) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, PermissionError):
        return AppError(
            "File System",
            "FS_PERMISSION_DENIED",
            "저장 폴더 권한을 확인하세요.",
            str(exc),
            False,
        )
    if isinstance(exc, FileNotFoundError):
        return AppError(
            "File System",
            "FS_NOT_FOUND",
            "필요한 파일 또는 폴더를 찾을 수 없습니다.",
            str(exc),
            False,
        )
    return AppError(
        "Unknown",
        "UNKNOWN_ERROR",
        "알 수 없는 오류가 발생했습니다. 로그를 확인하세요.",
        str(exc),
        False,
    )

