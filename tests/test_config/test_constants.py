"""Constants 委托 Settings 读取测试。"""

from __future__ import annotations

from config.constants import Constants


class TestConstants:
    def test_default_values(self) -> None:
        assert isinstance(Constants.MAX_REFLECTION_ROUNDS, int)

    def test_doc_supported_formats_type(self) -> None:
        fmts = Constants.DOC_SUPPORTED_FORMATS
        assert isinstance(fmts, tuple) and ".pdf" in fmts

    def test_settings_in_sync(self) -> None:
        from config.settings import get_settings

        assert Constants.MAX_REFLECTION_ROUNDS == get_settings().MAX_REFLECTION_ROUNDS

    def test_cannot_instantiate(self) -> None:
        import pytest

        with pytest.raises(TypeError):
            Constants()
