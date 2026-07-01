"""Tavily 联网搜索工具 -- 指数退避重试 + 结果截断 + 异常隔离 + 结构化日志。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, Field
from tavily import AsyncTavilyClient

from config.settings import get_settings

logger = logging.getLogger(__name__)


class SearchInput(BaseModel):
    """搜索工具入参 Pydantic Schema，适配 ToolRegistry 注册规范。"""

    query: str = Field(..., description="搜索查询词", min_length=1)
    max_results: int = Field(default=5, description="最大返回结果数", ge=1, le=10)
    search_depth: str = Field(default="advanced", description="搜索深度: basic 或 advanced")


def _truncate_result(raw_text: str, max_chars: int = 4000) -> str:
    """智能截断超长网页摘要，保留首尾关键内容，防止 LLM 上下文溢出。"""
    if len(raw_text) <= max_chars:
        return raw_text
    half = max_chars // 2
    return raw_text[:half] + f"\n\n... [{len(raw_text)} 字符截断] ...\n\n" + raw_text[-half:]


def _classify_search_error(exc: Exception) -> str:
    """分类搜索异常类型，用于结构化日志埋点。

    Returns:
        异常类型标签: timeout / network / rate_limit / auth / unknown
    """
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg or "connect timeout" in msg:
        return "timeout"
    if "connection" in msg or "network" in msg or "refused" in msg or "unreachable" in msg:
        return "network"
    if "rate" in msg or "limit" in msg or "429" in msg or "too many" in msg:
        return "rate_limit"
    if "auth" in msg or "key" in msg or "unauthorized" in msg or "401" in msg or "403" in msg:
        return "auth"
    return "unknown"


async def web_search(query: str, max_results: int = 5, search_depth: str = "advanced") -> dict[str, Any]:
    """异步搜索内核：全异步 async/await + 指数退避重试 + 异常全场景覆盖。

    Args:
        query: 搜索查询词。
        max_results: 最大返回结果数（上限 10）。
        search_depth: Tavily 搜索深度，basic 或 advanced。

    Returns:
        {"status": "success"|"failed", "query": str, "results": list[dict],
         "formatted": str, "retry_count": int, "elapsed_ms": int}
    """
    t_start = time.monotonic()
    settings = get_settings()
    api_key = settings.TAVILY_API_KEY

    # --- 密钥校验 ---
    if not api_key or api_key.startswith("your-") or api_key.startswith("test-"):
        logger.warning(
            "[search_tool] TAVILY_API_KEY not configured | query=%s",
            query[:100] if query else "<empty>",
        )
        return {
            "status": "failed",
            "query": query,
            "results": [],
            "formatted": "[搜索降级] 搜索服务未配置，请设置 TAVILY_API_KEY。我将基于已有知识回答您的问题。",
            "retry_count": 0,
            "elapsed_ms": int((time.monotonic() - t_start) * 1000),
        }

    max_r = max_results or settings.SEARCH_RESULT_MAX_LENGTH
    max_chars = settings.SEARCH_RESULT_MAX_LENGTH * 2
    retry_count = 0
    last_exc: Exception | None = None

    try:
        client = AsyncTavilyClient(api_key=api_key)
        for attempt in range(settings.SEARCH_RETRY_MAX + 1):
            try:
                data = await client.search(
                    query=query,
                    max_results=min(max_r, 10),
                    search_depth=search_depth,
                )
                break
            except Exception as e:
                last_exc = e
                retry_count = attempt + 1
                err_type = _classify_search_error(e)
                if attempt < settings.SEARCH_RETRY_MAX:
                    delay = settings.SEARCH_RETRY_BASE_DELAY_S * (2**attempt)
                    logger.warning(
                        "[search_tool] Retry %d/%d after %.1fs | query=%s | err_type=%s | exc=%s",
                        attempt + 1,
                        settings.SEARCH_RETRY_MAX,
                        delay,
                        query[:100] if query else "<empty>",
                        err_type,
                        e,
                    )
                    await asyncio.sleep(delay)
        else:
            assert last_exc is not None
            raise last_exc

        # --- 成功路径：解析并格式化结果 ---
        raw_results = data.get("results", [])
        results: list[dict[str, Any]] = []
        for r in raw_results[:max_results]:
            snippet = _truncate_result(r.get("content", "") or r.get("snippet", ""), max_chars)
            results.append({"title": r.get("title", ""), "snippet": snippet, "url": r.get("url", "")})

        lines = ["【搜索结果】查询：" + query]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   URL: {r['url']}")
        formatted = "\n".join(lines)
        elapsed_ms = int((time.monotonic() - t_start) * 1000)

        logger.info(
            "[search_tool] Success | query=%s | results=%d | retries=%d | elapsed=%dms",
            query[:100] if query else "<empty>",
            len(results),
            retry_count,
            elapsed_ms,
        )
        return {
            "status": "success",
            "query": query,
            "results": results,
            "formatted": formatted,
            "retry_count": retry_count,
            "elapsed_ms": elapsed_ms,
        }

    except Exception as e:
        last_exc = e
        err_type = _classify_search_error(e)
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        logger.error(
            "[search_tool] Failed | query=%s | err_type=%s | retries=%d | elapsed=%dms | exc=%s",
            query[:100] if query else "<empty>",
            err_type,
            retry_count,
            elapsed_ms,
            e,
        )
        return {
            "status": "failed",
            "query": query,
            "results": [],
            "formatted": "[搜索降级] 搜索暂时不可用，请稍后重试。我将基于已有知识回答您的问题。",
            "retry_count": retry_count,
            "elapsed_ms": elapsed_ms,
        }


async def search_tool(query: str, max_results: int = 5, search_depth: str = "advanced") -> str:
    """ToolRegistry 兼容封装：调用 web_search 并返回人类可读格式化文本。

    适配 ToolRegistry 注册规范（返回 str），供 LangGraph tool_execute 节点调度。
    故障完全隔离：所有异常已在 web_search 内部捕获并转换为降级提示字符串。
    """
    result = await web_search(query, max_results, search_depth)
    return str(result["formatted"])


# 同步版指数退避重试（遗留工具函数，供 sync 调用方使用）
def _retry_with_backoff(func: Any, max_retries: int = 2, base_delay: float = 1.0) -> Any:
    """同步指数退避重试，保留用于向后兼容。"""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning("Retry %d/%d after %ds: %s", attempt + 1, max_retries, delay, e)
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


__all__ = ["SearchInput", "search_tool", "web_search", "_retry_with_backoff", "_truncate_result"]
