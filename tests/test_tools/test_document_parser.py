"""Document parser unit tests — 12 cases covering all three formats + chunker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.document_parser import (
    _fixed_width_chunks,
    _parse_docx,
    _parse_pdf,
    _parse_xlsx,
    _sanitize_whitespace,
    _split_paragraphs,
    parse_document,
    split_text_into_chunks,
)


class TestParseDocument:
    """Unified entry-point dispatch + error handling (5 cases)."""

    def test_dispatches_pdf(self) -> None:
        with (
            patch("tools.document_parser._PARSERS", {".pdf": lambda _: "PDF content"}),
            patch("pathlib.Path.exists", return_value=True),
        ):
            ok, text = parse_document("test.pdf")
        assert ok is True and "PDF content" in text

    def test_dispatches_docx(self) -> None:
        with (
            patch("tools.document_parser._PARSERS", {".docx": lambda _: "DOCX content"}),
            patch("pathlib.Path.exists", return_value=True),
        ):
            ok, text = parse_document("test.docx")
        assert ok is True and "DOCX content" in text

    def test_dispatches_xlsx(self) -> None:
        with (
            patch("tools.document_parser._PARSERS", {".xlsx": lambda _: "XLSX content"}),
            patch("pathlib.Path.exists", return_value=True),
        ):
            ok, text = parse_document("test.xlsx")
        assert ok is True and "XLSX content" in text

    def test_file_not_found(self) -> None:
        ok, msg = parse_document("nonexistent.pdf")
        assert ok is False and "不存在" in msg

    def test_unsupported_format(self) -> None:
        with patch("pathlib.Path.exists", return_value=True):
            ok, msg = parse_document("image.png")
        assert ok is False and "不支持" in msg


class TestParsePdf:
    """PDF parsing (2 cases)."""

    def test_normal(self) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 text"
        with patch("pypdf.PdfReader") as mr:
            mr.return_value.pages = [mock_page]
            text = _parse_pdf("dummy.pdf")
        assert "Page 1 text" in text

    def test_empty_page_skipped(self) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        with patch("pypdf.PdfReader") as mr:
            mr.return_value.pages = [mock_page]
            text = _parse_pdf("dummy.pdf")
        assert text == ""


class TestParseDocx:
    """DOCX parsing (2 cases)."""

    def test_normal(self) -> None:
        mock_doc = MagicMock()
        p1 = MagicMock()
        p1.text = "Hello world"
        mock_doc.paragraphs = [p1]
        with patch("docx.Document", return_value=mock_doc):
            text = _parse_docx("dummy.docx")
        assert "Hello world" in text

    def test_empty_paragraphs(self) -> None:
        mock_doc = MagicMock()
        p1 = MagicMock()
        p1.text = ""
        mock_doc.paragraphs = [p1]
        with patch("docx.Document", return_value=mock_doc):
            text = _parse_docx("dummy.docx")
        assert text == ""


class TestParseXlsx:
    """XLSX parsing (2 cases)."""

    def test_normal(self) -> None:
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [("A", "B"), ("C", "D")]
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_ws
        with patch("openpyxl.load_workbook", return_value=mock_wb):
            text = _parse_xlsx("dummy.xlsx")
        assert "Sheet: Sheet1" in text and "A\tB" in text

    def test_empty_rows_skipped(self) -> None:
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [("", None), ("", "")]
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_ws
        with patch("openpyxl.load_workbook", return_value=mock_wb):
            text = _parse_xlsx("dummy.xlsx")
        assert "Sheet: Sheet1" in text


class TestSanitizeWhitespace:
    """Whitespace normalization helper (1 case)."""

    def test_collapses_spaces_keeps_paragraphs(self) -> None:
        raw = "Hello    world\r\n\r\nFoo  bar\r\nBaz"
        out = _sanitize_whitespace(raw)
        assert "Hello world" in out
        assert "\n\n" in out


class TestChunking:
    """Semantic text chunker (4 cases)."""

    def test_short_text_single_chunk(self) -> None:
        chunks = split_text_into_chunks("Hello world", chunk_size=500, overlap=50)
        assert len(chunks) == 1 and chunks[0] == "Hello world"

    def test_paragraph_boundary_split(self) -> None:
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = split_text_into_chunks(text, chunk_size=500, overlap=50)
        assert len(chunks) == 3

    def test_long_paragraph_fallback(self) -> None:
        text = "A" * 1500
        chunks = split_text_into_chunks(text, chunk_size=500, overlap=100)
        assert len(chunks) >= 3
        for c in chunks:
            assert len(c) <= 500

    def test_empty_text_returns_empty_list(self) -> None:
        assert split_text_into_chunks("") == []
        assert split_text_into_chunks("   ") == []


class TestHelpers:
    """Low-level helper functions (2 cases)."""

    def test_split_paragraphs(self) -> None:
        parts = _split_paragraphs("A\n\nB\n\nC")
        assert len(parts) == 3
        assert parts[0].strip() == "A"

    def test_fixed_width_chunks(self) -> None:
        chunks = _fixed_width_chunks("ABCDEFGHIJ", 4, 2)
        assert len(chunks) == 5  # ABCD, CDEF, EFGH, GHIJ, IJ
        assert "ABCD" in chunks[0]
