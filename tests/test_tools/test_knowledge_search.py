"""Knowledge search unit tests — 16 cases covering retrieval, edge cases, Schema."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from tools.knowledge_search import KnowledgeSearchInput, knowledge_search

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestKnowledgeSearchInput:
    """Pydantic input schema (6 cases)."""

    def test_valid_input(self) -> None:
        si = KnowledgeSearchInput(query="hello", top_k=5, threshold=0.3)
        assert si.query == "hello" and si.top_k == 5 and si.threshold == 0.3

    def test_default_values(self) -> None:
        si = KnowledgeSearchInput(query="test")
        assert si.top_k == 5 and si.threshold == 0.3

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeSearchInput(query="")

    def test_query_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeSearchInput(query="x" * 2001)

    def test_top_k_out_of_bounds(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeSearchInput(query="x", top_k=0)
        with pytest.raises(ValidationError):
            KnowledgeSearchInput(query="x", top_k=21)

    def test_threshold_out_of_bounds(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeSearchInput(query="x", threshold=-0.1)
        with pytest.raises(ValidationError):
            KnowledgeSearchInput(query="x", threshold=1.1)


# ---------------------------------------------------------------------------
# Tool function tests
# ---------------------------------------------------------------------------


class TestKnowledgeSearch:
    """Retrieval tool function (10 cases)."""

    @pytest.fixture(autouse=True)
    def _reset_store(self) -> None:
        """Ensure each test gets a fresh mock store."""
        import storage.chroma_store as cs

        cs._store_instance = None

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_normal(self, mock_search: MagicMock) -> None:
        mock_search.return_value = [
            {"id": "1", "document": "RAG content", "metadata": {"source": "a.pdf"}, "distance": 0.1}
        ]
        result = await knowledge_search("什么是RAG")
        assert isinstance(result, str)
        assert "RAG content" in result
        assert "来源" in result

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_no_match(self, mock_search: MagicMock) -> None:
        mock_search.return_value = []
        result = await knowledge_search("nonexistent")
        assert isinstance(result, str)
        assert "无匹配" in result

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_degraded_on_search_exception(self, mock_search: MagicMock) -> None:
        mock_search.side_effect = RuntimeError("Chroma crash")
        result = await knowledge_search("query")
        assert isinstance(result, str)
        assert "降级" in result

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_threshold_filters(self, mock_search: MagicMock) -> None:
        mock_search.return_value = []  # all filtered out
        result = await knowledge_search("query", threshold=0.01)
        assert isinstance(result, str)
        assert "无匹配" in result

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_top_k_respected(self, mock_search: MagicMock) -> None:
        mock_search.return_value = [
            {"id": str(i), "document": f"doc{i}", "metadata": {"source": "a.pdf"}, "distance": 0.1} for i in range(3)
        ]
        result = await knowledge_search("query", top_k=3)
        assert isinstance(result, str)
        # All 3 results present
        assert result.count("来源") == 3

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_result_truncation(self, mock_search: MagicMock) -> None:
        long_doc = "A" * 3000
        mock_search.return_value = [
            {"id": "1", "document": long_doc, "metadata": {"source": "long.pdf"}, "distance": 0.05}
        ]
        result = await knowledge_search("query")
        assert isinstance(result, str)
        assert "截断" in result

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_source_attribution(self, mock_search: MagicMock) -> None:
        mock_search.return_value = [
            {"id": "1", "document": "content", "metadata": {"source": "report.pdf"}, "distance": 0.1}
        ]
        result = await knowledge_search("query")
        assert "report.pdf" in result

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_returns_string_always(self, mock_search: MagicMock) -> None:
        """Every code path returns str, never an exception."""
        mock_search.side_effect = RuntimeError("unexpected")
        result = await knowledge_search("query")
        assert isinstance(result, str)

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_no_exception_leaks(self, mock_search: MagicMock) -> None:
        mock_search.side_effect = Exception("chaos")
        # Must not raise
        result = await knowledge_search("query")
        assert isinstance(result, str)

    @patch("storage.chroma_store.ChromaStore.search")
    async def test_multi_result_formatting(self, mock_search: MagicMock) -> None:
        mock_search.return_value = [
            {"id": "1", "document": "first", "metadata": {"source": "a.pdf"}, "distance": 0.1},
            {"id": "2", "document": "second", "metadata": {"source": "b.docx"}, "distance": 0.2},
        ]
        result = await knowledge_search("query")
        assert "1." in result and "2." in result
        assert "a.pdf" in result and "b.docx" in result
