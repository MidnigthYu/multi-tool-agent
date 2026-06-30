"""强类型 TypedDict AgentState -- 11 个 Required 字段。"""

from __future__ import annotations

from typing import Annotated, Any, Required, TypedDict, cast

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from config.settings import get_settings


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: Required[str]
    model_name: Required[str]
    model_retry_count: Required[int]
    fallback_flag: Required[bool]
    chroma_degraded: Required[bool]
    tools_disabled: Required[list[str]]
    memory_context: Required[dict[str, Any]]
    tool_calls: Required[list[dict[str, Any]]]
    tool_results: Required[dict[str, str]]
    next_action: str
    reflection_count: int
    selected_tools: list[str]
    needs_reflection: bool
    observability: Required[dict[str, Any]]


def create_initial_state(session_id: str, message: str) -> AgentState:
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=message)],
        "session_id": session_id,
        "model_name": get_settings().LLM_DEEPSEEK_MODEL,
        "model_retry_count": 0,
        "fallback_flag": False,
        "chroma_degraded": False,
        "tools_disabled": [],
        "memory_context": {},
        "tool_calls": [],
        "tool_results": {},
        "observability": {
            "node_timings": {},
            "errors": [],
            "warnings": [],
            "degraded_flags": {},
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        },
    }


def merge_agent_state(base: AgentState, update: AgentState) -> AgentState:
    merged: dict[str, Any] = dict(base)
    merged.update(update)
    merged["messages"] = base.get("messages", []) + update.get("messages", [])
    merged["tool_calls"] = base.get("tool_calls", []) + update.get("tool_calls", [])
    merged["tool_results"] = {**base.get("tool_results", {}), **update.get("tool_results", {})}
    obs_b = base.get("observability", {})
    obs_u = update.get("observability", {})
    merged["observability"] = {
        "node_timings": {**obs_b.get("node_timings", {}), **obs_u.get("node_timings", {})},
        "errors": obs_b.get("errors", []) + obs_u.get("errors", []),
        "warnings": obs_b.get("warnings", []) + obs_u.get("warnings", []),
        "degraded_flags": {**obs_b.get("degraded_flags", {}), **obs_u.get("degraded_flags", {})},
        "token_usage": {**obs_b.get("token_usage", {}), **obs_u.get("token_usage", {})},
    }
    return cast(AgentState, merged)
