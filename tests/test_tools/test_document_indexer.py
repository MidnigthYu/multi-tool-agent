"""Document indexer unit tests — 6 cases covering indexing pipeline + edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from tools.document_indexer import IndexDocumentsInput, index_documents


class TestIndexDocumentsInput:
    """Pydantic input schema (3 cases)."""

    def test_valid_input(self) -> None:
        si = IndexDocumentsInput(file_paths=["a.pdf", "b.docx"])
        assert si.file_paths == ["a.pdf", "b.docx"]

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IndexDocumentsInput(file_paths=[])

    def test_too_many_files_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IndexDocumentsInput(file_paths=[f"{i}.pdf" for i in range(21)])


class TestIndexDocuments:
    """Tool function (3 cases)."""

    @pytest.fixture(autouse=True)
    def _reset_store(self) -> None:
        import storage.chroma_store as cs

        cs._store_instance = None

    @patch("storage.chroma_store.ChromaStore.add_documents")
    async def test_normal(self, mock_add: MagicMock) -> None:
        mock_add.return_value = (1, 5, [])
        mock_stat = MagicMock(st_size=1000, st_mode=0o100644)
        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.stat", return_value=mock_stat):
            result = await index_documents(["test.pdf"])
        assert isinstance(result, str)
        assert "已索引" in result

    @patch("storage.chroma_store.ChromaStore.add_documents")
    async def test_all_files_failed(self, mock_add: MagicMock) -> None:
        mock_add.return_value = (0, 0, ["bad.pdf"])
        mock_stat = MagicMock(st_size=1000, st_mode=0o100644)
        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.stat", return_value=mock_stat):
            result = await index_documents(["bad.pdf"])
        assert isinstance(result, str)
        assert "失败" in result

    @patch("storage.chroma_store.ChromaStore.add_documents")
    async def test_returns_string_always(self, mock_add: MagicMock) -> None:
        mock_add.side_effect = Exception("chaos")
        mock_stat = MagicMock(st_size=1000, st_mode=0o100644)
        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.stat", return_value=mock_stat):
            result = await index_documents(["test.pdf"])
        assert isinstance(result, str)
