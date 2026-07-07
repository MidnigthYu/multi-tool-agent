"""Document loader - save uploaded files to disk and delegate to the existing index pipeline.
Provides a synchronous build_document_index function suitable for Streamlit call sites.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from config.settings import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def build_document_index(uploaded_files: list[Any]) -> str:
    """Save uploaded PDF files to the configured upload dir and index them.

    Args:
        uploaded_files: List of Streamlit UploadedFile objects.

    Returns:
        Human-readable summary from the indexing pipeline.
    """
    settings = get_settings()
    upload_dir = settings.upload_dir_path
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    try:
        for f in uploaded_files:
            dest = upload_dir / f.name
            dest.write_bytes(f.getbuffer())
            saved_paths.append(str(dest.resolve()))
            logger.info("Saved uploaded file: %s -> %s", f.name, dest)

        from tools.document_indexer import index_documents

        result = asyncio.run(index_documents(saved_paths))
        return result

    except Exception as exc:
        logger.error("build_document_index failed: %s", exc)
        return f"[upload index failed] {exc}"
