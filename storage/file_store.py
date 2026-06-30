"""文件系统存储 -- 路径安全校验 + 过期清理 + 扩展名白名单。"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import IO, Any

from config import ErrorCode

logger = logging.getLogger(__name__)
_ALLOWED: set[str] = {".pdf", ".docx", ".xlsx", ".txt", ".csv", ".json", ".md", ".png", ".jpg", ".jpeg"}
_MAX_SIZE = 50 * 1024 * 1024


class FileStore:
    def __init__(self, upload_dir: str) -> None:
        self._upload_dir = Path(upload_dir).resolve()
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        if not self._upload_dir.exists():
            try:
                self._upload_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise RuntimeError(ErrorCode.to_user_message(ErrorCode.E0407)) from e

    def _safe_path(self, session_id: str, filename: str) -> Path:
        sd = (self._upload_dir / session_id).resolve()
        if not str(sd).startswith(str(self._upload_dir.resolve())):
            raise PermissionError("Path traversal")
        fp = (sd / Path(filename).name).resolve()
        if not str(fp).startswith(str(self._upload_dir.resolve())):
            raise PermissionError("Path traversal")
        return fp

    def _validate_filename(self, fn: str) -> str:
        safe = Path(fn).name
        ext = Path(safe).suffix.lower()
        if ext and ext not in _ALLOWED:
            raise ValueError(f"Unsupported extension: {ext}")
        return safe

    def _validate_size(self, content: bytes) -> None:
        if len(content) > _MAX_SIZE:
            raise ValueError(f"File too large: {len(content)}")

    @property
    def upload_dir(self) -> Path:
        return self._upload_dir

    def save_file(self, session_id: str, filename: str, content: bytes) -> Path:
        fn = self._validate_filename(filename)
        self._validate_size(content)
        fp = self._safe_path(session_id, fn)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)
        return fp

    def open_file(self, session_id: str, filename: str, mode: str = "rb") -> IO[Any] | None:
        fp = self._safe_path(session_id, filename)
        if not fp.exists():
            return None
        try:
            return open(fp, mode)
        except OSError as e:
            logger.error("Failed to open file: %s", e)
            return None

    def read_file(self, session_id: str, filename: str) -> bytes | None:
        fp = self._safe_path(session_id, filename)
        return fp.read_bytes() if fp.exists() else None

    def delete_file(self, session_id: str, filename: str) -> bool:
        fp = self._safe_path(session_id, filename)
        if fp.exists():
            fp.unlink()
            return True
        return False

    def list_files(self, session_id: str) -> list[Path]:
        sd = self._upload_dir / session_id
        return sorted(p for p in sd.iterdir() if p.is_file()) if sd.exists() else []

    def cleanup_session(self, session_id: str) -> None:
        sd = self._upload_dir / session_id
        if sd.exists():
            shutil.rmtree(sd)

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        cutoff = time.time() - max_age_hours * 3600
        count = 0
        for sd in self._upload_dir.iterdir():
            if sd.is_dir():
                for f in sd.rglob("*"):
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        f.unlink()
                        count += 1
        return count

    def get_file_size(self, session_id: str, filename: str) -> int | None:
        fp = self._safe_path(session_id, filename)
        return fp.stat().st_size if fp.exists() else None

    def get_usage_bytes(self) -> int:
        return sum(f.stat().st_size for f in self._upload_dir.rglob("*") if f.is_file())


_instance: FileStore | None = None


def get_file_store(upload_dir: str = "data/uploads") -> FileStore:
    global _instance
    if _instance is None:
        _instance = FileStore(upload_dir)
    return _instance


def read_file(path: str) -> bytes | None:
    p = Path(path)
    return p.read_bytes() if p.exists() else None


def write_file(path: str, content: bytes) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
