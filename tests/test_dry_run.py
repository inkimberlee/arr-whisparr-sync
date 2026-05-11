"""Tests for DRY_RUN mode — I1."""
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from whisparr_sync import (
    StashFile,
    StashSceneModel,
    WhisparrInterface,
    WhisparrScene,
    WhisparrStatistics,
)
from config import PluginConfig


BASE_CONFIG = dict(WHISPARR_URL="http://whisparr-v3:6969", WHISPARR_KEY="abc123")


def _make_interface(dry_run: bool, existing_scene=None) -> WhisparrInterface:
    scene = StashSceneModel(
        title="Dry Run Scene",
        stash_ids=[{"endpoint": "stashdb.org", "stash_id": "abc123"}],
        files=[StashFile(path=Path("/stash/file.mp4"))],
    )
    config = MagicMock(spec=PluginConfig)
    config.WHISPARR_URL = "http://whisparr-v3:6969"
    config.WHISPARR_KEY = "abc123"
    config.MONITORED = True
    config.MOVE_FILES = True
    config.WHISPARR_RENAME = True
    config.QUALITY_PROFILE = "Any"
    config.ROOT_FOLDER = None
    config.ROOT_FOLDER_MAP = {}
    config.PATH_MAPPING = {}
    config.DRY_RUN = dry_run
    config.BULK_DELAY_SECONDS = 0.0

    iface = WhisparrInterface(config=config, stash_scene=scene)
    iface.find_existing_scene = MagicMock(return_value=existing_scene)
    iface.create_scene = MagicMock()
    iface.process_stash_files = MagicMock(return_value=False)
    iface.import_stash_file = MagicMock()
    iface._queue_command = MagicMock()

    if existing_scene:
        iface.whisparr_scene = existing_scene

    return iface


def _make_whisparr_scene():
    return WhisparrScene(
        title="Dry Run Scene",
        id=1,
        path=Path("/whisparr/scenes/dry-run"),
        statistics=WhisparrStatistics(movieFileCount=0, sizeOnDisk=0),
    )


class TestDryRunMode:
    def test_dry_run_skips_create_when_scene_exists(self):
        """DRY_RUN=True: create_scene not called when scene already in Whisparr."""
        existing = _make_whisparr_scene()
        iface = _make_interface(dry_run=True, existing_scene=existing)

        iface.process_scene()

        iface.create_scene.assert_not_called()

    def test_dry_run_calls_create_but_skips_import(self):
        """DRY_RUN=True: create_scene called for unknown scenes, but import is skipped."""
        iface = _make_interface(dry_run=True, existing_scene=None)

        iface.process_scene()

        iface.create_scene.assert_called_once()
        iface.import_stash_file.assert_not_called()
        iface.process_stash_files.assert_not_called()

    def test_dry_run_does_not_queue_commands(self):
        """DRY_RUN=True: no Whisparr commands queued."""
        iface = _make_interface(dry_run=True, existing_scene=None)

        iface.process_scene()

        iface._queue_command.assert_not_called()

    def test_live_mode_calls_import_and_move(self):
        """DRY_RUN=False: normal path calls process_stash_files and import_stash_file."""
        existing = _make_whisparr_scene()
        iface = _make_interface(dry_run=False, existing_scene=existing)

        iface.process_scene()

        iface.process_stash_files.assert_called_once()
        iface.import_stash_file.assert_called_once()

    def test_dry_run_create_scene_logs_and_returns(self):
        """DRY_RUN=True in create_scene: no POST made, returns immediately."""
        scene = StashSceneModel(
            title="Test",
            stash_ids=[{"endpoint": "stashdb.org", "stash_id": "abc123"}],
            files=[],
        )
        config = MagicMock(spec=PluginConfig)
        config.WHISPARR_URL = "http://whisparr-v3:6969"
        config.WHISPARR_KEY = "abc123"
        config.MONITORED = True
        config.MOVE_FILES = False
        config.WHISPARR_RENAME = True
        config.QUALITY_PROFILE = "Any"
        config.ROOT_FOLDER = None
        config.ROOT_FOLDER_MAP = {}
        config.PATH_MAPPING = {}
        config.DRY_RUN = True
        config.BULK_DELAY_SECONDS = 0.0

        http_mock = MagicMock()
        iface = WhisparrInterface(config=config, stash_scene=scene, http_func=http_mock)
        iface.get_default_root_folder = MagicMock(return_value="/data/scenes")

        iface.create_scene()

        # No POST should have been made
        for c in http_mock.call_args_list:
            assert c.kwargs.get("method") != "POST"
