"""Unit tests for pat.analysis.annual.

Exercises the Annual Assessment report builder against the TierA
fixture CSVs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pat import ingest
from pat.analysis import annual

FIXTURES = Path(__file__).parent / "fixtures"


def _combined() -> pd.DataFrame:
    frames = []
    for prog in ("CE", "CON", "ENE"):
        path = FIXTURES / f"summaryReport{prog}_TierA.csv"
        frames.append(ingest.read_pat_csv(path, program=prog))
    return pd.concat(frames, ignore_index=True)


def test_empty_dataframe_returns_narrative():
    df = pd.DataFrame()
    r = annual.build(df, semesters=["Spring 2025"], suboutcomes=["1.1"])
    assert r.title == "Annual Assessment"
    assert r.tables == []
    assert len(r.narrative) == 1
    assert "No PAT data" in r.narrative[0].body_markdown


def test_no_selection_returns_prompt():
    df = _combined()
    r = annual.build(df, semesters=[], suboutcomes=[])
    assert r.tables == []
    assert "Pick at least one" in r.narrative[0].body_markdown


def test_semester_selected_no_suboutcome_returns_prompt():
    df = _combined()
    r = annual.build(df, semesters=["Spring 2025"], suboutcomes=[])
    assert r.tables == []
    assert "Pick at least one" in r.narrative[0].body_markdown


def test_no_matches_returns_friendly_message():
    df = _combined()
    r = annual.build(df, semesters=["Fall 2099"], suboutcomes=["1.1"])
    assert r.tables == []
    assert "No measurements matched" in r.narrative[0].body_markdown


def test_groups_by_program_and_suboutcome():
    df = _combined()
    # Spring 2020 has CE 282 (CE, 1.1) and CE 464 (CON, 1.1) both with sub-outcome 1.1.
    r = annual.build(df, semesters=["Spring 2020"], suboutcomes=["1.1"])
    titles = [t.title for t in r.tables]
    assert "CE — 1.1" in titles
    assert "CON — 1.1" in titles
    assert len(r.tables) == 2


def test_program_order_matches_program_labels():
    df = _combined()
    # Spring 2024 has ENE 400 (ENE, 2.1) and CE 469 (CON, 2.1).
    # PROGRAM_LABELS iterates CE, ENE, CON so ENE tables come before CON.
    r = annual.build(df, semesters=["Spring 2024"], suboutcomes=["2.1"])
    titles = [t.title for t in r.tables]
    assert titles == ["ENE — 2.1", "CON — 2.1"]


def test_suboutcome_order_is_numeric():
    df = _combined()
    # Ensure 1.1 sorts before 2.1 within a program (not lexicographic).
    r = annual.build(
        df,
        semesters=["Spring 2020", "Fall 2023"],
        suboutcomes=["2.1", "1.1"],  # deliberately reversed on input
    )
    ce_titles = [t.title for t in r.tables if t.title.startswith("CE —")]
    assert ce_titles == ["CE — 1.1", "CE — 2.1"]


def test_table_columns_are_raw_measurement_fields():
    df = _combined()
    r = annual.build(df, semesters=["Spring 2020"], suboutcomes=["1.1"])
    assert r.tables[0].columns == [
        "Course", "Semester", "Instructor", "Performance", "N", "Comment"
    ]


def test_row_values_pull_from_raw_data():
    df = _combined()
    r = annual.build(df, semesters=["Spring 2020"], suboutcomes=["1.1"])
    ce_table = next(t for t in r.tables if t.title == "CE — 1.1")
    # Spring 2020 CE 282 row has performance=82, total_scores=34.
    row = ce_table.rows[0]
    assert row[0] == "CE 282"
    assert row[1] == "Spring 2020"
    assert row[3] == "82.0%"
    assert row[4] == "34"
    assert row[5] == "Solid performance."


def test_null_performance_renders_dash():
    df = _combined()
    # CE 342, 2.1, Spring 2025 has performance=null.
    r = annual.build(df, semesters=["Spring 2025"], suboutcomes=["2.1"])
    ce_table = next(t for t in r.tables if t.title == "CE — 2.1")
    row = next(r_ for r_ in ce_table.rows if r_[0] == "CE 342")
    assert row[3] == "—"


def test_empty_groups_are_omitted():
    df = _combined()
    # Fall 2023 has only CE 342, 2.1 (a CE row). No CON/ENE rows for 2.1
    # that semester, so only one table should be emitted.
    r = annual.build(df, semesters=["Fall 2023"], suboutcomes=["2.1"])
    assert [t.title for t in r.tables] == ["CE — 2.1"]


def test_multiple_semesters_included_in_same_group():
    df = _combined()
    r = annual.build(
        df,
        semesters=["Spring 2020", "Spring 2021"],
        suboutcomes=["1.1"],
    )
    ce_table = next(t for t in r.tables if t.title == "CE — 1.1")
    # Spring 2020 (CE 282) and Spring 2021 (CE 282), same course two semesters.
    semesters_in_rows = sorted(r_[1] for r_ in ce_table.rows)
    assert "Spring 2020" in semesters_in_rows
    assert "Spring 2021" in semesters_in_rows


def test_subtitle_shows_selection():
    df = _combined()
    r = annual.build(
        df,
        semesters=["Spring 2020", "Spring 2021"],
        suboutcomes=["1.1", "2.1"],
    )
    assert r.subtitle is not None
    assert "Spring 2020" in r.subtitle
    assert "1.1" in r.subtitle
    assert "2.1" in r.subtitle


def test_report_renders_via_all_renderers():
    """Smoke test: the emitted Report is consumable by every renderer."""
    from pat.render import markdown as md_renderer
    from pat.render import html as html_renderer

    df = _combined()
    r = annual.build(df, semesters=["Spring 2020"], suboutcomes=["1.1"])
    md_out = md_renderer.render(r)
    html_out = html_renderer.render(r)
    assert "CE — 1.1" in md_out or "CE" in md_out and "1.1" in md_out
    assert "CE" in html_out and "1.1" in html_out
    assert "CE 282" in md_out and "CE 282" in html_out
