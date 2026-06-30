"""L1 短期会话内存 -- 内存 dict 存储，按 SHORT_TERM_MAX_MESSAGES 截断。"""

from __future__ import annotations

import threading

from langchain_core.messages import BaseMessage

from config.settings import get_settings


class ShortTermMemory:
    """短期会话内存，按 session_id 分区存储消息。"""

    def __init__(self) -> None:
        self._store: dict[str, list[BaseMessage]] = {}
        self._lock = threading.RLock()

    def add_message(self, session_id: str, message: BaseMessage) -> None:
        """追加消息，超限时截断早期消息。"""
        max_messages = get_settings().SHORT_TERM_MAX_MESSAGES
        with self._lock:
            if session_id not in self._store:
                self._store[session_id] = []
            self._store[session_id].append(message)
            if len(self._store[session_id]) > max_messages:
                self._store[session_id] = self._store[session_id][-max_messages:]

    def get_context(self, session_id: str) -> list[BaseMessage]:
        """返回当前消息列表副本。"""
        with self._lock:
            return list(self._store.get(session_id, []))

    def get_message_count(self, session_id: str) -> int:
        """返回当前 session 的消息数量。"""
        with self._lock:
            return len(self._store.get(session_id, []))

    def clear(self, session_id: str) -> None:
        """清空指定 session 的短期内存。"""
        with self._lock:
            self._store.pop(session_id, None)

    def cleanup_expired(self, max_age_seconds: int = 86400) -> None:
        """清理超过 max_age_seconds 未活动的 session（预留）。"""
        _ = max_age_seconds
        pass


_short_term_instance: ShortTermMemory | None = None


def get_short_term_memory() -> ShortTermMemory:
    global _short_term_instance
    if _short_term_instance is None:
        _short_term_instance = ShortTermMemory()
    return _short_term_instance
