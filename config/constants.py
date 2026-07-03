"""全局阈值常量 -- 全部委托到 Settings 动态读取，代码内禁止硬编码。"""

from __future__ import annotations

from typing import Any, Final

from config.settings import get_settings

_SETTINGS_CACHE: dict[str, Any] = {}
_INITIALIZED: bool = False


def _build_constants() -> None:
    """从 Settings 惰性填充所有常量。"""
    global _INITIALIZED
    if _INITIALIZED:
        return
    s = get_settings()
    _SETTINGS_CACHE["MODEL_REQUEST_TIMEOUT_S"] = s.MODEL_REQUEST_TIMEOUT_S
    _SETTINGS_CACHE["MODEL_FALLBACK_COOLDOWN_S"] = s.MODEL_FALLBACK_COOLDOWN_S
    _SETTINGS_CACHE["FALLBACK_MAX_RETRIES"] = s.FALLBACK_MAX_RETRIES
    _SETTINGS_CACHE["TOKEN_MAX_PER_SESSION"] = s.TOKEN_MAX_PER_SESSION
    _SETTINGS_CACHE["TOKEN_COMPRESS_THRESHOLD"] = s.TOKEN_COMPRESS_THRESHOLD
    _SETTINGS_CACHE["MAX_REFLECTION_ROUNDS"] = s.MAX_REFLECTION_ROUNDS
    _SETTINGS_CACHE["SEARCH_TIMEOUT_S"] = s.SEARCH_TIMEOUT_S
    _SETTINGS_CACHE["SEARCH_RETRY_MAX"] = s.SEARCH_RETRY_MAX
    _SETTINGS_CACHE["SEARCH_RETRY_BASE_DELAY_S"] = s.SEARCH_RETRY_BASE_DELAY_S
    _SETTINGS_CACHE["SEARCH_RESULT_MAX_LENGTH"] = s.SEARCH_RESULT_MAX_LENGTH
    _SETTINGS_CACHE["DOC_MAX_FILE_SIZE_MB"] = s.DOC_MAX_FILE_SIZE_MB
    _SETTINGS_CACHE["DOC_CHUNK_SIZE"] = s.DOC_CHUNK_SIZE
    _SETTINGS_CACHE["DOC_CHUNK_OVERLAP"] = s.DOC_CHUNK_OVERLAP
    _SETTINGS_CACHE["DOC_SUPPORTED_FORMATS"] = tuple(
        fmt.strip().lower() for fmt in s.DOC_SUPPORTED_FORMATS.split(",") if fmt.strip()
    )
    _SETTINGS_CACHE["CHROMA_HEARTBEAT_INTERVAL_S"] = s.CHROMA_HEARTBEAT_INTERVAL_S
    _SETTINGS_CACHE["CHROMA_DEGRADED_THRESHOLD"] = s.CHROMA_DEGRADED_THRESHOLD
    _SETTINGS_CACHE["CHROMA_COLLECTION_DOCS"] = s.CHROMA_COLLECTION_DOCS
    _SETTINGS_CACHE["CHROMA_COLLECTION_MEMORY"] = s.CHROMA_COLLECTION_MEMORY
    _SETTINGS_CACHE["SQLITE_BUSY_TIMEOUT_S"] = s.SQLITE_BUSY_TIMEOUT_S
    _SETTINGS_CACHE["SESSION_EXPIRE_HOURS"] = s.SESSION_EXPIRE_HOURS
    _SETTINGS_CACHE["MID_TERM_SUMMARY_THRESHOLD"] = s.MID_TERM_SUMMARY_THRESHOLD
    _SETTINGS_CACHE["CODE_SANDBOX_TIMEOUT_S"] = s.CODE_SANDBOX_TIMEOUT_S
    _SETTINGS_CACHE["CODE_SANDBOX_SOFT_TIMEOUT_S"] = s.CODE_SANDBOX_SOFT_TIMEOUT_S
    _SETTINGS_CACHE["CODE_SANDBOX_MEMORY_LIMIT_MB"] = s.CODE_SANDBOX_MEMORY_LIMIT_MB
    _SETTINGS_CACHE["CODE_SANDBOX_MAX_OUTPUT_CHARS"] = s.CODE_SANDBOX_MAX_OUTPUT_CHARS
    _SETTINGS_CACHE["RAG_DEFAULT_TOP_K"] = s.RAG_DEFAULT_TOP_K
    _SETTINGS_CACHE["RAG_SIMILARITY_THRESHOLD"] = s.RAG_SIMILARITY_THRESHOLD
    _SETTINGS_CACHE["RAG_MAX_RESULT_LENGTH"] = s.RAG_MAX_RESULT_LENGTH
    _SETTINGS_CACHE["SHORT_TERM_MAX_MESSAGES"] = s.SHORT_TERM_MAX_MESSAGES
    _SETTINGS_CACHE["SESSION_MAX_ROUNDS"] = s.SESSION_MAX_ROUNDS
    _SETTINGS_CACHE["LONG_TERM_MEMORY_TOP_K"] = s.LONG_TERM_MEMORY_TOP_K
    _SETTINGS_CACHE["LONG_TERM_MEMORY_SIMILARITY_THRESHOLD"] = s.LONG_TERM_MEMORY_SIMILARITY_THRESHOLD
    _SETTINGS_CACHE["SUMMARY_PROMPT_TEMPLATE"] = s.SUMMARY_PROMPT_TEMPLATE
    _INITIALIZED = True


class ConstantsMeta(type):
    """元类实现 Constants.XXX 委托到 Settings 动态值。"""

    def __getattr__(cls, name: str) -> Any:
        _build_constants()
        if name in _SETTINGS_CACHE:
            return _SETTINGS_CACHE[name]
        msg = f"type object 'Constants' has no attribute '{name}'"
        raise AttributeError(msg)


class Constants(metaclass=ConstantsMeta):
    """所有阈值常量通过 Constants.XXX 访问，值来自 Settings（即 .env）。"""

    DOC_SUPPORTED_FORMATS: Final[tuple[str, ...]] = (".pdf", ".docx", ".xlsx")
    SUMMARY_PROMPT_TEMPLATE: Final[str] = (
        "请为以下对话生成结构化摘要。返回 JSON 格式："
        '{"intent":"对话核心意图","conclusion":"主要结论",'
        '"todos":["待办1","待办2"],"preferences":["偏好1"]}'
    )

    def __init_subclass__(cls) -> None:
        raise TypeError("Constants cannot be subclassed")

    def __init__(self) -> None:
        raise TypeError("Constants cannot be instantiated")


_build_constants()
__all__ = ["Constants"]
