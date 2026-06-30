"""LangGraph 完整 Agent 图 -- 7 节点 + ReAct 反思循环 + MemorySaver Checkpointer。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from config import Constants
from core.agent_state import AgentState, create_initial_state
from core.model_adapter import ModelAdapter
from core.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def build_agent_graph(
    _model_adapter: ModelAdapter,
    tool_registry: ToolRegistry,
    memory_manager: Any | None = None,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    async def _preprocess_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[preprocess] Entering node")
        messages = state.get("messages", [])
        if not messages:
            obs = state.get("observability", {})
            obs.setdefault("errors", []).append({"code": "E0307", "detail": "No messages"})
            return {"next_action": "end_conversation", "observability": obs}
        last = messages[-1]
        raw_content = last.content if hasattr(last, "content") else str(last)
        content = raw_content if isinstance(raw_content, str) else str(raw_content)
        if not content.strip():
            return {"next_action": "end_conversation"}
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["preprocess"] = elapsed
        return {"observability": obs}

    async def _router_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[router] Entering node")
        from core.router_node import router_node as _do_router

        result = await _do_router(state)
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["router"] = elapsed
        result["observability"] = obs
        return result

    async def _direct_reply_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[direct_reply] Entering node")
        from core.router_node import direct_reply_node as _do_reply

        result = await _do_reply(state)
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["direct_reply"] = elapsed
        result["observability"] = obs
        return result

    def _tool_dispatch_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[tool_dispatch] Entering node")
        selected = state.get("selected_tools", [])
        tool_calls: list[dict[str, Any]] = [{"tool": t, "params": {}, "status": "pending"} for t in selected]
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["tool_dispatch"] = elapsed
        return {"tool_calls": tool_calls, "observability": obs}

    async def _tool_execute_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[tool_execute] Entering node")
        tool_calls = state.get("tool_calls", [])
        results: dict[str, str] = {}
        for tc in tool_calls:
            tool_name = tc.get("tool", "")
            func = tool_registry.get_func(tool_name)
            if func is None:
                results[tool_name] = f"工具 '{tool_name}' 未注册"
                continue
            try:
                maybe_coro = func(**tc.get("params", {}))
                if asyncio.iscoroutine(maybe_coro):
                    tool_output: str = await maybe_coro
                else:
                    tool_output = str(maybe_coro)
                results[tool_name] = tool_output
                logger.info("[tool_execute] %s succeeded", tool_name)
            except Exception as e:
                logger.warning("[tool_execute] %s failed: %s", tool_name, e)
                results[tool_name] = f"工具 '{tool_name}' 执行错误: {e}"
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["tool_execute"] = elapsed
        return {"tool_results": results, "tool_calls": [], "observability": obs}

    def _result_integration_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[result_integration] Entering node")
        tool_results = state.get("tool_results", {})
        rc = state.get("reflection_count", 0)
        errors = [k for k, v in tool_results.items() if "错误" in v or "未注册" in v]
        needs = len(errors) > 0 and rc < Constants.MAX_REFLECTION_ROUNDS
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["result_integration"] = elapsed
        r: dict[str, Any] = {"needs_reflection": needs, "reflection_count": rc + 1, "observability": obs}
        if needs:
            r["next_action"] = "tool_dispatch"
        return r

    def _memory_update_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[memory_update] Entering node")
        obs = state.get("observability", {})
        if memory_manager is not None:
            try:
                memory_manager.update(state)
                obs["memory_updated"] = True
            except Exception as e:
                logger.warning("[memory_update] Failed: %s", e)
                obs.setdefault("warnings", []).append(f"Memory update failed: {e}")
                obs["memory_updated"] = False
        else:
            obs["memory_updated"] = False
        elapsed = int((time.monotonic() - start) * 1000)
        obs.setdefault("node_timings", {})["memory_update"] = elapsed
        return {"observability": obs}

    def _should_continue(state: AgentState) -> str:
        a = state.get("next_action", "direct_reply")
        return "end" if a == "end_conversation" else ("tools" if a == "tool_dispatch" else "direct_reply")

    def _should_reflect(state: AgentState) -> str:
        return "reflect" if state.get("needs_reflection", False) else "complete"

    workflow = StateGraph(AgentState)
    for name, fn in [
        ("preprocess", _preprocess_node),
        ("router", _router_node),
        ("direct_reply", _direct_reply_node),
        ("tool_dispatch", _tool_dispatch_node),
        ("tool_execute", _tool_execute_node),
        ("result_integration", _result_integration_node),
        ("memory_update", _memory_update_node),
    ]:
        workflow.add_node(name, fn)
    workflow.add_edge(START, "preprocess")
    workflow.add_conditional_edges(
        "preprocess", _should_continue, {"end": END, "tools": "tool_dispatch", "direct_reply": "router"}
    )
    workflow.add_conditional_edges(
        "router", _should_continue, {"direct_reply": "direct_reply", "tools": "tool_dispatch", "end": "memory_update"}
    )
    workflow.add_edge("direct_reply", "memory_update")
    workflow.add_edge("tool_dispatch", "tool_execute")
    workflow.add_edge("tool_execute", "result_integration")
    workflow.add_conditional_edges(
        "result_integration", _should_reflect, {"reflect": "router", "complete": "memory_update"}
    )
    workflow.add_edge("memory_update", END)
    return workflow.compile(checkpointer=MemorySaver())


_compiled_agent: CompiledStateGraph[AgentState, None, AgentState, AgentState] | None = None


def get_agent() -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    global _compiled_agent
    if _compiled_agent is None:
        from core.model_adapter import get_model_adapter
        from core.tool_registry import get_tool_registry

        _compiled_agent = build_agent_graph(get_model_adapter(), get_tool_registry())
    return _compiled_agent


def main() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print("Multi-Tool Agent CLI v0.1.0-skeleton")
    agent = get_agent()
    sid = f"cli_{int(time.time())}"
    while True:
        try:
            inp = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not inp or inp.lower() in ("exit", "quit"):
            break
        try:
            fs = asyncio.run(agent.ainvoke(create_initial_state(sid, inp), {"configurable": {"thread_id": sid}}))
            msgs = fs.get("messages", [])
            print(f"\n{msgs[-1].content if msgs and hasattr(msgs[-1], 'content') else fs}\n")
        except Exception as e:
            logger.error("Agent invoke failed: %s", e)
            print(f"\n错误: {e}\n")


if __name__ == "__main__":
    main()
