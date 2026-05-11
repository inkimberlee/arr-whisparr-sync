"""
Test configuration and shared fixtures.

whisparr-sync.py uses a hyphenated filename that Python's import system cannot
load directly. We register it as 'whisparr_sync' in sys.modules here so all
test files can simply `from whisparr_sync import ...`.
"""
import importlib.util
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).parent.parent / "plugins" / "whisparr-sync"

# Make the plugin directory importable (for config, etc.)
sys.path.insert(0, str(_PLUGIN_DIR))

# Register whisparr-sync.py under an importable name
_spec = importlib.util.spec_from_file_location(
    "whisparr_sync", _PLUGIN_DIR / "whisparr-sync.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["whisparr_sync"] = _mod
_spec.loader.exec_module(_mod)
