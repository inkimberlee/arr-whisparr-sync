"""Tests for WhisparrInterface.process_stash_files."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whisparr_sync import (
    StashFile,
    StashSceneModel,
    WhisparrInterface,
    WhisparrScene,
    WhisparrStatistics,
)


def _make_interface(files, move=False):
    scene = StashSceneModel(
        title="Test",
        stash_ids=[{"endpoint": "stashdb.org", "stash_id": "abc"}],
        files=files,
    )
    config = MagicMock()
    config.WHISPARR_URL = "http://whisparr-v3:6969"
    config.WHISPARR_KEY = "key"
    config.MONITORED = True
    config.MOVE_FILES = move
    config.WHISPARR_RENAME = True
    config.QUALITY_PROFILE = "Any"
    config.ROOT_FOLDER = None
    config.ROOT_FOLDER_MAP = {}
    config.PATH_MAPPING = {}
    config.DRY_RUN = False
    config.BULK_DELAY_SECONDS = 0.0

    iface = WhisparrInterface(config=config, stash_scene=scene)
    iface.whisparr_scene = WhisparrScene(
        title="Test",
        id=1,
        path=Path("/whisparr/scenes/test"),
        statistics=WhisparrStatistics(movieFileCount=0, sizeOnDisk=0),
    )
    return iface


class TestProcessStashFiles:
    def test_returns_false_when_move_disabled(self, tmp_path):
        f = tmp_path / "scene.mp4"
        f.touch()
        iface = _make_interface([StashFile(path=f)], move=False)
        result = iface.process_stash_files()
        assert result is False

    def test_returns_true_when_file_moved(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "whisparr" / "scenes" / "test"
        dst.mkdir(parents=True)
        f = src / "scene.mp4"
        f.write_bytes(b"data")

        iface = _make_interface([StashFile(path=f)], move=True)
        iface.whisparr_scene.path = dst

        result = iface.process_stash_files()
        assert result is True
        assert (dst / "scene.mp4").exists()

    def test_returns_false_when_no_files(self, tmp_path):
        iface = _make_interface([], move=True)
        result = iface.process_stash_files()
        assert result is False

    def test_continues_after_file_error(self, tmp_path):
        """FileNotFoundError on one file doesn't crash the whole batch."""
        bad = StashFile(path=Path("/nonexistent/scene.mp4"))
        iface = _make_interface([bad], move=True)
        # Should not raise
        result = iface.process_stash_files()
        assert result is False
