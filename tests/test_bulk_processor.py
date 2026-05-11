"""Tests for bulk_processor — I2 (resume), I3 (rate limiting), I5 (no-stashdb CSV), T6."""
import csv
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whisparr_sync import StashHelpers, _load_already_processed, bulk_processor
from config import PluginConfig


BASE_CONFIG = dict(WHISPARR_URL="http://whisparr-v3:6969", WHISPARR_KEY="abc123")


def _make_config(log_dir: Path, **overrides) -> PluginConfig:
    return PluginConfig(**{
        **BASE_CONFIG,
        "LOG_FILE_LOCATION": str(log_dir),
        "LOG_FILE_ENABLE": True,
        "BULK_DELAY_SECONDS": 0.0,
        **overrides,
    })


def _write_csv(path: Path, rows: list):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["scene_id", "result"])
        writer.writerows(rows)


class TestLoadAlreadyProcessed:
    def test_empty_file_returns_empty_set(self, tmp_path):
        p = tmp_path / "bulk_results.csv"
        assert _load_already_processed(p) == set()

    def test_nonexistent_file_returns_empty_set(self, tmp_path):
        assert _load_already_processed(tmp_path / "missing.csv") == set()

    def test_loads_success_rows(self, tmp_path):
        p = tmp_path / "bulk_results.csv"
        _write_csv(p, [[1, "Success"], [2, "NoStashDB ID"], [3, "Success"]])
        done = _load_already_processed(p)
        assert done == {1, 3}

    def test_skips_non_success_rows(self, tmp_path):
        p = tmp_path / "bulk_results.csv"
        _write_csv(p, [[1, "Failed"], [2, "SkippedTag"], [3, "Error"]])
        assert _load_already_processed(p) == set()

    def test_ignores_malformed_scene_id(self, tmp_path):
        p = tmp_path / "bulk_results.csv"
        _write_csv(p, [["bad-id", "Success"], [1, "Success"]])
        done = _load_already_processed(p)
        assert done == {1}


class TestBulkProcessorResume:
    def _setup_stash(self, scene_ids: list):
        stash = MagicMock()
        stash.get_configuration.return_value = {"general": {"databasePath": ":memory:"}}
        StashHelpers._stash_conn = stash
        return stash

    def test_skips_already_successful_scenes(self, tmp_path):
        """I2: scenes already in the CSV as Success are not re-processed."""
        self._setup_stash([])
        bulk_results = tmp_path / "bulk_results.csv"
        _write_csv(bulk_results, [[10, "Success"], [11, "Success"]])

        config = _make_config(tmp_path, DEV_MODE=True)

        scene_ids_processed = []
        def fake_process(cfg, scene_id):
            scene_ids_processed.append(scene_id)
            return "Success"

        with (
            patch("whisparr_sync.process_single_scene", side_effect=fake_process),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
                (10,), (11,), (12,)
            ]
            bulk_processor(config)

        assert 10 not in scene_ids_processed
        assert 11 not in scene_ids_processed
        assert 12 in scene_ids_processed

    def test_full_run_when_no_existing_csv(self, tmp_path):
        """I2: no CSV → all scenes processed."""
        self._setup_stash([])
        config = _make_config(tmp_path, DEV_MODE=True)

        processed = []
        def fake_process(cfg, scene_id):
            processed.append(scene_id)
            return "Success"

        with (
            patch("whisparr_sync.process_single_scene", side_effect=fake_process),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
                (1,), (2,), (3,)
            ]
            bulk_processor(config)

        assert set(processed) == {1, 2, 3}


class TestBulkProcessorNoStashdb:
    def test_no_stashdb_scenes_written_to_separate_csv(self, tmp_path):
        """I5: scenes returning NoStashDB ID appear in no_stashdb.csv."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True)

        def fake_process(cfg, scene_id):
            return "NoStashDB ID" if scene_id == 2 else "Success"

        with (
            patch("whisparr_sync.process_single_scene", side_effect=fake_process),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
                (1,), (2,), (3,)
            ]
            bulk_processor(config)

        no_stashdb = tmp_path / "no_stashdb.csv"
        assert no_stashdb.exists()
        with open(no_stashdb) as f:
            rows = list(csv.reader(f))
        scene_ids = [int(r[0]) for r in rows[1:]]  # skip header
        assert 2 in scene_ids
        assert 1 not in scene_ids

    def test_no_stashdb_csv_empty_when_all_match(self, tmp_path):
        """I5: no_stashdb.csv contains only header when all scenes have StashDB IDs."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True)

        with (
            patch("whisparr_sync.process_single_scene", return_value="Success"),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
                (1,), (2,)
            ]
            bulk_processor(config)

        with open(tmp_path / "no_stashdb.csv") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1  # header only


class TestBulkProcessorErrorHandling:
    def test_db_failure_returns_early(self, tmp_path):
        """DB connection failure causes bulk_processor to return without processing."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True)

        processed = []
        with (
            patch("whisparr_sync.process_single_scene", side_effect=lambda *a: processed.append(a)),
            patch("sqlite3.connect", side_effect=Exception("DB gone")),
        ):
            bulk_processor(config)

        assert processed == []

    def test_empty_scene_list_returns_early(self, tmp_path):
        """Empty scene list causes early return after logging."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True)

        processed = []
        with (
            patch("whisparr_sync.process_single_scene", side_effect=lambda *a: processed.append(a)),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = []
            bulk_processor(config)

        assert processed == []

    def test_exception_in_scene_loop_is_caught(self, tmp_path):
        """Exception during process_single_scene is caught and written as Error."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True)

        def boom(cfg, scene_id):
            raise RuntimeError("unexpected crash")

        with (
            patch("whisparr_sync.process_single_scene", side_effect=boom),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [(1,)]
            bulk_processor(config)  # should not raise

        bulk_csv = tmp_path / "bulk_results.csv"
        assert bulk_csv.exists()
        with open(bulk_csv) as f:
            rows = list(csv.reader(f))
        result_rows = [r for r in rows[1:] if r]
        assert any(r[1] == "Error" for r in result_rows)


class TestBulkProcessorFlushAndNonDev:
    def test_flushes_every_50_scenes(self, tmp_path):
        """CSV is flushed every 50 scenes during bulk processing."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True)

        scene_ids = [(i,) for i in range(1, 52)]  # 51 scenes → crosses 50 boundary

        with (
            patch("whisparr_sync.process_single_scene", return_value="Success"),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = scene_ids
            bulk_processor(config)

        bulk_csv = tmp_path / "bulk_results.csv"
        assert bulk_csv.exists()
        with open(bulk_csv) as f:
            rows = list(csv.reader(f))
        assert len(rows) == 52  # header + 51 data rows

    def test_non_dev_mode_reads_db_path_from_config(self, tmp_path):
        """Non-DEV_MODE reads databasePath from Stash general config (line 803)."""
        stash_conn = MagicMock()
        stash_conn.get_configuration.return_value = {
            "general": {"databasePath": str(tmp_path / "stash.sqlite")}
        }
        StashHelpers._stash_conn = stash_conn
        config = _make_config(tmp_path, DEV_MODE=False)

        with (
            patch("whisparr_sync.process_single_scene", return_value="Success"),
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = []
            bulk_processor(config)

        # connect should have been called with the path from databasePath
        connect_args = mock_db.call_args[0]
        assert "stash.sqlite" in str(connect_args[0])


class TestBulkProcessorRateLimit:
    def test_delay_applied_between_scenes(self, tmp_path):
        """I3: BULK_DELAY_SECONDS > 0 causes sleep between scenes."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True, BULK_DELAY_SECONDS=0.05)

        sleep_calls = []
        original_sleep = time.sleep

        with (
            patch("whisparr_sync.process_single_scene", return_value="Success"),
            patch("whisparr_sync.time") as mock_time,
            patch("sqlite3.connect") as mock_db,
        ):
            mock_time.sleep.side_effect = lambda s: sleep_calls.append(s)
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
                (1,), (2,), (3,)
            ]
            bulk_processor(config)

        assert len(sleep_calls) == 3
        assert all(s == 0.05 for s in sleep_calls)

    def test_no_delay_when_zero(self, tmp_path):
        """I3: BULK_DELAY_SECONDS=0 skips sleep calls."""
        StashHelpers._stash_conn = MagicMock()
        config = _make_config(tmp_path, DEV_MODE=True, BULK_DELAY_SECONDS=0.0)

        with (
            patch("whisparr_sync.process_single_scene", return_value="Success"),
            patch("whisparr_sync.time") as mock_time,
            patch("sqlite3.connect") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
                (1,), (2,)
            ]
            bulk_processor(config)

        mock_time.sleep.assert_not_called()
