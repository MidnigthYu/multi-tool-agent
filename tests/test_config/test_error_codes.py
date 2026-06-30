"""ErrorCode 枚举完整性测试。"""

from __future__ import annotations

from config.error_codes import ErrorCode


class TestErrorCodes:
    def test_all_categories_present(self) -> None:
        codes = list(ErrorCode)
        prefixes = {c.value[:3] for c in codes}
        for p in ["E01", "E02", "E03", "E04", "E05"]:
            assert p in prefixes

    def test_to_http_status(self) -> None:
        assert ErrorCode.to_http_status(ErrorCode.E0101) == 502
        assert ErrorCode.to_http_status(ErrorCode.E0201) == 504
        assert ErrorCode.to_http_status(ErrorCode.E0301) == 422
        assert ErrorCode.to_http_status(ErrorCode.E0401) == 500
        assert ErrorCode.to_http_status(ErrorCode.E0501) == 400

    def test_to_user_message(self) -> None:
        msg = ErrorCode.to_user_message(ErrorCode.E0103)
        assert "主模型" in msg and "备用模型" in msg

    def test_str_representation(self) -> None:
        assert str(ErrorCode.E0101) == "E0101"

    def test_unknown_code_message(self) -> None:
        class FakeCode:
            value = "E0999"

        msg = ErrorCode.to_user_message(FakeCode())
        assert "未知错误" in msg
