"""ChromaStore unit tests — 8 cases covering index, search, degradation, edges."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from storage.chroma_store import ChromaStore, get_chroma_store


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure each test starts with a fresh ChromaStore singleton."""
    import storage.chroma_store as mod

    mod._store_instance = None


class TestChromaStoreInit:
    """Construction (1 case)."""

    def test_composes_chroma_client(self) -> None:
        with patch("storage.chroma_store.get_chroma_client") as gc:
            ChromaStore()
            gc.assert_called_once()


class TestAddDocuments:
    """Batch document indexing (3 cases)."""

    def test_normal(self) -> None:
        store = ChromaStore()
        store._embed = MagicMock(return_value=[[0.1] * 1536])
        store._client.add_documents = MagicMock()

        with patch("tools.document_parser.parse_document", return_value=(True, "hello world")):
            indexed, total, failed = store.add_documents(["a.pdf"], parser_func=lambda _: (True, "hello world"))

        assert indexed == 1 and total > 0 and failed == []

    def test_parse_failure_reported(self) -> None:
        store = ChromaStore()

        indexed, total, failed = store.add_documents(["bad.pdf"], parser_func=lambda _: (False, "parse error"))
        assert indexed == 0 and "bad.pdf" in failed

    def test_embed_degraded_still_indexes(self) -> None:
        store = ChromaStore()
        store._embed = MagicMock(return_value=[[0.0] * 1536])
        store._client.add_documents = MagicMock()

        indexed, total, failed = store.add_documents(["doc.pdf"], parser_func=lambda _: (True, "content"))
        assert indexed == 1 and failed == []


class TestSearch:
    """Semantic similarity search (2 cases)."""

    def test_normal(self) -> None:
        store = ChromaStore()
        store._embed = MagicMock(return_value=[[0.5] * 1536])
        store._client.similarity_search = MagicMock(
            return_value=[{"id": "1", "document": "match", "metadata": {"source": "a.pdf"}, "distance": 0.1}]
        )
        hits = store.search("test query")
        assert len(hits) == 1 and hits[0]["id"] == "1"

    def test_below_threshold_filters_out(self) -> None:
        store = ChromaStore()
        store._embed = MagicMock(return_value=[[0.5] * 1536])
        store._client.similarity_search = MagicMock(
            return_value=[{"id": "low", "document": "far", "metadata": {}, "distance": 0.99}]
        )
        hits = store.search("test", cutoff=0.3)
        assert hits == []


class TestDegradation:
    """Failure recovery (2 cases)."""

    def test_embed_failure_returns_empty(self) -> None:
        store = ChromaStore()
        store._embed = MagicMock(side_effect=RuntimeError("API down"))
        assert store.search("query") == []

    def test_chroma_exception_returns_empty(self) -> None:
        store = ChromaStore()
        store._embed = MagicMock(return_value=[[0.5] * 1536])
        store._client.similarity_search = MagicMock(side_effect=RuntimeError("Chroma crash"))
        assert store.search("query") == []


class TestSingleton:
    """Global singleton (1 case)."""

    def test_get_chroma_store_returns_same_instance(self) -> None:
        a = get_chroma_store()
        b = get_chroma_store()
        assert a is b
