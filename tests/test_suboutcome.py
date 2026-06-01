"""Unit tests for pat.analysis.suboutcome.

Traceability: R17 (course selection), R18 (description joining).
"""

from __future__ import annotations

from pathlib import Path

from pat import ingest
from pat.analysis import suboutcome

FIXTURES = Path(__file__).parent / "fixtures"


def _schedule():
    return ingest.read_assessment_schedule(FIXTURES / "assessment_schedule_TierA.xlsx")


def test_lookup_known_course():
    r = suboutcome.build(_schedule(), "CE 488")
    assert r.title == "CE 488"
    # Two narrative blocks: Programs, Sub-Outcomes.
    headings = [b.heading for b in r.narrative]
    assert headings == ["Programs", "Sub-Outcomes"]


def test_programs_joined_with_slash():
    r = suboutcome.build(_schedule(), "CE 488")
    programs_block = next(b for b in r.narrative if b.heading == "Programs")
    # Fixture has Programs="CE/ENE".
    assert "CE" in programs_block.body_markdown
    assert "ENE" in programs_block.body_markdown


def test_suboutcomes_include_descriptions():
    r = suboutcome.build(_schedule(), "CE 488")
    sub_block = next(b for b in r.narrative if b.heading == "Sub-Outcomes")
    # 1.2 -> "Formulate the solution to engineering problems." from fixture.
    assert "**1.2:**" in sub_block.body_markdown
    assert "Formulate" in sub_block.body_markdown


def test_suboutcomes_sorted_by_code():
    r = suboutcome.build(_schedule(), "CE 488")
    sub_block = next(b for b in r.narrative if b.heading == "Sub-Outcomes")
    # CE 488 in fixture has 1.2, 2.1 checked.
    text = sub_block.body_markdown
    assert text.index("1.2") < text.index("2.1")


def test_unknown_course_returns_friendly_report():
    r = suboutcome.build(_schedule(), "CE 999")
    assert r.subtitle == "Not on the Assessment Schedule"
    body = r.narrative[0].body_markdown
    assert "not found" in body.lower()


def test_normalizes_input_format():
    r1 = suboutcome.build(_schedule(), "CE 488")
    r2 = suboutcome.build(_schedule(), "ce-488")
    r3 = suboutcome.build(_schedule(), "  CE488 ")
    assert r1.title == r2.title == r3.title == "CE 488"
