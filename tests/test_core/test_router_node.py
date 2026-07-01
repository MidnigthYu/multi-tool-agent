"""意图路由节点测试 -- async + AIMessage 适配。"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from core.agent_state import create_initial_state
from core.router_node import should_continue


class TestRouterNode:
    def test_should_continue_direct_reply(self) -> None:
        assert should_continue({"next_action": "direct_reply"}) == "direct_reply"

    def test_should_continue_end(self) -> None:
        assert should_continue({"next_action": "end_conversation"}) == "end"

    def test_should_continue_tools(self) -> None:
        assert should_continue({"next_action": "tool_dispatch"}) == "tools"

    def test_default(self) -> None:
        assert should_continue({}) == "direct_reply"

    @pytest.mark.asyncio
    async def test_direct_reply_generates_message(self) -> None:
        from core.router_node import direct_reply_node

        state = create_initial_state("s1", "你好")
        result = await direct_reply_node(state)
        assert "messages" in result and len(result["messages"]) > len(state["messages"])

    @pytest.mark.asyncio
    async def test_direct_reply_with_tool_results(self) -> None:
        from core.router_node import direct_reply_node

        state = create_initial_state("s2", "搜索天气")
        state["tool_results"] = {"search": "晴天"}
        result = await direct_reply_node(state)
        assert isinstance(result["messages"][-1], AIMessage)

    @pytest.mark.asyncio
    async def test_router_no_messages(self) -> None:
        from core.router_node import router_node

        state = create_initial_state("s3", "")
        state["messages"] = []
        result = await router_node(state)
        assert result["next_action"] == "end_conversation"

    @pytest.mark.asyncio
    async def test_router_with_tool_results(self) -> None:
        from core.router_node import router_node

        state = create_initial_state("s4", "hi")
        state["tool_results"] = {"search": "result"}
        result = await router_node(state)
        assert result["next_action"] == "direct_reply"
