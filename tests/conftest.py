"""Pytest configuration shared across the test suite.

Forces a ``/tmp`` (or platform tmp dir) basetemp so that pytest's
fixture cleanup doesn't recurse into the project's filesystem mount
(which may be a slow/non-POSIX path like OneDrive on Windows).
"""

from __future__ import annotations

import os
import tempfile


def pytest_configure(config):
    if not config.getoption("--basetemp"):
        # Use the OS-default tmp dir, not the project tree.
        config.option.basetemp = os.path.join(tempfile.gettempdir(), "pat_pytest")
