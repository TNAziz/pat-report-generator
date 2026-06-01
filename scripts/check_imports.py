"""Lint: no Streamlit or network library imports inside pat/.

Architectural invariant from specs/02_architecture.md: the `pat/`
package is pure domain logic and must not depend on Streamlit or pull
in any network library. Violations defeat unit testability and the
"all processing happens locally" non-functional requirement (N4, N7).

Run:
    python scripts/check_imports.py

Exit code 0 = clean, 1 = violations (with one line per offense printed
to stderr).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAT_DIR = PROJECT_ROOT / "pat"

FORBIDDEN = {
    "streamlit",
    # Network libraries -- the runtime path must be local-only.
    "requests",
    "httpx",
    "urllib",
    "urllib2",
    "urllib3",
    "aiohttp",
    "socket",
    "http",
}


def collect_imports(path: Path):
    """Yield (module_name, lineno) for every import statement in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module.split(".")[0], node.lineno


def main() -> int:
    violations = []
    if not PAT_DIR.is_dir():
        print("pat/ not found at " + str(PAT_DIR), file=sys.stderr)
        return 2
    for py in sorted(PAT_DIR.rglob("*.py")):
        rel = py.relative_to(PROJECT_ROOT)
        for mod, lineno in collect_imports(py):
            if mod in FORBIDDEN:
                violations.append(str(rel) + ":" + str(lineno) +
                                  " forbidden import '" + mod + "'")
    if violations:
        print("Forbidden imports found in pat/:", file=sys.stderr)
        for v in violations:
            print("  " + v, file=sys.stderr)
        return 1
    print("OK: no forbidden imports inside pat/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
