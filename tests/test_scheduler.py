"""Unit tests for pat.analysis.scheduler (the PAT Scheduler tool).

The fixture workbook reuses the TierA ``CourseSubOutcomes`` and
``OutcomeDescriptions`` sheets and adds a planned ``Assessment Schedule``
grid, so program membership and sub-outcome descriptions stay in one
place.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pat import ingest
from pat.analysis import scheduler
from pat.render import docx as docx_renderer
from pat.render import html as html_renderer
from pat.render import markdown as md_renderer

FIXTURES = Path(__file__).parent / "fixtures"
TIER_A = FIXTURES / "assessment_schedule_TierA.xlsx"

# Offering, Course, then one column per semester.
#   CE 469 is offered in Spring only but scheduled in F26 -> conflict.
#   CE 488 is '?' in S26 -> tentative.
#   CE 999 is absent from CourseSubOutcomes -> unmapped.
PLANNED_ROWS = [
    ("F,S", "CE 282", None, None, "X"),
    ("S",   "CE 469", None, None, "X"),
    ("F,S", "CE 488", None, "?", "X"),
    ("F,S", "CE 342", "X",  None, None),
    ("F",   "ENE 300", None, None, "X"),
    ("F,S", "CE 999", None, None, "X"),
]


@pytest.fixture(scope="module")
def schedule(tmp_path_factory):
    src = pd.ExcelFile(TIER_A, engine="openpyxl")
    courses = pd.read_excel(src, sheet_name="CourseSubOutcomes")
    descriptions = pd.read_excel(src, sheet_name="OutcomeDescriptions")
    planned = pd.DataFrame(
        PLANNED_ROWS, columns=["Offering", "Course", "F25", "S26", "F26"]
    )
    path = tmp_path_factory.mktemp("sched") / "schedule_with_plan.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        planned.to_excel(writer, sheet_name="Assessment Schedule", index=False)
        courses.to_excel(writer, sheet_name="CourseSubOutcomes", index=False)
        descriptions.to_excel(writer, sheet_name="OutcomeDescriptions", index=False)
    return ingest.read_assessment_schedule(path)


# ---------------------------------------------------------------------------
# Semester helpers
# ---------------------------------------------------------------------------


def test_semester_columns_are_chronological(schedule):
    assert scheduler.semester_columns(schedule) == ["F25", "S26", "F26"]


def test_semester_columns_exclude_non_semester_headers(schedule):
    cols = scheduler.semester_columns(schedule)
    assert "Offering" not in cols and "Course" not in cols


def test_semester_columns_empty_without_planned_sheet():
    plain = ingest.read_assessment_schedule(TIER_A)
    assert plain.planned is None
    assert scheduler.semester_columns(plain) == []


@pytest.mark.parametrize("code,label", [
    ("F23", "Fall 2023"), ("S24", "Spring 2024"), ("junk", "junk"),
])
def test_semester_label(code, label):
    assert scheduler.semester_label(code) == label


def test_default_semester_picks_current_by_calendar(schedule):
    assert scheduler.default_semester(schedule, today=date(2026, 9, 1)) == "F26"
    assert scheduler.default_semester(schedule, today=date(2026, 3, 1)) == "S26"


def test_default_semester_falls_forward_then_to_last(schedule):
    # Spring 2025 is not a column; the next later one is.
    assert scheduler.default_semester(schedule, today=date(2025, 3, 1)) == "F25"
    # Past the end of the plan, fall back to the last column.
    assert scheduler.default_semester(schedule, today=date(2030, 1, 1)) == "F26"


@pytest.mark.parametrize("value,expected", [
    ("X", "planned"), ("x", "planned"), ("yes", "planned"),
    ("?", "tentative"), (" ? ", "tentative"),
    ("", ""), (None, ""), (float("nan"), ""), ("notes", ""),
])
def test_cell_status(value, expected):
    assert scheduler.cell_status(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("F,S", {"F", "S"}), ("F", {"F"}), ("Spring", {"S"}), ("", set()), (None, set()),
])
def test_parse_offering(value, expected):
    assert scheduler.parse_offering(value) == expected


# ---------------------------------------------------------------------------
# collect()
# ---------------------------------------------------------------------------


def test_collect_filters_by_program(schedule):
    ce = scheduler.collect(schedule, "CE", "F26")
    # CE 469 is CON-only in CourseSubOutcomes, so it must not appear for CE.
    assert [e.course for e in ce.courses] == ["CE 282", "CE 488"]
    con = scheduler.collect(schedule, "CON", "F26")
    assert "CE 469" in [e.course for e in con.courses]


def test_collect_includes_cross_listed_course_in_both_programs(schedule):
    ce = scheduler.collect(schedule, "CE", "F26")
    ene = scheduler.collect(schedule, "ENE", "F26")
    # CE 488 is CE/ENE.
    assert "CE 488" in [e.course for e in ce.courses]
    assert "CE 488" in [e.course for e in ene.courses]


def test_collect_groups_by_suboutcome_sorted(schedule):
    ce = scheduler.collect(schedule, "CE", "F26")
    assert [g.code for g in ce.groups] == ["1.1", "1.2", "2.1"]
    by_code = {g.code: g.courses for g in ce.groups}
    assert by_code["1.1"] == ["CE 282"]
    assert by_code["1.2"] == ["CE 488"]
    assert by_code["2.1"] == ["CE 488"]


def test_collect_group_carries_outcome_and_description(schedule):
    ce = scheduler.collect(schedule, "CE", "F26")
    g = next(g for g in ce.groups if g.code == "1.2")
    assert g.outcome == "1"
    assert "Formulate" in g.description


def test_entry_count_is_course_times_suboutcome(schedule):
    ce = scheduler.collect(schedule, "CE", "F26")
    # CE 282 -> 1.1; CE 488 -> 1.2, 2.1.
    assert ce.entry_count == 3
    assert len(ce.flat_rows()) == 3
    assert len(scheduler.FLAT_COLUMNS) == len(ce.flat_rows()[0])


def test_tentative_courses_are_separated(schedule):
    ce = scheduler.collect(schedule, "CE", "S26")
    assert [e.course for e in ce.tentative] == ["CE 488"]
    # '?' must not inflate the working list.
    assert ce.courses == []
    assert ce.groups == []
    assert ce.entry_count == 0


def test_unmapped_course_is_reported(schedule):
    ce = scheduler.collect(schedule, "CE", "F26")
    assert ce.unmapped_courses == ["CE 999"]


def test_offering_conflict_is_reported(schedule):
    con = scheduler.collect(schedule, "CON", "F26")
    assert any("CE 469" in msg for msg in con.offering_conflicts)
    # A course offered both terms raises nothing.
    ce = scheduler.collect(schedule, "CE", "F26")
    assert ce.offering_conflicts == []


def test_unknown_semester_yields_empty_result(schedule):
    r = scheduler.collect(schedule, "CE", "F99")
    assert r.courses == [] and r.groups == [] and r.unmapped_courses == []


def test_program_matching_is_case_insensitive(schedule):
    assert scheduler.collect(schedule, "ce", "F26").entry_count == 3


# ---------------------------------------------------------------------------
# build()
# ---------------------------------------------------------------------------


def test_build_report_shape(schedule):
    r = scheduler.build(schedule, "CE", "F26", generated_on=date(2026, 9, 1))
    assert r.title == "PAT Scheduler"
    assert "CE" in r.subtitle and "Fall 2026" in r.subtitle
    titles = [b.title for b in r.body if hasattr(b, "columns")]
    assert "Courses to add, by sub-outcome" in titles
    assert "Cross-check: by course" in titles


def test_build_lists_courses_under_each_suboutcome(schedule):
    r = scheduler.build(schedule, "CE", "F26")
    table = next(
        b for b in r.body
        if getattr(b, "title", "") == "Courses to add, by sub-outcome"
    )
    assert table.columns == [
        "Outcome", "Sub-outcome", "Description", "Courses", "#",
    ]
    row = next(row for row in table.rows if row[1] == "2.1")
    assert row[3] == "CE 488"


def test_build_flags_tentative_and_workbook_issues(schedule):
    r = scheduler.build(schedule, "CE", "F26")
    headings = [b.heading for b in r.body if hasattr(b, "body_markdown")]
    assert "Workbook issues" in headings
    issues = next(
        b for b in r.body
        if getattr(b, "heading", None) == "Workbook issues"
    )
    assert "CE 999" in issues.body_markdown

    s26 = scheduler.build(schedule, "CE", "S26")
    assert "Needs confirmation (marked ?)" in [
        b.title for b in s26.body if hasattr(b, "columns")
    ]


def test_build_empty_selection_is_friendly(schedule):
    r = scheduler.build(schedule, "ENE", "F25")
    assert not r.is_empty()
    assert "No courses are scheduled" in r.body[0].body_markdown


def test_report_renders_in_every_format(schedule):
    r = scheduler.build(schedule, "CE", "F26")
    md = md_renderer.render(r)
    assert "PAT Scheduler" in md and "CE 488" in md
    html = html_renderer.render(r)
    assert "Courses to add, by sub-outcome" in html
    assert isinstance(docx_renderer.render(r), (bytes, bytearray))
