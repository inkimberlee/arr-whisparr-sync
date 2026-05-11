"""Tests for PluginConfig validators (B4 and general config)."""
import pytest
from pydantic import ValidationError

from config import PluginConfig


BASE = dict(WHISPARR_URL="http://whisparr:6969", WHISPARR_KEY="abc123")


class TestWhisparrUrlValidator:
    def test_bare_host_port_gets_http_scheme(self):
        """B4: bare host:port is prefixed with http://"""
        cfg = PluginConfig(**{**BASE, "WHISPARR_URL": "whisparr:6969"})
        assert cfg.WHISPARR_URL == "http://whisparr:6969"

    def test_bare_localhost_gets_scheme(self):
        cfg = PluginConfig(**{**BASE, "WHISPARR_URL": "localhost:6969"})
        assert cfg.WHISPARR_URL == "http://localhost:6969"

    def test_https_scheme_preserved(self):
        cfg = PluginConfig(**{**BASE, "WHISPARR_URL": "https://whisparr:6969"})
        assert cfg.WHISPARR_URL == "https://whisparr:6969"

    def test_http_scheme_preserved(self):
        cfg = PluginConfig(**{**BASE, "WHISPARR_URL": "http://whisparr:6969"})
        assert cfg.WHISPARR_URL == "http://whisparr:6969"

    def test_trailing_slash_stripped(self):
        cfg = PluginConfig(**{**BASE, "WHISPARR_URL": "http://whisparr:6969/"})
        assert cfg.WHISPARR_URL == "http://whisparr:6969"

    def test_trailing_slashes_stripped(self):
        cfg = PluginConfig(**{**BASE, "WHISPARR_URL": "whisparr:6969///"})
        assert cfg.WHISPARR_URL == "http://whisparr:6969"

    def test_whitespace_stripped(self):
        cfg = PluginConfig(**{**BASE, "WHISPARR_URL": "  whisparr:6969  "})
        assert cfg.WHISPARR_URL == "http://whisparr:6969"

    def test_empty_url_raises(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            PluginConfig(**{**BASE, "WHISPARR_URL": ""})

    def test_whitespace_only_url_raises(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            PluginConfig(**{**BASE, "WHISPARR_URL": "   "})


class TestWhisparrKeyValidator:
    def test_empty_key_raises(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            PluginConfig(**{**BASE, "WHISPARR_KEY": ""})

    def test_whitespace_key_raises(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            PluginConfig(**{**BASE, "WHISPARR_KEY": "   "})

    def test_valid_key_accepted(self):
        cfg = PluginConfig(**BASE)
        assert cfg.WHISPARR_KEY == "abc123"


class TestNormalizeIgnoreTags:
    def test_none_returns_empty_list(self):
        cfg = PluginConfig(**{**BASE, "IGNORE_TAGS": None})
        assert cfg.IGNORE_TAGS == []

    def test_empty_string_returns_empty_list(self):
        cfg = PluginConfig(**{**BASE, "IGNORE_TAGS": ""})
        assert cfg.IGNORE_TAGS == []

    def test_json_list_string_parsed(self):
        cfg = PluginConfig(**{**BASE, "IGNORE_TAGS": '["tag1", "tag2"]'})
        assert cfg.IGNORE_TAGS == ["tag1", "tag2"]

    def test_json_non_list_string_falls_back_to_split(self):
        """Non-list JSON (like a string) falls back to comma split."""
        cfg = PluginConfig(**{**BASE, "IGNORE_TAGS": '"tag1"'})
        assert isinstance(cfg.IGNORE_TAGS, list)


class TestNormalizePaths:
    def test_empty_string_root_folder_returns_none(self):
        cfg = PluginConfig(**{**BASE, "ROOT_FOLDER": ""})
        assert cfg.ROOT_FOLDER is None

    def test_none_root_folder_returns_none(self):
        cfg = PluginConfig(**{**BASE, "ROOT_FOLDER": None})
        assert cfg.ROOT_FOLDER is None

    def test_valid_path_resolved(self):
        from pathlib import Path
        cfg = PluginConfig(**{**BASE, "ROOT_FOLDER": "/data/scenes"})
        assert cfg.ROOT_FOLDER == Path("/data/scenes")

    def test_tilde_in_log_location_expanded(self):
        cfg = PluginConfig(**{**BASE, "LOG_FILE_LOCATION": "~/logs"})
        assert "~" not in str(cfg.LOG_FILE_LOCATION)


class TestNewConfigFields:
    def test_dry_run_defaults_false(self):
        cfg = PluginConfig(**BASE)
        assert cfg.DRY_RUN is False

    def test_dry_run_can_be_set(self):
        cfg = PluginConfig(**{**BASE, "DRY_RUN": True})
        assert cfg.DRY_RUN is True

    def test_bulk_delay_defaults(self):
        cfg = PluginConfig(**BASE)
        assert cfg.BULK_DELAY_SECONDS == 0.1

    def test_bulk_delay_can_be_zero(self):
        cfg = PluginConfig(**{**BASE, "BULK_DELAY_SECONDS": 0.0})
        assert cfg.BULK_DELAY_SECONDS == 0.0

    def test_root_folder_map_defaults_empty(self):
        cfg = PluginConfig(**BASE)
        assert cfg.ROOT_FOLDER_MAP == {}

    def test_root_folder_map_can_be_set(self):
        cfg = PluginConfig(**{**BASE, "ROOT_FOLDER_MAP": {"movies": "/data/movies", "scenes": "/data/scenes"}})
        assert cfg.ROOT_FOLDER_MAP["movies"] == "/data/movies"

    def test_ignore_tags_default_empty(self):
        cfg = PluginConfig(**BASE)
        assert cfg.IGNORE_TAGS == []

    def test_ignore_tags_from_list(self):
        cfg = PluginConfig(**{**BASE, "IGNORE_TAGS": ["skip", "ignore"]})
        assert "skip" in cfg.IGNORE_TAGS

    def test_ignore_tags_from_comma_string(self):
        cfg = PluginConfig(**{**BASE, "IGNORE_TAGS": "skip,ignore"})
        assert "skip" in cfg.IGNORE_TAGS
        assert "ignore" in cfg.IGNORE_TAGS
