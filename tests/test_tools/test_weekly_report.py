"""单元测试 -- 周报生成工具 5 个核心场景。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.weekly_report_tool import generate_weekly_report


class TestWeeklyReport:
    @pytest.mark.asyncio
    async def test_weekly_report_normal(self) -> None:
        mock_response = MagicMock()
        mock_response.content = """# 周报

## 核心主题
测试周报生成
"""
        with patch("core.model_adapter.get_model_adapter") as mock_get:
            adapter = AsyncMock()
            adapter.invoke.return_value = (mock_response, {})
            mock_get.return_value = adapter
            result = await generate_weekly_report(
                session_id="s1", message_count=5,
                tool_call_records=[{"tool": "web_search", "status": "success"}],
            )
            assert "# 周报" in result
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_weekly_report_empty_session(self) -> None:
        result = await generate_weekly_report(message_count=0)
        assert "暂无消息" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_weekly_report_invalid_format(self) -> None:
        mock_response = MagicMock()
        mock_response.content = "markdown content"
        with patch("core.model_adapter.get_model_adapter") as mock_get:
            adapter = AsyncMock()
            adapter.invoke.return_value = (mock_response, {})
            mock_get.return_value = adapter
            result = await generate_weekly_report(
                session_id="s1", format="html", message_count=5,
            )
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_weekly_report_llm_failed(self) -> None:
        with patch("core.model_adapter.get_model_adapter") as mock_get:
            adapter = AsyncMock()
            adapter.invoke.side_effect = RuntimeError("model error")
            mock_get.return_value = adapter
            result = await generate_weekly_report(
                session_id="s1", message_count=5,
            )
            assert isinstance(result, str)
            assert "统计降级" in result

    @pytest.mark.asyncio
    async def test_weekly_report_long_content(self) -> None:
        mock_response = MagicMock()
        mock_response.content = "truncated report"
        with patch("core.model_adapter.get_model_adapter") as mock_get:
            adapter = AsyncMock()
            adapter.invoke.return_value = (mock_response, {})
            mock_get.return_value = adapter
            result = await generate_weekly_report(
                session_id="s1", message_count=5, session_summary="A" * 4000,
            )
            assert isinstance(result, str)
