"""Tests for get_default_root_folder — B3 (type guard) and I4 (tag routing)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whisparr_sync import (
    StashFile,
    StashSceneModel,
    WhisparrError,
    WhisparrInterface,
    WhisparrScene,
    WhisparrStatistics,
)


def _make_interface(tags=None, root_folder=None, root_folder_map=None, http_responses=None):
    scene = StashSceneModel(
        title="Test Scene",
        stash_ids=[{"endpoint": "stashdb.org", "stash_id": "abc123"}],
        files=[],
        tags=[{"name": t} for t in (tags or [])],
    )
    config = MagicMock()
    config.WHISPARR_URL = "http://whisparr-v3:6969"
    config.WHISPARR_KEY = "testkey"
    config.MONITORED = True
    config.MOVE_FILES = False
    config.WHISPARR_RENAME = True
    config.QUALITY_PROFILE = "Any"
    config.ROOT_FOLDER = Path(root_folder) if root_folder else None
    config.ROOT_FOLDER_MAP = root_folder_map or {}
    config.PATH_MAPPING = {}
    config.DRY_RUN = False
    config.BULK_DELAY_SECONDS = 0.0

    iface = WhisparrInterface(config=config, stash_scene=scene)
    iface.whisparr_scene = WhisparrScene(
        title="Test Scene",
        id=1,
        path=Path("/whisparr/scenes"),
        statistics=WhisparrStatistics(movieFileCount=0, sizeOnDisk=0),
    )

    if http_responses is not None:
        responses = iter(http_responses)
        iface.http_json = MagicMock(side_effect=lambda **kw: next(responses))

    return iface


class TestGetDefaultRootFolder:
    def test_returns_first_folder_when_no_config(self):
        iface = _make_interface()
        iface.http_json = MagicMock(return_value=(200, [{"path": "/data/scenes"}, {"path": "/data/movies"}]))
        assert iface.get_default_root_folder() == "/data/scenes"

    def test_returns_configured_root_folder_when_matched(self):
        iface = _make_interface(root_folder="/data/movies")
        iface.http_json = MagicMock(return_value=(200, [{"path": "/data/scenes"}, {"path": "/data/movies"}]))
        assert iface.get_default_root_folder() == "/data/movies"

    def test_falls_back_to_first_when_configured_not_found(self):
        iface = _make_interface(root_folder="/data/missing")
        iface.http_json = MagicMock(return_value=(200, [{"path": "/data/scenes"}]))
        assert iface.get_default_root_folder() == "/data/scenes"

    def test_raises_when_no_root_folders(self):
        """B3 + empty list: raises WhisparrError rather than returning None."""
        iface = _make_interface()
        iface.http_json = MagicMock(return_value=(200, []))
        with pytest.raises(WhisparrError, match="No root folders"):
            iface.get_default_root_folder()

    def test_raises_on_dict_response(self):
        """B3 regression: API error returns dict instead of list."""
        iface = _make_interface()
        iface.http_json = MagicMock(return_value=(200, {"error": "unauthorized"}))
        with pytest.raises(WhisparrError, match="expected list"):
            iface.get_default_root_folder()

    def test_raises_on_string_response(self):
        """B3: string response is also not a list."""
        iface = _make_interface()
        iface.http_json = MagicMock(return_value=(200, "bad response"))
        with pytest.raises(WhisparrError, match="expected list"):
            iface.get_default_root_folder()


class TestRootFolderTagRouting:
    def test_tag_match_returns_mapped_folder(self):
        """I4: scene tag maps to a specific root folder."""
        iface = _make_interface(
            tags=["movies"],
            root_folder_map={"movies": "/data/movies", "scenes": "/data/scenes"},
        )
        assert iface.get_default_root_folder() == "/data/movies"

    def test_first_matching_tag_wins(self):
        """I4: first tag that matches the map is used."""
        iface = _make_interface(
            tags=["scenes", "movies"],
            root_folder_map={"scenes": "/data/scenes", "movies": "/data/movies"},
        )
        assert iface.get_default_root_folder() == "/data/scenes"

    def test_no_tag_match_falls_through_to_api(self):
        """I4: non-matching tags fall through to normal root folder logic."""
        iface = _make_interface(
            tags=["unrelated-tag"],
            root_folder_map={"movies": "/data/movies"},
        )
        iface.http_json = MagicMock(return_value=(200, [{"path": "/data/default"}]))
        assert iface.get_default_root_folder() == "/data/default"

    def test_empty_tag_map_falls_through_to_api(self):
        """I4: empty ROOT_FOLDER_MAP skips tag routing entirely."""
        iface = _make_interface(tags=["movies"], root_folder_map={})
        iface.http_json = MagicMock(return_value=(200, [{"path": "/data/default"}]))
        assert iface.get_default_root_folder() == "/data/default"

    def test_tag_routing_bypasses_api(self):
        """I4: when tag matches, http_json is NOT called."""
        iface = _make_interface(
            tags=["scenes"],
            root_folder_map={"scenes": "/data/scenes"},
        )
        iface.http_json = MagicMock()
        iface.get_default_root_folder()
        iface.http_json.assert_not_called()
