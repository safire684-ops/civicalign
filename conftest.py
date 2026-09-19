"""Make `civicalign` importable from src/ without requiring an install.

The package is stdlib-only, so there is nothing to build and no reason to depend
on an editable install working. (In this environment the editable-install .pth
proved unreliable across invocations; PYTHONPATH is deterministic.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
