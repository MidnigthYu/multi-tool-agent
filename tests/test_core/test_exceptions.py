"""core/exceptions.py 单元测试。"""

from __future__ import annotations

from config.error_codes import ErrorCode
from core.exceptions import AppError, ModelError, StorageError, ToolError, wrap_error


class TestExceptions:
    def test_app_error_init(self) -> None:
        err = AppError(ErrorCode.E0101, detail="timeout")
        assert err.error_code == ErrorCode.E0101
        assert "超时" in err.message
        assert err.detail == "timeout"

    def test_app_error_str(self) -> None:
        assert "[E0101]" in str(AppError(ErrorCode.E0101))

    def test_model_error(self) -> None:
        assert isinstance(ModelError(ErrorCode.E0101), AppError)

    def test_tool_error(self) -> None:
        assert isinstance(ToolError(ErrorCode.E0201), AppError)

    def test_storage_error(self) -> None:
        assert isinstance(StorageError(ErrorCode.E0401), AppError)

    def test_wrap_model(self) -> None:
        assert isinstance(wrap_error(ErrorCode.E0101), ModelError)

    def test_wrap_tool(self) -> None:
        assert isinstance(wrap_error(ErrorCode.E0201), ToolError)

    def test_wrap_storage(self) -> None:
        assert isinstance(wrap_error(ErrorCode.E0401), StorageError)

    def test_wrap_default(self) -> None:
        err = wrap_error(ErrorCode.E0301)
        assert isinstance(err, AppError)
        assert not isinstance(err, ModelError)

    def test_wrap_with_detail(self) -> None:
        err = wrap_error(ErrorCode.E0107, detail="bad key")
        assert err.detail == "bad key"
        assert isinstance(err, ModelError)
