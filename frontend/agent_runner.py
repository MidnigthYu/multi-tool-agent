"""Agent 同步封装层 — nest_asyncio 补丁 + stderr 终端日志 + 异常兜底。

解决 Streamlit 事件循环冲突，提供同步调用接口，
同时保持与路由节点统一的 stderr 双写日志规范。
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Any

import nest_asyncio

# === 全局补丁：解决 Streamlit asyncio 事件循环嵌套冲突 ===
nest_asyncio.apply()

logger = logging.getLogger(__name__)


def _console(msg: str) -> None:
    """写入 stderr 终端日志，对齐路由节点双写日志规范。

    确保 PowerShell / 终端中前端请求链路可见，
    与 [router] 日志共同构成完整可追溯链路。
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [frontend] {msg}\n"
    sys.stderr.write(line)
    sys.stderr.flush()


def _extract_response(result: dict[str, Any]) -> dict[str, Any]:
    """从 AgentState 字典提取前端所需的格式化响应。

    Returns:
        dict with keys: reply, tool_calls, tool_results, observability, error
    """
    messages = result.get("messages", [])

    # 提取最后一条 AI 回复
    reply = ""
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", "")
        if msg_type == "ai":
            content = getattr(msg, "content", "")
            reply = content if isinstance(content, str) else str(content)
            break

    return {
        "reply": reply or "（Agent 未返回有效回复）",
        "tool_calls": result.get("tool_calls", []),
        "tool_results": result.get("tool_results", {}),
        "observability": result.get("observability", {}),
        "error": False,
    }


def run_agent_sync(
    session_id: str,
    user_input: str,
    state_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同步调用 Agent，返回结构化响应字典。

    封装 asyncio.run() 调用 LangGraph Agent，
    支持通过 state_overrides 注入会话级配置（tools_disabled 等），
    捕获全部异常并返回友好提示，不抛出堆栈。

    Args:
        session_id: 会话 ID，同时用作 LangGraph checkpointer thread_id
        user_input: 用户输入文本
        state_overrides: 可选的 AgentState 字段覆盖，
            例如 {"tools_disabled": ["web_search"]}

    Returns:
        {
            "reply": str,           # Agent 最终回复
            "tool_calls": list,     # 工具调用记录
            "tool_results": dict,   # 工具执行结果
            "observability": dict,  # 可观测数据（node_timings, errors 等）
            "error": bool,          # 是否发生异常
        }
    """
    from core.agent_graph import get_agent
    from core.agent_state import create_initial_state

    _console(f"Receive session={session_id}, input={user_input[:80]}...")

    try:
        agent = get_agent()
        state: Any = create_initial_state(session_id, user_input)
        if state_overrides:
            state = dict(state)
            state.update(state_overrides)
        result = asyncio.run(
            agent.ainvoke(state, {"configurable": {"thread_id": session_id}})
        )
        _console(f"Agent invoke finished, session={session_id}")
        return _extract_response(result)

    except Exception as exc:
        logger.error("Agent invoke failed for session=%s: %s", session_id, exc)
        _console(f"Agent invoke FAILED, session={session_id}: {exc}")
        return {
            "reply": f"抱歉，处理请求时遇到了问题：{exc}",
            "tool_calls": [],
            "tool_results": {},
            "observability": {"errors": [{"code": "FRONTEND_AGENT_RUNNER", "detail": str(exc)}]},
            "error": True,
        }
