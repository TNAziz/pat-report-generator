"""Unit tests for pat.data.

Traceability: R5 (combined frame with program column), R10 (course list),
R11 (year range filter), R12 (program filter), R20 (semester listing).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pat import cache, data

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def populated_cache(tmp_path, monkeypatch):
    """Cache pre-seeded with all three Tier A fixtures and the schedule."""
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    cache.save_upload("CE", (FIXTURES / "summaryReportCE_TierA.csv").read_bytes(),
                      "summaryReportCE_TierA.csv")
    cache.save_upload("CON", (FIXTURES / "summaryReportCON_TierA.csv").read_bytes(),
                      "summaryReportCON_TierA.csv")
    cache.save_upload("ENE", (FIXTURES / "summaryReportENE_TierA.csv").read_bytes(),
                      "summaryReportENE_TierA.csv")
    cache.save_upload(cache.SCHEDULE_KEY,
                      (FIXTURES / "assessment_schedule_TierA.xlsx").read_bytes(),
                      "assessment_schedule_TierA.xlsx")
    return tmp_path


# -------- load_program / get_combined (R5) --------


def test_load_program_returns_canonical_frame(populated_cache):
    df = data.load_program("CE")
    assert not df.empty
    assert set(df["program"].astype(str).unique()) == {"CE"}
    # Canonical column present.
    for col in ("course_key", "semester_year", "performance_indicator"):
        assert col in df.columns


def test_load_program_empty_when_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    assert data.load_program("CE").empty


def test_get_combined_concatenates_all_programs(populated_cache):
    df = data.get_combined()
    progs = set(df["program"].astype(str).unique())
    assert progs == {"CE", "CON", "ENE"}


def test_get_combined_preserves_row_counts(populated_cache):
    ce = data.load_program("CE")
    con = data.load_program("CON")
    ene = data.load_program("ENE")
    combined = data.get_combined()
    assert len(combined) == len(ce) + len(con) + len(ene)


def test_get_combined_empty_when_nothing_loaded(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    assert data.get_combined().empty


# -------- schedule --------


def test_load_schedule_returns_wrapper(populated_cache):
    sched = data.load_schedule()
    assert sched is not None
    assert "CE 488" in sched.all_courses()


def test_load_schedule_none_when_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    assert data.load_schedule() is None


# -------- surfaces (R10, R20) --------


def test_get_loaded_programs(populated_cache):
    assert data.get_loaded_programs() == ["CE", "CON", "ENE"]


def test_get_loaded_courses_sorted(populated_cache):
    courses = data.get_loaded_courses()
    # Sample some expected values.
    for c in ("CE 282", "CE 342", "CE 464", "CE 469", "ENE 300", "ENE 400"):
        assert c in courses
    # Sorted by program prefix then number: CE before ENE.
    assert courses.index("CE 282") < courses.index("ENE 300")


def test_get_loaded_semesters_newest_first(populated_cache):
    sems = data.get_loaded_semesters()
    assert sems  # non-empty
    # Spring 2025 should appear before Spring 2020.
    s2025 = sems.index("Spring 2025") if "Spring 2025" in sems else None
    s2020 = sems.index("Spring 2020") if "Spring 2020" in sems else None
    assert s2025 is not None and s2020 is not None
    assert s2025 < s2020


def test_get_year_range(populated_cache):
    lo, hi = data.get_year_range()
    assert lo <= 2020
    assert hi >= 2025


# -------- filters (R11, R12) --------


def test_filter_course(populated_cache):
    df = data.get_combined()
    only = data.filter_course(df, "CE 342")
    assert set(only["course_key"].unique()) == {"CE342"}
    # Both CE and CON programs have CE 342.
    assert set(only["program"].astype(str).unique()) == {"CE", "CON"}


def test_filter_course_normalizes_input(populated_cache):
    df = data.get_combined()
    a = data.filter_course(df, "CE 342")
    b = data.filter_course(df, "ce-342")
    c = data.filter_course(df, "  CE342 ")
    assert len(a) == len(b) == len(c)
    assert len(a) > 0


def test_filter_year_range(populated_cache):
    df = data.get_combined()
    narrow = data.filter_year_range(df, 2022, 2024)
    # No Spring 2020 / Spring 2021 / Spring 2025 rows after filtering.
    assert (narrow["semester_year"] < 2022).sum() == 0
    assert (narrow["semester_year"] > 2024).sum() == 0


def test_filter_programs(populated_cache):
    df = data.get_combined()
    ce_only = data.filter_programs(df, ["CE"])
    assert set(ce_only["program"].astype(str).unique()) == {"CE"}
