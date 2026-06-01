"""Architectural invariant tests.

Traceability: N4 (no network in pat/), N7 (no streamlit in pat/,
stub modules present).
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_imports_script_passes():
    """scripts/check_imports.py must exit 0 (no forbidden imports)."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_imports.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        "check_imports.py reported violations:\n" + result.stderr
    )


def test_stub_modules_present():
    """Future-extension stubs (pat.viz, pat.llm) must import cleanly."""
    for name in ("pat.viz", "pat.llm"):
        mod = importlib.import_module(name)
        assert mod is not None
