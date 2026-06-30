"""L3 长期向量记忆 -- ChromaDB 持久化用户偏好向量。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from config.constants import Constants
from config.settings import get_settings
from storage.chroma_client import ChromaClient

logger = logging.getLogger(__name__)


class LongTermMemory:
    """长期向量记忆：跨会话自动召回历史用户偏好。"""

    def __init__(self, chroma_client: ChromaClient) -> None:
        self._chroma = chroma_client

    def store_fact(self, session_id: str, fact: str, metadata: dict[str, Any] | None = None) -> None:
        """存储用户事实到长期记忆。"""
        try:
            meta = dict(metadata or {})
            meta["session_id"] = session_id
            self._chroma.add_documents(
                collection=Constants.CHROMA_COLLECTION_MEMORY,
                ids=[str(uuid.uuid4())],
                documents=[fact],
                metadatas=[meta],
            )
        except Exception as e:
            logger.error("LongTermMemory store failed: %s", e)

    def recall_relevant(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """召回与查询相关的长期记忆，低于阈值的过滤。"""
        if self._chroma.is_degraded:
            logger.warning("ChromaDB degraded, returning empty recall")
            return []
        k = top_k or get_settings().LONG_TERM_MEMORY_TOP_K
        threshold = get_settings().LONG_TERM_MEMORY_SIMILARITY_THRESHOLD
        try:
            results = self._chroma.similarity_search(
                collection=Constants.CHROMA_COLLECTION_MEMORY,
                query_texts=[query],
                n_results=k,
            )
            filtered = [r for r in results if r.get("distance", 1.0) >= threshold]
            return filtered
        except Exception as e:
            logger.error("LongTermMemory recall failed: %s", e)
            return []

    def delete_session_facts(self, session_id: str) -> None:
        """删除指定 session 的所有长期记忆。"""
        try:
            collection = Constants.CHROMA_COLLECTION_MEMORY
            col = self._chroma.get_or_create_collection(collection)
            results = col.get(where={"session_id": session_id})
            ids = results.get("ids", [])
            if ids:
                col.delete(ids=ids)
                logger.info("Deleted %d facts for session: %s", len(ids), session_id)
        except Exception as e:
            logger.warning("LongTermMemory delete failed: %s", e)

    def health_check(self) -> bool:
        """检测 ChromaDB 是否可用。"""
        return self._chroma.heartbeat()


_long_term_instance: LongTermMemory | None = None


def get_long_term_memory(chroma_client: ChromaClient) -> LongTermMemory:
    global _long_term_instance
    if _long_term_instance is None:
        _long_term_instance = LongTermMemory(chroma_client)
    return _long_term_instance
