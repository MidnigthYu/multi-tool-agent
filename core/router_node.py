"""意图路由判断节点 -- LLM 决策 + 条件边 + selected_tools。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from config import Constants, get_settings
from core.agent_state import AgentState
from core.model_adapter import get_model_adapter

logger = logging.getLogger(__name__)
ROUTER_PROMPT = (
    "你是一个智能路由判断系统。根据用户输入和历史对话，判断下一步行动。\n"
    "路由规则：\n"
    '1. "direct_reply"：闲聊/问候、自我介绍、主观意见、已有工具结果总结\n'
    '2. "tool_dispatch"：实时/时效性信息、未知外部知识、事实查询、联网验证\n'
    '   此时 selected_tools=["web_search"]\n'
    '3. "end_conversation"：用户明确结束对话\n\n'
    "请只输出 JSON 格式，reason 不超过20字: "
    '{"action": "direct_reply|tool_dispatch|end_conversation", '
    '"reason": "判断理由", "selected_tools": []}'
)


async def router_node(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages", [])
    if not messages:
        return {"next_action": "end_conversation"}
    if state.get("tool_results"):
        return {"next_action": "direct_reply"}
    if state.get("reflection_count", 0) >= Constants.MAX_REFLECTION_ROUNDS:
        return {"next_action": "direct_reply"}
    try:
        limit = get_settings().SHORT_TERM_MAX_MESSAGES
        recent = messages[-limit:] if len(messages) > limit else messages
        router_messages: list[BaseMessage] = [SystemMessage(content=ROUTER_PROMPT)]
        router_messages.extend(recent)
        router_messages.append(HumanMessage(content="请判断下一步行动（JSON 格式）"))
        adapter = get_model_adapter()
        response, _ = await adapter.invoke(state, router_messages)
        raw = response.content
        assert isinstance(raw, str)
        result = json.loads(raw)
        action = result.get("action", "direct_reply")
        selected = result.get("selected_tools", [])
    except (json.JSONDecodeError, Exception):
        logger.warning("Router parse failed, defaulting to direct_reply")
        action = "direct_reply"
        selected = []
    return {"next_action": action, "selected_tools": selected, "reflection_count": state.get("reflection_count", 0)}


async def direct_reply_node(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages", [])
    tool_results = state.get("tool_results", {})
    memory_ctx = state.get("memory_context", {}).get("formatted", "")
    system_content = "你是一个多工具智能助理，请根据上下文友好地回复用户。"
    if memory_ctx:
        system_content = memory_ctx + "\n\n" + system_content
    if tool_results:
        system_content += "\n\n以下是工具返回的结果，请基于这些信息回答："
        for tool_name, result_text in tool_results.items():
            system_content += f"\n--- {tool_name} ---\n{result_text}"
    limit = get_settings().SHORT_TERM_MAX_MESSAGES * 2
    recent = messages[-limit:] if len(messages) > limit else messages
    llm_messages: list[BaseMessage] = [SystemMessage(content=system_content)]
    llm_messages.extend(recent)
    adapter = get_model_adapter()
    response, updated_state = await adapter.invoke(state, llm_messages)
    return {
        "messages": [*messages, response],
        "fallback_flag": updated_state.get("fallback_flag", False),
        "tool_results": {},
    }


def should_continue(state: AgentState) -> str:
    action = state.get("next_action", "direct_reply")
    if action == "end_conversation":
        return "end"
    if action == "tool_dispatch":
        return "tools"
    return "direct_reply"
