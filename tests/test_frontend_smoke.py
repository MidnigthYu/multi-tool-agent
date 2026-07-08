"""前端专项冒烟测试 — 覆盖 agent_runner / session_manager / 核心流程。

运行方式:
    pytest tests/test_frontend_smoke.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontend.agent_runner import _console, _extract_response, run_agent_sync
from frontend.session_manager import SessionManager, SessionState


# ============================================================
# agent_runner 单元测试
# ============================================================
class TestAgentRunner:
    """测试 Agent 同步封装层：导入、补丁、异常兜底、stderr 日志。"""

    def test_nest_asyncio_import(self) -> None:
        """验证 nest_asyncio 可正常导入（间接验证补丁已应用）。"""
        import nest_asyncio

        assert nest_asyncio is not None

    def test_console_writes_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """验证 _console() 写入 sys.stderr。"""
        _console("test message 测试")
        captured = capsys.readouterr()
        assert "test message 测试" in captured.err
        assert "[frontend]" in captured.err

    def test_extract_response_with_ai_message(self) -> None:
        """验证从含 AI 消息的 state 中正确提取回复。"""
        from langchain_core.messages import AIMessage, HumanMessage

        ai_msg = AIMessage(content="你好！有什么可以帮助你的？")
        result = {
            "messages": [HumanMessage(content="你好"), ai_msg],
            "tool_calls": [],
            "tool_results": {},
            "observability": {"node_timings": {"router": 500}},
        }
        extracted = _extract_response(result)
        assert extracted["reply"] == "你好！有什么可以帮助你的？"
        assert extracted["tool_calls"] == []
        assert extracted["tool_results"] == {}
        assert not extracted["error"]

    def test_extract_response_no_ai_message(self) -> None:
        """验证无 AI 消息时返回兜底文本。"""
        from langchain_core.messages import HumanMessage

        result = {
            "messages": [HumanMessage(content="你好")],
            "tool_calls": [],
            "tool_results": {},
            "observability": {},
        }
        extracted = _extract_response(result)
        assert "未返回有效回复" in extracted["reply"]

    def test_run_agent_sync_error_handling(self) -> None:
        """验证 Agent 调用异常时返回 error=True，不抛出堆栈。"""
        with patch("core.agent_graph.get_agent", side_effect=RuntimeError("模拟故障")):
            result = run_agent_sync("test-sid", "测试输入")
            assert result["error"] is True
            assert "模拟故障" in result["reply"]
            assert result["observability"]["errors"]

    def test_run_agent_sync_success(self) -> None:
        """验证正常调用返回结构化结果。"""
        from langchain_core.messages import AIMessage, HumanMessage

        mock_agent = MagicMock()
        ai_msg = AIMessage(content="这是测试回复")
        mock_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [HumanMessage(content="测试"), ai_msg],
                "tool_calls": [],
                "tool_results": {},
                "observability": {},
            }
        )

        with patch("core.agent_graph.get_agent", return_value=mock_agent):
            result = run_agent_sync("test-sid", "测试输入")
            assert not result["error"]
            assert result["reply"] == "这是测试回复"

    def test_run_agent_sync_with_state_overrides(self) -> None:
        """验证 state_overrides 正确注入 AgentState。"""
        from langchain_core.messages import AIMessage, HumanMessage

        mock_agent = MagicMock()
        ai_msg = AIMessage(content="回复")
        captured_state: dict[str, Any] = {}

        async def capture_ainvoke(state: Any, _config: Any) -> dict[str, Any]:
            nonlocal captured_state
            captured_state = dict(state)
            return {
                "messages": [HumanMessage(content="测试"), ai_msg],
                "tool_calls": [],
                "tool_results": {},
                "observability": {},
            }

        mock_agent.ainvoke = capture_ainvoke

        with patch("core.agent_graph.get_agent", return_value=mock_agent):
            run_agent_sync(
                "test-sid",
                "测试",
                state_overrides={"tools_disabled": ["web_search"], "custom_key": 42},
            )
            assert captured_state.get("tools_disabled") == ["web_search"]
            assert captured_state.get("custom_key") == 42


# ============================================================
# session_manager 单元测试
# ============================================================
class TestSessionManager:
    """测试会话管理器：创建、查询、删除、状态隔离。"""

    def test_create_session(self) -> None:
        """验证创建会话返回合法 SessionState。"""
        sm = SessionManager()
        state = sm.create_session("测试会话")
        assert isinstance(state, SessionState)
        assert state.name == "测试会话"
        assert len(state.session_id) == 36
        assert state.tools_disabled == []
        assert state.short_term_max_messages == 5

    def test_get_session_existing(self) -> None:
        """验证按 ID 查询已存在会话。"""
        sm = SessionManager()
        created = sm.create_session()
        found = sm.get_session(created.session_id)
        assert found is not None
        assert found.session_id == created.session_id

    def test_get_session_missing(self) -> None:
        """验证查询不存在会话返回 None。"""
        sm = SessionManager()
        assert sm.get_session("no-such-id") is None

    def test_list_sessions(self) -> None:
        """验证列出全部会话。"""
        sm = SessionManager()
        sm.create_session("A")
        sm.create_session("B")
        sm.create_session("C")
        assert len(sm.list_sessions()) == 3

    def test_remove_session(self) -> None:
        """验证删除会话。"""
        sm = SessionManager()
        state = sm.create_session()
        assert sm.remove_session(state.session_id) is True
        assert sm.get_session(state.session_id) is None

    def test_remove_nonexistent_session(self) -> None:
        """验证删除不存在会话返回 False。"""
        sm = SessionManager()
        assert sm.remove_session("no-such-id") is False

    def test_tools_disabled_default(self) -> None:
        """验证新会话 tools_disabled 默认为空列表。"""
        sm = SessionManager()
        state = sm.create_session()
        assert state.tools_disabled == []

    def test_unique_session_ids(self) -> None:
        """验证连续创建的会话 ID 不重复。"""
        sm = SessionManager()
        ids = {sm.create_session().session_id for _ in range(20)}
        assert len(ids) == 20

    def test_get_cached_agent_returns_singleton(self) -> None:
        """验证 get_cached_agent 返回全局单例 Agent。"""
        agent1 = SessionManager.get_cached_agent()
        agent2 = SessionManager.get_cached_agent()
        assert agent1 is agent2

    def test_get_cached_memory_manager_returns_instance(self) -> None:
        """验证 get_cached_memory_manager 返回有效 MemoryManager 实例。"""
        from memory import MemoryManager

        mm = SessionManager.get_cached_memory_manager()
        assert isinstance(mm, MemoryManager)

    # === Phase 1 T08: new scenario tests ===

    def test_session_concurrent_isolation(self) -> None:
        """Two sessions: independent state, no cross-contamination."""
        sm = SessionManager()
        s1 = sm.create_session("Session A")
        s2 = sm.create_session("Session B")
        assert s1.session_id != s2.session_id
        s1.tools_disabled.append("web_search")
        assert "web_search" in s1.tools_disabled
        assert "web_search" not in s2.tools_disabled
        s2.short_term_max_messages = 10
        assert s2.short_term_max_messages == 10
        assert s1.short_term_max_messages == 5

    def test_session_bulk_create(self) -> None:
        """Bulk create 100 sessions and verify all accessible."""
        sm = SessionManager()
        created = [sm.create_session(f"Bulk-{i}") for i in range(100)]
        assert len(sm.list_sessions()) >= 100
        assert all(sm.get_session(s.session_id) is not None for s in created)

    def test_session_boundary_truncation(self) -> None:
        """Boundary: empty name -> default name; very long name preserved."""
        sm = SessionManager()
        state_empty = sm.create_session("")
        assert state_empty.name.startswith("会话-")
        assert len(state_empty.session_id) == 36
        long_name = "A" * 1000
        state_long = sm.create_session(long_name)
        assert state_long.name == long_name

    def test_session_cleanup_expired(self) -> None:
        """Verify _cleanup_expired exists, callable, returns int >= 0."""
        sm = SessionManager()
        count = sm._cleanup_expired()
        assert isinstance(count, int)
        assert count >= 0


# ============================================================
# Streamlit app 导入冒烟测试
# ============================================================
class TestFrontendAppImport:
    """验证前端包和 app 模块可正常导入。"""

    def test_streamlit_available(self) -> None:
        """验证 streamlit 包可用。"""
        import streamlit

        assert streamlit is not None

    def test_agent_runner_import(self) -> None:
        """验证 agent_runner 模块可导入。"""
        from frontend.agent_runner import run_agent_sync

        assert callable(run_agent_sync)

    def test_session_manager_import(self) -> None:
        """验证 session_manager 模块可导入。"""
        from frontend.session_manager import SessionManager

        assert SessionManager is not None

    def test_app_module_import(self) -> None:
        """验证 app 模块核心函数可导入（不触发 streamlit 运行时）。"""
        # 仅测试非 Streamlit 运行时依赖的部分
        from frontend.app import TOOL_LABELS

        assert "web_search" in TOOL_LABELS
        assert "code_executor" in TOOL_LABELS
