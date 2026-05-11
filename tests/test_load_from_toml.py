"""Tests for load_from_toml in config module and whisparr_sync module."""
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config as cfg_module
from config import load_from_toml as config_load_from_toml
from whisparr_sync import load_from_toml as sync_load_from_toml


@pytest.fixture(autouse=True)
def reset_config():
    """Restore global CONFIG after each test in this module."""
    original = cfg_module.CONFIG
    yield
    cfg_module.CONFIG = original


class TestConfigLoadFromToml:
    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        result = config_load_from_toml(str(tmp_path / "missing.toml"))
        assert result == {}

    def test_returns_dict_for_valid_toml(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text('[section]\nkey = "value"\n')
        result = config_load_from_toml(str(f))
        assert result == {"section": {"key": "value"}}

    def test_returns_top_level_keys(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text('WHISPARR_URL = "http://localhost:6969"\nWHISPARR_KEY = "abc"\n')
        result = config_load_from_toml(str(f))
        assert result["WHISPARR_URL"] == "http://localhost:6969"


class TestSyncLoadFromToml:
    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        result = sync_load_from_toml(str(tmp_path / "missing.toml"))
        assert result == {}

    def test_returns_dict_for_valid_toml(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text('[section]\nkey = "value"\n')
        result = sync_load_from_toml(str(f))
        assert result == {"section": {"key": "value"}}


class TestLoadPluginConfig:
    def test_returns_config_for_valid_toml(self, tmp_path):
        from config import load_plugin_config
        f = tmp_path / "config.toml"
        f.write_text('WHISPARR_URL = "http://localhost"\nWHISPARR_KEY = "key"\n')
        config = load_plugin_config(toml_path=str(f))
        assert config.WHISPARR_KEY == "key"

    def test_logs_not_found_when_toml_missing(self, tmp_path):
        from config import load_plugin_config
        with pytest.raises(Exception):
            load_plugin_config(
                toml_path=str(tmp_path / "missing.toml"),
            )

    def test_uses_stash_config_when_provided(self, tmp_path):
        """Stash UI settings are merged when stash dict is provided."""
        from config import load_plugin_config
        stash_data = {
            "server_connection": {"url": "http://stash:9999", "ApiKey": "stashkey"},
        }
        mock_iface = MagicMock()
        mock_iface.get_configuration.return_value = {
            "plugins": {
                "whisparr-sync": {
                    "WHISPARR_URL": "http://whisparr",
                    "WHISPARR_KEY": "fromstash",
                }
            }
        }
        with patch("config.StashInterface", return_value=mock_iface):
            config = load_plugin_config(toml_path="/nonexistent/config.toml", stash=stash_data)
        assert config.WHISPARR_KEY == "fromstash"

    def test_handles_stash_config_exception_gracefully(self, tmp_path):
        """Exception fetching Stash config is logged, not raised."""
        from config import load_plugin_config
        f = tmp_path / "config.toml"
        f.write_text('WHISPARR_URL = "http://localhost"\nWHISPARR_KEY = "key"\n')
        stash_data = {"server_connection": {}}
        mock_iface = MagicMock()
        mock_iface.get_configuration.side_effect = Exception("stash down")
        with patch("config.StashInterface", return_value=mock_iface):
            config = load_plugin_config(toml_path=str(f), stash=stash_data)
        assert config.WHISPARR_KEY == "key"

    def test_raises_when_toml_is_corrupt(self, tmp_path):
        """Exception during TOML load is re-raised."""
        from config import load_plugin_config
        f = tmp_path / "config.toml"
        f.write_bytes(b"\xff\xfe invalid toml bytes")
        with pytest.raises(Exception):
            load_plugin_config(toml_path=str(f))

    def test_raises_validation_error_when_required_fields_missing(self, tmp_path):
        """Missing WHISPARR_URL/KEY causes ValidationError."""
        from config import load_plugin_config
        f = tmp_path / "config.toml"
        f.write_text("BULK_DELAY_SECONDS = 0.0\n")  # no URL or KEY
        with pytest.raises(Exception):
            load_plugin_config(toml_path=str(f))


class TestLoadConfigLogging:
    def test_returns_logger_and_config_in_dev_mode(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text('WHISPARR_URL = "http://localhost"\nWHISPARR_KEY = "key"\n')

        from config import load_config_logging
        python_logger, config = load_config_logging(
            toml_path=str(f), STASH_DATA={}, dev=True
        )
        import logging
        assert isinstance(python_logger, logging.Logger)
        assert config.WHISPARR_KEY == "key"

    def test_adds_stash_handler_in_non_dev_mode(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text('WHISPARR_URL = "http://localhost"\nWHISPARR_KEY = "key"\n')

        from config import load_config_logging, StashHandler
        import logging

        with patch("config.load_plugin_config") as mock_lpc, \
             patch("config.setup_logger") as mock_sl:
            mock_config = MagicMock()
            mock_lpc.return_value = mock_config
            mock_logger = MagicMock(spec=logging.Logger)
            mock_logger.handlers = []
            mock_sl.return_value = mock_logger

            python_logger, config = load_config_logging(
                toml_path=str(f), STASH_DATA={"server_connection": {}}, dev=False
            )
            mock_logger.addHandler.assert_called_once()
            added = mock_logger.addHandler.call_args[0][0]
            assert isinstance(added, StashHandler)
