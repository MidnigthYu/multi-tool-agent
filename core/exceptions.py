"""标准化异常类 -- AppError + ErrorCode 绑定。"""

from __future__ import annotations

from config.error_codes import ErrorCode


class AppError(Exception):
    def __init__(self, error_code: ErrorCode, detail: str = "") -> None:
        self.error_code = error_code
        self.message = ErrorCode.to_user_message(error_code)
        self.detail = detail
        super().__init__(f"[{error_code.value}] {self.message}")


class ModelError(AppError):
    pass


class ToolError(AppError):
    pass


class StorageError(AppError):
    pass


def wrap_error(error_code: ErrorCode, detail: str = "") -> AppError:
    prefix = error_code.value[:3]
    if prefix == "E01":
        return ModelError(error_code, detail)
    if prefix == "E02":
        return ToolError(error_code, detail)
    if prefix == "E04":
        return StorageError(error_code, detail)
    return AppError(error_code, detail)
