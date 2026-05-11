"""Tests for config helper functions: truncate_path, safe_json_preview."""
import config as cfg_module
from config import safe_json_preview, truncate_path
from pathlib import Path


def _reset_config():
    cfg_module.CONFIG = None


class TestTruncatePath:
    def test_short_path_returned_as_is(self):
        _reset_config()
        result = truncate_path(Path("/short/path.mp4"))
        assert result == "/short/path.mp4"

    def test_long_path_truncated_with_ellipsis(self):
        _reset_config()
        long = Path("/very/" + "long/" * 20 + "file.mp4")
        result = truncate_path(long)
        assert result.startswith("...")
        assert len(result) <= 100

    def test_uses_config_max_path_length(self):
        from unittest.mock import MagicMock
        mock_cfg = MagicMock()
        mock_cfg.MAX_PATH_LENGTH = 20
        mock_cfg.MAX_LOG_BODY = 1000
        cfg_module.CONFIG = mock_cfg
        result = truncate_path(Path("/a/very/long/path/to/a/file.mp4"))
        assert len(result) <= 20
        cfg_module.CONFIG = None


class TestSafeJsonPreview:
    def test_returns_json_for_dict(self):
        _reset_config()
        result = safe_json_preview({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_redacts_api_key(self):
        _reset_config()
        result = safe_json_preview({"apiKey": "supersecret"})
        assert "supersecret" not in result
        assert "REDACTED" in result

    def test_redacts_whisparr_key(self):
        _reset_config()
        result = safe_json_preview({"WHISPARR_KEY": "mysecretkey"})
        assert "mysecretkey" not in result

    def test_truncates_long_output(self):
        _reset_config()
        large = {"data": "x" * 2000}
        result = safe_json_preview(large)
        assert len(result) <= 1100  # 1000 + "...(truncated)"
        assert "truncated" in result

    def test_handles_unserializable_gracefully(self):
        _reset_config()

        class Unserializable:
            def __str__(self):
                raise TypeError("cannot str")

        result = safe_json_preview(Unserializable())
        assert result == "<unserializable>"

    def test_handles_object_with_str_representation(self):
        _reset_config()
        result = safe_json_preview(object())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_handles_list(self):
        _reset_config()
        result = safe_json_preview([1, 2, 3])
        assert "[1" in result
