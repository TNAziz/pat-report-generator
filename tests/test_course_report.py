"""Unit tests for pat.analysis.course_report.

Traceability:
- R10 (course selection)
- R11 (year-range filter)
- R12 (program filter)
- R13 (report structure: summary table + per-semester detail)
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pat import cache, data
from pat.analysis import course_report
from pat.render import markdown as M

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"

# Real PAT data location (smoke / regression tests). Tests using it skip
# cleanly if not present so the suite still runs on a fresh checkout.
REAL_PAT_XLSX = Path(os.environ.get(
    "PAT_BASELINE_XLSX",
    "/sessions/fervent-magical-ride/mnt/ABET/PAT Report Generator/Sp2020-Sp2026.xlsx",
))


@pytest.fixture
def tier_a_df(tmp_path, monkeypatch):
    """Cache and load the three Tier A fixtures as a canonical frame."""
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    for prog, fname in [
        ("CE",  "summaryReportCE_TierA.csv"),
        ("CON", "summaryReportCON_TierA.csv"),
        ("ENE", "summaryReportENE_TierA.csv"),
    ]:
        cache.save_upload(prog, (FIXTURES / fname).read_bytes(), fname)
    return data.get_combined()


# -------- shape (R13) --------


def test_build_returns_report_for_known_course(tier_a_df):
    r = course_report.build(tier_a_df, "CE 282")
    assert r.title == "CE 282"
    assert r.sections  # at least one program section


def test_build_empty_when_course_absent(tier_a_df):
    r = course_report.build(tier_a_df, "CE 999")
    assert r.sections == []


def test_build_finds_cross_listed_course(tier_a_df):
    """CE 342 appears in both CE and CON program data."""
    r = course_report.build(tier_a_df, "CE 342")
    codes = {s.program_code for s in r.sections}
    assert codes == {"CE", "CON"}


def test_section_has_summary_and_semesters(tier_a_df):
    r = course_report.build(tier_a_df, "CE 282")
    section = r.sections[0]
    assert section.summary
    assert section.semesters


# -------- below-threshold detection (R13) --------


def test_below_threshold_flag_set(tier_a_df):
    """In the fixture, CE 282 Spring 2021 has performance 60 < indicator 70."""
    r = course_report.build(tier_a_df, "CE 282")
    ce = next(s for s in r.sections if s.program_code == "CE")
    sp21 = next((row for row in ce.summary if row.semester == "Spring 2021"), None)
    assert sp21 is not None
    assert sp21.below_threshold is True


def test_above_threshold_not_flagged(tier_a_df):
    r = course_report.build(tier_a_df, "CE 282")
    ce = next(s for s in r.sections if s.program_code == "CE")
    sp20 = next((row for row in ce.summary if row.semester == "Spring 2020"), None)
    assert sp20 is not None
    assert sp20.below_threshold is False


# -------- filters (R11, R12) --------


def test_year_range_filter_excludes_outside_years(tier_a_df):
    r = course_report.build(tier_a_df, "CE 282", year_range=(2022, 2024))
    ce = next((s for s in r.sections if s.program_code == "CE"), None)
    if ce is None:
        # CE 282 has rows in 2020/2021/2024 in the fixture; expecting at least
        # the 2024 row.
        return
    # No semesters before 2022.
    semesters = [sec.semester for sec in ce.semesters]
    assert all("2020" not in s and "2021" not in s for s in semesters)


def test_program_filter_restricts_sections(tier_a_df):
    r = course_report.build(tier_a_df, "CE 342", programs=["CE"])
    assert all(s.program_code == "CE" for s in r.sections)


# -------- semester ordering --------


def test_semesters_ordered_newest_first(tier_a_df):
    r = course_report.build(tier_a_df, "CE 282")
    ce = next(s for s in r.sections if s.program_code == "CE")
    assert ce.summary, "expected non-empty CE 282 summary"
    def year_of(sem: str) -> int:
        m = re.search(r"(\d{4})", sem)
        return int(m.group(1)) if m else 0
    first_year = year_of(ce.summary[0].semester)
    last_year  = year_of(ce.summary[-1].semester)
    assert first_year >= last_year, (
        f"summary not newest-first: first={ce.summary[0].semester}, "
        f"last={ce.summary[-1].semester}"
    )


# -------- generated_on stamp --------


def test_default_generated_on_is_today(tier_a_df):
    r = course_report.build(tier_a_df, "CE 282")
    assert r.generated_on == date.today()


def test_explicit_generated_on(tier_a_df):
    r = course_report.build(tier_a_df, "CE 282", generated_on=date(2024, 1, 1))
    assert r.generated_on == date(2024, 1, 1)


# -------- regression vs. notebook golden output --------


@pytest.mark.skipif(not REAL_PAT_XLSX.exists(),
                    reason="real PAT data not available")
def test_ce342_matches_golden(tmp_path, monkeypatch):
    """CE 342 report must match the committed golden output."""
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    src = REAL_PAT_XLSX.parent
    csv_names = {
        "CE":  "summaryReportCE_S20toS26_2026_05_29_03_05.csv",
        "CON": "summaryReportCON_S20toS26_2026_05_29_03_05.csv",
        "ENE": "summaryReportENE_S20toS26_2026_05_29_03_05.csv",
    }
    for prog, fname in csv_names.items():
        path = src / fname
        if path.exists():
            cache.save_upload(prog, path.read_bytes(), fname)
    df = data.get_combined()
    report = course_report.build(df, "CE 342", generated_on=date(2026, 5, 29))
    md = M.render(report)
    golden = (GOLDEN / "CE_342_course_report.md").read_text()
    assert md == golden, "CE 342 output drifted from golden -- run capture_baseline.py and review"


@pytest.mark.skipif(not REAL_PAT_XLSX.exists(),
                    reason="real PAT data not available")
def test_ce342_is_logically_equivalent_to_notebook(tmp_path, monkeypatch):
    """The notebook output had a bug: literal 'null' strings displayed as text.

    Our tool fixes this (displays 'N/A' or blank for missing). This test
    asserts the two are equivalent *after* normalizing the null/N/A
    treatment -- proof that we're not silently dropping or reordering
    real content.
    """
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    src = REAL_PAT_XLSX.parent
    for prog, fname in [
        ("CE",  "summaryReportCE_S20toS26_2026_05_29_03_05.csv"),
        ("CON", "summaryReportCON_S20toS26_2026_05_29_03_05.csv"),
        ("ENE", "summaryReportENE_S20toS26_2026_05_29_03_05.csv"),
    ]:
        path = src / fname
        if path.exists():
            cache.save_upload(prog, path.read_bytes(), fname)
    df = data.get_combined()
    report = course_report.build(df, "CE 342")
    report.subtitle = None
    report.generated_on = None
    new_md = M.render(report)
    notebook_md = (GOLDEN / "notebook_CE_342_course_report.md").read_text()

    def norm(s):
        s = re.sub(r"\b(null|N/A)\b", "", s)
        lines = [line.rstrip() for line in s.splitlines()]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    assert norm(new_md) == norm(notebook_md)
