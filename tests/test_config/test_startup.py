"""config/startup.py 单元测试。"""

from __future__ import annotations

import logging
from contextlib import suppress
from unittest.mock import patch

from config.startup import bootstrap


class TestStartup:
    def test_bootstrap_imports(self) -> None:
        from config.env_validator import validate_or_exit
        from core.logger import setup_logging

        assert callable(validate_or_exit)
        assert callable(setup_logging)

    def test_bootstrap_runs(self) -> None:
        root = logging.getLogger()
        old_level = root.level
        old_handlers = list(root.handlers)
        root.handlers.clear()
        try:
            with patch("config.startup.validate_or_exit"):
                bootstrap()
        finally:
            root.setLevel(old_level)
            root.handlers.clear()
            for h in old_handlers:
                root.addHandler(h)

    def test_bootstrap_sets_level(self) -> None:
        root = logging.getLogger()
        old_level = root.level
        old_handlers = list(root.handlers)
        root.handlers.clear()
        try:
            with patch("config.startup.validate_or_exit"):
                bootstrap()
            assert root.level == logging.INFO
        finally:
            root.setLevel(old_level)
            root.handlers.clear()
            for h in old_handlers:
                root.addHandler(h)

    def test_bootstrap_no_crash(self) -> None:
        with suppress(SystemExit), patch("config.startup.validate_or_exit"):
            bootstrap()
