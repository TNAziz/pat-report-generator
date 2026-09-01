"""HTML renderer.

Renders a `Report` to a standalone HTML document. Used both for the
in-app preview (Streamlit injects via st.markdown(html, ...)) and as
the source for the PDF renderer (WeasyPrint reads HTML+CSS).

The HTML is intentionally self-contained: inlined CSS, no external
fonts or scripts. This makes the file portable (drop into email,
archive in OneDrive) and avoids the runtime cost of loading remote
resources during PDF generation.
"""

from __future__ import annotations

import html
from typing import Optional

import markdown as md_lib

from . import markdown as M
from .model import (
    Chart,
    Heatmap,
    NamedTable,
    NarrativeBlock,
    ProgramSection,
    Report,
    SemesterSection,
)


# Print-friendly stylesheet. Lives here, not in a .css file, so the
# rendered HTML stays self-contained.
_STYLESHEET = """
@page { size: letter; margin: 0.75in 0.7in; @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 9pt; color: #666; } }
* { box-sizing: border-box; }
body { font-family: "Georgia", "Times New Roman", serif; font-size: 11pt; line-height: 1.45; color: #222; max-width: 7.5in; margin: 0 auto; padding: 0 0.25in; }
h1, h2, h3, h4 { font-family: "Helvetica", "Arial", sans-serif; color: #111; line-height: 1.2; }
h1 { font-size: 22pt; margin: 0.4em 0 0.2em; border-bottom: 2px solid #444; padding-bottom: 0.15em; }
h2 { font-size: 16pt; margin: 1.0em 0 0.3em; border-bottom: 1px solid #ccc; padding-bottom: 0.1em; }
h3 { font-size: 13pt; margin: 0.8em 0 0.2em; color: #444; }
h4 { font-size: 11pt; margin: 0.6em 0 0.1em; color: #555; }
p { margin: 0.3em 0; }
.subtitle { font-style: italic; color: #555; font-size: 12pt; margin-bottom: 0.4em; }
.generated { font-size: 9pt; color: #888; margin-bottom: 1em; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 10pt; page-break-inside: avoid; background: #fff; color: #222; }
th, td { border: 1px solid #bbb; padding: 4pt 6pt; text-align: left; vertical-align: top; color: #222; }
th { background: #f0f0f0; font-weight: 600; color: #222; }
tr:nth-child(even) td { background: #fafafa; color: #222; }
.below-threshold { font-weight: 700; color: #a00; }
blockquote { border-left: 3px solid #ccc; margin: 0.4em 0 0.4em 1em; padding-left: 0.6em; color: #555; }
hr { border: none; border-top: 1px solid #ddd; margin: 0.8em 0; }
.measure-block { page-break-inside: avoid; margin-bottom: 0.6em; }
.chart-figure { margin: 0.8em 0; page-break-inside: avoid; }
.chart-figure svg { max-width: 100%; height: auto; }
.footnote { font-size: 9pt; color: #666; font-style: italic; }
.heatmap-figure { margin: 0.8em 0; page-break-inside: avoid; }
table.heatmap { border-collapse: collapse; margin: 0.4em 0; font-size: 9.5pt; background: #fff; }
table.heatmap th, table.heatmap td { border: 1px solid #ddd; padding: 4pt 6pt; text-align: center; }
table.heatmap th.heatmap-corner { background: #fff; border-color: #fff; color: #222; }
table.heatmap th.heatmap-col, table.heatmap th.heatmap-row { background: #f5f5f5; color: #333; font-weight: 600; }
table.heatmap td.heatmap-cell { min-width: 32pt; font-variant-numeric: tabular-nums; }

"""


def _e(s) -> str:
    """HTML-escape a string."""
    return html.escape(str(s), quote=True)


def _fmt_percent_html(val, below_threshold: bool = False) -> str:
    label = M._fmt_percent(val)
    if below_threshold:
        return f'<span class="below-threshold">{_e(label)}</span>'
    return _e(label)


def _render_summary_table_html(section: ProgramSection) -> str:
    if not section.summary:
        return '<p><em>No data for this program.</em></p>'
    rows_html = []
    for r in section.summary:
        rows_html.append(
            "<tr>"
            f"<td>{_e(r.semester)}</td>"
            f"<td>{_e(r.suboutcome)}</td>"
            f"<td>{_fmt_percent_html(r.performance_indicator, r.below_threshold)}</td>"
            f"<td>{_fmt_percent_html(r.performance, r.below_threshold)}</td>"
            "</tr>"
        )
    return (
        "<table>"
        "<thead><tr>"
        "<th>Semester</th><th>Sub-Outcome</th>"
        "<th>Performance Indicator</th><th>Performance</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
        '<p class="footnote">Cells in bold red indicate the average '
        "performance was below the performance indicator.</p>"
    )


def _render_measure_html(m) -> str:
    perf = _fmt_percent_html(m.performance, m.below_threshold)
    pi = _fmt_percent_html(m.performance_indicator, m.below_threshold)
    n = _e(m.n) if m.n is not None else "N/A"
    return (
        '<div class="measure-block">'
        f"<h4>Sub-Outcome: {_e(m.suboutcome)}</h4>"
        f"<p><strong>Measure Description:</strong> {_e(m.measure_description or 'N/A')}</p>"
        f"<p><strong>Performance Threshold:</strong> {pi}</p>"
        f"<p><strong>Student Performance:</strong> {perf}</p>"
        f"<p><strong>n =</strong> {n}</p>"
        f"<blockquote><strong>Comments:</strong> {_e(m.comments)}<br>"
        f"<strong>Actions Taken:</strong> {_e(m.actions_taken)}</blockquote>"
        "<hr>"
        "</div>"
    )


def _render_semester_section_html(section: SemesterSection) -> str:
    parts = [f"<h2>{_e(section.semester)}</h2>",
             f"<h3>Instructor: {_e(section.instructor or 'N/A')}</h3>"]
    for m in section.measures:
        parts.append(_render_measure_html(m))
    return "".join(parts)


def _render_program_section_html(section: ProgramSection) -> str:
    parts = [f"<h1>{_e(section.program_label)}</h1>",
             _render_summary_table_html(section)]
    for sem in section.semesters:
        parts.append(_render_semester_section_html(sem))
    return "".join(parts)


def _render_named_table_html(t: NamedTable) -> str:
    parts = []
    if t.title:
        parts.append(f"<h2>{_e(t.title)}</h2>")
    if t.columns:
        head = "".join(f"<th>{_e(c)}</th>" for c in t.columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>"
            for row in t.rows
        )
        parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
    if t.footnote:
        parts.append(f'<p class="footnote">{_e(t.footnote)}</p>')
    return "".join(parts)


def _render_narrative_html(block: NarrativeBlock) -> str:
    parts = []
    if block.heading:
        level = max(1, min(6, getattr(block, "level", 2)))
        parts.append(f"<h{level}>{_e(block.heading)}</h{level}>")
    # Body is markdown; convert to HTML via the markdown library.
    parts.append(md_lib.markdown(block.body_markdown, extensions=["tables"]))
    return "".join(parts)


def _render_chart_html(chart: Chart) -> str:
    """Render a chart as an inline SVG line graph.

    Hand-rolled SVG so we don't pull in matplotlib at HTML/PDF render
    time. Suitable for the simple line/bar charts the spec calls for.
    """
    if not chart.series:
        return ""
    width, height = 640, 320
    margin = {"l": 50, "r": 20, "t": 30, "b": 40}
    plot_w = width - margin["l"] - margin["r"]
    plot_h = height - margin["t"] - margin["b"]

    all_x = sorted({x for s in chart.series for x in s.x})
    all_y = [y for s in chart.series for y in s.y]
    if not all_x or not all_y:
        return ""
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = 0, max(max(all_y), 100)
    if x_max == x_min:
        x_max = x_min + 1

    def x_to_px(x):
        return margin["l"] + (x - x_min) / (x_max - x_min) * plot_w

    def y_to_px(y):
        return margin["t"] + plot_h - (y - y_min) / (y_max - y_min) * plot_h

    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet">',
        # White background so dark-themed host pages don't turn this into
        # dark-on-dark. Acts like a card -- consistent in both themes.
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        '<style>.axis{stroke:#666;stroke-width:1}.grid{stroke:#eee;stroke-width:1}'
        '.label{font-family:sans-serif;font-size:10px;fill:#444}'
        '.title{font-family:sans-serif;font-size:12px;font-weight:bold;fill:#222}</style>',
        f'<text class="title" x="{width/2}" y="18" text-anchor="middle">{_e(chart.title)}</text>',
    ]
    # Y-axis gridlines and labels (0, 25, 50, 75, 100).
    for tick in (0, 25, 50, 75, 100):
        y = y_to_px(tick)
        svg_parts.append(f'<line class="grid" x1="{margin["l"]}" y1="{y}" x2="{width-margin["r"]}" y2="{y}"/>')
        svg_parts.append(f'<text class="label" x="{margin["l"]-6}" y="{y+3}" text-anchor="end">{tick}</text>')
    # X-axis labels.
    for x in all_x:
        px = x_to_px(x)
        svg_parts.append(f'<text class="label" x="{px}" y="{height-margin["b"]+14}" text-anchor="middle">{x}</text>')
    # Axis lines.
    svg_parts.append(f'<line class="axis" x1="{margin["l"]}" y1="{margin["t"]}" x2="{margin["l"]}" y2="{height-margin["b"]}"/>')
    svg_parts.append(f'<line class="axis" x1="{margin["l"]}" y1="{height-margin["b"]}" x2="{width-margin["r"]}" y2="{height-margin["b"]}"/>')
    # Series.
    # Legend layout: short colored swatch line, then label text to its right.
    # Both elements live in the upper-right corner of the plot area; the
    # swatch and the text occupy non-overlapping x-ranges.
    swatch_x1 = width - margin["r"] - 70
    swatch_x2 = width - margin["r"] - 50
    label_x = width - margin["r"] - 45
    legend_top = margin["t"] + 12
    for i, s in enumerate(chart.series):
        color = palette[i % len(palette)]
        pts = " ".join(f"{x_to_px(x):.1f},{y_to_px(y):.1f}" for x, y in zip(s.x, s.y))
        svg_parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in zip(s.x, s.y):
            svg_parts.append(
                f'<circle cx="{x_to_px(x):.1f}" cy="{y_to_px(y):.1f}" r="3" fill="{color}"/>'
            )
        # Legend entry: swatch + left-anchored label.
        ly = legend_top + i * 16
        svg_parts.append(
            f'<line x1="{swatch_x1}" y1="{ly}" x2="{swatch_x2}" y2="{ly}" '
            f'stroke="{color}" stroke-width="2"/>'
            f'<circle cx="{(swatch_x1+swatch_x2)/2}" cy="{ly}" r="3" fill="{color}"/>'
            f'<text class="label" x="{label_x}" y="{ly+3}" text-anchor="start">'
            f'{_e(s.name)}</text>'
        )
    svg_parts.append("</svg>")
    return (
        f'<div class="chart-figure"><h2>{_e(chart.title)}</h2>'
        + "".join(svg_parts) + "</div>"
    )




# Named color ramps. Each is a list of (low_rgb, high_rgb).
_RAMPS = {
    "blues":  ((247, 251, 255), (8,  48,  107)),
    "greens": ((247, 252, 245), (0,  68,  27)),
    "reds":   ((255, 245, 240), (103, 0,   13)),
}


def _interpolate_color(low, high, t):
    """Linear interpolation in RGB. t in [0, 1]."""
    return tuple(int(low[i] + (high[i] - low[i]) * t) for i in range(3))


def _text_color_for(bg_rgb):
    """Pick black or white text for readable contrast on bg color."""
    r, g, b = bg_rgb
    # Perceived luminance (W3C-ish coefficients).
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#222" if lum > 130 else "#fff"


def _render_heatmap_html(h: Heatmap) -> str:
    """Render a Heatmap as a styled HTML table with color-shaded cells."""
    if not h.rows or not h.columns:
        return ""
    # Determine value bounds.
    flat = [v for row in h.values for v in row
            if v is not None and not (isinstance(v, float) and v != v)]
    vmin = h.vmin if h.vmin is not None else (min(flat) if flat else 0)
    vmax = h.vmax if h.vmax is not None else (max(flat) if flat else 1)
    if vmax <= vmin:
        vmax = vmin + 1  # avoid division by zero
    low_rgb, high_rgb = _RAMPS.get(h.color_scheme, _RAMPS["blues"])

    # Build header row.
    head_cells = [f'<th class="heatmap-corner">{_e(h.row_label or "")}</th>']
    for c in h.columns:
        head_cells.append(f'<th class="heatmap-col">{_e(c)}</th>')

    # Build data rows.
    body_rows = []
    for r, label in enumerate(h.rows):
        cells = [f'<th class="heatmap-row">{_e(label)}</th>']
        for c in range(len(h.columns)):
            try:
                v = h.values[r][c]
            except IndexError:
                v = None
            is_zero = (v == 0)
            is_missing = (v is None or (isinstance(v, float) and v != v))
            if is_missing:
                t = 0.0
                display = h.empty_marker
            else:
                t = max(0.0, min(1.0, (v - vmin) / (vmax - vmin)))
                display = h.value_format.format(v)
            if h.highlight_zero and is_zero:
                # Distinct "no coverage" treatment: light pink background,
                # bold red text. Visually unambiguous against the blue scale.
                style = "background:#fce6e6;color:#a00000;font-weight:700;"
                cell_class = "heatmap-cell heatmap-zero"
            else:
                bg = _interpolate_color(low_rgb, high_rgb, t)
                fg = _text_color_for(bg)
                style = (
                    f'background:rgb({bg[0]},{bg[1]},{bg[2]});'
                    f'color:{fg};'
                )
                cell_class = "heatmap-cell"
            cells.append(f'<td class="{cell_class}" style="{style}">{_e(display)}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    # Color legend (gradient bar).
    grad_id = "grad_" + str(abs(hash(h.title)) % 10**8)
    legend_svg = (
        '<svg width="220" height="40" xmlns="http://www.w3.org/2000/svg" '
        'style="margin-top:6px">'
        # Light background card so dark-mode hosts don't hide dark legend text.
        '<rect x="0" y="0" width="220" height="40" fill="#ffffff"/>'
        f'<defs><linearGradient id="{grad_id}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="rgb({low_rgb[0]},{low_rgb[1]},{low_rgb[2]})"/>'
        f'<stop offset="100%" stop-color="rgb({high_rgb[0]},{high_rgb[1]},{high_rgb[2]})"/>'
        '</linearGradient></defs>'
        f'<rect x="0" y="6" width="200" height="14" fill="url(#{grad_id})" '
        'stroke="#888" stroke-width="0.5"/>'
        f'<text x="0"   y="35" font-family="sans-serif" font-size="10" fill="#444">{_e(h.value_format.format(vmin))}</text>'
        f'<text x="200" y="35" font-family="sans-serif" font-size="10" fill="#444" text-anchor="end">{_e(h.value_format.format(vmax))}</text>'
        '</svg>'
    )

    # Standalone "no coverage" legend chip when highlight_zero is on.
    if h.highlight_zero:
        legend_svg += (
            '<svg width="160" height="22" xmlns="http://www.w3.org/2000/svg" '
            'style="margin-left:14px;vertical-align:bottom">'
            '<rect x="0" y="0" width="160" height="22" fill="#ffffff"/>'
            '<rect x="0" y="4" width="18" height="14" fill="#fce6e6" stroke="#888" stroke-width="0.5"/>'
            '<text x="24" y="15" font-family="sans-serif" font-size="10" fill="#444">= not assessed</text>'
            '</svg>'
        )

    parts = [
        '<div class="heatmap-figure">',
        f"<h2>{_e(h.title)}</h2>",
        '<table class="heatmap">',
        '<thead><tr>' + "".join(head_cells) + '</tr></thead>',
        '<tbody>' + "".join(body_rows) + '</tbody>',
        '</table>',
        legend_svg,
    ]
    if h.caption:
        parts.append(f'<p class="footnote">{_e(h.caption)}</p>')
    parts.append('</div>')
    return "".join(parts)


def _render_body_item_html(item) -> str:
    """Render one ordered ``Report.body`` item by type."""
    if isinstance(item, NarrativeBlock):
        return _render_narrative_html(item)
    if isinstance(item, NamedTable):
        return _render_named_table_html(item)
    if isinstance(item, Chart):
        return _render_chart_html(item)
    if isinstance(item, Heatmap):
        return _render_heatmap_html(item)
    raise TypeError(f"unsupported Report.body item: {type(item).__name__}")


def render_body(report: Report) -> str:
    """Render the inner HTML for the report (no <html>/<head>/<body> wrapper)."""
    parts = [f"<h1>{_e(report.title)}</h1>"]
    if report.subtitle:
        parts.append(f'<p class="subtitle">{_e(report.subtitle)}</p>')
    if report.generated_on:
        parts.append(
            f'<p class="generated">Generated '
            f"{_e(report.generated_on.strftime('%B %d, %Y'))}</p>"
        )
    for section in report.sections:
        parts.append(_render_program_section_html(section))
    for item in report.body:
        parts.append(_render_body_item_html(item))
    for block in report.narrative:
        parts.append(_render_narrative_html(block))
    for table in report.tables:
        parts.append(_render_named_table_html(table))
    for chart in report.charts:
        parts.append(_render_chart_html(chart))
    for heatmap in report.heatmaps:
        parts.append(_render_heatmap_html(heatmap))
    return "".join(parts)


def render(report: Report) -> str:
    """Render a Report to a standalone HTML document."""
    body = render_body(report)
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8">'
        f"<title>{_e(report.title)}</title>"
        f"<style>{_STYLESHEET}</style></head>"
        f"<body>{body}</body></html>"
    )
