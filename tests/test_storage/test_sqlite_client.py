"""SQLiteClient 单元测试。"""

from __future__ import annotations

import os

import pytest

from storage.sqlite_client import SQLiteClient


class TestSQLiteClient:
    @pytest.fixture
    def client(self) -> SQLiteClient:
        p = "/tmp/test_sessions.db"
        if os.path.exists(p):
            os.unlink(p)
        return SQLiteClient(p)

    def test_create_and_get(self, client: SQLiteClient) -> None:
        client.create_session("s1", "t1")
        assert client.get_session("s1")["session_id"] == "s1"

    def test_get_nonexistent(self, client: SQLiteClient) -> None:
        assert client.get_session("x") is None

    def test_save_and_get(self, client: SQLiteClient) -> None:
        client.create_session("s1", "t1")
        client.save_message("s1", "user", "hello")
        client.save_message("s1", "assistant", "hi")
        assert len(client.get_messages("s1")) == 2

    def test_update_summary(self, client: SQLiteClient) -> None:
        client.create_session("s1", "t1")
        client.update_summary("s1", '{"i":"test"}')
        assert "test" in client.get_session("s1")["summary"]

    def test_isolation(self, client: SQLiteClient) -> None:
        client.create_session("s1", "t1")
        client.create_session("s2", "t2")
        client.save_message("s1", "user", "a")
        client.save_message("s2", "user", "b")
        assert len(client.get_messages("s1")) == 1
        assert len(client.get_messages("s2")) == 1
