"""Tests for pat.llm.drafting_packet.

The packet is simultaneously the prompt and the audit record, so the
things worth pinning are: the data is embedded verbatim, the fingerprint
covers exactly that data, and the provenance block actually reports the
selection and the source hashes.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pat import ingest, llm
from pat.analysis import annual
from pat.render import markdown as md_renderer
from pat.render.model import NamedTable, Report

from tests.test_annual import DESCRIPTIONS, _combined


MANIFEST = {
    "CE": {
        "original_name": "summaryReportCE_F17toF26.csv",
        "uploaded_at": "2026-08-25T13:47:00Z",
        "sha256": "abcdef0123456789" * 4,
        "size_bytes": 370758,
    },
    "schedule": {
        "original_name": "Assessment Schedule - 2025.xlsx",
        "uploaded_at": "2026-08-20T09:00:00Z",
        "sha256": "9876543210fedcba" * 4,
        "size_bytes": 50169,
    },
}


def _report_and_markdown():
    report = annual.build(
        _combined(), semesters=["Spring 2020"], outcomes=["1"],
        programs=["CE"], descriptions=DESCRIPTIONS,
    )
    return report, md_renderer.render(report)


def _packet(**kwargs) -> str:
    report, data = _report_and_markdown()
    return llm.drafting_packet(report, data, generated_on=date(2026, 8, 25), **kwargs)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

def test_packet_has_all_five_sections_in_order():
    packet = _packet()
    positions = [
        packet.index(h) for h in (
            "## 1. Task",
            "## 2. House style and required structure",
            "## 3. Rules for using the data",
            "## 4. Provenance",
            "## 5. Data",
        )
    ]
    assert positions == sorted(positions)


def test_data_section_is_embedded_verbatim():
    """The packet must contain the same bytes as the Markdown download."""
    report, data = _report_and_markdown()
    packet = llm.drafting_packet(report, data, generated_on=date(2026, 8, 25))
    body = packet.split("## 5. Data", 1)[1].strip()
    assert body == data.strip()


def test_fingerprint_covers_the_data_and_nothing_else():
    report, data = _report_and_markdown()
    packet = llm.drafting_packet(report, data, generated_on=date(2026, 8, 25))
    assert f"`{llm.fingerprint(data)}`" in packet


def test_fingerprint_changes_when_the_data_changes():
    a = llm.fingerprint("one measurement")
    b = llm.fingerprint("one measurement.")
    assert a != b
    assert len(a) == 64


def test_fingerprint_is_stable_across_calls():
    assert llm.fingerprint("same text") == llm.fingerprint("same text")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_selection_is_recorded():
    packet = _packet(selection={
        "Programs": ["CE"],
        "Semesters": ["Fall 2024", "Spring 2025"],
        "Outcomes": ["1", "3"],
    })
    assert "- Programs: CE" in packet
    assert "- Semesters: Fall 2024, Spring 2025" in packet
    assert "- Outcomes: 1, 3" in packet


def test_empty_selection_values_read_as_all():
    packet = _packet(selection={"Programs": []})
    assert "- Programs: all" in packet


def test_sources_are_recorded_with_hash_and_upload_time():
    packet = _packet(sources=MANIFEST)
    assert "summaryReportCE_F17toF26.csv" in packet
    assert "2026-08-25T13:47:00Z" in packet
    assert "abcdef012345" in packet          # truncated digest
    assert "370,758 bytes" in packet
    assert "Assessment Schedule - 2025.xlsx" in packet


def test_missing_manifest_is_stated_not_faked():
    packet = _packet(sources=None)
    assert "no upload manifest available" in packet


def test_malformed_manifest_entry_does_not_crash():
    packet = _packet(sources={"CE": {}, "ENE": None})
    assert "## 5. Data" in packet


def test_row_counts_are_reported():
    packet = _packet()
    # Spring 2020 CE / outcome 1 is a single measurement in one table.
    assert "1 measurement rows across 1 courses" in packet


def test_notes_are_included():
    packet = _packet(notes=["Newest measurement update: 2026-03-13"])
    assert "- Newest measurement update: 2026-03-13" in packet


def test_generated_date_is_recorded():
    assert "Packet generated: August 25, 2026" in _packet()


# ---------------------------------------------------------------------------
# Prompt content
# ---------------------------------------------------------------------------

def test_the_three_anthology_sections_are_named_in_the_style():
    packet = _packet()
    assert "Findings" in packet
    assert "Analysis of Findings" in packet
    assert "Actions Taken to Address Areas for Improvement" in packet


def test_rules_forbid_recomputing_the_weighted_average():
    """The single easiest way for a draft to go quietly wrong."""
    assert "Do not recompute it by averaging the per-row Performance" in _packet()


def test_rules_forbid_inventing_a_missing_action():
    packet = _packet()
    assert "None recorded" in packet
    assert "Never invent one" in packet


def test_prompt_sections_are_overridable():
    packet = _packet(task="Just summarize.", style="Terse.", rules="No rules.")
    assert "Just summarize." in packet
    assert "Terse." in packet
    assert "No rules." in packet
    # And the defaults are gone, not merely appended to.
    assert "Anthology" not in packet.split("## 4. Provenance")[0]


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------

def test_counts_fall_back_to_legacy_tables_field():
    report = Report(title="t", tables=[
        NamedTable(title="a", columns=["Course"], rows=[["CE 1"], ["CE 2"]]),
    ])
    packet = llm.drafting_packet(report, "data", generated_on=date(2026, 1, 1))
    assert "2 measurement rows across 2 courses" in packet


def test_counts_dedupe_courses_across_tables():
    report = Report(title="t", body=[
        NamedTable(title="", columns=["Course"], rows=[["CE 282"], ["CE 300"]]),
        NamedTable(title="", columns=["Course"], rows=[["CE 282"]]),
    ])
    packet = llm.drafting_packet(report, "data", generated_on=date(2026, 1, 1))
    assert "3 measurement rows across 2 courses" in packet
    assert "in 2 sub-outcome tables" in packet


def test_empty_report_still_produces_a_packet():
    report = annual.build(pd.DataFrame(), semesters=["Fall 2024"], outcomes=["1"])
    packet = llm.drafting_packet(report, md_renderer.render(report))
    assert "## 5. Data" in packet
    assert "0 measurement rows" in packet
