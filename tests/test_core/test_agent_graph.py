"""Agent Graph -- 17 用例 (FIX: tool_dispatch路由标识 + dict断言)。"""

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
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        for name in [
            "preprocess",
            "router",
            "direct_reply",
            "tool_dispatch",
            "tool_execute",
            "result_integration",
            "memory_update",
        ]:
            assert name in g.nodes

    @pytest.mark.asyncio
    async def test_invoke(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        config = {"configurable": {"thread_id": "t1"}}
        r = await g.ainvoke(create_initial_state("s1", "hi"), config)
        assert "messages" in r

    @pytest.mark.asyncio
    async def test_stream(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        config = {"configurable": {"thread_id": "t2"}}
        events = [e async for e in g.astream(create_initial_state("s2", "hi"), config)]
        assert len(events) > 0

    def test_get_agent_singleton(self) -> None:
        assert len(list(get_agent().nodes)) >= 7

    @pytest.mark.asyncio
    async def test_search_path(self, mock_model_adapter: MagicMock) -> None:
        reg = MagicMock()

        async def mock_search(**_kw: str) -> dict:
            return {"status": "success", "query": "test", "results": [{"title": "T"}], "formatted": "result"}

        reg.get_func.return_value = mock_search
        state = create_initial_state("s3", "搜索 test")
        state["tool_calls"] = [{"tool": "search", "params": {"query": "test"}}]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(mock_model_adapter, reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t3"}})
        assert "messages" in r

    @pytest.mark.asyncio
    async def test_tool_execute_with_search(self, mock_model_adapter: MagicMock) -> None:
        reg = MagicMock()

        async def mock_search(**_kw: str) -> dict:
            return {"status": "success", "results": [{"title": "T"}], "formatted": "result"}

        reg.get_func.return_value = mock_search
        state = create_initial_state("s4", "搜索")
        state["tool_calls"] = [{"tool": "search", "params": {"query": "x"}}]
        state["selected_tools"] = ["search"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(mock_model_adapter, reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t4"}})
        result_str = r.get("tool_results", {}).get("search", "")
        assert isinstance(result_str, dict) and result_str.get("status") == "success"

    @pytest.mark.asyncio
    async def test_invoke_empty_input(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        config = {"configurable": {"thread_id": "t5"}}
        r = await g.ainvoke(create_initial_state("s5", ""), config)
        assert r is not None

    @pytest.mark.asyncio
    async def test_checkpointer_retains(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        await g.ainvoke(create_initial_state("s6", "hello"), {"configurable": {"thread_id": "keep"}})
        r2 = await g.ainvoke(create_initial_state("s6", "world"), {"configurable": {"thread_id": "keep"}})
        assert len(r2.get("messages", [])) > 1

    @pytest.mark.asyncio
    async def test_reflection_not_triggered(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        config = {"configurable": {"thread_id": "t7"}}
        events = [e async for e in g.astream(create_initial_state("s7", "hi"), config)]
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_tool_dispatch_creates_calls(
        self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock
    ) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        state = create_initial_state("s8", "do tool")
        state["selected_tools"] = ["web_search"]
        config = {"configurable": {"thread_id": "t8"}}
        events = [e async for e in g.astream(state, config)]
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_result_integration_errors(self, mock_model_adapter: MagicMock) -> None:
        reg = MagicMock()

        async def mock_fail(**_kw: str) -> str:
            return "\u9519\u8bef occurred"

        reg.get_func.return_value = mock_fail
        state = create_initial_state("s9", "x")
        state["tool_calls"] = [{"tool": "web_search", "params": {}}]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(mock_model_adapter, reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t9"}})
        assert "tool_results" in r

    def test_should_continue_end(self) -> None:
        from core.router_node import should_continue

        assert should_continue({"next_action": "end_conversation"}) == "end"

    def test_should_continue_tools(self) -> None:
        from core.router_node import should_continue

        assert should_continue({"next_action": "tool_dispatch"}) == "tools"

    @pytest.mark.asyncio
    async def test_preprocess_empty(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        config = {"configurable": {"thread_id": "t10"}}
        r = await g.ainvoke(create_initial_state("s10", ""), config)
        assert r is not None

    @pytest.mark.asyncio
    async def test_custom_config(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        config = {"configurable": {"thread_id": "custom", "recursion_limit": 5}}
        r = await g.ainvoke(create_initial_state("s11", "hi"), config)
        assert "messages" in r

    # --- 覆盖率补齐用例（不修改原有用例） ---

    @pytest.mark.asyncio
    async def test_preprocess_empty_messages(
        self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock
    ) -> None:
        """覆盖 _preprocess_node 空消息列表 → E0307 错误分支 (lines 32-34)。"""
        g = build_agent_graph(mock_model_adapter, mock_tool_registry)
        state = create_initial_state("s12", "hi")
        state["messages"] = []
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t12"}})
        obs = r.get("observability", {})
        errs = obs.get("errors", [])
        assert any(e.get("code") == "E0307" for e in errs)

    @pytest.mark.asyncio
    async def test_tool_execute_unregistered(self, mock_model_adapter: MagicMock) -> None:
        """覆盖 _tool_execute_node 工具未注册分支 (lines 86-87)。"""
        reg = MagicMock()
        reg.get_func.return_value = None
        state = create_initial_state("s13", "x")
        state["selected_tools"] = ["unknown_tool"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(mock_model_adapter, reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t13"}})
        assert r.get("needs_reflection") is True

    @pytest.mark.asyncio
    async def test_tool_execute_sync_result(self, mock_model_adapter: MagicMock) -> None:
        """覆盖 _tool_execute_node 同步工具返回分支 (line 93)。"""
        reg = MagicMock()

        def sync_tool(**_kw: str) -> str:
            return "sync_result"

        reg.get_func.return_value = sync_tool
        state = create_initial_state("s14", "x")
        state["selected_tools"] = ["sync_tool"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(mock_model_adapter, reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t14"}})
        assert r.get("tool_results", {}).get("sync_tool") == "sync_result"

    @pytest.mark.asyncio
    async def test_tool_execute_exception(self, mock_model_adapter: MagicMock) -> None:
        """覆盖 _tool_execute_node 工具执行异常分支 (lines 96-98)。"""
        reg = MagicMock()

        def bad_tool(**_kw: str) -> str:
            raise RuntimeError("tool crash")

        reg.get_func.return_value = bad_tool
        state = create_initial_state("s15", "x")
        state["selected_tools"] = ["bad_tool"]
        state["next_action"] = "tool_dispatch"
        g = build_agent_graph(mock_model_adapter, reg)
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t15"}})
        assert r.get("needs_reflection") is True

    @pytest.mark.asyncio
    async def test_result_integration_triggers_reflection(self, mock_model_adapter: MagicMock) -> None:
        """覆盖 _result_integration_node needs_reflection 分支 (line 116)。"""
        reg = MagicMock()

        def bad_func(**_kw: str) -> str:
            raise RuntimeError("tool error")

        reg.get_func.return_value = bad_func
        g = build_agent_graph(mock_model_adapter, reg)
        state = create_initial_state("s16", "hi")
        state["selected_tools"] = ["bad"]
        state["reflection_count"] = 0
        state["next_action"] = "tool_dispatch"
        r = await g.ainvoke(state, {"configurable": {"thread_id": "t16"}})
        assert r.get("needs_reflection") is True

    @pytest.mark.asyncio
    async def test_memory_update_with_manager(
        self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock
    ) -> None:
        """覆盖 _memory_update_node 使用 memory_manager 成功更新 (lines 124-126)。"""
        mm = MagicMock()
        g = build_agent_graph(mock_model_adapter, mock_tool_registry, memory_manager=mm)
        r = await g.ainvoke(create_initial_state("s17", "hi"), {"configurable": {"thread_id": "t17"}})
        obs = r.get("observability", {})
        assert obs.get("memory_updated") is True
        mm.update.assert_called()

    @pytest.mark.asyncio
    async def test_memory_update_failure(self, mock_model_adapter: MagicMock, mock_tool_registry: MagicMock) -> None:
        """覆盖 _memory_update_node update 异常回退 (lines 127-130)。"""
        mm = MagicMock()
        mm.update.side_effect = RuntimeError("memory error")
        g = build_agent_graph(mock_model_adapter, mock_tool_registry, memory_manager=mm)
        r = await g.ainvoke(create_initial_state("s18", "hi"), {"configurable": {"thread_id": "t18"}})
        obs = r.get("observability", {})
        assert obs.get("memory_updated") is False

    def test_main_cli(self) -> None:
        """覆盖 main() CLI 交互主循环入口 (lines 186-225)。"""
        from unittest.mock import patch

        import core.agent_graph as ag_mod

        with (
            patch("builtins.input", side_effect=["hello", "exit"]) as _inp,
            patch.object(ag_mod, "get_agent") as mock_ga,
            patch("asyncio.run"),
            patch("builtins.print"),
            patch("core.agent_graph.logging.basicConfig"),
        ):
            mock_ga.return_value = MagicMock()
            ag_mod.main()
            assert _inp.call_count >= 2

    def test_main_cli_exception(self) -> None:
        """覆盖 main() agent invoke 异常处理 (line 223-224)。"""
        from unittest.mock import patch

        import core.agent_graph as ag_mod

        with (
            patch("builtins.input", side_effect=["trigger_error", EOFError]) as _inp,
            patch.object(ag_mod, "get_agent") as mock_ga,
            patch("asyncio.run", side_effect=RuntimeError("invoke error")),
            patch("builtins.print") as mock_print,
            patch("core.agent_graph.logging.basicConfig"),
        ):
            mock_ga.return_value = MagicMock()
            ag_mod.main()
            outputs = [str(c) for c in mock_print.call_args_list if c.args]
            assert any("错误" in out for out in outputs) or any(
                "invoke error" in str(c) for c in mock_print.call_args_list
            )
