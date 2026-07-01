"""应用启动编排 -- 环境校验 → 日志初始化。"""

from __future__ import annotations

from config.env_validator import validate_or_exit
from config.settings import get_settings
from core.logger import setup_logging


def bootstrap() -> None:
    validate_or_exit()
    settings = get_settings()
    setup_logging(level=settings.LOG_LEVEL, log_file=settings.LOG_FILE if settings.LOG_FILE else None)
