"""Unit tests for pat.analysis.coverage.

Traceability: R20 (semester listing), R21 (missing-by-blank-submitter),
R22 (semester summary stats), R23 (per-year summary stats),
R24 (trend chart in coverage report).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pat import cache, data
from pat.analysis import coverage

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tier_a_df(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    for prog, fname in [
        ("CE",  "summaryReportCE_TierA.csv"),
        ("CON", "summaryReportCON_TierA.csv"),
        ("ENE", "summaryReportENE_TierA.csv"),
    ]:
        cache.save_upload(prog, (FIXTURES / fname).read_bytes(), fname)
    return data.get_combined()


# -------- missing_for_semester (R21) --------


def test_missing_courses_blank_submitter(tier_a_df):
    """CE 342 in Spring 2025 has submitter='' in fixture (CE + CON)."""
    missing = coverage.missing_for_semester(tier_a_df, "Spring 2025")
    assert "CE 342" in missing["CE"]
    assert "CE 342" in missing["CON"]


def test_partially_assessed_not_flagged(tier_a_df):
    """CE 282 Spring 2020 has a real submitter -- should not be missing."""
    missing = coverage.missing_for_semester(tier_a_df, "Spring 2020")
    assert "CE 282" not in missing["CE"]


def test_missing_for_unknown_semester_returns_empty(tier_a_df):
    missing = coverage.missing_for_semester(tier_a_df, "Spring 9999")
    assert all(v == [] for v in missing.values())


# -------- semester_summary (R22) --------


def test_semester_summary_counts(tier_a_df):
    sem_sum = coverage.semester_summary(tier_a_df, "Spring 2025")
    # 3 program rows.
    assert len(sem_sum) == 3
    # CE in Spring 2025: only CE 342 row (with blank submitter) -> 0 assessed of 1.
    ce_row = sem_sum[sem_sum["program"] == "CE"].iloc[0]
    assert ce_row["total_courses"] == 1
    assert ce_row["missing_courses"] == 1
    assert ce_row["pct_missing"] == 100.0


def test_semester_summary_handles_empty_semester(tier_a_df):
    sem_sum = coverage.semester_summary(tier_a_df, "Spring 9999")
    # All zeros.
    assert (sem_sum["total_courses"] == 0).all()


# -------- per_year_summary (R23) --------


def test_per_year_summary_one_row_per_program_year(tier_a_df):
    yr = coverage.per_year_summary(tier_a_df)
    # Each (program, year) combo unique.
    assert yr.duplicated(subset=["program", "year"]).sum() == 0


def test_per_year_summary_counts_match_hand_computed(tier_a_df):
    yr = coverage.per_year_summary(tier_a_df)
    ce_2025 = yr[(yr["program"] == "CE") & (yr["year"] == 2025)]
    # CE 342 (blank submitter) in Spring 2025 -> 1 missing, 0 assessed.
    if not ce_2025.empty:
        row = ce_2025.iloc[0]
        assert row["missing_courses"] == 1
        assert row["assessed_courses"] == 0


def test_per_year_summary_respects_year_filter(tier_a_df):
    yr = coverage.per_year_summary(tier_a_df, year_min=2023, year_max=2025)
    assert yr["year"].min() >= 2023
    assert yr["year"].max() <= 2025


# -------- suboutcome_coverage_heatmap --------


def test_heatmap_emits_one_per_loaded_program(tier_a_df):
    heatmaps = coverage.suboutcome_coverage_heatmap(tier_a_df, 2020, 2025)
    progs = [h.title.split(":")[0] for h in heatmaps]
    # Order should be CE, CON, ENE.
    assert "Civil Engineering" in progs
    assert "Construction Engineering" in progs
    assert "Environmental Engineering" in progs


def test_heatmap_columns_span_year_range(tier_a_df):
    heatmaps = coverage.suboutcome_coverage_heatmap(tier_a_df, 2020, 2025)
    for h in heatmaps:
        assert h.columns == ["2020", "2021", "2022", "2023", "2024", "2025"]


def test_heatmap_counts_only_submitted(tier_a_df):
    """Rows with blank submitter (CE 342 Spring 2025) don't count toward coverage."""
    heatmaps = coverage.suboutcome_coverage_heatmap(tier_a_df, 2020, 2025)
    ce_h = next(h for h in heatmaps if "Civil Engineering" in h.title)
    if "2.1" in ce_h.rows:
        idx = ce_h.rows.index("2.1")
        # Fixture: CE 342 has 2.1 in Fall 2023 (submitter ok) and Spring 2025 (blank).
        # Only the 2023 row should count.
        col_2023 = ce_h.columns.index("2023")
        col_2025 = ce_h.columns.index("2025")
        assert ce_h.values[idx][col_2023] >= 1
        assert ce_h.values[idx][col_2025] == 0


def test_heatmap_uses_explicit_sub_outcomes_when_provided(tier_a_df):
    """Caller can pass a canonical sub-outcome list so zero-coverage rows appear."""
    codes = ["1.1", "2.1", "5.1", "7.2"]
    heatmaps = coverage.suboutcome_coverage_heatmap(
        tier_a_df, 2020, 2025, sub_outcomes=codes,
    )
    for h in heatmaps:
        assert h.rows == codes


# -------- check (top-level Report) --------


def test_check_returns_report_with_all_pieces(tier_a_df):
    r = coverage.check(tier_a_df, "Spring 2025", year_min=2020, year_max=2025)
    assert r.title == "Coverage Check"
    assert "Spring 2025" in (r.subtitle or "")
    assert r.tables  # missing + summary
    # Trend chart present (R24).
    assert r.charts
    # Heatmaps present.
    assert r.heatmaps


def test_check_omits_heatmap_when_requested(tier_a_df):
    r = coverage.check(tier_a_df, "Spring 2025", include_heatmap=False)
    assert r.heatmaps == []


def test_check_generated_on(tier_a_df):
    r = coverage.check(tier_a_df, "Spring 2025", generated_on=date(2024, 1, 1))
    assert r.generated_on == date(2024, 1, 1)
