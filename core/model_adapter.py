"""双模型适配器 -- langchain_openai.ChatOpenAI + 异常分类 + 状态回写。"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from openai import APIStatusError, APITimeoutError, AuthenticationError, InternalServerError, RateLimitError

from config import ErrorCode, get_settings
from core.agent_state import AgentState

logger = logging.getLogger(__name__)


class ModelAdapter:
    def __init__(self) -> None:
        self._last_fallback_ts: float = 0.0

    def _build_primary(self) -> ChatOpenAI:
        s = get_settings()
        return ChatOpenAI(
            model=s.LLM_DEEPSEEK_MODEL,
            api_key=s.LLM_DEEPSEEK_API_KEY,  
            base_url=s.LLM_DEEPSEEK_BASE_URL,
            timeout=s.MODEL_REQUEST_TIMEOUT_S,
            max_retries=0,
        )

    def _build_fallback(self) -> ChatOpenAI:
        s = get_settings()
        return ChatOpenAI(
            model=s.LLM_DOUBAO_MODEL,
            api_key=s.LLM_DOUBAO_API_KEY,  
            base_url=s.LLM_DOUBAO_BASE_URL,
            timeout=s.MODEL_REQUEST_TIMEOUT_S,
            max_retries=0,
        )

    def _classify_error(self, exc: Exception) -> str:
        if isinstance(exc, APITimeoutError):
            return ErrorCode.E0101.value
        if isinstance(exc, AuthenticationError):
            return ErrorCode.E0107.value
        if isinstance(exc, InternalServerError):
            return ErrorCode.E0102.value
        if isinstance(exc, RateLimitError):
            return ErrorCode.E0102.value
        if isinstance(exc, httpx.TimeoutException):
            return ErrorCode.E0101.value
        if isinstance(exc, APIStatusError):
            code = exc.status_code
            if code >= 500:
                return ErrorCode.E0102.value
            if code in (401, 403):
                return ErrorCode.E0107.value
            return ErrorCode.E0105.value
        return ErrorCode.E0105.value

    def _build_error_record(self, code: str, detail: str) -> dict[str, Any]:
        return {"code": code, "timestamp": datetime.now(UTC).isoformat(), "detail": detail}

    async def _try_primary(
        self, state: AgentState, messages: list[BaseMessage], **kwargs: Any
    ) -> tuple[AIMessage | None, AgentState]:
        s = get_settings()
        now = time.monotonic()
        if state.get("fallback_flag", False) and (now - self._last_fallback_ts) < s.MODEL_FALLBACK_COOLDOWN_S:
            return None, state
        try:
            llm = self._build_primary()
            result: AIMessage = await llm.ainvoke(messages, **kwargs)
            state["model_retry_count"] = 0
            state["model_name"] = s.LLM_DEEPSEEK_MODEL
            if state.get("fallback_flag"):
                state["fallback_flag"] = False
            self._record_token_usage(result, state)
            return result, state
        except Exception as e:
            code = self._classify_error(e)
            logger.warning("Primary model failed: [%s] %s", code, e)
            state["model_retry_count"] = state.get("model_retry_count", 0) + 1
            state.setdefault("observability", {}).setdefault("errors", []).append(
                self._build_error_record(code, str(e))
            )
            if state["model_retry_count"] >= s.FALLBACK_MAX_RETRIES:
                state["fallback_flag"] = True
                self._last_fallback_ts = now
                state["observability"]["errors"].append(
                    self._build_error_record(ErrorCode.E0103.value, "Switching to fallback")
                )
            return None, state

    async def _try_fallback(
        self, state: AgentState, messages: list[BaseMessage], **kwargs: Any
    ) -> tuple[AIMessage, AgentState]:
        s = get_settings()
        try:
            llm = self._build_fallback()
            result: AIMessage = await llm.ainvoke(messages, **kwargs)
            state["model_name"] = s.LLM_DOUBAO_MODEL
            state["fallback_flag"] = True
            self._last_fallback_ts = time.monotonic()
            self._record_token_usage(result, state)
            return result, state
        except Exception as e:
            code = self._classify_error(e)
            logger.error("Fallback model also failed: [%s] %s", code, e)
            state.setdefault("observability", {}).setdefault("errors", []).append(
                self._build_error_record(code, str(e))
            )
            state["observability"]["errors"].append(
                self._build_error_record(ErrorCode.E0104.value, "Both models failed")
            )
            return AIMessage(content=ErrorCode.to_user_message(ErrorCode.E0104)), state

    async def invoke(
        self, state: AgentState, messages: list[BaseMessage], **kwargs: Any
    ) -> tuple[AIMessage, AgentState]:
        result, st = await self._try_primary(state, messages, **kwargs)
        if result is not None:
            return result, st
        return await self._try_fallback(st, messages, **kwargs)

    def _record_token_usage(self, result: AIMessage, state: AgentState) -> None:
        try:
            meta = result.response_metadata or {}
            usage = meta.get("token_usage", {}) or meta.get("usage", {})
            if usage:
                obs = state.setdefault("observability", {})
                obs.setdefault("token_usage", {})
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    obs["token_usage"][k] = usage.get(k, 0)
        except Exception as e:
            logger.debug("Token usage extraction failed: %s", e)


_adapter_instance: ModelAdapter | None = None


def get_model_adapter() -> ModelAdapter:
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = ModelAdapter()
    return _adapter_instance
