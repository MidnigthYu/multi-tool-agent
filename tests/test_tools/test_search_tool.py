"""Tavily 搜索工具 -- 全套边界单元测试（覆盖正常、异常、重试、降级、截断）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from tools.search_tool import (
    SearchInput,
    _classify_search_error,
    _retry_with_backoff,
    _truncate_result,
    search_tool,
    web_search,
)


class TestWebSearch:
    """web_search 异步搜索内核测试。"""

    @pytest.mark.asyncio
    async def test_normal_query(self) -> None:
        """正常搜索查询返回 success 状态和结果。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T1", "content": "C1", "url": "http://x.com"}]}
            r = await web_search("test")
            assert r["status"] == "success" and len(r["results"]) == 1

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        """空关键词仍正常返回 success（Tavily 处理空查询）。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": []}
            r = await web_search("")
            assert r["status"] == "success" and r["results"] == []

    @pytest.mark.asyncio
    async def test_timeout_retry(self) -> None:
        """接口超时重试耗尽后返回 failed 降级状态。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.side_effect = TimeoutError("timeout")
            r = await web_search("test")
            assert r["status"] == "failed"

    @pytest.mark.asyncio
    async def test_network_disconnect(self) -> None:
        """网络断开场景：连接拒绝异常被捕获，优雅降级返回。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.side_effect = ConnectionRefusedError("Connection refused")
            r = await web_search("test")
            assert r["status"] == "failed"
            assert "降级" in r["formatted"] or "搜索" in r["formatted"]

    @pytest.mark.asyncio
    async def test_rate_limit(self) -> None:
        """接口限流异常被捕获，优雅降级返回。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.side_effect = Exception("429 Too Many Requests: rate limit exceeded")
            r = await web_search("test")
            assert r["status"] == "failed"
            assert "降级" in r["formatted"] or "搜索" in r["formatted"]

    @pytest.mark.asyncio
    async def test_missing_api_key_your_prefix(self) -> None:
        """密钥为 'your-...' 占位符时降级返回。"""
        with patch("tools.search_tool.get_settings") as gs:
            s = MagicMock()
            s.TAVILY_API_KEY = "your-api-key-here"
            gs.return_value = s
            r = await web_search("test")
            assert r["status"] == "failed" and "API" in r["formatted"]

    @pytest.mark.asyncio
    async def test_empty_api_key(self) -> None:
        """密钥为空字符串时降级返回。"""
        with patch("tools.search_tool.get_settings") as gs:
            s = MagicMock()
            s.TAVILY_API_KEY = ""
            gs.return_value = s
            r = await web_search("test")
            assert r["status"] == "failed"

    @pytest.mark.asyncio
    async def test_test_prefix_key(self) -> None:
        """密钥为 'test-...' 前缀时降级返回。"""
        with patch("tools.search_tool.get_settings") as gs:
            s = MagicMock()
            s.TAVILY_API_KEY = "test-fake-key-12345"
            gs.return_value = s
            r = await web_search("test")
            assert r["status"] == "failed"

    @pytest.mark.asyncio
    async def test_truncation(self) -> None:
        """超长文本被截断并包含省略标记。"""
        t = _truncate_result("A" * 5000, 100)
        assert len(t) < 5000 and "..." in t

    @pytest.mark.asyncio
    async def test_no_truncation(self) -> None:
        """短文本不触发截断。"""
        assert _truncate_result("Hello", 100) == "Hello"

    @pytest.mark.asyncio
    async def test_max_results(self) -> None:
        """max_results 参数限制返回条数生效。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": f"T{i}", "content": "x", "url": "U"} for i in range(20)]}
            r = await web_search("test", max_results=3)
            assert len(r["results"]) == 3

    @pytest.mark.asyncio
    async def test_formatted_contains_query(self) -> None:
        """格式化结果包含原始查询词。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "U"}]}
            r = await web_search("hello world")
            assert "hello world" in r["formatted"]

    @pytest.mark.asyncio
    async def test_formatted_numbered(self) -> None:
        """格式化结果包含序号标记。"""
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
        """返回结果包含所有必要字段。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": []}
            r = await web_search("x")
            assert "status" in r and "query" in r and "results" in r and "formatted" in r
            assert "retry_count" in r and "elapsed_ms" in r

    @pytest.mark.asyncio
    async def test_search_depth(self) -> None:
        """search_depth 参数正确传递给 Tavily 客户端。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search = AsyncMock(return_value={"results": []})
            await web_search("test", search_depth="basic")
            assert inst.search.call_args.kwargs.get("search_depth") == "basic"

    @pytest.mark.asyncio
    async def test_retry_then_success(self) -> None:
        """首次失败后重试成功，最终返回 success。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc, patch("tools.search_tool.logger") as _lg:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.side_effect = [TimeoutError("fail"), {"results": [{"title": "T", "content": "C", "url": "U"}]}]
            r = await web_search("test", max_results=1)
            assert r["status"] == "success"
            assert r.get("retry_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_snippet_fallback(self) -> None:
        """content 为空时 snippet 作为回退字段。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "", "url": "U"}]}
            r = await web_search("test")
            assert r["results"][0]["snippet"] == ""

    @pytest.mark.asyncio
    async def test_special_chars(self) -> None:
        """特殊字符查询正常返回 success。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "U"}]}
            r = await web_search("test + query #1")
            assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_formatted_has_url(self) -> None:
        """格式化结果包含结果 URL。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "http://example.com"}]}
            r = await web_search("test")
            assert "http://example.com" in r["formatted"]

    @pytest.mark.asyncio
    async def test_default_max_results(self) -> None:
        """不使用 max_results 参数时默认返回 ≤5 条。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": f"T{i}", "content": "x", "url": "U"} for i in range(10)]}
            r = await web_search("test")
            assert len(r["results"]) <= 5

    @pytest.mark.asyncio
    async def test_elapsed_ms_field(self) -> None:
        """返回结果包含耗时统计字段。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "U"}]}
            r = await web_search("test")
            assert isinstance(r.get("elapsed_ms"), int) and r["elapsed_ms"] >= 0

    @pytest.mark.asyncio
    async def test_retry_count_on_success(self) -> None:
        """首次成功时 retry_count 为 0。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "U"}]}
            r = await web_search("test")
            assert r.get("retry_count") == 0


class TestSearchTool:
    """ToolRegistry 兼容封装 search_tool 测试。"""

    @pytest.mark.asyncio
    async def test_returns_string(self) -> None:
        """search_tool 返回 str 类型（符合 ToolRegistry 签名规范）。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": "T", "content": "C", "url": "http://x.com"}]}
            result = await search_tool("test query")
            assert isinstance(result, str)
            assert "test query" in result

    @pytest.mark.asyncio
    async def test_returns_degraded_on_failure(self) -> None:
        """搜索失败时返回降级提示字符串（不抛异常）。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.side_effect = TimeoutError("timeout")
            result = await search_tool("test")
            assert isinstance(result, str)
            assert "降级" in result

    @pytest.mark.asyncio
    async def test_passes_max_results(self) -> None:
        """max_results 参数正确传递至 web_search。"""
        with patch("tools.search_tool.AsyncTavilyClient") as mc:
            inst = AsyncMock()
            mc.return_value = inst
            inst.search.return_value = {"results": [{"title": f"T{i}", "content": "x", "url": "U"} for i in range(10)]}
            result = await search_tool("test", max_results=3)
            assert "1." in result and "2." in result and "3." in result


class TestSearchInput:
    """Pydantic SearchInput Schema 测试。"""

    def test_valid_input(self) -> None:
        """合法输入通过校验。"""
        si = SearchInput(query="test query", max_results=5, search_depth="advanced")
        assert si.query == "test query"
        assert si.max_results == 5
        assert si.search_depth == "advanced"

    def test_default_values(self) -> None:
        """默认值正确：max_results=5, search_depth='advanced'。"""
        si = SearchInput(query="hello")
        assert si.max_results == 5
        assert si.search_depth == "advanced"

    def test_empty_query_rejected(self) -> None:
        """空查询被 pydantic 校验拒绝（min_length=1）。"""
        with pytest.raises(ValidationError):
            SearchInput(query="")

    def test_min_results(self) -> None:
        """max_results 最小值 1 通过校验。"""
        si = SearchInput(query="test", max_results=1)
        assert si.max_results == 1

    def test_max_results_cap(self) -> None:
        """max_results 最大值 10 通过校验。"""
        si = SearchInput(query="test", max_results=10)
        assert si.max_results == 10

    def test_max_results_exceeded_rejected(self) -> None:
        """max_results 超过 10 被 pydantic 校验拒绝。"""
        with pytest.raises(ValidationError):
            SearchInput(query="test", max_results=11)


class TestClassifySearchError:
    """异常类型分类函数测试。"""

    def test_classify_timeout(self) -> None:
        assert _classify_search_error(TimeoutError("Connection timed out")) == "timeout"

    def test_classify_network_refused(self) -> None:
        assert _classify_search_error(ConnectionRefusedError("Connection refused")) == "network"

    def test_classify_rate_limit_429(self) -> None:
        assert _classify_search_error(Exception("429 Too Many Requests")) == "rate_limit"

    def test_classify_rate_limit_text(self) -> None:
        assert _classify_search_error(Exception("rate limit exceeded")) == "rate_limit"

    def test_classify_auth_401(self) -> None:
        assert _classify_search_error(Exception("401 Unauthorized")) == "auth"

    def test_classify_auth_key_invalid(self) -> None:
        assert _classify_search_error(Exception("Invalid API key")) == "auth"

    def test_classify_unknown(self) -> None:
        assert _classify_search_error(Exception("something weird happened")) == "unknown"


class TestRetryWithBackoff:
    """覆盖 _retry_with_backoff 指数退避重试函数。"""

    def test_success_first_attempt(self) -> None:
        """首次调用成功，不触发重试。"""
        calls = []
        result = _retry_with_backoff(lambda: calls.append(1) or "ok")
        assert result == "ok" and calls == [1]

    def test_retry_then_success(self) -> None:
        """失败后重试成功，验证 sleep 次数。"""
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
        """全部重试失败后抛出最终异常。"""
        with patch("tools.search_tool.time.sleep"), pytest.raises(ValueError, match="always fail"):
            _retry_with_backoff(lambda: (_ for _ in ()).throw(ValueError("always fail")), max_retries=2)
