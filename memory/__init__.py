"""三级分层记忆 -- MemoryManager 统一接口。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from memory.long_term import LongTermMemory
from memory.mid_term import MidTermMemory
from memory.short_term import ShortTermMemory

if TYPE_CHECKING:
    from core.agent_state import AgentState
logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, short_term: ShortTermMemory, mid_term: MidTermMemory, long_term: LongTermMemory) -> None:
        self._short = short_term
        self._mid = mid_term
        self._long = long_term

    def update(self, state: AgentState) -> AgentState:
        messages = state.get("messages", [])
        sid = state.get("session_id", "default")
        if len(messages) >= 2:
            last = messages[-1]
            u = messages[-2].content if hasattr(messages[-2], "content") else str(messages[-2])
            a = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
            assert isinstance(u, str)
            assert isinstance(a, str)
            user_msg: str = u
            assistant_msg: str = a
            if hasattr(last, "content"):
                self._short.add_message(sid, last)
            self._mid.add_turn(sid, user_msg, assistant_msg)
        return state


__all__ = ["ShortTermMemory", "MidTermMemory", "LongTermMemory", "MemoryManager"]
