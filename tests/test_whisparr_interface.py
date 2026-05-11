"""Tests for WhisparrInterface methods: find_existing_scene, create_scene (live),
_execute_manual_import, _queue_command, get_default_quality_profile, import_stash_file."""
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from whisparr_sync import (
    ManualImportPreviewFile,
    StashFile,
    StashSceneModel,
    WhisparrError,
    WhisparrInterface,
    WhisparrScene,
    WhisparrStatistics,
)


def _make_scene(tags=None, files=None):
    return StashSceneModel(
        title="Test Scene",
        stash_ids=[{"endpoint": "stashdb.org", "stash_id": "abc123"}],
        files=files or [],
        tags=[{"name": t} for t in (tags or [])],
    )


def _make_whisparr_scene(file_count=0):
    return WhisparrScene(
        title="Test Scene",
        id=42,
        path=Path("/whisparr/scenes/test-scene"),
        statistics=WhisparrStatistics(movieFileCount=file_count, sizeOnDisk=0),
    )


def _make_interface(scene=None, http_mock=None, dry_run=False, rename=True):
    if scene is None:
        scene = _make_scene()
    config = MagicMock()
    config.WHISPARR_URL = "http://whisparr-v3:6969"
    config.WHISPARR_KEY = "testkey"
    config.MONITORED = True
    config.MOVE_FILES = False
    config.WHISPARR_RENAME = rename
    config.QUALITY_PROFILE = "Any"
    config.ROOT_FOLDER = None
    config.ROOT_FOLDER_MAP = {}
    config.PATH_MAPPING = {}
    config.DRY_RUN = dry_run
    config.BULK_DELAY_SECONDS = 0.0

    http = http_mock or MagicMock()
    iface = WhisparrInterface(config=config, stash_scene=scene, http_func=http)
    return iface, http


class TestFindExistingScene:
    def test_returns_scene_when_found(self):
        ws = _make_whisparr_scene()
        iface, http = _make_interface()
        http.return_value = (200, [ws])
        result = iface.find_existing_scene()
        assert result == ws

    def test_returns_none_when_not_found(self):
        iface, http = _make_interface()
        http.return_value = (200, [])
        assert iface.find_existing_scene() is None

    def test_returns_none_on_non_200(self):
        iface, http = _make_interface()
        http.return_value = (404, [])
        assert iface.find_existing_scene() is None

    def test_returns_none_when_multiple_results(self):
        """Ambiguous result — multiple scenes returned for same stashId."""
        ws1 = _make_whisparr_scene()
        ws2 = _make_whisparr_scene()
        iface, http = _make_interface()
        http.return_value = (200, [ws1, ws2])
        assert iface.find_existing_scene() is None


class TestCreateScene:
    def test_creates_scene_on_201(self):
        ws = _make_whisparr_scene()
        iface, http = _make_interface()
        iface.get_default_quality_profile = MagicMock(return_value=1)
        iface.get_default_root_folder = MagicMock(return_value="/data/scenes")
        http.return_value = (201, ws)
        iface.create_scene()
        assert http.call_count == 1
        call_kwargs = http.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert "/api/v3/movie" in call_kwargs["url"]

    def test_creates_scene_on_200(self):
        ws = _make_whisparr_scene()
        iface, http = _make_interface()
        iface.get_default_quality_profile = MagicMock(return_value=1)
        iface.get_default_root_folder = MagicMock(return_value="/data/scenes")
        http.return_value = (200, ws)
        iface.create_scene()
        assert iface.whisparr_scene == ws

    def test_raises_on_error_status(self):
        iface, http = _make_interface()
        iface.get_default_quality_profile = MagicMock(return_value=1)
        iface.get_default_root_folder = MagicMock(return_value="/data/scenes")
        http.return_value = (422, {"message": "invalid"})
        with pytest.raises(WhisparrError):
            iface.create_scene()

    def test_dry_run_skips_post(self):
        iface, http = _make_interface(dry_run=True)
        iface.get_default_root_folder = MagicMock(return_value="/data/scenes")
        iface.create_scene()
        http.assert_not_called()


class TestExecuteManualImport:
    def test_executes_import_successfully(self):
        ws = _make_whisparr_scene()
        iface, http = _make_interface()
        iface.whisparr_scene = ws
        http.return_value = (201, {"id": 1})

        preview = ManualImportPreviewFile(
            path=Path("/whisparr/scenes/test-scene/scene.mp4"),
            folderName="test-scene",
            size=1000,
            quality=None,
        )
        iface._execute_manual_import(preview)
        assert http.call_count == 1
        assert http.call_args.kwargs["method"] == "POST"

    def test_raises_on_non_2xx(self):
        ws = _make_whisparr_scene()
        iface, http = _make_interface()
        iface.whisparr_scene = ws
        http.return_value = (500, "error")

        preview = ManualImportPreviewFile(
            path=Path("/whisparr/scenes/test-scene/scene.mp4"),
            folderName="test-scene",
            size=1000,
            quality=None,
        )
        with pytest.raises(WhisparrError):
            iface._execute_manual_import(preview)


class TestQueueCommand:
    def _setup(self, rename=True):
        ws = _make_whisparr_scene()
        iface, http = _make_interface(rename=rename)
        iface.whisparr_scene = ws
        http.return_value = (201, {"id": 99, "status": "queued"})
        return iface, http

    def test_queues_rename_files_command(self):
        iface, http = self._setup()
        iface._queue_command("RenameFiles")
        body = http.call_args.kwargs["body"].model_dump()
        assert body["name"] == "RenameFiles"
        assert 42 in body["movieIds"]

    def test_queues_refresh_movie_command(self):
        iface, http = self._setup()
        iface._queue_command("RefreshMovie")
        body = http.call_args.kwargs["body"].model_dump()
        assert body["name"] == "RefreshMovie"

    def test_does_not_raise_on_error(self):
        """_queue_command swallows errors — must not propagate."""
        iface, http = self._setup()
        http.side_effect = Exception("network error")
        iface._queue_command("RefreshMovie")  # should not raise


class TestGetDefaultQualityProfile:
    def test_returns_id_for_named_profile(self):
        iface, http = _make_interface()
        http.return_value = (200, [{"id": 2, "name": "HD"}, {"id": 1, "name": "Any"}])
        assert iface.get_default_quality_profile() == 1

    def test_returns_first_profile_when_name_not_found(self):
        iface, http = _make_interface()
        http.return_value = (200, [{"id": 5, "name": "Other"}])
        assert iface.get_default_quality_profile() == 5

    def test_returns_1_when_no_profiles(self):
        iface, http = _make_interface()
        http.return_value = (200, [])
        assert iface.get_default_quality_profile() == 1


class TestImportStashFile:
    def test_queues_rename_after_import_when_rename_enabled(self):
        ws = _make_whisparr_scene()
        preview = ManualImportPreviewFile(
            path=Path("/whisparr/scenes/test/scene.mp4"),
            folderName="test",
            size=1000,
            quality=None,
        )
        iface, _ = _make_interface(rename=True)
        iface.whisparr_scene = ws
        iface._get_matching_preview_files = MagicMock(return_value=[preview])
        iface._execute_manual_import = MagicMock()
        iface._queue_command = MagicMock()

        iface.import_stash_file()

        iface._execute_manual_import.assert_called_once_with(preview)
        iface._queue_command.assert_called_once_with("RenameFiles")

    def test_queues_refresh_when_rename_disabled(self):
        ws = _make_whisparr_scene()
        preview = ManualImportPreviewFile(
            path=Path("/whisparr/scenes/test/scene.mp4"),
            folderName="test",
            size=1000,
            quality=None,
        )
        iface, _ = _make_interface(rename=False)
        iface.whisparr_scene = ws
        iface._get_matching_preview_files = MagicMock(return_value=[preview])
        iface._execute_manual_import = MagicMock()
        iface._queue_command = MagicMock()

        iface.import_stash_file()

        iface._queue_command.assert_called_once_with("RefreshMovie")

    def test_skips_import_when_no_matches(self):
        ws = _make_whisparr_scene()
        iface, _ = _make_interface()
        iface.whisparr_scene = ws
        iface._get_matching_preview_files = MagicMock(return_value=[])
        iface._execute_manual_import = MagicMock()
        iface._queue_command = MagicMock()

        iface.import_stash_file()

        iface._execute_manual_import.assert_not_called()
        iface._queue_command.assert_not_called()

    def test_imports_all_matched_files(self):
        """import_stash_file calls _execute_manual_import for each matched preview."""
        ws = _make_whisparr_scene()
        previews = [
            ManualImportPreviewFile(path=Path("/w/p1.mp4"), folderName="d", size=1000, quality=None),
            ManualImportPreviewFile(path=Path("/w/p2.mp4"), folderName="d", size=1000, quality=None),
        ]
        iface, _ = _make_interface(rename=False)
        iface.whisparr_scene = ws
        iface._get_matching_preview_files = MagicMock(return_value=previews)
        iface._execute_manual_import = MagicMock()
        iface._queue_command = MagicMock()

        iface.import_stash_file()

        assert iface._execute_manual_import.call_count == 2
        iface._queue_command.assert_called_once()


class TestQueueCommandErrorLogging:
    def test_logs_error_on_non_2xx_response(self):
        ws = _make_whisparr_scene()
        iface, http = _make_interface()
        iface.whisparr_scene = ws
        http.return_value = (500, {"message": "internal error"})
        iface._queue_command("RefreshMovie")  # should not raise; just log error


class TestProcessScene:
    def _make_iface(self, dry_run=False):
        scene = _make_scene()
        iface, http = _make_interface(scene=scene, dry_run=dry_run)
        ws = _make_whisparr_scene()
        iface.find_existing_scene = MagicMock(return_value=ws)
        iface.create_scene = MagicMock()
        iface.process_stash_files = MagicMock(return_value=False)
        iface.import_stash_file = MagicMock()
        iface._queue_command = MagicMock()
        return iface

    def test_queues_refresh_when_files_moved(self):
        iface = self._make_iface()
        iface.process_stash_files = MagicMock(return_value=True)
        iface.process_scene()
        iface._queue_command.assert_any_call("RefreshMovie")

    def test_refetches_scene_after_create(self):
        """After create_scene, process_scene fetches the newly-created scene."""
        iface = self._make_iface()
        ws = _make_whisparr_scene()
        # First call: not found; second: found after create
        iface.find_existing_scene = MagicMock(side_effect=[None, ws])
        iface.process_scene()
        iface.create_scene.assert_called_once()
        assert iface.find_existing_scene.call_count == 2

    def test_dry_run_logs_but_skips_ops(self):
        iface = self._make_iface(dry_run=True)
        iface.process_scene()
        iface.process_stash_files.assert_not_called()
        iface.import_stash_file.assert_not_called()


class TestProcessStashFilesSceneNotFound:
    def test_raises_when_no_whisparr_scene(self):
        from whisparr_sync import SceneNotFoundError
        scene = _make_scene()
        iface, _ = _make_interface(scene=scene)
        iface.whisparr_scene = None
        with pytest.raises(SceneNotFoundError):
            iface.process_stash_files()


class TestStashHelpers:
    def test_open_conn_returns_none_on_missing_key(self):
        from whisparr_sync import StashHelpers
        StashHelpers._stash_conn = None
        StashHelpers.STASH_DATA = {}  # missing server_connection
        result = StashHelpers.open_conn()
        assert result is None

    def test_open_conn_returns_none_on_interface_exception(self):
        from whisparr_sync import StashHelpers
        from unittest.mock import patch
        StashHelpers._stash_conn = None
        StashHelpers.STASH_DATA = {"server_connection": {"url": "http://stash"}}
        with patch("whisparr_sync.StashInterface", side_effect=Exception("conn failed")):
            result = StashHelpers.open_conn()
        assert result is None

    def test_open_conn_reuses_existing_connection(self):
        from whisparr_sync import StashHelpers
        mock_conn = MagicMock()
        StashHelpers._stash_conn = mock_conn
        result = StashHelpers.open_conn()
        assert result is mock_conn

    def test_open_conn_establishes_connection_on_first_call(self):
        from whisparr_sync import StashHelpers
        from unittest.mock import patch
        StashHelpers._stash_conn = None
        StashHelpers.STASH_DATA = {"server_connection": {"url": "http://stash"}}
        mock_iface = MagicMock()
        with patch("whisparr_sync.StashInterface", return_value=mock_iface):
            result = StashHelpers.open_conn()
        assert result is mock_iface
        assert StashHelpers._stash_conn is mock_iface

    def test_init_stores_scene_id(self):
        from whisparr_sync import StashHelpers
        helper = StashHelpers(scene_id=42)
        assert helper.scene_id == 42
