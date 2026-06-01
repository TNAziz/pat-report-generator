"""Markdown renderer.

Renders a `Report` to a Markdown string. The output format matches the
existing notebook's output for the Course Report tool so the Phase 3
regression diff is byte-clean. For the other tools (Sub-Outcome Lookup,
Coverage Check) the format is intentionally similar but not strictly
notebook-compatible -- the notebook formatting for those was looser.
"""

from __future__ import annotations

from typing import Optional

from .model import (
    Chart,
    Heatmap,
    NamedTable,
    NarrativeBlock,
    ProgramSection,
    Report,
    SemesterSection,
    SummaryRow,
)


def _fmt_percent(val: Optional[float]) -> str:
    """Format a percent like the notebook: integer if exact, else 1 decimal."""
    if val is None:
        return "N/A"
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}%"
    return f"{val:.1f}%"


def _bold(s: str) -> str:
    return f"**{s}**"


def _render_summary_table(rows) -> str:
    """Render the per-semester / per-sub-outcome summary table."""
    if not rows:
        return "_No data for this program._\n"
    lines = [
        "| Semester | Sub-Outcome | Performance Indicator | Performance |",
        "|---|---|---|---|",
    ]
    for r in rows:
        pi = _fmt_percent(r.performance_indicator)
        perf = _fmt_percent(r.performance)
        if r.below_threshold:
            pi, perf = _bold(pi), _bold(perf)
        lines.append(f"| {r.semester} | {r.suboutcome} | {pi} | {perf} |")
    lines.append("")
    lines.append("_Cells in **bold** indicate the average performance was below the performance indicator._")
    lines.append("")
    return "\n".join(lines)


def _render_semester_section(section: SemesterSection) -> str:
    lines = [
        f"## {section.semester}",
        f"### Instructor: {section.instructor or 'N/A'}",
        "",
    ]
    for m in section.measures:
        perf_str = _fmt_percent(m.performance)
        pi_str = _fmt_percent(m.performance_indicator)
        n_str = str(m.n) if m.n is not None else "N/A"
        lines.append(f"#### Sub-Outcome: {m.suboutcome}")
        lines.append(f"**Measure Description:** {m.measure_description or 'N/A'}")
        lines.append("")
        lines.append(f"**Performance Threshold:** {pi_str}")
        lines.append("")
        lines.append(f"**Student Performance:** {perf_str}")
        lines.append("")
        lines.append(f"**n =** {n_str}")
        lines.append(f"> **Comments:** {m.comments}")
        lines.append(">")
        lines.append(f"> **Actions Taken:** {m.actions_taken}")
        lines.append(">")
        lines.append("---")
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def _render_program_section(section: ProgramSection) -> str:
    parts = [f"# {section.program_label}", ""]
    parts.append(_render_summary_table(section.summary))
    for sem in section.semesters:
        parts.append(_render_semester_section(sem))
    return "\n".join(parts)


def _render_named_table(t: NamedTable) -> str:
    lines = []
    if t.title:
        lines.append(f"## {t.title}")
        lines.append("")
    if t.columns:
        lines.append("| " + " | ".join(t.columns) + " |")
        lines.append("|" + "|".join(["---"] * len(t.columns)) + "|")
        for row in t.rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        lines.append("")
    if t.footnote:
        lines.append(f"_{t.footnote}_")
        lines.append("")
    return "\n".join(lines)


def _render_narrative(block: NarrativeBlock) -> str:
    lines = []
    if block.heading:
        lines.append(f"## {block.heading}")
        lines.append("")
    lines.append(block.body_markdown)
    lines.append("")
    return "\n".join(lines)


def _render_chart_textual(chart: Chart) -> str:
    """Text-only chart placeholder for Markdown.

    Markdown has no native charting; renderers that target visual
    formats (PDF, DOCX, HTML) embed an actual chart image. The Markdown
    output describes the chart as a table so the information isn't
    lost.
    """
    if not chart.series:
        return ""
    lines = [
        f"## {chart.title}",
        "",
    ]
    # Build a wide table: rows = x values, columns = series.
    all_x = sorted({x for s in chart.series for x in s.x})
    header = [chart.x_label] + [s.name for s in chart.series]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for x in all_x:
        row = [str(x)]
        for s in chart.series:
            try:
                idx = s.x.index(x)
                row.append(str(s.y[idx]))
            except ValueError:
                row.append("")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return "\n".join(lines)




def _render_heatmap_textual(h: Heatmap) -> str:
    """Markdown has no native heat-colored cells; render as a counts table.

    The grid is preserved so the information is still readable in plain
    text or unstyled markdown viewers.
    """
    if not h.rows or not h.columns:
        return ""
    lines = [f"## {h.title}", ""]
    header = [h.row_label or "" ] + [str(c) for c in h.columns]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for r, label in enumerate(h.rows):
        row_vals = []
        for c in range(len(h.columns)):
            try:
                v = h.values[r][c]
            except IndexError:
                v = None
            if v is None or (isinstance(v, float) and v != v):
                row_vals.append(h.empty_marker)
            else:
                row_vals.append(h.value_format.format(v))
        lines.append("| " + " | ".join([str(label)] + row_vals) + " |")
    lines.append("")
    if h.caption:
        lines.append(f"_{h.caption}_")
        lines.append("")
    return "\n".join(lines)

def render(report: Report) -> str:
    """Render a Report to a single Markdown string.

    The leading H1 title and optional subtitle are produced once;
    sections, tables, narrative blocks, and charts then follow in
    insertion order.
    """
    parts = [f"# {report.title}", ""]
    if report.subtitle:
        parts.append(report.subtitle)
        parts.append("")
    if report.generated_on:
        parts.append(f"_Generated {report.generated_on.strftime('%B %d, %Y')}_")
        parts.append("")
    for section in report.sections:
        parts.append(_render_program_section(section))
    for block in report.narrative:
        parts.append(_render_narrative(block))
    for table in report.tables:
        parts.append(_render_named_table(table))
    for chart in report.charts:
        parts.append(_render_chart_textual(chart))
    for heatmap in report.heatmaps:
        parts.append(_render_heatmap_textual(heatmap))
    return "\n".join(parts).strip() + "\n"
