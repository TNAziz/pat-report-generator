"""Tests for the new ABET-cycle coverage helpers and the sub-outcome
course-lookup helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from pat import cache, data, ingest
from pat.analysis import coverage

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tier_a(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    for prog, fname in [
        ("CE",  "summaryReportCE_TierA.csv"),
        ("CON", "summaryReportCON_TierA.csv"),
        ("ENE", "summaryReportENE_TierA.csv"),
    ]:
        cache.save_upload(prog, (FIXTURES / fname).read_bytes(), fname)
    schedule = ingest.read_assessment_schedule(FIXTURES / "assessment_schedule_TierA.xlsx")
    return data.get_combined(), schedule


# -------- filter_semester_range --------


def test_filter_semester_range_inclusive(tier_a):
    df, _ = tier_a
    sliced = coverage.filter_semester_range(df, "Spring 2021", "Spring 2024")
    yrs = sliced["semester_year"].dropna().unique().tolist()
    # Spring 2020 (year 2020) excluded; Spring 2024 (year 2024) included.
    assert min(yrs) >= 2021
    assert max(yrs) <= 2024


def test_filter_semester_range_handles_reversed_bounds(tier_a):
    df, _ = tier_a
    a = coverage.filter_semester_range(df, "Spring 2021", "Spring 2024")
    b = coverage.filter_semester_range(df, "Spring 2024", "Spring 2021")
    assert len(a) == len(b)


def test_filter_semester_range_rejects_garbage(tier_a):
    df, _ = tier_a
    with pytest.raises(ValueError):
        coverage.filter_semester_range(df, "garbage", "Spring 2025")


# -------- cycle_coverage_heatmap --------


def test_cycle_heatmap_shape(tier_a):
    df, sched = tier_a
    h = coverage.cycle_coverage_heatmap(
        df, "Spring 2020", "Spring 2025",
        sub_outcomes=sched.suboutcome_columns,
    )
    # 13 sub-outcomes (Tier A fixture), 3 programs.
    assert len(h.rows) == len(sched.suboutcome_columns)
    assert h.columns == ["CE", "ENE", "CON"]  # PROGRAM_LABELS insertion order
    assert len(h.values) == len(h.rows)
    assert all(len(r) == len(h.columns) for r in h.values)


def test_cycle_heatmap_counts_submitted_only(tier_a):
    df, _ = tier_a
    h = coverage.cycle_coverage_heatmap(
        df, "Spring 2020", "Spring 2025",
        sub_outcomes=["1.1", "2.1"],
    )
    # Tier A: CE 282 has 1.1 entries in Spring 2020 / Spring 2021 / S24
    # (all with valid submitters) -> CE column for 1.1 should be > 0.
    ce_idx = h.columns.index("CE")
    row_11 = h.rows.index("1.1")
    assert h.values[row_11][ce_idx] >= 1


def test_cycle_heatmap_default_subset_when_no_explicit_codes(tier_a):
    df, _ = tier_a
    h = coverage.cycle_coverage_heatmap(df, "Spring 2020", "Spring 2025")
    # Should include only sub-outcomes that show up in submitted data.
    assert h.rows  # non-empty
    for code in h.rows:
        assert "." in code or code.isdigit()


def test_cycle_heatmap_title_includes_cycle_bounds(tier_a):
    df, _ = tier_a
    h = coverage.cycle_coverage_heatmap(df, "Fall 2023", "Spring 2025")
    assert "Fall 2023" in h.title
    assert "Spring 2025" in h.title


# -------- SubOutcomeSchedule.courses_for_suboutcome --------


def test_courses_for_suboutcome_known_code(tier_a):
    _, sched = tier_a
    courses = sched.courses_for_suboutcome("1.1")
    # Tier A fixture: CE 282 (CE), CE 464 (CE/CON) check 1.1.
    assert "CE" in courses
    assert "CE 282" in courses["CE"]
    assert "CE 464" in courses["CE"]
    assert "CON" in courses
    assert "CE 464" in courses["CON"]


def test_courses_for_suboutcome_returns_empty_for_unknown(tier_a):
    _, sched = tier_a
    assert sched.courses_for_suboutcome("9.9") == {}


def test_courses_for_suboutcome_sorted_within_program(tier_a):
    _, sched = tier_a
    # Pick 2.1 -- multiple courses across programs in the fixture.
    courses = sched.courses_for_suboutcome("2.1")
    for prog, lst in courses.items():
        # Course list sorted by (prefix, number).
        nums = []
        import re
        for c in lst:
            m = re.match(r"([A-Z]+)\s*(\d+)", c)
            nums.append((m.group(1), int(m.group(2))) if m else ("ZZ", 0))
        assert nums == sorted(nums)
