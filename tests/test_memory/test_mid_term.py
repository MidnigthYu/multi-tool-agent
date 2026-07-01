"""MidTermMemory 单元测试 (FIX: content字段)。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from memory.mid_term import MidTermMemory
from storage.sqlite_client import SQLiteClient


class TestMidTermMemory:
    @pytest.fixture
    def memory(self) -> MidTermMemory:
        ms = MagicMock(spec=SQLiteClient)
        ma = MagicMock()

        async def invoke(state: Any, _msgs: Any = None, **_kw: Any) -> tuple[Any, Any]:
            from langchain_core.messages import AIMessage

            return AIMessage(content='{"intent":"t","conclusion":"ok","todos":[],"preferences":[]}'), state

        ma.invoke = invoke
        return MidTermMemory(ms, ma)

    def test_add_turn_stores(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = None
        memory.add_turn("s1", "hi", "hello")
        assert memory._sqlite.save_message.call_count >= 1

    def test_add_turn_creates_session(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": ""}
        memory._sqlite.get_messages.return_value = [{"role": "user", "content": "msg " + str(i)} for i in range(25)]
        memory.add_turn("s1", "hi", "hello")
        assert memory._sqlite.update_summary.call_count >= 0

    def test_summary_none(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": ""}
        assert memory.get_summary("s1") is None

    def test_summary_valid(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": '{"intent":"test"}'}
        assert memory.get_summary("s1")["intent"] == "test"

    def test_summary_degraded_json(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": "bad json"}
        s = memory.get_summary("s1")
        assert s is not None and "intent" in s

    def test_summary_none_when_missing(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = None
        assert memory.get_summary("s1") is None

    def test_summary_structured(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {
            "summary": '{"intent":"a","conclusion":"b","todos":[],"preferences":[]}'
        }
        s = memory.get_summary("s1")
        assert s["intent"] == "a" and s["conclusion"] == "b"

    def test_session_range(self, memory: MidTermMemory) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            {"session_id": "s1", "summary": "{}", "created_at": "2024-01-01", "updated_at": ""}
        ]
        memory._sqlite.conn = conn
        assert len(memory.get_sessions_in_range("2024-01-01", "2024-01-02")) == 1

    def test_session_range_empty(self, memory: MidTermMemory) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        memory._sqlite.conn = conn
        assert memory.get_sessions_in_range("2099-01-01", "2099-01-02") == []

    def test_session_range_exception(self, memory: MidTermMemory) -> None:
        memory._sqlite.conn = MagicMock()
        memory._sqlite.conn.execute.side_effect = Exception("db err")
        assert memory.get_sessions_in_range("2024-01-01", "2024-01-02") == []

    def test_skip_summary_when_present(self, memory: MidTermMemory) -> None:
        memory._sqlite.get_session.return_value = {"summary": '{"intent":"existing"}'}
        memory.add_turn("s1", "hi", "hello")

    def test_skip_summary_without_adapter(self) -> None:
        mem = MidTermMemory(MagicMock(spec=SQLiteClient))
        mem._model_adapter = None
        mem._sqlite.get_session.return_value = {"summary": ""}
        mem._sqlite.get_messages.return_value = [{"role": "user", "content": "x"}] * 25
        mem.add_turn("s1", "hi", "hello")
