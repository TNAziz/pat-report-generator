"""Per-user file cache for uploaded PAT exports.

Resolves a platform-appropriate data directory via :mod:`platformdirs`
unless the ``PAT_DATA_DIR`` environment variable overrides it. Stores
each program's most recent CSV with a single-step ``.bak`` backup, plus
the Assessment Schedule workbook, plus a ``manifest.json`` with upload
metadata.

This module has no Streamlit dependency and is safe to import in tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import platformdirs

from . import normalize as N

APP_NAME = "PAT-Report-Generator"
APP_AUTHOR = "NCSU-CCEE"

# File keys recognized by the cache. Programs use PROGRAM_LABELS keys.
SCHEDULE_KEY = "schedule"

# File naming inside the cache directory.
_PROGRAM_FILENAMES = {
    "CE": "pat_ce.csv",
    "CON": "pat_con.csv",
    "ENE": "pat_ene.csv",
    SCHEDULE_KEY: "assessment_schedule.xlsx",
}

_MANIFEST_NAME = "manifest.json"


def _all_keys():
    """All cache slot keys: programs plus the schedule slot."""
    return list(N.PROGRAM_LABELS.keys()) + [SCHEDULE_KEY]


def cache_dir() -> Path:
    """Return the per-user cache directory, creating it if needed.

    Honors the ``PAT_DATA_DIR`` environment variable as an override.
    """
    override = os.environ.get("PAT_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    else:
        path = Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass
class ManifestEntry:
    original_name: str
    uploaded_at: str        # ISO-8601 UTC
    sha256: str
    size_bytes: int

    def as_dict(self):
        return asdict(self)


def _manifest_path(dir_: Optional[Path] = None) -> Path:
    return (dir_ or cache_dir()) / _MANIFEST_NAME


def load_manifest(dir_: Optional[Path] = None) -> dict:
    """Read the manifest, or return an empty dict if absent / unreadable."""
    p = _manifest_path(dir_)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_manifest(manifest: dict, dir_: Optional[Path] = None) -> None:
    p = _manifest_path(dir_)
    with p.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Save / load / list / clear
# ---------------------------------------------------------------------------


def _slot_path(key: str, dir_: Optional[Path] = None) -> Path:
    if key not in _PROGRAM_FILENAMES:
        raise ValueError(
            "Unknown cache slot '" + str(key) + "'. Expected one of "
            + str(list(_PROGRAM_FILENAMES))
        )
    return (dir_ or cache_dir()) / _PROGRAM_FILENAMES[key]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_upload(
    key: str,
    file_bytes: bytes,
    original_name: str,
    *,
    dir_: Optional[Path] = None,
) -> Path:
    """Write file_bytes to the cache slot for `key`, with a one-step backup.

    Returns the absolute path of the newly-written file. Updates the
    manifest with original filename, timestamp, and SHA-256.
    """
    if key not in _PROGRAM_FILENAMES:
        raise ValueError(
            "Unknown cache slot '" + str(key) + "'. Expected one of "
            + str(list(_PROGRAM_FILENAMES))
        )
    target = _slot_path(key, dir_)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Keep one backup of the previous version, if any.
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)

    target.write_bytes(file_bytes)

    # Update manifest.
    manifest = load_manifest(dir_)
    manifest[key] = ManifestEntry(
        original_name=original_name,
        uploaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sha256=_sha256(file_bytes),
        size_bytes=len(file_bytes),
    ).as_dict()
    save_manifest(manifest, dir_)
    return target


def list_cached(dir_: Optional[Path] = None) -> dict:
    """Return a dict of {key: Path} for all currently-cached files."""
    out = {}
    base = dir_ or cache_dir()
    for key, name in _PROGRAM_FILENAMES.items():
        p = base / name
        if p.exists():
            out[key] = p
    return out


def is_cached(key: str, dir_: Optional[Path] = None) -> bool:
    return _slot_path(key, dir_).exists()


def clear(key: Optional[str] = None, *, dir_: Optional[Path] = None,
          remove_backups: bool = False) -> None:
    """Remove one cached file (or all, when key=None).

    Backups are preserved by default so a mistaken `clear` is recoverable;
    pass `remove_backups=True` for a hard wipe.
    """
    base = dir_ or cache_dir()
    keys = [key] if key else list(_PROGRAM_FILENAMES.keys())
    manifest = load_manifest(dir_)
    for k in keys:
        if k not in _PROGRAM_FILENAMES:
            raise ValueError("Unknown cache slot '" + str(k) + "'.")
        p = _slot_path(k, dir_)
        if p.exists():
            p.unlink()
        if remove_backups:
            bak = p.with_suffix(p.suffix + ".bak")
            if bak.exists():
                bak.unlink()
        manifest.pop(k, None)
    save_manifest(manifest, dir_)
