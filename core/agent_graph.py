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
        rc = last.content if hasattr(last, "content") else str(last)
        content = rc if isinstance(rc, str) else str(rc)
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
        user_query = ""
        for msg in reversed(state.get("messages", [])):
            content = msg.content if hasattr(msg, "content") else ""
            if isinstance(content, str) and content.strip():
                user_query = content.strip()
                break
        tcs = []
        for t in state.get("selected_tools", []):
            params = {"query": user_query} if t == "web_search" and user_query else {}
            tcs.append({"tool": t, "params": params, "status": "pending"})
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["tool_dispatch"] = elapsed
        return {"tool_calls": tcs, "observability": obs}

    async def _tool_execute_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[tool_execute] Entering node")
        results: dict[str, str] = {}
        for tc in state.get("tool_calls", []):
            tn = tc.get("tool", "")
            func = tool_registry.get_func(tn)
            if func is None:
                results[tn] = f"工具 '{tn}' 未注册"
                continue
            try:
                maybe_coro = func(**tc.get("params", {}))
                if asyncio.iscoroutine(maybe_coro):
                    raw = await maybe_coro
                else:
                    raw = maybe_coro
                tool_output: str = raw.get("formatted", str(raw)) if isinstance(raw, dict) else str(raw)
                results[tn] = tool_output
                logger.info("[tool_execute] %s succeeded", tn)
            except Exception as e:
                logger.warning("[tool_execute] %s failed: %s", tn, e)
                results[tn] = f"工具 '{tn}' 执行错误: {e}"
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["tool_execute"] = elapsed
        return {"tool_results": results, "tool_calls": [], "observability": obs}

    def _result_integration_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[result_integration] Entering node")
        tr = state.get("tool_results", {})
        rc = state.get("reflection_count", 0)
        errors = [k for k, v in tr.items() if isinstance(v, str) and ("错误" in v or "未注册" in v)]
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
    for n, f in [
        ("preprocess", _preprocess_node),
        ("router", _router_node),
        ("direct_reply", _direct_reply_node),
        ("tool_dispatch", _tool_dispatch_node),
        ("tool_execute", _tool_execute_node),
        ("result_integration", _result_integration_node),
        ("memory_update", _memory_update_node),
    ]:
        workflow.add_node(n, f)
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
        from tools import SearchInput, search_tool

        reg = get_tool_registry()
        if "web_search" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                "web_search",
                "Tavily 联网搜索工具 — 搜索获取实时信息、新闻、百科。适用：需要时效性信息、未知知识、事实查询。",
                search_tool,
                SearchInput.model_json_schema(),
            )

        _compiled_agent = build_agent_graph(get_model_adapter(), reg)
    return _compiled_agent


def main() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print("Multi-Tool Agent CLI v0.2.0-search")
    print("输入 'exit' 退出\n")
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
