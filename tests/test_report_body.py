"""Tests for Report.body -- the ordered narrative/table sequence.

The legacy ``tables`` / ``narrative`` lists render as two groups in a
fixed order. ``body`` exists so a report can interleave them; these
tests pin that ordering in every renderer, since a silent fallback to
group order would quietly scramble the Annual Assessment report.
"""

from __future__ import annotations

import pytest

from pat.render import docx as docx_r
from pat.render import html as html_r
from pat.render import markdown as md_r
from pat.render.model import NamedTable, NarrativeBlock, Report


def _report() -> Report:
    return Report(title="Doc", body=[
        NarrativeBlock(heading="First", body_markdown="alpha", level=1),
        NamedTable(title="", columns=["C"], rows=[["CELL_ALPHA"]]),
        NarrativeBlock(heading="Second", body_markdown="beta", level=3),
        NamedTable(title="", columns=["C"], rows=[["CELL_BETA"]]),
    ])


def test_markdown_keeps_body_order():
    out = md_r.render(_report())
    assert out.index("First") < out.index("CELL_ALPHA") < out.index("Second") < out.index("CELL_BETA")


def test_html_keeps_body_order():
    out = html_r.render(_report())
    assert out.index("First") < out.index("CELL_ALPHA") < out.index("Second") < out.index("CELL_BETA")


def test_markdown_honors_heading_level():
    out = md_r.render(_report())
    assert "# First" in out
    assert "### Second" in out


def test_html_honors_heading_level():
    out = html_r.render(_report())
    assert "<h1>First</h1>" in out
    assert "<h3>Second</h3>" in out


def test_narrative_level_defaults_to_two():
    """Every pre-existing caller omits `level` and must keep H2."""
    r = Report(title="Doc", narrative=[NarrativeBlock(heading="H", body_markdown="x")])
    assert NarrativeBlock(heading="H", body_markdown="x").level == 2
    assert "## H" in md_r.render(r)
    assert "<h2>H</h2>" in html_r.render(r)


def test_docx_renders_body_items():
    blob = docx_r.render(_report())
    assert blob[:2] == b"PK"


def test_docx_body_paragraph_order():
    docx = pytest.importorskip("docx")
    import io
    doc = docx.Document(io.BytesIO(docx_r.render(_report())))
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert texts.index("First") < texts.index("Second")
    assert len(doc.tables) == 2
    assert doc.tables[0].rows[1].cells[0].text == "CELL_ALPHA"
    assert doc.tables[1].rows[1].cells[0].text == "CELL_BETA"


def test_body_counts_toward_is_empty():
    assert Report(title="x").is_empty()
    assert not Report(title="x", body=[NamedTable(title="", columns=["a"], rows=[])]).is_empty()


def test_unsupported_body_item_is_rejected_loudly():
    bad = Report(title="x", body=["just a string"])
    with pytest.raises(TypeError, match="unsupported Report.body item"):
        md_r.render(bad)
    with pytest.raises(TypeError, match="unsupported Report.body item"):
        html_r.render(bad)
    with pytest.raises(TypeError, match="unsupported Report.body item"):
        docx_r.render(bad)
