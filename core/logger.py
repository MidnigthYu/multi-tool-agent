"""全局统一日志模块 -- JSON 格式 + 轮转 + 双输出。"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if isinstance(record.exc_info, tuple) and record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


_LOGGING_SETUP_DONE: bool = False


def setup_logging(
    level: str = "INFO", log_file: str | None = None, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5
) -> None:
    global _LOGGING_SETUP_DONE
    if _LOGGING_SETUP_DONE:
        return
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(console)
    if log_file:
        fh = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)
    _LOGGING_SETUP_DONE = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
