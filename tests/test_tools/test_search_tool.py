"""Tavily 搜索工具 -- 17 用例。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.search_tool import _retry_with_backoff, _truncate_result, web_search


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_normal_query(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T1", "content": "C1", "url": "http://x.com"}]}
            r = await web_search("test")
            assert r["status"] == "success" and len(r["results"]) == 1

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": []}
            r = await web_search("")
            assert r["status"] == "success" and r["results"] == []

    @pytest.mark.asyncio
    async def test_timeout_retry(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.side_effect = TimeoutError("timeout")
            r = await web_search("test")
            assert r["status"] == "failed"

    @pytest.mark.asyncio
    async def test_missing_api_key(self) -> None:
        with patch("tools.search_tool.get_settings") as gs:
            s = MagicMock()
            s.TAVILY_API_KEY = "your-api-key-here"
            gs.return_value = s
            r = await web_search("test")
            assert r["status"] == "failed" and "API" in r["formatted"]

    @pytest.mark.asyncio
    async def test_truncation(self) -> None:
        t = _truncate_result("A" * 5000, 100)
        assert len(t) < 5000 and "..." in t

    @pytest.mark.asyncio
    async def test_no_truncation(self) -> None:
        assert _truncate_result("Hello", 100) == "Hello"

    @pytest.mark.asyncio
    async def test_max_results(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": f"T{i}", "content": "x", "url": "U"} for i in range(20)]}
            r = await web_search("test", max_results=3)
            assert len(r["results"]) == 3

    @pytest.mark.asyncio
    async def test_formatted_contains_query(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "U"}]}
            r = await web_search("hello world")
            assert "hello world" in r["formatted"]

    @pytest.mark.asyncio
    async def test_formatted_numbered(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {
                "results": [{"title": "A", "content": "B", "url": "C"}, {"title": "D", "content": "E", "url": "F"}]
            }
            r = await web_search("test")
            assert "1." in r["formatted"] and "2." in r["formatted"]

    @pytest.mark.asyncio
    async def test_has_status_field(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": []}
            r = await web_search("x")
            assert "status" in r and "query" in r and "results" in r and "formatted" in r

    @pytest.mark.asyncio
    async def test_search_depth(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search = AsyncMock(return_value={"results": []})
            await web_search("test", search_depth="basic")
            assert inst.search.call_args.kwargs.get("search_depth") == "basic"

    @pytest.mark.asyncio
    async def test_retry_then_success(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc, patch("tools.search_tool.logger") as _lg:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.side_effect = [TimeoutError("fail"), {"results": [{"title": "T", "content": "C", "url": "U"}]}]
            r = await web_search("test", max_results=1)
            assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_snippet_fallback(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "", "url": "U"}]}
            r = await web_search("test")
            assert r["results"][0]["snippet"] == ""

    @pytest.mark.asyncio
    async def test_special_chars(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "U"}]}
            r = await web_search("test + query #1")
            assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_formatted_has_url(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "http://example.com"}]}
            r = await web_search("test")
            assert "http://example.com" in r["formatted"]

    @pytest.mark.asyncio
    async def test_empty_api_key(self) -> None:
        with patch("tools.search_tool.get_settings") as gs:
            s = MagicMock()
            s.TAVILY_API_KEY = ""
            gs.return_value = s
            r = await web_search("test")
            assert r["status"] == "failed"

    @pytest.mark.asyncio
    async def test_default_max_results(self) -> None:
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": f"T{i}", "content": "x", "url": "U"} for i in range(10)]}
            r = await web_search("test")
            assert len(r["results"]) <= 5


class TestRetryWithBackoff:
    """覆盖 _retry_with_backoff 指数退避重试函数 (lines 25-36)。"""

    def test_success_first_attempt(self) -> None:
        """覆盖 retry 首次成功路径 (line 28)。"""
        calls = []
        result = _retry_with_backoff(lambda: calls.append(1) or "ok")
        assert result == "ok" and calls == [1]

    def test_retry_then_success(self) -> None:
        """覆盖 retry 失败后重试成功 (lines 31-34)。"""
        with patch("tools.search_tool.time.sleep") as mock_sleep:
            count = [0]

            def flaky() -> str:
                count[0] += 1
                if count[0] < 3:
                    raise TimeoutError("fail")
                return "recovered"

            result = _retry_with_backoff(flaky, max_retries=2, base_delay=0.1)
            assert result == "recovered"
            assert mock_sleep.call_count == 2

    def test_all_retries_fail(self) -> None:
        """覆盖 retry 全部失败抛出最后异常 (lines 35-36)。"""
        with patch("tools.search_tool.time.sleep"), pytest.raises(ValueError, match="always fail"):
            _retry_with_backoff(lambda: (_ for _ in ()).throw(ValueError("always fail")), max_retries=2)
