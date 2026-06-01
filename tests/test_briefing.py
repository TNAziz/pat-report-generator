"""Unit tests for pat.analysis.briefing."""

from __future__ import annotations

from pathlib import Path

import pytest

from pat import cache, data, ingest
from pat.analysis import briefing

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


# -------- inventory --------


def test_inventory_basic(tier_a):
    df, sched = tier_a
    inv = briefing.inventory(df, schedule=sched)
    assert set(inv["programs"]) == {"CE", "CON", "ENE"}
    assert inv["courses"] >= 4  # Tier A has CE 282, CE 342, CE 464, CE 469, ENE 300, ENE 400
    assert inv["measurements"] > 0
    assert inv["year_min"] is not None and inv["year_max"] is not None
    assert inv["most_recent_semester"]  # non-empty
    assert inv["schedule_course_count"] == 7  # Tier A schedule has 7 courses


def test_inventory_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    inv = briefing.inventory(data.get_combined(), schedule=None)
    assert inv["programs"] == []
    assert inv["courses"] == 0
    assert inv["measurements"] == 0
    assert inv["year_min"] is None
    assert inv["schedule_course_count"] is None


def test_inventory_no_schedule(tier_a):
    df, _ = tier_a
    inv = briefing.inventory(df, schedule=None)
    assert inv["schedule_course_count"] is None


# -------- recent_semester_coverage --------


def test_recent_semester_coverage_returns_latest(tier_a):
    df, _ = tier_a
    rc = briefing.recent_semester_coverage(df)
    # Tier A's latest semester is Spring 2025.
    assert rc["semester"] == "Spring 2025"
    assert rc["per_program"]


def test_recent_semester_coverage_has_per_program_counts(tier_a):
    df, _ = tier_a
    rc = briefing.recent_semester_coverage(df)
    progs = {row["program"] for row in rc["per_program"]}
    assert progs == {"CE", "CON", "ENE"}
    for row in rc["per_program"]:
        assert row["total"] >= 0
        assert row["assessed"] + row["missing"] == row["total"]
        if row["total"]:
            assert 0 <= row["pct_assessed"] <= 100


def test_recent_semester_coverage_missing_list_present(tier_a):
    df, _ = tier_a
    rc = briefing.recent_semester_coverage(df)
    # Tier A's Spring 2025 has CE 342 missing in both CE and CON.
    ce_row = next(r for r in rc["per_program"] if r["program"] == "CE")
    assert "CE 342" in ce_row["missing_courses"]


def test_recent_semester_coverage_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    rc = briefing.recent_semester_coverage(data.get_combined())
    assert rc["semester"] is None
    assert rc["per_program"] == []


# -------- below_threshold_summary --------


def test_below_threshold_summary_default_uses_most_recent_year(tier_a):
    df, _ = tier_a
    bt = briefing.below_threshold_summary(df)
    assert bt["year"] is not None
    assert len(bt["per_program"]) == 3


def test_below_threshold_summary_finds_known_below(tier_a):
    df, _ = tier_a
    # Tier A: CE 282 Spring 2021 has performance=60, indicator=70.
    bt = briefing.below_threshold_summary(df, year=2021, top_n=10)
    found = any(
        item["course"] == "CE 282" and item["suboutcome"] == "1.1"
        for item in bt["top_items"]
    )
    assert found, f"expected CE 282 1.1 in top_items, got {bt['top_items']}"


def test_below_threshold_summary_top_items_sorted_worst_first(tier_a):
    df, _ = tier_a
    bt = briefing.below_threshold_summary(df, top_n=10)
    gaps = [item["gap"] for item in bt["top_items"]]
    assert gaps == sorted(gaps, reverse=True)


def test_below_threshold_summary_respects_top_n(tier_a):
    df, _ = tier_a
    bt = briefing.below_threshold_summary(df, top_n=2)
    assert len(bt["top_items"]) <= 2


def test_below_threshold_summary_empty_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    bt = briefing.below_threshold_summary(data.get_combined())
    assert bt["year"] is None
    assert bt["per_program"] == []
    assert bt["top_items"] == []
