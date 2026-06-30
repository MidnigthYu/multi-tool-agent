"""ShortTermMemory 单元测试。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from config.settings import get_settings
from memory.short_term import ShortTermMemory


class TestShortTermMemory:
    def test_add_and_get(self) -> None:
        m = ShortTermMemory()
        m.add_message("s1", HumanMessage(content="hi"))
        ctx = m.get_context("s1")
        assert len(ctx) == 1

    def test_truncation(self) -> None:
        m = ShortTermMemory()
        limit = get_settings().SHORT_TERM_MAX_MESSAGES
        for i in range(limit + 3):
            m.add_message("s1", HumanMessage(content=str(i)))
        ctx = m.get_context("s1")
        assert len(ctx) == limit

    def test_session_isolation(self) -> None:
        m = ShortTermMemory()
        m.add_message("s1", HumanMessage(content="a"))
        m.add_message("s2", HumanMessage(content="b"))
        assert len(m.get_context("s1")) == 1
        assert len(m.get_context("s2")) == 1

    def test_clear(self) -> None:
        m = ShortTermMemory()
        m.add_message("s1", HumanMessage(content="x"))
        m.clear("s1")
        assert m.get_context("s1") == []

    def test_empty_session(self) -> None:
        m = ShortTermMemory()
        assert m.get_context("nonexistent") == []

    def test_message_count(self) -> None:
        m = ShortTermMemory()
        assert m.get_message_count("s1") == 0
        m.add_message("s1", HumanMessage(content="x"))
        assert m.get_message_count("s1") == 1

    def test_cleanup_expired(self) -> None:
        m = ShortTermMemory()
        m.add_message("s1", HumanMessage(content="x"))
        m.cleanup_expired(0)
        assert m.get_context("s1")[0].content == "x"
