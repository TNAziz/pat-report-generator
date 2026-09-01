"""Unit tests for pat.analysis.annual.

Exercises the Annual Assessment report builder against the TierA
fixture CSVs, plus a few synthetic frames where the fixtures are too
uniform to distinguish two aggregation methods.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pat import ingest
from pat.analysis import annual
from pat.render.model import NamedTable, NarrativeBlock

FIXTURES = Path(__file__).parent / "fixtures"

DESCRIPTIONS = {
    "1.1": "Apply knowledge of mathematics, science, and engineering.",
    "1.2": "Formulate the solution to engineering problems.",
    "2.1": "Analyze engineering design with consideration of constraints.",
}


def _combined() -> pd.DataFrame:
    frames = []
    for prog in ("CE", "CON", "ENE"):
        path = FIXTURES / f"summaryReport{prog}_TierA.csv"
        frames.append(ingest.read_pat_csv(path, program=prog))
    return pd.concat(frames, ignore_index=True)


def _headings(report, level=None):
    return [
        b.heading for b in report.body
        if isinstance(b, NarrativeBlock) and b.heading
        and (level is None or b.level == level)
    ]


def _tables(report):
    return [b for b in report.body if isinstance(b, NamedTable)]


# ---------------------------------------------------------------------------
# Prompt / empty states
# ---------------------------------------------------------------------------

def test_empty_dataframe_returns_narrative():
    r = annual.build(pd.DataFrame(), semesters=["Spring 2025"], outcomes=["1"])
    assert r.title == "Annual Assessment"
    assert r.body == []
    assert len(r.narrative) == 1
    assert "No PAT data" in r.narrative[0].body_markdown


def test_no_selection_returns_prompt():
    r = annual.build(_combined(), semesters=[], outcomes=[])
    assert r.body == []
    assert "Pick at least one" in r.narrative[0].body_markdown


def test_semester_without_outcome_returns_prompt():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=[])
    assert r.body == []
    assert "Pick at least one" in r.narrative[0].body_markdown


def test_no_matches_returns_friendly_message():
    r = annual.build(_combined(), semesters=["Fall 2099"], outcomes=["1"])
    assert r.body == []
    assert "No measurements matched" in r.narrative[0].body_markdown


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_single_program_nests_outcome_then_suboutcome_then_table():
    r = annual.build(
        _combined(), semesters=["Spring 2020"], outcomes=["1"],
        programs=["CE"], descriptions=DESCRIPTIONS,
    )
    kinds = [
        (type(b).__name__, getattr(b, "heading", None), getattr(b, "level", None))
        for b in r.body
    ]
    assert kinds == [
        ("NarrativeBlock", "CE — Outcome 1", 1),
        ("NarrativeBlock", "Sub-outcome 1.1", 2),
        ("NamedTable", None, None),
        ("NarrativeBlock", "Actions Taken — Outcome 1", 2),
    ]


def test_multiple_programs_add_a_program_level_heading():
    """Spring 2020 has a CE row and a CON row, both sub-outcome 1.1."""
    r = annual.build(
        _combined(), semesters=["Spring 2020"], outcomes=["1"],
        descriptions=DESCRIPTIONS,
    )
    assert _headings(r, level=1) == [
        "Civil Engineering (CE)", "Construction Engineering (CON)",
    ]
    # With a program heading above it, the outcome drops to H2.
    assert _headings(r, level=2) == ["Outcome 1", "Outcome 1"]
    assert _headings(r, level=3) == [
        "Sub-outcome 1.1", "Actions Taken — Outcome 1",
        "Sub-outcome 1.1", "Actions Taken — Outcome 1",
    ]


def test_program_order_follows_program_labels():
    """CE, then ENE, then CON -- not alphabetical, not data order."""
    r = annual.build(
        _combined(), semesters=["Spring 2024", "Spring 2025"],
        outcomes=["1", "2", "3"], descriptions=DESCRIPTIONS,
    )
    assert _headings(r, level=1) == [
        "Civil Engineering (CE)",
        "Environmental Engineering (ENE)",
        "Construction Engineering (CON)",
    ]


def test_outcomes_sort_numerically_within_a_program():
    r = annual.build(
        _combined(), semesters=["Spring 2020", "Spring 2022", "Fall 2023"],
        outcomes=["1", "2", "4"], programs=["CE"],
    )
    outcome_headings = [h for h in _headings(r) if h.startswith("CE — Outcome")]
    assert outcome_headings == ["CE — Outcome 1", "CE — Outcome 2", "CE — Outcome 4"]


def test_one_table_per_suboutcome():
    r = annual.build(
        _combined(), semesters=["Spring 2020", "Spring 2021", "Spring 2024"],
        outcomes=["1"], programs=["CE"],
    )
    # All three CE rows are sub-outcome 1.1, so one table with three rows.
    tables = _tables(r)
    assert len(tables) == 1
    assert len(tables[0].rows) == 3


def test_explicit_suboutcomes_override_outcomes():
    r = annual.build(
        _combined(), semesters=["Spring 2024", "Spring 2025"],
        outcomes=["1", "2", "3"], suboutcomes=["2.1"],
    )
    subs = [h for h in _headings(r) if h.startswith("Sub-outcome")]
    assert subs and set(subs) == {"Sub-outcome 2.1"}


def test_empty_groups_are_omitted():
    """Fall 2023 has only a CE 2.1 row."""
    r = annual.build(_combined(), semesters=["Fall 2023"], outcomes=["1", "2"])
    assert _headings(r) == ["CE — Outcome 2", "Sub-outcome 2.1",
                            "Actions Taken — Outcome 2"]


def test_rows_run_chronologically():
    r = annual.build(
        _combined(), semesters=["Spring 2024", "Spring 2020", "Spring 2021"],
        outcomes=["1"], programs=["CE"],
    )
    semesters = [row[1] for row in _tables(r)[0].rows]
    assert semesters == ["Spring 2020", "Spring 2021", "Spring 2024"]


# ---------------------------------------------------------------------------
# Table cells
# ---------------------------------------------------------------------------

def test_table_columns():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"])
    assert _tables(r)[0].columns == [
        "Course", "Semester", "Instructor", "Goal", "Performance", "N",
        "Comment", "Actions Taken",
    ]


def test_row_values_pull_from_raw_data():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"])
    row = _tables(r)[0].rows[0]
    assert row[0] == "CE 282"
    assert row[1] == "Spring 2020"
    assert row[3] == "70.0%"          # the instructor's goal for this measure
    assert row[4] == "82.0%"          # what students actually achieved
    assert row[5] == "34"
    assert row[6] == "Solid performance."
    assert row[7] == "Continue monitoring."


def test_null_performance_renders_dash():
    """CE 342 / 2.1 / Spring 2025 has performance=null."""
    r = annual.build(_combined(), semesters=["Spring 2025"], outcomes=["2"],
                     programs=["CE"])
    row = next(x for x in _tables(r)[0].rows if x[0] == "CE 342")
    assert row[4] == "—"


def test_blank_actions_taken_renders_placeholder():
    r = annual.build(_combined(), semesters=["Spring 2025"], outcomes=["2"],
                     programs=["CE"])
    row = next(x for x in _tables(r)[0].rows if x[0] == "CE 342")
    assert row[7] == annual.NO_ACTION_TEXT


def test_nullish_actions_strings_are_treated_as_blank():
    assert annual._format_actions(None) == annual.NO_ACTION_TEXT
    assert annual._format_actions("") == annual.NO_ACTION_TEXT
    assert annual._format_actions("   ") == annual.NO_ACTION_TEXT
    assert annual._format_actions("nan") == annual.NO_ACTION_TEXT
    assert annual._format_actions("N/A") == "N/A"


def test_no_ragged_rows():
    """Renderers index columns positionally, so every row must be full width."""
    r = annual.build(
        _combined(), semesters=["Spring 2020", "Spring 2024", "Spring 2025"],
        outcomes=["1", "2", "3"], descriptions=DESCRIPTIONS,
    )
    for table in _tables(r):
        assert len(table.columns) == 8
        for row in table.rows:
            assert len(row) == 8
            assert row[7]  # never an empty corrective-action cell


# ---------------------------------------------------------------------------
# Sub-outcome definitions
# ---------------------------------------------------------------------------

def test_definitions_appear_under_the_outcome_and_the_suboutcome():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"], descriptions=DESCRIPTIONS)
    assert "**1.1** — Apply knowledge" in r.body[0].body_markdown
    assert DESCRIPTIONS["1.1"] in r.body[1].body_markdown


def test_missing_descriptions_explain_themselves():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"], descriptions=None)
    assert "Assessment Schedule" in r.body[0].body_markdown


def test_only_the_relevant_definitions_are_listed():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"], descriptions=DESCRIPTIONS)
    body = r.body[0].body_markdown
    assert "**1.1**" in body
    assert "**1.2**" not in body   # ENE-only that semester
    assert "**2.1**" not in body


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _synthetic(rows) -> pd.DataFrame:
    """Minimal canonical-ish frame from (course, met, total, performance)."""
    return pd.DataFrame([
        {
            "program": "CE", "course": c, "semester": "Fall 2024",
            "semester_sort_key": 20244, "suboutcome": "1.1",
            "instructor": "X", "performance": perf, "total_scores": total,
            "scores_meeting_threshold": met, "comments": "", "actions_taken": "",
        }
        for (c, met, total, perf) in rows
    ])


def test_weighted_average_is_not_the_mean_of_performance():
    """A 1-student measure must not outweigh a 77-student one.

    Mean of performance would be (100 + 50) / 2 = 75%; the weighted
    figure is (1 + 38) / (1 + 77) = 50.0%.
    """
    df = _synthetic([("CE 305", 1, 1, 100.0), ("CE 332", 38, 77, 50.0)])
    stats = annual.group_stats(df)
    assert stats["n_assessments"] == 78
    assert stats["n_meeting"] == 39
    assert stats["weighted_pct"] == pytest.approx(50.0)


def test_stats_line_reports_courses_measures_and_weighted_percent():
    df = _synthetic([("CE 225", 28, 57, 55.0), ("CE 225", 31, 49, 55.0),
                     ("CE 332", 74, 77, 96.0)])
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"],
                     programs=["CE"])
    stats_text = r.body[1].body_markdown
    assert "2 courses" in stats_text
    assert "3 measures" in stats_text
    assert "N = 183 student assessments" in stats_text
    assert "133 of 183" in stats_text


def test_measures_without_counts_are_excluded_and_flagged():
    df = _synthetic([("CE 403", 41, 51, 80.0), ("CE 450", None, None, None)])
    stats = annual.group_stats(df)
    assert stats["measures"] == 2
    assert stats["measures_without_counts"] == 1
    assert stats["n_assessments"] == 51
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"], programs=["CE"])
    assert "1 measure reported no student counts" in r.body[1].body_markdown


def test_no_counts_at_all_says_so_instead_of_dividing_by_zero():
    df = _synthetic([("CE 450", None, None, None)])
    stats = annual.group_stats(df)
    assert stats["weighted_pct"] is None
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"], programs=["CE"])
    assert "No weighted average" in r.body[1].body_markdown


def test_single_course_and_measure_are_not_pluralized():
    df = _synthetic([("CE 305", 1, 1, 100.0)])
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"], programs=["CE"])
    text = r.body[1].body_markdown
    assert "1 course ·" in text
    assert "1 measure ·" in text


# ---------------------------------------------------------------------------
# Actions roll-up
# ---------------------------------------------------------------------------

def _rollup(report) -> str:
    return next(
        b.body_markdown for b in report.body
        if isinstance(b, NarrativeBlock) and b.heading
        and b.heading.startswith("Actions Taken")
    )


def test_rollup_lists_each_action_grouped_by_course():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"])
    assert "**CE 282** (1.1, Spring 2020) — Continue monitoring." in _rollup(r)


def test_rollup_collapses_repeated_action_text_for_one_course():
    """CE 282 records the same action in three semesters: one bullet, three contexts."""
    r = annual.build(
        _combined(), semesters=["Spring 2020", "Spring 2021", "Spring 2024"],
        outcomes=["1"], programs=["CE"],
    )
    text = _rollup(r)
    assert text.count("Continue monitoring.") == 1
    assert "1.1, Spring 2020; 1.1, Spring 2021; 1.1, Spring 2024" in text


def test_rollup_names_measures_with_no_action_recorded():
    r = annual.build(_combined(), semesters=["Spring 2025"], outcomes=["2"],
                     programs=["CE"])
    text = _rollup(r)
    assert "No corrective action recorded" in text
    assert "CE 342 (2.1, Spring 2025)" in text


def test_rollup_when_nothing_was_recorded_at_all():
    r = annual.build(_combined(), semesters=["Spring 2022"], outcomes=["4"],
                     programs=["CE"])
    assert "No corrective actions were recorded" in _rollup(r)


def test_rollup_keeps_multiline_action_text_in_one_bullet():
    df = _synthetic([("CE 225", 28, 57, 55.0)])
    df.loc[0, "actions_taken"] = "First line.\nSecond line.\n\nThird."
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"], programs=["CE"])
    text = _rollup(r)
    assert "First line. Second line. Third." in text
    assert "\n" not in text.split("— ", 1)[1]


def test_rollup_covers_the_whole_outcome_not_one_suboutcome():
    """Actions from 1.1 and 1.2 land in the same Outcome 1 roll-up."""
    df = _synthetic([("CE 225", 28, 57, 55.0), ("CE 373", 5, 14, 35.0)])
    df.loc[0, "actions_taken"] = "Extra torsion practice."
    df.loc[1, "suboutcome"] = "1.2"
    df.loc[1, "actions_taken"] = "Topic 0 quiz."
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"], programs=["CE"])
    text = _rollup(r)
    assert "Extra torsion practice." in text
    assert "Topic 0 quiz." in text


# ---------------------------------------------------------------------------
# Renderer round-trip
# ---------------------------------------------------------------------------

def test_report_survives_all_four_renderers():
    from pat.render import docx as docx_r
    from pat.render import html as html_r
    from pat.render import markdown as md_r

    r = annual.build(
        _combined(), semesters=["Spring 2020", "Spring 2024"],
        outcomes=["1", "2"], descriptions=DESCRIPTIONS,
    )

    md = md_r.render(r)
    # Ordering is the point of Report.body: the sub-outcome heading and its
    # stats must precede the table they describe.
    assert md.index("Sub-outcome 1.1") < md.index("| Course |")
    assert md.index("| Course |") < md.index("Actions Taken — Outcome 1")
    assert "Continue monitoring." in md

    html = html_r.render(r)
    assert "<h1>Civil Engineering (CE)</h1>" in html
    assert "<h3>Sub-outcome 1.1</h3>" in html
    assert html.index("Sub-outcome 1.1") < html.index("<table")

    blob = docx_r.render(r)
    assert blob[:2] == b"PK"


def test_outcome_helpers():
    assert annual.outcome_of("1.1") == "1"
    assert annual.outcome_of("10.20") == "10"
    assert annual.available_outcomes(_combined()) == ["1", "2", "3", "4"]
    assert annual.available_outcomes(pd.DataFrame()) == []


# ---------------------------------------------------------------------------
# Detail mode (the LLM drafting packet's column set)
# ---------------------------------------------------------------------------

def test_detail_mode_columns():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"], detail=True)
    assert _tables(r)[0].columns == [
        "Course", "Semester", "Instructor", "Measure", "Measure threshold",
        "Goal", "Performance", "Met / N", "Comment", "Actions Taken",
    ]


def test_detail_mode_carries_measure_and_counts():
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"], detail=True)
    row = _tables(r)[0].rows[0]
    assert row[0] == "CE 282"
    assert row[3]                      # measure description, non-empty
    assert row[4].endswith("points")   # threshold of scale
    assert row[7] == "28 of 34"        # met / N
    assert row[9] == "Continue monitoring."


def test_detail_mode_does_not_change_the_default():
    plain = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                         programs=["CE"])
    assert len(_tables(plain)[0].columns) == 8


def test_detail_rows_are_never_ragged():
    r = annual.build(
        _combined(), semesters=["Spring 2020", "Spring 2024", "Spring 2025"],
        outcomes=["1", "2", "3"], detail=True,
    )
    for table in _tables(r):
        assert len(table.columns) == 10
        for row in table.rows:
            assert len(row) == 10


def test_threshold_formatting():
    assert annual._format_threshold(11, 16) == "11 of 16 points"
    assert annual._format_threshold(70, None) == "70 points"
    assert annual._format_threshold(None, 100) == "out of 100 points"
    assert annual._format_threshold(None, None) == "—"


def test_met_over_n_formatting():
    assert annual._format_met(28, 57) == "28 of 57"
    assert annual._format_met(None, 57) == "— of 57"
    assert annual._format_met(None, None) == "—"


def test_detail_mode_stats_are_identical():
    """Only the columns change; the aggregate must not."""
    kwargs = dict(semesters=["Spring 2020", "Spring 2021"], outcomes=["1"],
                  programs=["CE"])
    plain = annual.build(_combined(), **kwargs)
    detailed = annual.build(_combined(), detail=True, **kwargs)
    assert plain.body[1].body_markdown == detailed.body[1].body_markdown


def test_goal_column_carries_the_instructors_own_indicator():
    """Instructors set different goals; the report must show which one applied."""
    df = _synthetic([("CE 225", 28, 57, 55.0), ("CE 301", 37, 46, 80.0)])
    df.loc[0, "performance_indicator"] = 50.0
    df.loc[1, "performance_indicator"] = 70.0
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"], programs=["CE"])
    goals = {row[0]: row[3] for row in _tables(r)[0].rows}
    assert goals == {"CE 225": "50.0%", "CE 301": "70.0%"}


def test_missing_goal_renders_dash():
    df = _synthetic([("CE 450", None, None, None)])
    df.loc[0, "performance_indicator"] = None
    r = annual.build(df, semesters=["Fall 2024"], outcomes=["1"], programs=["CE"])
    assert _tables(r)[0].rows[0][3] == "—"


def test_tables_carry_the_goal_footnote():
    """Goal beside Performance invites the wrong reading without it."""
    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"])
    footnote = _tables(r)[0].footnote
    assert "set per measure, not" in footnote
    assert "department-wide" in footnote


def test_footnote_reaches_every_renderer():
    from pat.render import html as html_r
    from pat.render import markdown as md_r

    r = annual.build(_combined(), semesters=["Spring 2020"], outcomes=["1"],
                     programs=["CE"])
    assert "set per measure" in md_r.render(r)
    assert "set per measure" in html_r.render(r)
