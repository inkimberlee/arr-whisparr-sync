"""Tests for FileManager — move, exists, path mapping."""
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whisparr_sync import FileManager


def _make_config(path_mapping=None):
    cfg = MagicMock()
    cfg.PATH_MAPPING = path_mapping or {}
    return cfg


class TestFileManagerExists:
    def test_finds_file_in_source(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        f = src_dir / "scene.mp4"
        f.touch()
        fm = FileManager(_make_config(), source=f, destination=dst_dir)
        assert fm.exists() == f.resolve()

    def test_finds_file_in_destination(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        f = dst_dir / "scene.mp4"
        f.touch()
        fm = FileManager(_make_config(), source=src_dir / "scene.mp4", destination=dst_dir)
        assert fm.exists() == f.resolve()

    def test_raises_when_file_not_found(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        fm = FileManager(_make_config(), source=src_dir / "missing.mp4", destination=dst_dir)
        with pytest.raises(FileNotFoundError):
            fm.exists()

    def test_same_file_source_and_dest(self, tmp_path):
        """When source and destination resolve to the same file, returns it if it exists."""
        f = tmp_path / "scene.mp4"
        f.touch()
        fm = FileManager(_make_config(), source=f, destination=tmp_path)
        result = fm.exists()
        assert result == f.resolve()


class TestFileManagerMove:
    def test_moves_file_to_destination(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        f = src_dir / "scene.mp4"
        f.write_bytes(b"data")
        fm = FileManager(_make_config(), source=f, destination=dst_dir)
        result = fm.move(f)
        assert result is True
        assert (dst_dir / "scene.mp4").exists()
        assert not f.exists()

    def test_returns_false_when_source_missing(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        fm = FileManager(_make_config(), source=src_dir / "missing.mp4", destination=dst_dir)
        result = fm.move(src_dir / "missing.mp4")
        assert result is False

    def test_returns_false_when_already_at_destination(self, tmp_path):
        """File already in destination — no move needed, returns False."""
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        f = dst_dir / "scene.mp4"
        f.write_bytes(b"data")
        fm = FileManager(_make_config(), source=f, destination=dst_dir)
        result = fm.move(f.resolve())
        assert result is False

    def test_creates_destination_subdirectories(self, tmp_path):
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest" / "sub" / "dir"
        f = src_dir / "scene.mp4"
        f.write_bytes(b"data")
        fm = FileManager(_make_config(), source=f, destination=dst_dir)
        fm.move(f)
        assert (dst_dir / "scene.mp4").exists()

    def test_returns_false_when_file_never_appears_after_move(self, tmp_path):
        """Retry loop exhausts when target file never appears (lines 378-385)."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        f = src_dir / "scene.mp4"
        f.write_bytes(b"data")
        fm = FileManager(_make_config(), source=f, destination=dst_dir)

        call_count = {"n": 0}

        def fake_is_file(self_path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return True  # source.is_file() check → file exists
            return False  # target_file.is_file() in retry loop → never appears

        from unittest.mock import patch
        with patch("pathlib.Path.is_file", fake_is_file), \
             patch("pathlib.Path.replace", return_value=None), \
             patch("whisparr_sync.time.sleep"):
            result = fm.move(f, retries=2, delay=0.0)
        assert result is False

    def test_returns_true_when_file_appears_on_retry(self, tmp_path):
        """File appears on second retry attempt (lines 370-377)."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        f = src_dir / "scene.mp4"
        f.write_bytes(b"data")
        fm = FileManager(_make_config(), source=f, destination=dst_dir)

        call_count = {"n": 0}

        def fake_is_file(self_path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return True   # source.is_file()
            if call_count["n"] == 2:
                return False  # first retry: not yet
            return True       # second retry: appears

        from unittest.mock import patch
        with patch("pathlib.Path.is_file", fake_is_file), \
             patch("pathlib.Path.replace", return_value=None), \
             patch("whisparr_sync.time.sleep"):
            result = fm.move(f, retries=3, delay=0.0)
        assert result is True

    def test_returns_false_on_unexpected_exception(self, tmp_path):
        """Exception during replace() is caught and returns False."""
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        dst_dir = tmp_path / "dest"
        dst_dir.mkdir()
        f = src_dir / "scene.mp4"
        f.write_bytes(b"data")
        fm = FileManager(_make_config(), source=f, destination=dst_dir)
        from unittest.mock import patch
        with patch("pathlib.Path.replace", side_effect=OSError("permission denied")):
            result = fm.move(f)
        assert result is False


class TestFileManagerPathMapping:
    def test_applies_path_mapping_to_source(self, tmp_path):
        real_src = tmp_path / "local" / "source"
        real_src.mkdir(parents=True)
        dst = tmp_path / "dest"
        dst.mkdir()
        f = real_src / "scene.mp4"
        f.touch()

        cfg = _make_config(path_mapping={"/server/source": str(real_src)})
        fm = FileManager(cfg, source=Path("/server/source/scene.mp4"), destination=dst)
        assert fm.exists() == f.resolve()
