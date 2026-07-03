"""RAG semantic retrieval tool — ToolRegistry-compatible async entry point.

Queries the ChromaStore vector index and returns formatted results suitable
for LLM consumption.  All error paths return a string (never raise), keeping
the LangGraph tool-execute node isolated from storage-layer failures.
"""

from __future__ import annotations

import logging
import time

from pydantic import BaseModel, Field

from config.settings import get_settings
from storage.chroma_store import get_chroma_store

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    """Pydantic input schema for the knowledge_search tool."""

    query: str = Field(..., min_length=1, max_length=2000, description="检索查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数")
    threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="相似度阈值（越小越严格）")


async def knowledge_search(query: str, top_k: int = 5, threshold: float = 0.3) -> str:
    """Search the local knowledge base and return relevant document excerpts.

    ToolRegistry-compatible async function.  Internally:
    1. Embeds *query* via the shared ChromaStore embedding client.
    2. Runs similarity search against the ``user_docs`` collection.
    3. Filters results by *threshold* (ChromaDB distance, smaller = better).
    4. Formats top hits with source attribution and truncates long excerpts.

    All storage / embedding exceptions are caught — the function always returns
    a human-readable string and never raises.

    Args:
        query: Natural-language search query.
        top_k: Maximum number of results to return (1–20).
        threshold: Maximum distance cutoff (0.0–1.0).

    Returns:
        Formatted search results string, or a degradation marker like
        ``[知识库无匹配]`` or ``[知识库降级]``.
    """
    t_start = time.monotonic()
    settings = get_settings()
    store = get_chroma_store()

    # --- search ---
    try:
        hits = store.search(query, top_k=top_k, cutoff=threshold)
    except Exception as exc:
        elapsed = int((time.monotonic() - t_start) * 1000)
        logger.error("[knowledge_search] Search exception | query=%.100s | exc=%s | elapsed=%dms", query, exc, elapsed)
        return "[知识库降级] 知识库检索暂时不可用，请稍后重试。我将基于已有知识回答您的问题。"

    elapsed = int((time.monotonic() - t_start) * 1000)

    # --- no match ---
    if not hits:
        logger.info("[knowledge_search] NoMatch | query=%.100s | elapsed=%dms", query, elapsed)
        return "[知识库无匹配] 未找到与您问题相关的文档内容。我将基于已有知识回答您的问题。"

    # --- format ---
    max_len = settings.RAG_MAX_RESULT_LENGTH
    lines: list[str] = [f"【知识库检索结果】查询：{query}\n"]
    for i, hit in enumerate(hits, 1):
        source = (
            hit.get("metadata", {}).get("source", "未知文档") if isinstance(hit.get("metadata"), dict) else "未知文档"
        )
        dist = hit.get("distance", 1.0)
        content = hit.get("document", "") or ""
        if len(content) > max_len:
            content = content[:max_len] + "\n…[截断]"
        lines.append(f"{i}. {content}\n   来源: {source}  |  相似度: {1.0 - dist:.2f}")

    logger.info("[knowledge_search] Success | query=%.100s | results=%d | elapsed=%dms", query, len(hits), elapsed)
    return "\n\n".join(lines)
