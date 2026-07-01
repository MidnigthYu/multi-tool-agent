"""ChromaClient 单元测试 -- 9 用例。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from storage.chroma_client import ChromaClient


class TestChromaClient:
    def test_init(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        assert c.is_degraded is False

    def test_heartbeat_success(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c.client, "heartbeat", return_value=1):
            assert c.heartbeat() is True

    def test_heartbeat_failure(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c.client, "heartbeat", side_effect=Exception("fail")):
            assert c.heartbeat() is False and c.is_degraded

    def test_get_or_create(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c.client, "get_or_create_collection") as m:
            m.return_value = MagicMock()
            assert c.get_or_create_collection("c") is not None

    def test_add_documents(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c, "get_or_create_collection") as m:
            coll = MagicMock()
            m.return_value = coll
            c.add_documents("c", ["id1"], ["doc1"])
            coll.add.assert_called_once()

    def test_add_with_metadata(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c, "get_or_create_collection") as m:
            coll = MagicMock()
            m.return_value = coll
            c.add_documents("c", ["id1"], ["doc1"], [{"k": "v"}])
            coll.add.assert_called_once()

    def test_similarity_search_empty(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c.client, "get_or_create_collection") as m:
            col = MagicMock()
            col.query.return_value = {"ids": [], "documents": [], "metadatas": [], "distances": []}
            m.return_value = col
            assert c.similarity_search("c", ["q"], n_results=5) == []

    def test_delete_collection(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c.client, "delete_collection", return_value=None):
            c.delete_collection("c")  # should not raise

    def test_delete_nonexistent(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c.client, "delete_collection", side_effect=ValueError("not found")):
            c.delete_collection("c")  # should not raise
