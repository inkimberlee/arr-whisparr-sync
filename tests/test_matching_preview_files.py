"""Tests for _get_matching_preview_files (B1 regression)."""
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from whisparr_sync import (
    ManualImportPreviewFile,
    StashFile,
    StashSceneModel,
    WhisparrInterface,
    WhisparrScene,
    WhisparrStatistics,
)


def _make_preview(filename: str) -> ManualImportPreviewFile:
    return ManualImportPreviewFile(
        path=Path(f"/whisparr/scenes/scene_dir/{filename}"),
        folderName="scene_dir",
        size=1_000_000,
        quality=None,
    )


def _make_stash_file(filename: str) -> StashFile:
    return StashFile(path=Path(f"/stash/staging/{filename}"))


def _make_interface(stash_files: list, preview_files: list) -> WhisparrInterface:
    scene = StashSceneModel(
        title="Test Scene",
        stash_ids=[{"endpoint": "stashdb.org", "stash_id": "abc123"}],
        files=stash_files,
    )
    config = MagicMock()
    config.WHISPARR_URL = "http://whisparr-v3:6969"
    config.WHISPARR_KEY = "testkey"
    config.MONITORED = True
    config.MOVE_FILES = False
    config.WHISPARR_RENAME = True
    config.QUALITY_PROFILE = "Any"
    config.ROOT_FOLDER = None
    config.PATH_MAPPING = {}

    iface = WhisparrInterface(config=config, stash_scene=scene)
    iface.whisparr_scene = WhisparrScene(
        title="Test Scene",
        id=1,
        path=Path("/whisparr/scenes/scene_dir"),
        statistics=WhisparrStatistics(movieFileCount=0, sizeOnDisk=0),
    )
    iface._get_manual_import_preview = MagicMock(return_value=preview_files)
    return iface


class TestGetMatchingPreviewFiles:
    def test_single_file_matched(self):
        """Single scene file matches its preview — returns one result."""
        previews = [_make_preview("scene.mp4")]
        stash_files = [_make_stash_file("scene.mp4")]
        iface = _make_interface(stash_files, previews)

        result = iface._get_matching_preview_files()

        assert len(result) == 1
        assert result[0].path.name == "scene.mp4"

    def test_multi_file_all_matched(self):
        """B1 regression: all files in a multi-file scene are returned, not just the last."""
        previews = [_make_preview("part1.mp4"), _make_preview("part2.mp4")]
        stash_files = [_make_stash_file("part1.mp4"), _make_stash_file("part2.mp4")]
        iface = _make_interface(stash_files, previews)

        result = iface._get_matching_preview_files()

        assert len(result) == 2
        names = {r.path.name for r in result}
        assert names == {"part1.mp4", "part2.mp4"}

    def test_multi_file_partial_match(self):
        """Only files that appear in both scene and preview are returned."""
        previews = [_make_preview("part1.mp4")]  # part2 already imported
        stash_files = [_make_stash_file("part1.mp4"), _make_stash_file("part2.mp4")]
        iface = _make_interface(stash_files, previews)

        result = iface._get_matching_preview_files()

        assert len(result) == 1
        assert result[0].path.name == "part1.mp4"

    def test_no_files_returns_empty(self):
        """B1 regression: empty self.filenames must not raise NameError."""
        iface = _make_interface(stash_files=[], preview_files=[])

        result = iface._get_matching_preview_files()

        assert result == []

    def test_no_preview_match_returns_empty(self):
        """Scene file not in preview list (already imported) — returns empty list."""
        previews = [_make_preview("other_scene.mp4")]
        stash_files = [_make_stash_file("scene.mp4")]
        iface = _make_interface(stash_files, previews)

        result = iface._get_matching_preview_files()

        assert result == []

    def test_empty_preview_returns_empty(self):
        """Empty preview response (all already imported) — returns empty list."""
        stash_files = [_make_stash_file("scene.mp4")]
        iface = _make_interface(stash_files, preview_files=[])

        result = iface._get_matching_preview_files()

        assert result == []
