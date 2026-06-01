"""Generate Tier A synthetic fixtures.

These are intentionally tiny — just enough rows to exercise every
cleaning rule in pat.normalize. Run this script whenever you need to
regenerate the .csv / .xlsx test fixtures.

    python -m tests.fixtures.build_fixtures

The generated files are checked into the repo so tests don't depend on
running the generator.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent

# Padding for the whitespace artifact — matches what PAT emits.
PAD = " " * 200


# ---------------------------------------------------------------------------
# Per-program PAT exports
# ---------------------------------------------------------------------------


PAT_COLUMNS = [
    "course",
    "suboutcome",
    "semester",
    "assigned-to",
    "submitted-by",
    "performance-indicator",
    "threshold",
    "scale",
    "performance",
    "score-data",
    "scores_meeting_threshold",
    "total_scores",
    "measurement-result-updated",
    "comments",
    "actions-taken",
    "measure-description",
]


def _row(**kwargs):
    """Build a row with defaults; overrides via kwargs."""
    default = {
        "course": "CE 282",
        "suboutcome": "1.1",
        "semester": "Spring 2020",
        "assigned-to": "Aziz, Tarek",
        "submitted-by": "Aziz, Tarek",
        "performance-indicator": 70,
        "threshold": 4,
        "scale": 6,
        "performance": 82,
        "score-data": "6 4 6 6 4",
        "scores_meeting_threshold": 28,
        "total_scores": 34,
        "measurement-result-updated": "05/15/2020",
        "comments": "Solid performance.",
        "actions-taken": "Continue monitoring.",
        "measure-description": "Exam 2 Q2c",
    }
    default.update(kwargs)
    return default


def build_ce_csv() -> pd.DataFrame:
    """CE program with multiple courses, semesters, and known artifacts."""
    rows = [
        # Normal row.
        _row(),
        # Same course, later semester, below-threshold performance.
        _row(semester="Spring 2021", performance=60, performance_indicator=70),
        # Whitespace-padded course (the CE 464 artifact).
        _row(
            course=PAD + "CE 464",
            suboutcome=4.1,  # float type
            semester="Spring 2022",
            performance="null",  # null string for performance
            comments="",
            **{"actions-taken": "null"},
        ),
        # Different course, fall semester.
        _row(
            course="CE 342",
            suboutcome="2.1",
            semester="Fall 2023",
            performance=85,
            **{"performance-indicator": "70%"},  # percent-as-string
        ),
        # CE 342 missing submitter (= no data submitted; used for coverage tests).
        _row(
            course="CE 342",
            suboutcome="2.1",
            semester="Spring 2025",
            **{"submitted-by": ""},
            performance="",
            comments="",
            **{"actions-taken": ""},
        ),
        # Short-form semester label ("S24").
        _row(
            course="CE 282",
            semester="S24",
            performance=88,
        ),
    ]
    # Build dict in PAT_COLUMNS order to ensure correct CSV column order;
    # rebuild each row by indexing.
    df = pd.DataFrame(rows)
    # _row builds dict using both "performance-indicator" and "performance_indicator"
    # if the test passes performance_indicator=... — guard against that by
    # coalescing.
    if "performance_indicator" in df.columns:
        df["performance-indicator"] = df["performance_indicator"].combine_first(df["performance-indicator"])
        df = df.drop(columns=["performance_indicator"])
    return df[PAT_COLUMNS]


def build_con_csv() -> pd.DataFrame:
    """CON program — small, includes a CE-prefixed cross-listed course."""
    rows = [
        _row(course="CE 464", suboutcome="1.1", semester="Spring 2020", performance=90),
        _row(course="CE 469", suboutcome="2.1", semester="Spring 2024", performance=75),
        # Cross-listed CE 342 in CON — also missing in Spring 2025.
        _row(
            course="CE 342",
            suboutcome="3.1",
            semester="Spring 2025",
            **{"submitted-by": ""},
            performance="",
        ),
    ]
    df = pd.DataFrame(rows)
    if "performance_indicator" in df.columns:
        df["performance-indicator"] = df["performance_indicator"].combine_first(df["performance-indicator"])
        df = df.drop(columns=["performance_indicator"])
    return df[PAT_COLUMNS]


def build_ene_csv() -> pd.DataFrame:
    """ENE program — sparse, used for coverage trend tests."""
    rows = [
        _row(course="ENE 300", suboutcome="1.2", semester="Fall 2022", performance=80),
        _row(course="ENE 400", suboutcome="2.1", semester="Spring 2024", performance=72),
        # ENE 400 missing in Spring 2025 (coverage trend).
        _row(
            course="ENE 400",
            suboutcome="2.1",
            semester="Spring 2025",
            **{"submitted-by": ""},
            performance="",
        ),
    ]
    df = pd.DataFrame(rows)
    if "performance_indicator" in df.columns:
        df["performance-indicator"] = df["performance_indicator"].combine_first(df["performance-indicator"])
        df = df.drop(columns=["performance_indicator"])
    return df[PAT_COLUMNS]


# ---------------------------------------------------------------------------
# Assessment Schedule workbook
# ---------------------------------------------------------------------------


def build_schedule_xlsx(path: Path) -> None:
    cso = pd.DataFrame(
        [
            {"Course": "CE 282", "Programs": "CE", "1.1": "X", "1.2": "", "2.1": "", "4.1": ""},
            {"Course": "CE 342", "Programs": "CE/CON", "1.1": "", "1.2": "", "2.1": "X", "4.1": ""},
            {"Course": "CE 464", "Programs": "CE/CON", "1.1": "X", "1.2": "", "2.1": "", "4.1": "X"},
            {"Course": "CE 469", "Programs": "CON", "1.1": "", "1.2": "X", "2.1": "X", "4.1": ""},
            {"Course": "CE 488", "Programs": "CE/ENE", "1.1": "", "1.2": "X", "2.1": "X", "4.1": ""},
            {"Course": "ENE 300", "Programs": "ENE", "1.1": "", "1.2": "X", "2.1": "", "4.1": ""},
            {"Course": "ENE 400", "Programs": "ENE", "1.1": "", "1.2": "", "2.1": "X", "4.1": ""},
        ]
    )
    desc = pd.DataFrame(
        [
            {"Outcomes": "1.1", "Description": "Identify engineering problems."},
            {"Outcomes": "1.2", "Description": "Formulate the solution to engineering problems."},
            {"Outcomes": "2.1", "Description": "Analyze engineering design with consideration of constraints."},
            {"Outcomes": "4.1", "Description": "Apply ethical and professional responsibility."},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        cso.to_excel(xw, sheet_name="CourseSubOutcomes", index=False)
        desc.to_excel(xw, sheet_name="OutcomeDescriptions", index=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    build_ce_csv().to_csv(HERE / "summaryReportCE_TierA.csv", index=False)
    build_con_csv().to_csv(HERE / "summaryReportCON_TierA.csv", index=False)
    build_ene_csv().to_csv(HERE / "summaryReportENE_TierA.csv", index=False)
    build_schedule_xlsx(HERE / "assessment_schedule_TierA.xlsx")
    print("Tier A fixtures written to", HERE)


if __name__ == "__main__":
    main()
