"""ChromaClient 单元测试。"""

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
            assert c.is_degraded is False

    def test_heartbeat_failure(self) -> None:
        c = ChromaClient("/tmp/test_chroma")
        with patch.object(c.client, "heartbeat", side_effect=Exception("fail")):
            assert c.heartbeat() is False
            assert c.is_degraded is True

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
