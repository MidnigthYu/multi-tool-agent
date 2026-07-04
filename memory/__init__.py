"""三级分层记忆 -- MemoryManager 门面层（惰性初始化）。"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage

from memory.long_term import LongTermMemory
from memory.mid_term import MidTermMemory
from memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """三级记忆门面层，内部惰性初始化短/中/长期记忆实例。"""

    def __init__(self) -> None:
        self._short: ShortTermMemory | None = None
        self._mid: MidTermMemory | None = None
        self._long: LongTermMemory | None = None

    def _get_short(self) -> ShortTermMemory:
        if self._short is None:
            from memory.short_term import get_short_term_memory

            self._short = get_short_term_memory()
        return self._short

    def _get_mid(self) -> MidTermMemory:
        if self._mid is None:
            from storage.sqlite_client import get_sqlite_client

            self._mid = MidTermMemory(get_sqlite_client())
        return self._mid

    def _get_long(self) -> LongTermMemory:
        if self._long is None:
            from storage.chroma_client import get_chroma_client

            self._long = LongTermMemory(get_chroma_client())
        return self._long

    def update(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """更新短期和中期记忆，不自动写入长期记忆。"""
        try:
            self._get_short().add_message(session_id, AIMessage(content=str(assistant_msg)))
        except Exception as e:
            logger.warning("Short-term add failed: %s", e)
        try:
            self._get_mid().add_turn(session_id, user_msg, assistant_msg)
        except Exception as e:
            logger.warning("Mid-term add failed: %s", e)

    def build_context(self, session_id: str, current_query: str, max_tokens: int = 800) -> str:
        """构建三层记忆上下文，用于注入 LLM SystemMessage。"""
        parts: list[str] = []
        remaining = max_tokens

        # Layer 1: mid-term summary
        try:
            summary = self._get_mid().get_summary(session_id)
            if summary:
                text = f"[Session Summary] {summary}"
                if len(text) <= remaining:
                    parts.append(text)
                    remaining -= len(text)
        except Exception as e:
            logger.warning("Mid-term context failed: %s", e)

        # Layer 2: long-term recall
        if remaining > 0:
            try:
                long_results = self._get_long().recall_relevant(session_id + " " + current_query)
                if long_results:
                    facts = "; ".join(r.get("document", "") for r in long_results if r.get("document"))
                    if facts:
                        text = f"[Memory] {facts}"
                        if len(text) <= remaining:
                            parts.append(text)
                            remaining -= len(text)
                        else:
                            parts.append(text[:remaining])
                            remaining = 0
            except Exception as e:
                logger.warning("Long-term context failed: %s", e)

        # Layer 3: short-term context (recent messages)
        if remaining > 0:
            try:
                recent = self._get_short().get_context(session_id)
                if recent:
                    lines = [m.content if hasattr(m, "content") else str(m) for m in recent[-3:]]
                    text = "[Recent] " + " | ".join(str(x) for x in lines)
                    if len(text) <= remaining:
                        parts.append(text)
                    else:
                        parts.append(text[:remaining])
            except Exception as e:
                logger.warning("Short-term context failed: %s", e)

        return "\n".join(parts)

    def clear_session(self, session_id: str) -> None:
        """同步清除三层记忆。"""
        with __import__("contextlib").suppress(Exception):
            self._get_short().clear(session_id)
        with __import__("contextlib").suppress(Exception):
            self._get_long().delete_session_facts(session_id)


__all__ = ["ShortTermMemory", "MidTermMemory", "LongTermMemory", "MemoryManager"]
