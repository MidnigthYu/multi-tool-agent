"""ToolRegistry 单元测试。"""

from __future__ import annotations

import pytest

from core.tool_registry import ToolRegistry


class TestToolRegistry:
    def test_register(self) -> None:
        r = ToolRegistry()
        r.register("search", "搜索", lambda _x: "ok")
        assert len(r) == 1

    def test_get_func(self) -> None:
        r = ToolRegistry()
        r.register("t", "desc", lambda: "result")
        assert r.get_func("t")() == "result"

    def test_unregister(self) -> None:
        r = ToolRegistry()
        r.register("a", "", lambda: "")
        assert r.unregister("a") is True and r.unregister("x") is False

    def test_list_tools(self) -> None:
        r = ToolRegistry()
        r.register("t1", "d1", lambda: "")
        r.register("t2", "d2", lambda: "")
        assert len(r.list_tools()) == 2

    def test_remove_disabled(self) -> None:
        r = ToolRegistry()
        r.register("a", "", lambda: "")
        r.register("b", "", lambda: "")
        r.register("c", "", lambda: "")
        assert r.remove_disabled(["a", "c"]) == 2 and len(r) == 1

    def test_get_func_nonexistent(self) -> None:
        assert ToolRegistry().get_func("nonexistent") is None

    def test_get_schema_keyerror(self) -> None:
        with pytest.raises(KeyError):
            ToolRegistry().get_schema("nonexistent")

    def test_get_schema_valid(self) -> None:
        r = ToolRegistry()
        r.register("t", "desc", lambda: "")
        assert r.get_schema("t")["function"]["name"] == "t"

    def test_register_overwrite(self) -> None:
        r = ToolRegistry()
        r.register("t", "old", lambda: "old")
        r.register("t", "new", lambda: "new")
        assert r.get_func("t")() == "new"
