"""ModelAdapter -- 19 用例。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, AuthenticationError, InternalServerError, RateLimitError

from core.agent_state import create_initial_state
from core.model_adapter import ModelAdapter


class TestModelAdapter:
    def test_init(self) -> None:
        assert ModelAdapter() is not None

    @pytest.mark.asyncio
    async def test_classify_timeout(self) -> None:
        assert ModelAdapter()._classify_error(APITimeoutError("timeout")) == "E0101"

    @pytest.mark.asyncio
    async def test_classify_auth(self) -> None:
        e = AuthenticationError("auth", response=MagicMock(), body=None)
        assert ModelAdapter()._classify_error(e) == "E0107"

    @pytest.mark.asyncio
    async def test_classify_5xx(self) -> None:
        assert ModelAdapter()._classify_error(InternalServerError("500", response=MagicMock(), body=None)) == "E0102"

    @pytest.mark.asyncio
    async def test_classify_rate_limit(self) -> None:
        assert ModelAdapter()._classify_error(RateLimitError("rate", response=MagicMock(), body=None)) == "E0102"

    @pytest.mark.asyncio
    async def test_classify_401(self) -> None:
        e = APIStatusError("401", response=MagicMock(status_code=401), body=None)
        assert ModelAdapter()._classify_error(e) == "E0107"

    @pytest.mark.asyncio
    async def test_classify_httpx_timeout(self) -> None:
        assert ModelAdapter()._classify_error(httpx.TimeoutException("timeout")) == "E0101"

    @pytest.mark.asyncio
    async def test_classify_generic(self) -> None:
        assert ModelAdapter()._classify_error(Exception("generic")) == "E0105"

    @pytest.mark.asyncio
    async def test_invoke_primary_success(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mb:
            llm = AsyncMock()
            llm.ainvoke.return_value = mock_ai_message
            mb.return_value = llm
            msg, st = await adapter.invoke(state, [])
            assert msg.content == "测试回复" and not st.get("fallback_flag")

    @pytest.mark.asyncio
    async def test_primary_fail_then_fallback(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            pllm = AsyncMock()
            pllm.ainvoke = AsyncMock(side_effect=Exception("fail"))
            mp.return_value = pllm
            fllm = AsyncMock()
            fllm.ainvoke = AsyncMock(return_value=mock_ai_message)
            mf.return_value = fllm
            msg, st = await adapter.invoke(state, [])
            assert st.get("model_retry_count") >= 1 and msg.content == "测试回复"

    @pytest.mark.asyncio
    async def test_cooling_skips_primary(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        state["fallback_flag"] = True
        adapter._last_fallback_ts = 9999999999.0
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            mp.return_value = AsyncMock(side_effect=Exception("should not"))
            mf.return_value = AsyncMock(ainvoke=AsyncMock(return_value=mock_ai_message))
            msg, st = await adapter.invoke(state, [])
            assert msg.content == "测试回复"

    @pytest.mark.asyncio
    async def test_both_fail(self) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            pllm = AsyncMock()
            pllm.ainvoke = AsyncMock(side_effect=Exception("fail"))
            mp.return_value = pllm
            fllm = AsyncMock()
            fllm.ainvoke = AsyncMock(side_effect=Exception("also fail"))
            mf.return_value = fllm
            msg, st = await adapter.invoke(state, [])
            assert "E0104" in str(st.get("observability", {}).get("errors", [])) and len(msg.content) > 0

    @pytest.mark.asyncio
    async def test_token_usage(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        adapter._record_token_usage(mock_ai_message, state)
        assert state["observability"]["token_usage"]["prompt_tokens"] == 10

    @pytest.mark.asyncio
    async def test_model_name_on_success(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mb:
            llm = AsyncMock()
            llm.ainvoke.return_value = mock_ai_message
            mb.return_value = llm
            _, st = await adapter.invoke(state, [])
            assert "deepseek" in st.get("model_name", "")

    @pytest.mark.asyncio
    async def test_model_name_on_fallback(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            pllm = AsyncMock()
            pllm.ainvoke = AsyncMock(side_effect=Exception("fail"))
            mp.return_value = pllm
            fllm = AsyncMock()
            fllm.ainvoke = AsyncMock(return_value=mock_ai_message)
            mf.return_value = fllm
            _, st = await adapter.invoke(state, [])
            assert "doubao" in st.get("model_name", "")

    @pytest.mark.asyncio
    async def test_fallback_flag(self, mock_ai_message: MagicMock) -> None:  # noqa: ARG002
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            pllm = AsyncMock()
            pllm.ainvoke = AsyncMock(side_effect=Exception("fail"))
            mp.return_value = pllm
            fllm = AsyncMock()
            fllm.ainvoke = AsyncMock(return_value=mock_ai_message)
            mf.return_value = fllm
            _, st = await adapter.invoke(state, [])
            assert st.get("fallback_flag") is True

    @pytest.mark.asyncio
    async def test_error_record(self) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            pllm = AsyncMock()
            pllm.ainvoke = AsyncMock(side_effect=Exception("fail"))
            mp.return_value = pllm
            fllm = AsyncMock()
            fllm.ainvoke = AsyncMock(side_effect=Exception("also fail"))
            mf.return_value = fllm
            _, st = await adapter.invoke(state, [])
            assert any(e.get("code") == "E0104" for e in st.get("observability", {}).get("errors", []))

    @pytest.mark.asyncio
    async def test_invoke_empty_messages(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mb:
            llm = AsyncMock()
            llm.ainvoke.return_value = mock_ai_message
            mb.return_value = llm
            msg, st = await adapter.invoke(state, [])
            assert msg.content == "测试回复"

    @pytest.mark.asyncio
    async def test_invoke_with_kwargs(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mb:
            llm = AsyncMock()
            llm.ainvoke.return_value = mock_ai_message
            mb.return_value = llm
            msg, st = await adapter.invoke(state, [], temperature=0.5)
            assert msg.content == "测试回复"

    @pytest.mark.asyncio
    async def test_build_error_record(self) -> None:
        rec = ModelAdapter()._build_error_record("E0101", "test detail")
        assert rec["code"] == "E0101" and rec["detail"] == "test detail"

    @pytest.mark.asyncio
    async def test_classify_403(self) -> None:
        e = APIStatusError("403", response=MagicMock(status_code=403), body=None)
        assert ModelAdapter()._classify_error(e) == "E0107"

    @pytest.mark.asyncio
    async def test_primary_fail_recovery(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            pllm = AsyncMock()
            pllm.ainvoke = AsyncMock(side_effect=Exception("fail"))
            mp.return_value = pllm
            fllm = AsyncMock()
            fllm.ainvoke = AsyncMock(return_value=mock_ai_message)
            mf.return_value = fllm
            msg, st = await adapter.invoke(state, [])
            assert st.get("model_retry_count") >= 1
