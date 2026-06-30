"""Agent Graph -- 7 节点 + Checkpointer + ReAct 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.agent_graph import build_agent_graph, get_agent
from core.agent_state import create_initial_state


class TestAgentGraph:
    def test_build_graph(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        graph = build_agent_graph(mock_model_adapter, mock_tool_registry)
        assert graph is not None

    def test_7_nodes(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        graph = build_agent_graph(mock_model_adapter, mock_tool_registry)
        required = [
            "preprocess",
            "router",
            "direct_reply",
            "tool_dispatch",
            "tool_execute",
            "result_integration",
            "memory_update",
        ]
        for name in required:
            assert name in graph.nodes

    @pytest.mark.asyncio
    async def test_invoke(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        graph = build_agent_graph(mock_model_adapter, mock_tool_registry)
        r = await graph.ainvoke(create_initial_state("s1", "hi"), {"configurable": {"thread_id": "t1"}})
        assert "messages" in r

    @pytest.mark.asyncio
    async def test_stream(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        graph = build_agent_graph(mock_model_adapter, mock_tool_registry)
        events = [
            e async for e in graph.astream(create_initial_state("s2", "hi"), {"configurable": {"thread_id": "t2"}})
        ]
        assert len(events) > 0

    def test_get_agent(self) -> None:
        agent = get_agent()
        assert agent is not None and len(list(agent.nodes)) >= 7
