"""Settings 环境变量加载测试。"""

from __future__ import annotations

from config.settings import get_settings


class TestSettings:
    def test_read_env_vars(self) -> None:
        s = get_settings()
        assert s.LLM_DEEPSEEK_API_KEY == "test-llm_deepseek_api_key"

    def test_default_values(self) -> None:
        s = get_settings()
        assert s.MAX_REFLECTION_ROUNDS == 2
        assert s.SHORT_TERM_MAX_MESSAGES == 5

    def test_supported_format_list(self) -> None:
        s = get_settings()
        assert ".pdf" in s.supported_format_list

    def test_chroma_persist_path(self) -> None:
        s = get_settings()
        assert s.chroma_persist_path is not None

    def test_log_file_none_when_empty(self) -> None:
        s = get_settings()
        assert s.log_file_path is None
