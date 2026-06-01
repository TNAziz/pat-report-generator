"""Add heatmap parity tests + extend renderer tests."""

import io
import zipfile

import pytest
from docx import Document

from pat.render import docx as Drx, html as H, markdown as M, pdf as P
from pat.render.model import Heatmap, Report
from tests.report_fixtures import make_suboutcome_coverage


def test_heatmap_markdown_renders_as_counts_table():
    r = make_suboutcome_coverage()
    out = M.render(r)
    # Title rendered.
    assert "Civil Engineering: sub-outcome" in out
    # Sub-outcome labels appear.
    for code in ("1.1", "2.1", "4.1"):
        assert code in out
    # Year columns.
    for yr in ("2020", "2025"):
        assert yr in out


def test_heatmap_html_includes_colored_cells_and_legend():
    r = make_suboutcome_coverage()
    out = H.render(r)
    # Cell styling.
    assert "background:rgb(" in out
    # Heatmap-specific CSS.
    assert "table.heatmap" in out
    # Gradient legend SVG.
    assert "<linearGradient" in out


def test_heatmap_html_renders_one_block_per_program():
    r = make_suboutcome_coverage()
    out = H.render(r)
    for prog in ("Civil Engineering", "Construction Engineering", "Environmental Engineering"):
        assert prog in out
    # Three heatmap-figure containers.
    assert out.count("heatmap-figure") >= 3


def test_heatmap_docx_includes_shaded_cells():
    r = make_suboutcome_coverage()
    blob = Drx.render(r)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        body = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    # Cell shading XML.
    assert "<w:shd " in body or "<w:shd>" in body
    # The fill attribute should appear with a hex color.
    assert 'w:fill="' in body


def test_heatmap_docx_has_one_table_per_heatmap():
    r = make_suboutcome_coverage()
    blob = Drx.render(r)
    doc = Document(io.BytesIO(blob))
    # 3 heatmaps -> at least 3 tables (no other content in this report).
    assert len(doc.tables) >= 3


def test_heatmap_pdf_produced():
    r = make_suboutcome_coverage()
    blob = P.render(r)
    assert blob[:5] == b"%PDF-"
    assert len(blob) > 5000


def test_heatmap_handles_empty_marker():
    """empty_marker applies to truly missing values (None/NaN), not zeros.

    Zeros get the highlight_zero treatment instead, so coverage gaps
    stand out from "data present but low".
    """
    h = Heatmap(
        title="t",
        row_label="r",
        col_label="c",
        rows=["a"],
        columns=["x", "y"],
        values=[[None, 3]],
        empty_marker="-",
    )
    r = Report(title="x", heatmaps=[h])
    md = M.render(r)
    assert "| - |" in md or " - " in md
    html = H.render(r)
    assert ">-<" in html


def test_heatmap_zero_cells_get_distinct_styling():
    """Zero cells render with pink/red treatment so gaps are visible."""
    h = Heatmap(
        title="t", row_label="r", col_label="c",
        rows=["a"], columns=["x", "y", "z"],
        values=[[0, 2, 5]],
        vmin=0, vmax=5,
        highlight_zero=True,
    )
    r = Report(title="x", heatmaps=[h])
    html = H.render(r)
    # Zero cell uses the salmon background, not the blue scale.
    assert "#fce6e6" in html
    # Legend includes the "not assessed" chip.
    assert "not assessed" in html


def test_heatmap_highlight_zero_off_uses_normal_scale():
    """When highlight_zero=False, zero cells use the regular color ramp."""
    h = Heatmap(
        title="t", row_label="r", col_label="c",
        rows=["a"], columns=["x"],
        values=[[0]],
        vmin=0, vmax=5,
        highlight_zero=False,
    )
    r = Report(title="x", heatmaps=[h])
    html = H.render(r)
    assert "#fce6e6" not in html
    assert "not assessed" not in html


def test_heatmap_color_ramp_respects_vmin_vmax():
    """The cell with max value should be deeper than the cell with min value.

    Use non-zero values so both cells use the blue color ramp (zero
    cells get the special "no coverage" treatment instead).
    """
    h = Heatmap(
        title="t", row_label="r", col_label="c",
        rows=["a"], columns=["x", "y"],
        values=[[1, 10]],
        vmin=0, vmax=10,
    )
    out = H.render(Report(title="x", heatmaps=[h]))
    # Two background-color declarations, the second should be darker
    # (lower channel values).
    import re
    matches = re.findall(r"background:rgb\((\d+),(\d+),(\d+)\)", out)
    # Filter to the two heatmap cells (the data cells).
    rgbs = [tuple(map(int, m)) for m in matches]
    # At least two cells; the high-value cell is darker overall.
    assert len(rgbs) >= 2
    # Sum across channels: higher sum = lighter; the last data cell should
    # have a lower sum than the first.
    sums = [sum(rgb) for rgb in rgbs[:2]]
    assert sums[1] < sums[0], f"expected darker cell for higher value, got {sums}"
