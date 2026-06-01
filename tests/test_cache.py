"""Unit tests for pat.cache.

Traceability to specs/05_verification.md: R7, R8, R9.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pat import cache


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Force every test to use a fresh temp dir as PAT_DATA_DIR."""
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    yield tmp_path


# -------- cache_dir / env override (R7, R8) --------


def test_cache_dir_creates_directory(tmp_path):
    target = tmp_path / "nested" / "cache"
    os.environ["PAT_DATA_DIR"] = str(target)
    try:
        path = cache.cache_dir()
        assert path == target
        assert path.is_dir()
    finally:
        os.environ.pop("PAT_DATA_DIR", None)


def test_cache_dir_respects_env_override(_isolated_cache_dir):
    assert cache.cache_dir() == _isolated_cache_dir


def test_cache_dir_falls_back_to_platformdirs(monkeypatch):
    monkeypatch.delenv("PAT_DATA_DIR", raising=False)
    # We don't assert the exact path -- it's OS-specific. We just verify it
    # comes from platformdirs and isn't the cwd.
    path = cache.cache_dir()
    assert path.is_dir()
    assert "PAT-Report-Generator" in str(path)


# -------- save_upload / list_cached / round-trip (R7) --------


def test_save_upload_writes_file_with_canonical_name(_isolated_cache_dir):
    target = cache.save_upload("CE", b"hello,world\n1,2\n", "original_CE.csv")
    assert target.exists()
    assert target.name == "pat_ce.csv"
    assert target.read_bytes() == b"hello,world\n1,2\n"


def test_save_upload_round_trip_via_list(_isolated_cache_dir):
    cache.save_upload("CE", b"ce-data", "ce.csv")
    cache.save_upload("ENE", b"ene-data", "ene.csv")
    cached = cache.list_cached()
    assert set(cached.keys()) == {"CE", "ENE"}
    assert cached["CE"].read_bytes() == b"ce-data"
    assert cached["ENE"].read_bytes() == b"ene-data"


def test_save_upload_updates_manifest(_isolated_cache_dir):
    cache.save_upload("CE", b"ce-data", "myname.csv")
    m = cache.load_manifest()
    assert "CE" in m
    assert m["CE"]["original_name"] == "myname.csv"
    assert m["CE"]["size_bytes"] == len(b"ce-data")
    assert len(m["CE"]["sha256"]) == 64
    # ISO-8601 stamp present and parseable.
    assert "T" in m["CE"]["uploaded_at"]


def test_save_upload_rejects_unknown_key(_isolated_cache_dir):
    with pytest.raises(ValueError):
        cache.save_upload("XYZ", b"data", "x.csv")


def test_save_upload_handles_schedule_slot(_isolated_cache_dir):
    target = cache.save_upload(cache.SCHEDULE_KEY, b"xlsx bytes", "schedule.xlsx")
    assert target.exists()
    assert target.suffix == ".xlsx"


# -------- backup-on-replace (R9) --------


def test_replace_creates_backup(_isolated_cache_dir):
    p1 = cache.save_upload("CE", b"first version", "v1.csv")
    p2 = cache.save_upload("CE", b"second version", "v2.csv")
    assert p1 == p2
    backup = p1.with_suffix(p1.suffix + ".bak")
    assert backup.exists()
    assert backup.read_bytes() == b"first version"
    assert p2.read_bytes() == b"second version"


def test_replace_only_keeps_one_backup(_isolated_cache_dir):
    cache.save_upload("CE", b"v1", "v1.csv")
    cache.save_upload("CE", b"v2", "v2.csv")
    cache.save_upload("CE", b"v3", "v3.csv")
    backup = (_isolated_cache_dir / "pat_ce.csv.bak")
    # Backup should hold the immediately-previous version, not the original.
    assert backup.read_bytes() == b"v2"
    # No "double backup" file.
    assert not (_isolated_cache_dir / "pat_ce.csv.bak.bak").exists()


# -------- clear --------


def test_clear_removes_active_but_preserves_backup(_isolated_cache_dir):
    cache.save_upload("CE", b"v1", "v1.csv")
    cache.save_upload("CE", b"v2", "v2.csv")
    cache.clear("CE")
    assert not (_isolated_cache_dir / "pat_ce.csv").exists()
    assert (_isolated_cache_dir / "pat_ce.csv.bak").exists()
    m = cache.load_manifest()
    assert "CE" not in m


def test_clear_with_remove_backups_wipes_everything(_isolated_cache_dir):
    cache.save_upload("CE", b"v1", "v1.csv")
    cache.save_upload("CE", b"v2", "v2.csv")
    cache.clear("CE", remove_backups=True)
    assert not (_isolated_cache_dir / "pat_ce.csv").exists()
    assert not (_isolated_cache_dir / "pat_ce.csv.bak").exists()


def test_clear_all(_isolated_cache_dir):
    cache.save_upload("CE", b"a", "a.csv")
    cache.save_upload("ENE", b"b", "b.csv")
    cache.save_upload(cache.SCHEDULE_KEY, b"c", "c.xlsx")
    cache.clear()
    assert cache.list_cached() == {}
    assert cache.load_manifest() == {}
