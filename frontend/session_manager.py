"""SessionManager — 会话生命周期管理 + 状态隔离。

纯 Python 实现，零 Streamlit 依赖，v0.9.0 FastAPI 服务层可直接复用。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SessionState:
    """单个会话的独立状态，多会话数据互不串流。"""

    session_id: str
    created_at: str
    name: str
    tools_disabled: list[str] = field(default_factory=list)
    short_term_max_messages: int = 5
    model_name: str = ""


class SessionManager:
    """会话管理器：创建、查询、清理会话，维护多会话状态隔离。

    设计要点：
    - 纯 Python 类，无 Streamlit 依赖，后续可直接嵌入 FastAPI
    - Agent / MemoryManager 缓存在 app.py 通过 @st.cache_resource 包装
    - 会话隔离由 Streamlit st.session_state（页面层）+ LangGraph thread_id（业务层）双层保障
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, name: str = "") -> SessionState:
        """创建新会话，返回 SessionState。

        Args:
            name: 会话显示名称，为空则自动生成 "会话-{short_id}"。

        Returns:
            新创建的 SessionState。
        """
        session_id = str(uuid.uuid4())[:8]
        state = SessionState(
            session_id=session_id,
            created_at=datetime.now(UTC).isoformat(),
            name=name or f"会话-{session_id}",
        )
        self._sessions[session_id] = state
        return state

    def get_session(self, session_id: str) -> SessionState | None:
        """按 session_id 查询会话状态。"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[SessionState]:
        """返回全部会话列表（按创建时间排序）。"""
        return sorted(self._sessions.values(), key=lambda s: s.created_at)

    def remove_session(self, session_id: str) -> bool:
        """删除会话及其关联状态。

        Returns:
            True 表示成功删除，False 表示会话不存在。
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    @staticmethod
    def get_cached_agent() -> Any:
        """获取全局单例 Agent（由 app.py 的 @st.cache_resource 包装调用）。

        Returns:
            CompiledStateGraph: LangGraph 编译后的 Agent 图。
        """
        from core.agent_graph import get_agent

        return get_agent()

    @staticmethod
    def get_cached_memory_manager() -> Any:
        """获取全局单例 MemoryManager（由 app.py 的 @st.cache_resource 包装调用）。

        Returns:
            MemoryManager: 三级记忆门面实例。
        """
        from memory import MemoryManager

        return MemoryManager()
