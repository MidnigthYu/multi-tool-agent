"""ChromaDB 连接管理、集合 CRUD、相似度检索封装。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)


class ChromaClient:
    def __init__(self, persist_dir: str) -> None:
        self._persist_dir = str(Path(persist_dir).resolve())
        self._client: Any = None
        self._degraded = False

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir, settings=ChromaSettings(anonymized_telemetry=False)
            )
        return self._client

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    def get_or_create_collection(self, name: str) -> Any:
        return self.client.get_or_create_collection(name=name)

    def delete_collection(self, name: str) -> None:
        try:
            self.client.delete_collection(name)
        except ValueError:
            logger.warning("Collection %s not found", name)

    def add_documents(
        self,
        collection: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        col = self.get_or_create_collection(collection)
        col.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    def similarity_search(self, collection: str, query_texts: list[str], n_results: int = 5) -> list[dict[str, Any]]:
        col = self.get_or_create_collection(collection)
        results = col.query(query_texts=query_texts, n_results=n_results)
        ids = results.get("ids") or [[]]
        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        dists = results.get("distances") or [[]]
        out: list[dict[str, Any]] = []
        for i in range(len(ids[0])):
            out.append(
                {
                    "id": ids[0][i],
                    "document": docs[0][i] if docs else "",
                    "metadata": metas[0][i] if metas else {},
                    "distance": dists[0][i] if dists else 0.0,
                }
            )
        return out

    def heartbeat(self) -> bool:
        try:
            self.client.heartbeat()
            self._degraded = False
            return True
        except Exception as e:
            logger.warning("ChromaDB heartbeat failed: %s", e)
            self._degraded = True
            return False


_chroma_instance: ChromaClient | None = None


def get_chroma_client(persist_dir: str = "data/chroma_data") -> ChromaClient:
    global _chroma_instance
    if _chroma_instance is None:
        _chroma_instance = ChromaClient(str(Path(persist_dir).resolve()))
    return _chroma_instance
