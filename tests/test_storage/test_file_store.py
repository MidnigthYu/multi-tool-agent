"""FileStore 单元测试 (FIX: cleanup_expired max_age_hours=-1)。"""

from __future__ import annotations

import tempfile
from pathlib import Path

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

    def test_delete_nonexistent(self, store: FileStore) -> None:
        assert store.delete_file("s1", "x.txt") is False

    def test_list(self, store: FileStore) -> None:
        store.save_file("s1", "a.txt", b"a")
        store.save_file("s1", "b.txt", b"b")
        assert len(store.list_files("s1")) == 2

    def test_list_empty(self, store: FileStore) -> None:
        assert store.list_files("nonexistent") == []

    def test_cleanup(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"d")
        store.cleanup_session("s1")
        assert store.list_files("s1") == []

    def test_cleanup_nonexistent(self, store: FileStore) -> None:
        store.cleanup_session("nonexistent")

    def test_open_file(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"hello")
        f = store.open_file("s1", "t.txt")
        assert f is not None and f.read() == b"hello"
        f.close()

    def test_open_file_nonexistent(self, store: FileStore) -> None:
        assert store.open_file("s1", "x.txt") is None

    def test_usage(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"12345")
        assert store.get_usage_bytes() >= 5

    def test_usage_empty(self, store: FileStore) -> None:
        assert store.get_usage_bytes() == 0

    def test_get_file_size(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"123")
        assert store.get_file_size("s1", "t.txt") == 3

    def test_get_file_size_nonexistent(self, store: FileStore) -> None:
        assert store.get_file_size("s1", "x.txt") is None

    def test_cleanup_expired(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"d")
        count = store.cleanup_expired(max_age_hours=-1)
        assert count >= 1

    def test_save_rejects_bad_ext(self, store: FileStore) -> None:
        with pytest.raises(ValueError):
            store.save_file("s1", "bad.exe", b"x")

    def test_upload_dir_property(self, store: FileStore) -> None:
        assert store.upload_dir is not None

    def test_session_isolation(self, store: FileStore) -> None:
        store.save_file("s1", "a.txt", b"1")
        store.save_file("s2", "b.txt", b"2")
        assert len(store.list_files("s1")) == 1 and len(store.list_files("s2")) == 1

    def test_overwrite(self, store: FileStore) -> None:
        store.save_file("s1", "t.txt", b"old")
        store.save_file("s1", "t.txt", b"new")
        assert store.read_file("s1", "t.txt") == b"new"

    def test_validate_size_too_large(self, store: FileStore) -> None:
        """覆盖 _validate_size 超大文件拒绝 (line 48)。"""
        big = b"x" * (51 * 1024 * 1024)
        with pytest.raises(ValueError, match="too large"):
            store.save_file("s1", "big.txt", big)

    def test_open_file_oserror(self, store: FileStore) -> None:
        """覆盖 open_file OSError 异常路径 (lines 68-70)。"""
        from unittest.mock import patch

        store.save_file("s1", "t.txt", b"hello")
        with patch("builtins.open", side_effect=OSError("io error")):
            assert store.open_file("s1", "t.txt") is None


class TestFileStoreModuleFunctions:
    """模块级函数单测：read_file / write_file / ensure_dir / get_file_store 单例路径。"""

    @pytest.fixture
    def tmp_dir(self) -> str:
        import shutil

        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    def test_module_read_file_exists(self, tmp_dir: str) -> None:
        from pathlib import Path

        from storage.file_store import read_file, write_file

        f = Path(tmp_dir) / "r.txt"
        write_file(str(f), b"hello")
        assert read_file(str(f)) == b"hello"

    def test_module_read_file_nonexistent(self, tmp_dir: str) -> None:
        from pathlib import Path

        from storage.file_store import read_file

        assert read_file(str(Path(tmp_dir) / "no.txt")) is None

    def test_module_write_file(self, tmp_dir: str) -> None:
        from pathlib import Path

        from storage.file_store import write_file

        p = write_file(str(Path(tmp_dir) / "sub" / "w.txt"), b"data")
        assert p.exists() and p.read_bytes() == b"data"

    def test_module_ensure_dir(self, tmp_dir: str) -> None:
        from pathlib import Path

        from storage.file_store import ensure_dir

        d = ensure_dir(str(Path(tmp_dir) / "a" / "b"))
        assert d.is_dir()

    def test_get_file_store_singleton(self) -> None:
        import storage.file_store as _fs

        _fs._instance = None
        f1 = _fs.get_file_store("data/uploads")
        f2 = _fs.get_file_store("data/uploads")
        assert f1 is f2


class TestFileStoreEdgeCases:
    """覆盖率补齐 —— 异常路径 / 边界场景。"""

    def test_ensure_dir_oserror(self) -> None:
        """覆盖 _ensure_dir mkdir OSError → RuntimeError (lines 27-28)。"""
        from unittest.mock import patch

        from storage.file_store import FileStore

        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir", side_effect=OSError("permission denied")),
            pytest.raises(RuntimeError, match="数据目录创建失败"),
        ):
            FileStore("nonexistent/dir")

    def test_read_file_nonexistent_path(self) -> None:
        """覆盖模块级 read_file 不存在文件分支 (lines 122-123)。"""
        import tempfile
        from pathlib import Path

        from storage.file_store import read_file

        d = tempfile.mkdtemp()
        assert read_file(str(Path(d) / "no.txt")) is None

    def test_write_file_creates_parent(self) -> None:
        """覆盖模块级 write_file 父目录创建 (lines 127-130)。"""
        import tempfile
        from pathlib import Path

        from storage.file_store import write_file

        d = tempfile.mkdtemp()
        p = write_file(str(Path(d) / "sub" / "new.txt"), b"data")
        assert p.exists() and p.read_bytes() == b"data"

    def test_ensure_dir_creates(self) -> None:
        """覆盖模块级 ensure_dir 目录创建 (lines 134-136)。"""
        import tempfile
        from pathlib import Path

        from storage.file_store import ensure_dir

        d = tempfile.mkdtemp()
        result = ensure_dir(str(Path(d) / "nested" / "dir"))
        assert result.is_dir()
