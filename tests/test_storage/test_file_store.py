"""FileStore 单元测试。"""

from __future__ import annotations

import tempfile

import pytest

from storage.file_store import FileStore


class TestFileStore:
    @pytest.fixture
    def store(self) -> FileStore:
        return FileStore(tempfile.mkdtemp())

    def test_save_and_read(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"hello")
        assert store.read_file("s1", "t.txt") == b"hello"

    def test_read_nonexistent(self, store: FileStore) -> None:
        assert store.read_file("s1", "x.txt") is None

    def test_delete(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"d")
        assert store.delete_file("s1", "t.txt") is True

    def test_list(self, store: FileStore) -> None:
        store.save_file("s1", "a.txt", b"a")
        store.save_file("s1", "b.txt", b"b")
        assert len(store.list_files("s1")) == 2

    def test_cleanup(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"d")
        store.cleanup_session("s1")
        assert store.list_files("s1") == []

    def test_open_file(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"hello")
        f = store.open_file("s1", "t.txt")
        assert f is not None and f.read() == b"hello"
        f.close()

    def test_usage(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"12345")
        assert store.get_usage_bytes() >= 5
