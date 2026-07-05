"""周报生成工具 -- Pydantic 入参 + LLM 组装 + 全异常下塋。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from config.prompts import WEEKLY_REPORT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


__all__ = ["WeeklyReportInput", "generate_weekly_report"]


class WeeklyReportInput(BaseModel):
    """Pydantic input schema for the weekly_report generation tool."""

    session_id: str = Field(default="", description="会话唯一标识")
    format: str = Field(default="markdown", description="输出格式: markdown 或 json")
    message_count: int = Field(default=0, description="对话消息总数")
    tool_call_records: list[dict[str, Any]] = Field(default_factory=list, description="工具调用明细")
    session_duration_minutes: float = Field(default=0.0, description="会话时长（分钟）")
    session_summary: str = Field(default="", description="中期记忆摘要")


def _build_stats_fallback(
    tool_stats: dict[str, dict[str, int]],
    message_count: int,
    session_duration_minutes: float,
) -> str:
    """生成纯统计数据的 markdown 降级周报。"""
    lines: list[str] = [
        "# 周报（统计降级）",
        "",
        f"- 消息总数: {message_count}",
        f"- 会话时长: {session_duration_minutes:.1f}分钟",
        "",
        "## 工具使用统计",
        "| 工具 | 调用次数 | 成功 | 失败 |",
        "|------|---------|------|------|",
    ]
    if tool_stats:
        for name, st in tool_stats.items():
            lines.append(f"| {name} | {st['total']} | {st['success']} | {st['failed']} |")
    else:
        lines.append("| (无工具调用) | 0 | 0 | 0 |")
    return "\n".join(lines)


async def generate_weekly_report(
    session_id: str = "",
    format: str = "markdown",
    message_count: int = 0,
    tool_call_records: list[dict[str, Any]] | None = None,
    session_duration_minutes: float = 0.0,
    session_summary: str = "",
) -> str:
    """生成结构化周报，ToolRegistry 兼容异步函数。

    内部处理流程：
    1. 空会话拦截 → 不触发 LLM
    2. 工具统计二次计算
    3. 超长内容截断（3000 字符限额）
    4. LLM 调用生成周报
    5. 格式兖底：JSON 解析失败降级为 markdown
    6. 全异常捕获，始终返回字符串

    Args:
        session_id: 会话唯一标识。
        format: 输出格式（markdown/json）。
        message_count: 对话消息总数。
        tool_call_records: 工具调用明细列表。
        session_duration_minutes: 会话时长（分钟）。
        session_summary: 中期记忆摘要。

    Returns:
        格式化的周报字符串，或降级提示。
    """
    t_start = time.monotonic()
    fmt = format if format in ("markdown", "json") else "markdown"
    if message_count <= 0:
        return "[周报降级] 当前会话暂无消息，请先与助手进行一些对话后再生成周报。"
    records = tool_call_records or []
    tool_stats: dict[str, dict[str, int]] = {}
    for rec in records:
        name = rec.get("tool", "unknown")
        if name not in tool_stats:
            tool_stats[name] = {"total": 0, "success": 0, "failed": 0}
        tool_stats[name]["total"] += 1
        status = rec.get("status", "")
        if status == "success":
            tool_stats[name]["success"] += 1
        elif status == "failed":
            tool_stats[name]["failed"] += 1
    context_parts: list[str] = []
    if session_summary:
        context_parts.append(f"会话摘要:\n{session_summary}")
    records_str = json.dumps(records, ensure_ascii=False) if records else "无工具调用记录"
    context_parts.append(f"工具调用记录:\n{records_str}")
    context = "\n\n".join(context_parts)
    max_context = 3000
    if len(context) > max_context:
        truncated_records = records[:10] if records else []
        context = session_summary + "\n\n工具调用记录(截断):\n" + json.dumps(truncated_records, ensure_ascii=False)
        if len(context) > max_context:
            context = context[:max_context] + "\n... [内容截断]"
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

    system_prompt = WEEKLY_REPORT_SYSTEM_PROMPT.replace("{format}", fmt)
    user_msg_text = (
        f"请根据以下会话数据生成周报。\n"
        f"消息总数: {message_count}\n"
        f"会话时长: {session_duration_minutes:.1f}分钟\n\n"
        f"{context}"
    )
    try:
        from core.agent_state import create_initial_state
        from core.model_adapter import get_model_adapter

        adapter = get_model_adapter()
        dummy = create_initial_state(session_id or "weekly", "")
        llm_messages: list[BaseMessage] = [SystemMessage(content=system_prompt), HumanMessage(content=user_msg_text)]
        response, _ = await adapter.invoke(dummy, llm_messages, temperature=0.5)
        raw = response.content if hasattr(response, "content") else str(response)
        raw = raw if isinstance(raw, str) else str(raw)
        result = raw.strip()
        if fmt == "json":
            try:
                json.loads(result)
            except json.JSONDecodeError:
                logger.warning("[weekly_report] JSON parse failed, fallback to markdown")
                fmt = "markdown"
        elapsed = int((time.monotonic() - t_start) * 1000)
        logger.info("[weekly_report] Success | session=%s | format=%s | elapsed=%dms", session_id, fmt, elapsed)
        return result
    except Exception as e:
        elapsed = int((time.monotonic() - t_start) * 1000)
        logger.error("[weekly_report] LLM failed | session=%s | exc=%s | elapsed=%dms", session_id, e, elapsed)
        return _build_stats_fallback(tool_stats, message_count, session_duration_minutes)
