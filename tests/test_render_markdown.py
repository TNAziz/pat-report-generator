"""Unit tests for pat.render.markdown.

Traceability: R13 (course-report format), R15 (multi-format), R16
(content parity will be checked in test_renderers.py).
"""

from __future__ import annotations

import pytest

from pat.render import markdown as M
from pat.render.model import (
    NamedTable, NarrativeBlock, ProgramSection, Report, SemesterSection,
    SummaryRow, MeasureDetail,
)
from tests.report_fixtures import (
    make_course_report, make_suboutcome_lookup, make_coverage_report,
)


# -------- fmt_percent --------


@pytest.mark.parametrize("val, expected", [
    (None, "N/A"),
    (70.0, "70%"),
    (70, "70%"),
    (82.5, "82.5%"),
    (0.0, "0%"),
    (100.0, "100%"),
])
def test_fmt_percent(val, expected):
    assert M._fmt_percent(val) == expected


# -------- summary table --------


def test_summary_table_bolds_below_threshold_rows():
    rows = [
        SummaryRow("Spring 2020", "1.1", 70.0, 60.0, below_threshold=True),
        SummaryRow("Spring 2021", "1.1", 70.0, 80.0, below_threshold=False),
    ]
    out = M._render_summary_table(rows)
    # Below-threshold row has bold markers.
    assert "| **70%** | **60%** |" in out
    # Above-threshold row does not.
    assert "| 70% | 80% |" in out


def test_summary_table_empty_returns_marker():
    out = M._render_summary_table([])
    assert "_No data for this program._" in out


# -------- end-to-end render --------


def test_render_course_report_has_title():
    out = M.render(make_course_report())
    assert out.startswith("# CE 282")
    assert "Spring 2020 – Spring 2026" in out


def test_render_course_report_includes_both_programs():
    out = M.render(make_course_report())
    assert "# Civil Engineering" in out
    assert "# Construction Engineering" in out


def test_render_course_report_has_per_semester_detail():
    out = M.render(make_course_report())
    assert "## Fall 2023" in out
    assert "### Instructor: Aziz, Tarek" in out
    assert "#### Sub-Outcome: 2.1" in out
    assert "**Measure Description:** Exam 2 Q2c" in out
    assert "**n =** 34" in out
    assert "> **Comments:** Solid performance." in out
    assert "> **Actions Taken:** Continue monitoring." in out


def test_render_course_report_marks_below_threshold_in_summary():
    out = M.render(make_course_report())
    # The Spring 2021 1.1 row went 60% < 70% indicator.
    assert "| **70%** | **60%** |" in out


def test_render_suboutcome_lookup():
    out = M.render(make_suboutcome_lookup())
    assert out.startswith("# CE 488")
    assert "## Programs" in out
    assert "CE / ENE" in out
    assert "**1.2:**" in out


def test_render_coverage_report():
    out = M.render(make_coverage_report())
    assert "# Coverage Check" in out
    assert "Spring 2025" in out
    assert "## Missing assessments in Spring 2025" in out
    assert "| CE | CE 339 |" in out
    assert "## Semester summary" in out
    # Chart is rendered as a table in markdown.
    assert "## Coverage trend by year" in out
    assert "| Year |" in out


def test_render_ends_with_newline():
    """Files should end with a single newline."""
    for fixture in (make_course_report, make_suboutcome_lookup, make_coverage_report):
        out = M.render(fixture())
        assert out.endswith("\n")
        assert not out.endswith("\n\n")


def test_render_empty_report():
    """An empty report should still produce minimal output without erroring."""
    r = Report(title="Empty")
    out = M.render(r)
    assert out.strip() == "# Empty"


# -------- escape helpers --------


def test_md_cell_escapes_pipe_and_newline():
    assert M._md_cell("a | b") == "a \\| b"
    assert M._md_cell("line1\nline2") == "line1<br>line2"
    assert M._md_cell("line1\r\nline2") == "line1<br>line2"
    assert M._md_cell(None) == ""


def test_md_blockquote_keeps_wrapped_lines_inside_quote():
    lines = M._md_blockquote_field("Comments", "first\nsecond\nthird")
    assert lines == [
        "> **Comments:** first",
        "> second",
        "> third",
    ]


def test_named_table_row_with_pipe_stays_a_table():
    tbl = NamedTable(
        title=None,
        columns=["A", "B"],
        rows=[["a | pipe", "b\nnewline"]],
        footnote=None,
    )
    out = M._render_named_table(tbl)
    # The literal pipe is escaped so column count stays 2.
    assert "a \\| pipe" in out
    # The newline becomes <br> so the row doesn't spill into a new row.
    assert "b<br>newline" in out


def test_measure_comments_with_newline_stay_inside_blockquote():
    r = Report(
        title="X",
        sections=[
            ProgramSection(
                program_code="CE",
                program_label="Civil Engineering",
                summary=[],
                semesters=[
                    SemesterSection(
                        semester="Fall 2024",
                        instructor="Aziz, Tarek",
                        measures=[
                            MeasureDetail(
                                suboutcome="1.1",
                                measure_description="Q1",
                                performance_indicator=70,
                                performance=80,
                                below_threshold=False,
                                n=10,
                                comments="line one\nline two",
                                actions_taken="ok",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    out = M.render(r)
    assert "> **Comments:** line one" in out
    assert "> line two" in out
