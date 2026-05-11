"""Tests for WhisparrInterface._get_manual_import_preview."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whisparr_sync import (
    ManualImportPreviewFile,
    ManualImportError,
    StashFile,
    StashSceneModel,
    WhisparrInterface,
    WhisparrScene,
    WhisparrStatistics,
)


def _make_interface(file_count=0, stash_files=None):
    files = stash_files or []
    scene = StashSceneModel(
        title="Test",
        stash_ids=[{"endpoint": "stashdb.org", "stash_id": "abc"}],
        files=files,
    )
    config = MagicMock()
    config.WHISPARR_URL = "http://whisparr-v3:6969"
    config.WHISPARR_KEY = "key"
    config.MONITORED = True
    config.MOVE_FILES = False
    config.WHISPARR_RENAME = True
    config.QUALITY_PROFILE = "Any"
    config.ROOT_FOLDER = None
    config.ROOT_FOLDER_MAP = {}
    config.PATH_MAPPING = {}
    config.DRY_RUN = False
    config.BULK_DELAY_SECONDS = 0.0

    http = MagicMock()
    iface = WhisparrInterface(config=config, stash_scene=scene, http_func=http)
    iface.whisparr_scene = WhisparrScene(
        title="Test",
        id=1,
        path=Path("/whisparr/scenes/test"),
        statistics=WhisparrStatistics(movieFileCount=file_count, sizeOnDisk=0),
    )
    return iface, http


class TestGetManualImportPreview:
    def test_returns_list_on_success(self):
        preview = ManualImportPreviewFile(
            path=Path("/whisparr/scenes/test/scene.mp4"),
            folderName="test",
            size=1000,
            quality=None,
        )
        iface, http = _make_interface()
        http.return_value = (200, [preview])
        result = iface._get_manual_import_preview()
        assert result == [preview]

    def test_returns_empty_when_already_imported(self):
        """When file count matches, empty preview means already imported."""
        iface, http = _make_interface(
            file_count=1,
            stash_files=[StashFile(path=Path("/stash/scene.mp4"))],
        )
        http.return_value = (200, [])
        result = iface._get_manual_import_preview()
        assert result == []

    def test_raises_manual_import_error_when_not_yet_imported(self):
        """Empty preview when file count does NOT match raises ManualImportError."""
        iface, http = _make_interface(file_count=0, stash_files=[StashFile(path=Path("/stash/scene.mp4"))])
        http.return_value = (200, [])
        with pytest.raises(ManualImportError):
            iface._get_manual_import_preview()

    def test_raises_on_non_200_status_when_files_pending(self):
        """500 response raises when there are unimported files."""
        iface, http = _make_interface(
            file_count=0,
            stash_files=[StashFile(path=Path("/stash/scene.mp4"))],
        )
        http.return_value = (500, "error")
        with pytest.raises(ManualImportError):
            iface._get_manual_import_preview()
