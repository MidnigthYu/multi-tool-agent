"""config/env_validator.py -- 6 用例 (FIX: settings缓存清理)。"""

from __future__ import annotations

import os

import pytest

import config.env_validator as _ev
import config.settings as _cs
from config.env_validator import REQUIRED_VARS, validate_env, validate_or_exit


class TestEnvValidator:
    def test_required_vars(self) -> None:
        assert len(REQUIRED_VARS) >= 3

    def test_validate_all_set(self) -> None:
        assert isinstance(validate_env(), list)

    @pytest.mark.skip(reason="???????v0.9.0?????????")
    def test_detects_missing(self) -> None:
        old = os.environ.pop("LLM_DEEPSEEK_API_KEY", None)
        try:
            _cs._settings = None
            _ev._TEST_MODE = False
            m = validate_env()
            assert any("DEEPSEEK" in x.upper() for x in m)
        finally:
            _ev._TEST_MODE = True
            if old is not None:
                os.environ["LLM_DEEPSEEK_API_KEY"] = old

    def test_empty_key_detected(self) -> None:
        old = os.environ.pop("LLM_DEEPSEEK_API_KEY", None)
        os.environ["LLM_DEEPSEEK_API_KEY"] = "your-"
        try:
            _cs._settings = None
            _ev._TEST_MODE = False
            m = validate_env()
            assert any("LLM_DEEPSEEK_API_KEY" in x for x in m)
        finally:
            _ev._TEST_MODE = True
            if old is not None:
                os.environ["LLM_DEEPSEEK_API_KEY"] = old

    def test_validate_or_exit_exits(self) -> None:
        olds = {k: os.environ.pop(k, None) for k in ["LLM_DEEPSEEK_API_KEY", "LLM_DOUBAO_API_KEY", "TAVILY_API_KEY"]}
        try:
            _cs._settings = None
            _ev._TEST_MODE = False
            with pytest.raises(SystemExit) as exc:
                validate_or_exit()
            assert exc.value.code == 1
        finally:
            _ev._TEST_MODE = True
            for k, v in olds.items():
                if v is not None:
                    os.environ[k] = v

    def test_validate_or_exit_passes(self) -> None:
        try:
            validate_or_exit()
        except SystemExit:
            pytest.fail("should not exit when env vars are set")
