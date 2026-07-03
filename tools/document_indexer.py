"""Document indexing tool — parse + chunk + embed + store pipeline.

ToolRegistry-compatible async entry point that accepts a list of file paths,
indexes every successfully parsed document into the ChromaStore, and returns
a human-readable summary.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from config.settings import get_settings
from storage.chroma_store import get_chroma_store

logger = logging.getLogger(__name__)


class IndexDocumentsInput(BaseModel):
    """Pydantic input schema for the index_documents tool."""

    file_paths: list[str] = Field(..., min_length=1, max_length=20, description="待索引的文档绝对路径列表")


async def index_documents(file_paths: list[str]) -> str:
    """Index one or more local documents into the RAG knowledge base.

    ToolRegistry-compatible async function.  For each file the pipeline is:
    parse → chunk → embed → write to ChromaDB (``user_docs`` collection).

    Files that fail any step are skipped and reported in the summary.
    A pre-check rejects the batch if the total file size exceeds the configured
    limit (``DOC_MAX_FILE_SIZE_MB``, default 50 MB).

    Args:
        file_paths: Absolute paths to ``.pdf`` / ``.docx`` / ``.xlsx`` files.

    Returns:
        Summary string e.g. ``"已索引 3 个文档，共 47 个片段"`` or
        ``"[索引失败] 所有文件处理失败"``.
    """
    t_start = time.monotonic()
    settings = get_settings()
    store = get_chroma_store()

    # --- pre-check: total file size ---
    max_bytes = settings.DOC_MAX_FILE_SIZE_MB * 1024 * 1024
    total_size = 0
    valid_paths: list[str] = []
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            logger.warning("[index_documents] File not found: %s", fp)
            continue
        if path.suffix.lower() not in (".pdf", ".docx", ".xlsx"):
            logger.warning("[index_documents] Unsupported format: %s", fp)
            continue
        try:
            sz = path.stat().st_size
        except OSError:
            logger.warning("[index_documents] Cannot stat: %s", fp)
            continue
        total_size += sz
        valid_paths.append(str(path))

    if not valid_paths:
        return "[索引失败] 未找到有效的文档文件（支持 PDF / DOCX / XLSX）"

    if total_size > max_bytes:
        return (
            f"[索引失败] 文件总大小 {total_size / 1024 / 1024:.1f}MB 超过限制"
            f"（{settings.DOC_MAX_FILE_SIZE_MB}MB），请分批索引"
        )

    # --- index ---
    try:
        indexed, chunks, failed = store.add_documents(valid_paths)
    except Exception as exc:
        elapsed = int((time.monotonic() - t_start) * 1000)
        logger.error("[index_documents] Fatal exception | exc=%s | elapsed=%dms", exc, elapsed)
        return f"[索引失败] 索引过程异常: {exc}"

    elapsed = int((time.monotonic() - t_start) * 1000)

    if indexed == 0:
        logger.warning("[index_documents] All files failed | attempted=%d | elapsed=%dms", len(valid_paths), elapsed)
        return f"[索引失败] 所有文件处理失败（{len(failed)} 个），请检查文档是否损坏或格式是否正确"

    parts: list[str] = [f"已索引 {indexed} 个文档，共 {chunks} 个片段"]
    if failed:
        parts.append(f"（{len(failed)} 个文件失败: {', '.join(Path(f).name for f in failed)}）")
    parts.append(f"\n耗时: {elapsed}ms")

    logger.info(
        "[index_documents] Success | indexed=%d | chunks=%d | failed=%d | elapsed=%dms",
        indexed,
        chunks,
        len(failed),
        elapsed,
    )
    return "".join(parts)
