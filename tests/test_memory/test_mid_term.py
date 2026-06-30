"""MidTermMemory 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from memory.mid_term import MidTermMemory
from storage.sqlite_client import SQLiteClient


class TestMidTermMemory:
    @pytest.fixture
    def memory(self) -> MidTermMemory:
        ms = MagicMock(spec=SQLiteClient)
        ma = MagicMock()

        async def invoke(state, _msgs=None, **_kw):
            from langchain_core.messages import AIMessage

            return AIMessage(content='{"intent":"t","conclusion":"ok","todos":[],"preferences":[]}'), state

        ma.invoke = invoke
        return MidTermMemory(ms, ma)

    def test_add_turn(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = None
        memory.add_turn("s1", "hi", "hello")
        memory._sqlite.save_message.assert_called()

    def test_summary_none(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": ""}
        assert memory.get_summary("s1") is None

    def test_summary_valid(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": '{"intent":"test"}'}
        assert memory.get_summary("s1")["intent"] == "test"

    def test_session_range(self, memory: MidTermMemory) -> None:
        conn = MagicMock()
        mock_row = {"session_id": "s1", "summary": "{}", "created_at": "2024-01-01", "updated_at": ""}
        conn.execute.return_value.fetchall.return_value = [mock_row]
        memory._sqlite.conn = conn
        assert len(memory.get_sessions_in_range("2024-01-01", "2024-01-02")) == 1

    def test_summary_degraded(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": "bad json"}
        assert memory.get_summary("s1") is not None
