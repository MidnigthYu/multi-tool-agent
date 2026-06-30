"""LongTermMemory 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from memory.long_term import LongTermMemory
from storage.chroma_client import ChromaClient


class TestLongTermMemory:
    @pytest.fixture
    def memory(self) -> LongTermMemory:
        mc = MagicMock(spec=ChromaClient)
        mc.is_degraded = False
        return LongTermMemory(mc)

    def test_store(self, memory: LongTermMemory) -> None:
        memory.store_fact("s1", "likes python")
        memory._chroma.add_documents.assert_called_once()

    def test_recall(self, memory: LongTermMemory) -> None:
        memory._chroma.similarity_search.return_value = [
            {"id": "1", "document": "python", "distance": 0.9, "metadata": {}}
        ]
        assert len(memory.recall_relevant("python")) == 1

    def test_degraded(self, memory: LongTermMemory) -> None:
        memory._chroma.is_degraded = True
        assert memory.recall_relevant("test") == []

    def test_threshold(self, memory: LongTermMemory) -> None:
        memory._chroma.similarity_search.return_value = [
            {"id": "1", "document": "low", "distance": 0.3, "metadata": {}},
            {"id": "2", "document": "high", "distance": 0.8, "metadata": {}},
        ]
        r = memory.recall_relevant("test")
        assert len(r) == 1 and r[0]["id"] == "2"

    def test_health(self, memory: LongTermMemory) -> None:
        memory._chroma.heartbeat.return_value = True
        assert memory.health_check() is True

    def test_delete(self, memory: LongTermMemory) -> None:
        mc = MagicMock()
        mc.get.return_value = {"ids": ["1"]}
        memory._chroma.get_or_create_collection.return_value = mc
        memory.delete_session_facts("s1")
        mc.delete.assert_called_once()

    def test_recall_exception(self, memory: LongTermMemory) -> None:
        memory._chroma.similarity_search.side_effect = Exception("err")
        assert memory.recall_relevant("test") == []
