"""Tavily 联网搜索工具 -- 指数退避重试 + 结果截断 + 异常隔离。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from tavily import AsyncTavilyClient

from config.settings import get_settings

logger = logging.getLogger(__name__)


def _truncate_result(raw_text: str, max_chars: int = 4000) -> str:
    if len(raw_text) <= max_chars:
        return raw_text
    half = max_chars // 2
    return raw_text[:half] + f"\n\n... [{len(raw_text)} 字符截断] ...\n\n" + raw_text[-half:]


def _retry_with_backoff(func: Any, max_retries: int = 2, base_delay: float = 1.0) -> Any:
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


async def web_search(query: str, max_results: int = 5, search_depth: str = "advanced") -> dict[str, Any]:
    settings = get_settings()
    api_key = settings.TAVILY_API_KEY
    if not api_key or api_key.startswith("your-") or api_key.startswith("test-"):
        logger.warning("TAVILY_API_KEY not configured")
        return {"status": "failed", "query": query, "results": [], "formatted": "搜索服务未配置，请设置 TAVILY_API_KEY"}
    max_r = max_results or settings.SEARCH_RESULT_MAX_LENGTH
    max_chars = settings.SEARCH_RESULT_MAX_LENGTH * 2
    try:
        client = AsyncTavilyClient(api_key=api_key)

        last_exc: Exception | None = None
        for attempt in range(settings.SEARCH_RETRY_MAX + 1):
            try:
                data = await client.search(query=query, max_results=min(max_r, 10), search_depth=search_depth)
                break
            except Exception as e:
                last_exc = e
                if attempt < settings.SEARCH_RETRY_MAX:
                    delay = settings.SEARCH_RETRY_BASE_DELAY_S * (2**attempt)
                    logger.warning("Retry %d/%d after %ds: %s", attempt + 1, settings.SEARCH_RETRY_MAX, delay, e)
                    await asyncio.sleep(delay)
        else:
            assert last_exc is not None
            raise last_exc
        raw_results = data.get("results", [])
        results: list[dict[str, Any]] = []
        for r in raw_results[:max_results]:
            snippet = _truncate_result(r.get("content", "") or r.get("snippet", ""), max_chars)
            results.append({"title": r.get("title", ""), "snippet": snippet, "url": r.get("url", "")})
        lines = ["【搜索结果】查询：" + query]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   URL: {r['url']}")
        return {"status": "success", "query": query, "results": results, "formatted": "\n".join(lines)}
    except Exception as e:
        logger.error("Search failed after retries: %s", e)
        return {"status": "failed", "query": query, "results": [], "formatted": "搜索失败: 请稍后重试"}
