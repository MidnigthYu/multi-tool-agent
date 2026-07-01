"""core/logger.py -- 8 用例 (FIX: logging.handlers显式导入)。"""

from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
import os
import sys
import tempfile

from core.logger import JsonFormatter, get_logger, setup_logging


class TestLogger:
    def test_get_logger(self) -> None:
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test"

    def test_setup_logging_adds_handler(self) -> None:
        root = logging.getLogger()
        old = list(root.handlers)
        root.handlers.clear()
        try:
            setup_logging(level="DEBUG", log_file=None)
            assert len(root.handlers) >= 1
        finally:
            root.handlers.clear()
            for h in old:
                root.addHandler(h)

    def test_json_formatter(self) -> None:
        fmt = JsonFormatter()
        r = logging.LogRecord("test_logger", logging.INFO, "t.py", 42, "msg", (), None)
        p = json.loads(fmt.format(r))
        assert p["level"] == "INFO"
        assert p["message"] == "msg"
        assert p["logger"] == "test_logger"

    def test_json_formatter_exception(self) -> None:
        fmt = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            record = logging.LogRecord("t", logging.ERROR, "t.py", 1, "err", (), None)
            record.exc_info = sys.exc_info()
        parsed = json.loads(fmt.format(record))
        assert "ValueError" in parsed.get("exception", "")

    def test_setup_idempotent(self) -> None:
        root = logging.getLogger()
        old = list(root.handlers)
        root.handlers.clear()
        try:
            setup_logging(level="INFO")
            c1 = len(root.handlers)
            setup_logging(level="DEBUG")
            assert len(root.handlers) == c1
        finally:
            root.handlers.clear()
            for h in old:
                root.addHandler(h)

    def test_no_exception_in_json(self) -> None:
        fmt = JsonFormatter()
        r = logging.LogRecord("t", logging.INFO, "t.py", 1, "no_exc", (), None)
        p = json.loads(fmt.format(r))
        assert "exception" not in p

    def test_json_timestamp(self) -> None:
        fmt = JsonFormatter()
        r = logging.LogRecord("t", logging.WARNING, "t.py", 1, "warn", (), None)
        p = json.loads(fmt.format(r))
        assert "timestamp" in p and p["level"] == "WARNING"

    def test_setup_with_file(self) -> None:
        root = logging.getLogger()
        old = list(root.handlers)
        root.handlers.clear()
        tmp = tempfile.mkstemp(suffix=".log")
        os.close(tmp[0])
        try:
            setup_logging(level="INFO", log_file=tmp[1])
            has_file = any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
            assert has_file
        finally:
            root.handlers.clear()
            for h in old:
                root.addHandler(h)
            with contextlib.suppress(PermissionError):
                os.unlink(tmp[1])
