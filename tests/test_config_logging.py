"""Tests for ColoredFormatter, setup_logger, StashHandler, and load_config_logging."""
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config as cfg_module
from config import ColoredFormatter, StashHandler, setup_logger


def _make_config(
    log_file=False,
    log_console=True,
    log_level="INFO",
    log_file_level="DEBUG",
    log_file_use_color=False,
    log_file_location=None,
):
    cfg = MagicMock()
    cfg.LOG_FILE_ENABLE = log_file
    cfg.LOG_CONSOLE_ENABLE = log_console
    cfg.LOG_LEVEL = log_level
    cfg.LOG_FILE_LEVEL = log_file_level
    cfg.LOG_FILE_USE_COLOR = log_file_use_color
    cfg.LOG_FILE_LOCATION = log_file_location or Path("/tmp/test-logs")
    return cfg


class TestColoredFormatter:
    def test_format_with_color(self):
        formatter = ColoredFormatter("%(message)s", use_color=True)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        result = formatter.format(record)
        assert "hello" in result
        assert "\033[" in result  # ANSI escape sequence

    def test_format_without_color(self):
        formatter = ColoredFormatter("%(message)s", use_color=False)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        result = formatter.format(record)
        assert result == "hello"
        assert "\033[" not in result

    def test_unknown_level_no_color(self):
        formatter = ColoredFormatter("%(message)s", use_color=True)
        record = logging.LogRecord(
            name="test", level=logging.NOTSET, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.levelname = "CUSTOM"
        result = formatter.format(record)
        assert "msg" in result


class TestSetupLogger:
    def test_console_handler_added(self):
        cfg = _make_config(log_console=True, log_file=False)
        log = setup_logger(cfg)
        assert any(isinstance(h, logging.StreamHandler) for h in log.handlers)

    def test_no_handlers_when_both_disabled(self):
        cfg = _make_config(log_console=False, log_file=False)
        log = setup_logger(cfg)
        assert len(log.handlers) == 0

    def test_file_handler_added(self, tmp_path):
        cfg = _make_config(log_file=True, log_console=False, log_file_location=tmp_path)
        log = setup_logger(cfg)
        assert any(isinstance(h, logging.FileHandler) for h in log.handlers)

    def test_file_handler_respects_level(self, tmp_path):
        cfg = _make_config(log_file=True, log_console=False, log_file_level="WARNING", log_file_location=tmp_path)
        log = setup_logger(cfg)
        file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
        assert file_handlers[0].level == logging.WARNING


class TestStashHandler:
    def test_emit_calls_stash_log_method(self):
        stash_log = MagicMock()
        handler = StashHandler(stash_log)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="stash message", args=(), exc_info=None,
        )
        handler.emit(record)
        stash_log.info.assert_called_once()

    def test_emit_uses_correct_log_level(self):
        stash_log = MagicMock()
        handler = StashHandler(stash_log)
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="warning msg", args=(), exc_info=None,
        )
        handler.emit(record)
        stash_log.warning.assert_called_once()

    def test_emit_handles_exception_gracefully(self):
        stash_log = MagicMock()
        stash_log.info.side_effect = Exception("logging failure")
        handler = StashHandler(stash_log)
        handler.handleError = MagicMock()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        handler.emit(record)
        handler.handleError.assert_called_once()
