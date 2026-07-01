"""Settings 环境变量加载测试。"""

from __future__ import annotations

from config.settings import get_settings


class TestSettings:
    def test_default_values(self) -> None:
        s = get_settings()
        assert s.MAX_REFLECTION_ROUNDS == 2
        assert s.SHORT_TERM_MAX_MESSAGES == 5

    def test_supported_format_list(self) -> None:
        s = get_settings()
        assert ".pdf" in s.supported_format_list

    def test_chroma_persist_path(self) -> None:
        assert get_settings().chroma_persist_path is not None

    def test_log_file_path_none(self) -> None:
        assert get_settings().log_file_path is None
