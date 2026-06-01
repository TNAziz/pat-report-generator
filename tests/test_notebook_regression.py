"""Regression tests vs. notebook baselines captured in Phase 1.

Strategy:
- For the Course Report: the new tool's output should be byte-identical
  to ``tests/golden/CE_342_course_report.md`` (the corrected baseline).
  It is also *logically equivalent* to the original notebook output --
  the only diffs are the notebook's literal-"null"-string bug that the
  new tool intentionally fixes.
- For the Coverage Check: the new tool's missing list and per-program
  summary should match the captured notebook outputs.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pat import cache, data
from pat.analysis import coverage, course_report
from pat.render import markdown as M

GOLDEN = Path(__file__).parent / "golden"
REAL_XLSX = Path(os.environ.get(
    "PAT_BASELINE_XLSX",
    "/sessions/fervent-magical-ride/mnt/ABET/PAT Report Generator/Sp2020-Sp2026.xlsx",
))


pytestmark = pytest.mark.skipif(
    not REAL_XLSX.exists(),
    reason="real PAT data not available",
)


@pytest.fixture
def real_df(tmp_path, monkeypatch):
    monkeypatch.setenv("PAT_DATA_DIR", str(tmp_path))
    src = REAL_XLSX.parent
    for prog, fname in [
        ("CE",  "summaryReportCE_S20toS26_2026_05_29_03_05.csv"),
        ("CON", "summaryReportCON_S20toS26_2026_05_29_03_05.csv"),
        ("ENE", "summaryReportENE_S20toS26_2026_05_29_03_05.csv"),
    ]:
        path = src / fname
        if path.exists():
            cache.save_upload(prog, path.read_bytes(), fname)
    return data.get_combined()


def test_ce342_course_report_matches_corrected_golden(real_df):
    r = course_report.build(real_df, "CE 342", generated_on=date(2026, 5, 29))
    md = M.render(r)
    golden = (GOLDEN / "CE_342_course_report.md").read_text()
    assert md == golden, (
        "CE 342 output drifted from the committed golden. Investigate "
        "before regenerating with: PAT_DATA_DIR=/tmp/pat_smoke python -m "
        "tests.capture_baseline (regenerate script will refresh the golden)."
    )


def test_ce342_logically_equivalent_to_notebook(real_df):
    r = course_report.build(real_df, "CE 342")
    r.subtitle = None
    r.generated_on = None
    new_md = M.render(r)
    notebook_md = (GOLDEN / "notebook_CE_342_course_report.md").read_text()

    def norm(s):
        # Collapse notebook 'null' bug -> our 'N/A'/'' treatment.
        s = re.sub(r"\b(null|N/A)\b", "", s)
        lines = [line.rstrip() for line in s.splitlines()]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    assert norm(new_md) == norm(notebook_md)


def test_spring2025_missing_list_matches_notebook(real_df):
    notebook_md = (GOLDEN / "notebook_Spring_2025_coverage.md").read_text()
    missing = coverage.missing_for_semester(real_df, "Spring 2025")
    # Each notebook bullet should appear in our missing list under the
    # right program; and every program's count should match.
    for line in notebook_md.splitlines():
        if line.startswith("- "):
            course = line[2:].strip()
            # Find which program this bullet falls under.
            # Notebook format: section header "## CE" then bullets.
            # Walk the file to find the bullet's section.
        # (full structural diff next)

    # Structural compare: parse the notebook md.
    nb = {}
    cur = None
    for line in notebook_md.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            nb[cur] = []
        elif line.startswith("- ") and cur is not None:
            nb[cur].append(line[2:].strip())
    # Drop any programs the notebook had as empty.
    nb = {k: sorted(v) for k, v in nb.items() if v}
    ours = {k: sorted(v) for k, v in missing.items() if v}
    assert nb == ours, f"missing-list drift: notebook={nb}, ours={ours}"


def test_spring2025_semester_summary_matches_notebook(real_df):
    sem_sum = coverage.semester_summary(real_df, "Spring 2025")
    notebook_csv = pd.read_csv(GOLDEN / "notebook_Spring_2025_semester_summary.csv")
    # Compare the per-program counts (the percentage columns are floats so
    # we round before comparing).
    cols = ["program", "total_courses", "assessed_courses", "missing_courses"]
    a = sem_sum[cols].sort_values("program").reset_index(drop=True)
    b = notebook_csv[cols].sort_values("program").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_per_year_summary_matches_notebook(real_df):
    yr_sum = coverage.per_year_summary(real_df)
    notebook_csv = pd.read_csv(GOLDEN / "notebook_per_year_summary.csv")
    cols = ["program", "year", "total_courses", "assessed_courses", "missing_courses"]
    a = yr_sum[cols].sort_values(["program", "year"]).reset_index(drop=True)
    b = notebook_csv[cols].sort_values(["program", "year"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_course_report_build_under_3_seconds(real_df):
    """R6 / N6: course report builds in < 3s on real data."""
    import time
    t0 = time.perf_counter()
    course_report.build(real_df, "CE 342", generated_on=date(2026, 5, 29))
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0, f"course_report.build took {elapsed:.2f}s (>3s threshold)"
