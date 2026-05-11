"""Tests for process_single_scene — T5."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whisparr_sync import (
    StashHelpers,
    WhisparrError,
    process_single_scene,
)
from config import PluginConfig


BASE_CONFIG = dict(WHISPARR_URL="http://whisparr-v3:6969", WHISPARR_KEY="abc123")


def _make_config(**overrides) -> PluginConfig:
    return PluginConfig(**{**BASE_CONFIG, **overrides})


def _make_scene_data(title="Test Scene", stash_ids=None, tags=None, files=None):
    return {
        "title": title,
        "stash_ids": [{"endpoint": "stashdb.org", "stash_id": "abc123"}] if stash_ids is None else stash_ids,
        "tags": [{"name": t} for t in (tags or [])],
        "files": files or [],
    }


@pytest.fixture(autouse=True)
def reset_stash_conn():
    """Ensure StashHelpers connection is reset between tests."""
    StashHelpers._stash_conn = None
    yield
    StashHelpers._stash_conn = None


class TestProcessSingleScene:
    def _make_stash_conn(self, scene_data=None, missing=False):
        conn = MagicMock()
        if missing:
            conn.find_scene.return_value = None
        else:
            conn.find_scene.return_value = scene_data or _make_scene_data()
        StashHelpers._stash_conn = conn
        return conn

    def test_returns_failed_when_scene_not_in_stash(self):
        self._make_stash_conn(missing=True)
        config = _make_config()
        result = process_single_scene(config, scene_id=1)
        assert result == "Failed"

    def test_returns_no_stashdb_id_when_no_stash_ids(self):
        self._make_stash_conn(scene_data=_make_scene_data(stash_ids=[]))
        config = _make_config()
        result = process_single_scene(config, scene_id=1)
        assert result == "NoStashDB ID"

    def test_returns_no_stashdb_id_when_endpoint_mismatch(self):
        data = _make_scene_data(stash_ids=[{"endpoint": "other-db.com", "stash_id": "xyz"}])
        self._make_stash_conn(scene_data=data)
        config = _make_config()
        result = process_single_scene(config, scene_id=1)
        assert result == "NoStashDB ID"

    def test_returns_skipped_tag_when_ignored_tag_present(self):
        data = _make_scene_data(tags=["skip-me"])
        self._make_stash_conn(scene_data=data)
        config = _make_config(IGNORE_TAGS=["skip-me"])
        result = process_single_scene(config, scene_id=1)
        assert result == "SkippedTag"

    def test_skip_applies_to_any_matching_tag(self):
        data = _make_scene_data(tags=["keep", "skip-me", "other"])
        self._make_stash_conn(scene_data=data)
        config = _make_config(IGNORE_TAGS=["skip-me"])
        result = process_single_scene(config, scene_id=1)
        assert result == "SkippedTag"

    def test_returns_failed_on_whisparr_error(self):
        self._make_stash_conn()
        config = _make_config()
        with patch("whisparr_sync.WhisparrInterface") as MockIface:
            MockIface.return_value.process_scene.side_effect = WhisparrError("boom")
            result = process_single_scene(config, scene_id=1)
        assert result == "Failed"

    def test_returns_failed_on_unexpected_exception(self):
        self._make_stash_conn()
        config = _make_config()
        with patch("whisparr_sync.WhisparrInterface") as MockIface:
            MockIface.return_value.process_scene.side_effect = RuntimeError("unexpected")
            result = process_single_scene(config, scene_id=1)
        assert result == "Failed"

    def test_returns_success_on_happy_path(self):
        self._make_stash_conn()
        config = _make_config()
        with patch("whisparr_sync.WhisparrInterface") as MockIface:
            MockIface.return_value.process_scene.return_value = None
            result = process_single_scene(config, scene_id=1)
        assert result == "Success"

    def test_returns_failed_on_validation_error(self):
        """ValidationError during scene model construction returns Failed."""
        conn = MagicMock()
        # Return data that will fail pydantic validation
        conn.find_scene.return_value = {"stash_ids": "not-a-list", "title": 123}
        StashHelpers._stash_conn = conn
        config = _make_config()
        result = process_single_scene(config, scene_id=1)
        assert result == "Failed"

    def test_returns_failed_on_find_scene_exception(self):
        """Generic exception from find_scene returns Failed (line 751-753)."""
        conn = MagicMock()
        conn.find_scene.side_effect = RuntimeError("stash connection dropped")
        StashHelpers._stash_conn = conn
        config = _make_config()
        result = process_single_scene(config, scene_id=1)
        assert result == "Failed"
