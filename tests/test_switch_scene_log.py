"""Tests for switch_scene_log (B2 regression)."""
import logging
import tempfile
from pathlib import Path

import pytest

from config import switch_scene_log


def _make_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    return logger


def test_switch_scene_log_no_file_handler_is_noop():
    """B2: switch_scene_log must not raise when no FileHandler is attached."""
    logger = _make_logger("test_no_file_handler")
    logger.addHandler(logging.StreamHandler())
    # Should silently return, not raise RuntimeError
    switch_scene_log(logger, scene_id=42)


def test_switch_scene_log_no_handlers_is_noop():
    """B2: switch_scene_log must not raise when logger has no handlers at all."""
    logger = _make_logger("test_no_handlers")
    switch_scene_log(logger, scene_id=99)


def test_switch_scene_log_switches_file_handler():
    """switch_scene_log redirects the FileHandler to a scene-specific file."""
    logger = _make_logger("test_file_handler")
    with tempfile.TemporaryDirectory() as tmpdir:
        initial_log = Path(tmpdir) / "Whisparrsync.log"
        handler = logging.FileHandler(str(initial_log))
        logger.addHandler(handler)

        switch_scene_log(logger, scene_id=7)

        expected = Path(tmpdir) / "scene_7.log"
        assert Path(handler.baseFilename) == expected
        handler.close()


def test_switch_scene_log_only_switches_first_file_handler():
    """switch_scene_log only touches the first FileHandler it finds."""
    logger = _make_logger("test_multiple_handlers")
    with tempfile.TemporaryDirectory() as tmpdir:
        log1 = Path(tmpdir) / "log1.log"
        log2 = Path(tmpdir) / "log2.log"
        h1 = logging.FileHandler(str(log1))
        h2 = logging.FileHandler(str(log2))
        logger.addHandler(h1)
        logger.addHandler(h2)

        switch_scene_log(logger, scene_id=3)

        assert Path(h1.baseFilename) == Path(tmpdir) / "scene_3.log"
        assert Path(h2.baseFilename) == log2  # untouched
        h1.close()
        h2.close()
