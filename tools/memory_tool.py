"""记忆工具 -- remember_this 主动写入长期记忆。"""

from __future__ import annotations

import logging

from memory.long_term import LongTermMemory
from storage.chroma_client import get_chroma_client

logger = logging.getLogger(__name__)


def remember_this(fact: str) -> str:
    """将重要事实写入长期记忆，供后续跨会话召回。
    ToolRegistry 兼容工具函数（同步）。
    """
    try:
        chroma = get_chroma_client()
        memory = LongTermMemory(chroma)
        memory.store_fact("tool", fact)
        logger.info("[remember_this] Fact stored: %.60s", fact)
        return f"记忆已保存: {fact[:100]}"
    except Exception as e:
        logger.error("[remember_this] Failed: %s", e)
        return "记忆保存失败，请稍后重试"
