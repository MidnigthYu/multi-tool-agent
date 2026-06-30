"""ModelAdapter 双模型调用与故障降级测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APITimeoutError, AuthenticationError

from core.agent_state import create_initial_state
from core.model_adapter import ModelAdapter


class TestModelAdapter:
    def test_init(self) -> None:
        assert ModelAdapter() is not None

    def test_classify_timeout(self) -> None:
        assert ModelAdapter()._classify_error(APITimeoutError("timeout")) == "E0101"

    def test_classify_auth(self) -> None:
        assert ModelAdapter()._classify_error(AuthenticationError("auth", response=MagicMock(), body=None)) == "E0107"

    @pytest.mark.asyncio
    async def test_invoke_primary_success(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mb:
            llm = AsyncMock()
            llm.ainvoke.return_value = mock_ai_message
            mb.return_value = llm
            msg, st = await adapter.invoke(state, [])
            assert msg.content == "测试回复" and st.get("fallback_flag") is False

    @pytest.mark.asyncio
    async def test_primary_fail_then_fallback(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            mp.return_value = AsyncMock(side_effect=Exception("fail"))
            mf.return_value = AsyncMock(ainvoke=AsyncMock(return_value=mock_ai_message))
            msg, st = await adapter.invoke(state, [])
            assert st.get("model_retry_count") >= 1

    @pytest.mark.asyncio
    async def test_token_usage(self, mock_ai_message: MagicMock) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        adapter._record_token_usage(mock_ai_message, state)
        assert state["observability"]["token_usage"]["prompt_tokens"] == 10

    @pytest.mark.asyncio
    async def test_both_fail(self) -> None:
        adapter = ModelAdapter()
        state = create_initial_state("s1", "hi")
        with patch.object(adapter, "_build_primary") as mp, patch.object(adapter, "_build_fallback") as mf:
            mp.return_value = AsyncMock(side_effect=Exception("fail"))
            mf.return_value = AsyncMock(side_effect=Exception("also fail"))
            msg, st = await adapter.invoke(state, [])
            assert "E0104" in str(st.get("observability", {}).get("errors", []))
            assert len(msg.content) > 0
