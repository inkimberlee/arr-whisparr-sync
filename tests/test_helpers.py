"""Tests for module-level helpers: has_ignored_tag, wait_for_file, map_to_local_fs."""
import tempfile
import time
from pathlib import Path
from threading import Timer

import pytest

from whisparr_sync import StashSceneModel, has_ignored_tag, map_to_local_fs, wait_for_file


def _scene(tags=None):
    return StashSceneModel(
        title="Test",
        stash_ids=[],
        files=[],
        tags=[{"name": t} for t in (tags or [])],
    )


class TestHasIgnoredTag:
    def test_returns_none_when_no_ignored_tags_configured(self):
        assert has_ignored_tag(_scene(["foo"]), []) is None

    def test_returns_none_when_no_matching_tag(self):
        assert has_ignored_tag(_scene(["keep"]), ["skip"]) is None

    def test_returns_matching_tag(self):
        assert has_ignored_tag(_scene(["skip"]), ["skip"]) == "skip"

    def test_returns_first_matching_tag(self):
        result = has_ignored_tag(_scene(["a", "skip", "b"]), ["skip", "also-skip"])
        assert result == "skip"

    def test_returns_none_when_scene_has_no_tags(self):
        assert has_ignored_tag(_scene([]), ["skip"]) is None


class TestWaitForFile:
    def test_returns_true_when_file_exists_immediately(self, tmp_path):
        f = tmp_path / "exists.txt"
        f.touch()
        assert wait_for_file(f, timeout=1.0) is True

    def test_returns_false_on_timeout(self, tmp_path):
        f = tmp_path / "never_created.txt"
        assert wait_for_file(f, timeout=0.1, interval=0.05) is False

    def test_returns_true_when_file_appears_during_wait(self, tmp_path):
        f = tmp_path / "delayed.txt"
        Timer(0.05, f.touch).start()
        assert wait_for_file(f, timeout=1.0, interval=0.02) is True


class TestMapToLocalFs:
    def test_maps_matching_prefix(self):
        result = map_to_local_fs(
            Path("/server/data/file.mp4"),
            {"/server/data": "/local/data"},
        )
        assert result == Path("/local/data/file.mp4")

    def test_preserves_subdirectory_structure(self):
        result = map_to_local_fs(
            Path("/server/data/sub/dir/file.mp4"),
            {"/server/data": "/local/data"},
        )
        assert result == Path("/local/data/sub/dir/file.mp4")

    def test_no_mapping_returns_original(self):
        p = Path("/server/data/file.mp4")
        result = map_to_local_fs(p, {})
        assert result == p

    def test_no_prefix_match_returns_original(self):
        p = Path("/other/path/file.mp4")
        result = map_to_local_fs(p, {"/server/data": "/local/data"})
        assert result == p

    def test_exact_path_match(self):
        result = map_to_local_fs(Path("/server"), {"/server": "/local"})
        assert result == Path("/local")

    def test_trailing_slash_in_mapping_handled(self):
        result = map_to_local_fs(
            Path("/server/data/file.mp4"),
            {"/server/data/": "/local/data/"},
        )
        assert result == Path("/local/data/file.mp4")


class TestStashSceneModelTagExtraction:
    def test_accepts_plain_string_list(self):
        """extract_tag_names handles pre-extracted string lists (line 231)."""
        scene = StashSceneModel(
            title="Test",
            stash_ids=[],
            files=[],
            tags=["tag1", "tag2"],
        )
        assert scene.tags == ["tag1", "tag2"]

    def test_extracts_names_from_dict_list(self):
        scene = StashSceneModel(
            title="Test",
            stash_ids=[],
            files=[],
            tags=[{"name": "foo"}, {"name": "bar"}],
        )
        assert scene.tags == ["foo", "bar"]

    def test_empty_tags_returns_empty_list(self):
        scene = StashSceneModel(title="Test", stash_ids=[], files=[], tags=[])
        assert scene.tags == []
