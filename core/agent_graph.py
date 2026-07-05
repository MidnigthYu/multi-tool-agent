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
        if memory_manager is not None:
            try:
                sid = state.get("session_id", "default")
                msgs = state.get("messages", [])
                last = msgs[-1] if msgs else None
                query = str(last.content) if last and hasattr(last, "content") and isinstance(last.content, str) else ""
                ctx = memory_manager.build_context(sid, query)
                if ctx:
                    state["memory_context"] = {"formatted": ctx}
            except Exception as e:
                logger.warning("[direct_reply] Memory context injection failed: %s", e)
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
        disabled = state.get("tools_disabled", [])
        tcs = []
        for t in state.get("selected_tools", []):
            if t in disabled:
                continue
            if t == "web_search" and user_query:
                params = {"query": user_query}
            elif t == "weekly_report":
                p: dict[str, Any] = {
                    "session_id": state.get("session_id", ""),
                    "format": "markdown",
                    "message_count": len(state.get("messages", [])),
                    "tool_call_records": [
                        {
                            "tool": k,
                            "status": (
                                "failed" if isinstance(v, str) and ("错误" in v or "未注册" in v) else "success"
                            ),
                        }
                        for k, v in state.get("tool_results", {}).items()
                    ],
                    "session_duration_minutes": round(
                        max(state.get("observability", {}).get("node_timings", {}).values(), default=0) / 60000, 2
                    ),
                    "session_summary": state.get("memory_context", {}).get("formatted", ""),
                }
                params = p
            else:
                params = {}
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
        ccf = state.get("consecutive_code_failures", 0)
        disabled = list(state.get("tools_disabled", []))
        errors = [k for k, v in tr.items() if isinstance(v, str) and ("错误" in v or "未注册" in v)]
        for k, v in tr.items():
            if not isinstance(v, str) or k != "code_executor":
                continue
            if v.startswith("[CODE_BLOCKED]") or v.startswith("[CODE_DEGRADED]"):
                pass  # Security block / infra failure: no reflection, no counter
            elif v.startswith("[CODE_TIMEOUT]") or v.startswith("[CODE_CRASH]"):
                ccf += 1
                if ccf >= 3 and "code_executor" not in disabled:
                    disabled.append("code_executor")
                    logger.warning("[code_executor] Disabled after %d consecutive failures", ccf)
                errors.append(k)
            else:
                ccf = 0  # Success: reset counter
        needs = len(errors) > 0 and rc < Constants.MAX_REFLECTION_ROUNDS
        elapsed = int((time.monotonic() - start) * 1000)
        obs = state.get("observability", {})
        obs.setdefault("node_timings", {})["result_integration"] = elapsed
        r: dict[str, Any] = {
            "needs_reflection": needs,
            "reflection_count": rc + 1,
            "consecutive_code_failures": ccf,
            "tools_disabled": disabled,
            "observability": obs,
        }
        if needs:
            r["next_action"] = "tool_dispatch"
        return r

    def _memory_update_node(state: AgentState) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("[memory_update] Entering node")
        obs = state.get("observability", {})
        if memory_manager is not None:
            try:
                messages = state.get("messages", [])
                sid = state.get("session_id", "default")
                user_msg = ""
                assistant_msg = ""
                for msg in reversed(messages):
                    content = msg.content if hasattr(msg, "content") else str(msg)
                    if isinstance(content, str) and content.strip():
                        if not assistant_msg:
                            assistant_msg = content
                        elif not user_msg:
                            user_msg = content
                            break
                memory_manager.update(sid, user_msg, assistant_msg)
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
        from tools import (
            CodeExecutionInput,
            IndexDocumentsInput,
            KnowledgeSearchInput,
            SearchInput,
            WeeklyReportInput,
            code_executor,
            generate_weekly_report,
            index_documents,
            knowledge_search,
            remember_this,
            search_tool,
        )

        reg = get_tool_registry()
        if "web_search" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                "web_search",
                "Tavily 联网搜索工具 — 搜索获取实时信息、新闻、百科。适用：需要时效性信息、未知知识、事实查询。",
                search_tool,
                SearchInput.model_json_schema(),
            )
        if "code_executor" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                "code_executor",
                "Python 代码执行工具 — 沙箱容器安全执行 Python 代码。适用：数学运算、数据处理、算法验证。",
                code_executor,
                CodeExecutionInput.model_json_schema(),
            )
        if "index_documents" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                "index_documents",
                "文档索引工具 — 将本地 PDF/Word/Excel 文档解析并索引到知识库。"
                "适用：用户上传文档后需要建立索引以供检索。",
                index_documents,
                IndexDocumentsInput.model_json_schema(),
            )
        if "knowledge_search" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                "knowledge_search",
                "本地知识库检索工具 — 语义搜索已索引的文档内容。适用：需要查询已上传文档中的具体信息、数据、条款。",
                knowledge_search,
                KnowledgeSearchInput.model_json_schema(),
            )
        if "remember_this" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                "remember_this",
                "记忆写入工具 — 将重要事实、用户偏好永久保存到长期记忆。适用场景：用户明确告知偏好、重要事实。",
                remember_this,  # type: ignore[arg-type]
                {
                    "type": "object",
                    "properties": {"fact": {"type": "string", "description": "要记住的事实"}},
                    "required": ["fact"],
                },
            )
        if "weekly_report" not in [t["name"] for t in reg.list_tools()]:
            reg.register(
                "weekly_report",
                "周报生成工具 — 根据会话数据自动生成结构化周报。适用：对近期对话总结、工具统计、任务跟进。",
                generate_weekly_report,
                WeeklyReportInput.model_json_schema(),
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
