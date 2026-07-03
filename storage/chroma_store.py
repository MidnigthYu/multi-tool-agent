"""ChromaStore — business-layer wrapper over ChromaClient singleton.

Responsibilities:
- Embedding generation scheduling (OpenAI text-embedding-ada-002).
- Batch document indexing with metadata tracking.
- Similarity retrieval with threshold filtering.
- Delegates connection management and degradation to ChromaClient.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from config.settings import get_settings
from storage.chroma_client import get_chroma_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------


class ChromaStore:
    """Business-layer vector-store facade.

    Composes the global ChromaClient singleton — does **not** create its own
    ChromaDB connection, avoiding resource duplication with the memory and
    long-term-memory subsystems.
    """

    def __init__(self, collection_name: str | None = None) -> None:
        settings = get_settings()
        self._client = get_chroma_client()
        self._collection = collection_name or settings.CHROMA_COLLECTION_DOCS
        self._embedding_model = settings.EMBEDDING_MODEL
        self._dim = settings.EMBEDDING_DIMENSION

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_documents(
        self,
        file_paths: list[str],
        parser_func: Any = None,
    ) -> tuple[int, int, list[str]]:
        """Parse, chunk, embed, and index a batch of documents.

        Args:
            file_paths: Absolute paths to .pdf / .docx / .xlsx files.
            parser_func: Callable ``(path) -> tuple[bool, str]``.  Defaults to
                ``tools.document_parser.parse_document`` (lazy import to avoid
                circular imports).

        Returns:
            (indexed_count, total_chunks, failed_paths) — *indexed_count* is
            the number of files successfully processed; *total_chunks* is the
            sum of chunks across all processed files; *failed_paths* lists
            every file whose parsing or embedding failed.
        """
        if parser_func is None:
            from tools.document_parser import parse_document as parser_func  # noqa: PLR1704

        from tools.document_parser import split_text_into_chunks

        indexed = 0
        total = 0
        failed: list[str] = []

        for fp in file_paths:
            ok, text_or_err = parser_func(fp)
            if not ok:
                logger.warning("[ChromaStore] Parse failed | file=%s | reason=%s", fp, text_or_err)
                failed.append(fp)
                continue

            try:
                chunks = split_text_into_chunks(text_or_err)
            except Exception as exc:
                logger.warning("[ChromaStore] Chunk failed | file=%s | exc=%s", fp, exc)
                failed.append(fp)
                continue

            if not chunks:
                failed.append(fp)
                continue

            try:
                vectors = self._embed(chunks)
            except Exception as exc:
                logger.warning("[ChromaStore] Embed failed | file=%s | chunks=%d | exc=%s", fp, len(chunks), exc)
                failed.append(fp)
                continue

            ids = [f"{uuid.uuid4().hex[:16]}" for _ in chunks]
            metas: list[dict[str, Any]] = [{"source": fp} for _ in chunks]

            try:
                self._client.add_documents(
                    collection=self._collection,
                    ids=ids,
                    documents=chunks,
                    metadatas=metas,
                    embeddings=vectors,
                )
            except Exception as exc:
                logger.error("[ChromaStore] Write failed | file=%s | exc=%s", fp, exc)
                failed.append(fp)
                continue

            indexed += 1
            total += len(chunks)
            logger.info("[ChromaStore] Indexed | file=%s | chunks=%d", fp, len(chunks))

        return indexed, total, failed

    def search(self, query: str, top_k: int | None = None, cutoff: float | None = None) -> list[dict[str, Any]]:
        """Semantic similarity search over indexed documents.

        Args:
            query: Natural-language search query.
            top_k: Max results to return (default ``RAG_DEFAULT_TOP_K``).
            cutoff: Distance threshold — only results with ``distance < cutoff``
                are kept (ChromaDB uses *smaller-is-better* distance).

        Returns:
            List of ``{id, document, metadata, distance}`` dicts, sorted by
            distance ascending.  Empty list when no results pass the cutoff.
        """
        settings = get_settings()
        k = top_k if top_k is not None else settings.RAG_DEFAULT_TOP_K
        thresh = cutoff if cutoff is not None else settings.RAG_SIMILARITY_THRESHOLD

        try:
            self._embed([query])
        except Exception as exc:
            logger.warning("[ChromaStore] Query embed failed | exc=%s", exc)
            return []

        try:
            raw = self._client.similarity_search(self._collection, [query], n_results=k)
        except Exception as exc:
            logger.error("[ChromaStore] Search failed | query=%.100s | exc=%s", query, exc)
            return []

        filtered: list[dict[str, Any]] = []
        for r in raw:
            dist = r.get("distance", 1.0)
            if dist < thresh:
                filtered.append(r)
        return filtered

    def clear_collection(self, collection_name: str | None = None) -> None:
        """Delete a collection, e.g. to reset the knowledge base."""
        name = collection_name or self._collection
        try:
            self._client.delete_collection(name)
            logger.info("[ChromaStore] Collection cleared | name=%s", name)
        except Exception as exc:
            logger.warning("[ChromaStore] Clear failed | name=%s | exc=%s", name, exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via OpenAI text-embedding API.

        Returns a list of zero-vectors (length == EMBEDDING_DIMENSION) when
        the embedding service is unavailable, so callers never receive an
        exception.
        """
        import openai

        settings = get_settings()
        client = openai.OpenAI(
            api_key=settings.LLM_DEEPSEEK_API_KEY,
            base_url=settings.LLM_DEEPSEEK_BASE_URL,
        )
        try:
            resp = client.embeddings.create(model=self._embedding_model, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as exc:
            logger.warning("[ChromaStore] Embed API failed | texts=%d | exc=%s", len(texts), exc)
            return [[0.0] * self._dim for _ in texts]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store_instance: ChromaStore | None = None


def get_chroma_store() -> ChromaStore:
    """Return the global ChromaStore singleton."""
    global _store_instance
    if _store_instance is None:
        _store_instance = ChromaStore()
    return _store_instance
