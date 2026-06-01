"""Report intermediate representation.

A `Report` is a typed, renderer-agnostic description of what should
appear in a generated document. Every analysis function in
``pat.analysis`` returns a `Report`; every renderer in
``pat.render.{markdown,html,docx,pdf}`` consumes one.

This decoupling means new output formats are new renderer modules, not
rewrites of analysis logic, and content parity across formats is
enforced by type rather than by string-conversion fidelity. See
``specs/03_data_model.md`` §5 and ``specs/02_architecture.md`` D1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


# ---------------------------------------------------------------------------
# Course-report content
# ---------------------------------------------------------------------------


@dataclass
class SummaryRow:
    """One row of a course's per-semester summary table.

    ``below_threshold`` is set when ``performance < performance_indicator``;
    renderers use it to bold or otherwise highlight underperforming rows.
    """
    semester: str                       # "Spring 2020"
    suboutcome: str                     # "1.1"
    performance_indicator: Optional[float]
    performance: Optional[float]
    below_threshold: bool


@dataclass
class MeasureDetail:
    """One measurement event for a sub-outcome in a given semester."""
    suboutcome: str
    measure_description: str
    performance_indicator: Optional[float]
    performance: Optional[float]
    n: Optional[int]
    comments: str
    actions_taken: str
    below_threshold: bool = False


@dataclass
class SemesterSection:
    """All measurement detail for one semester within a program section."""
    semester: str
    instructor: str
    measures: List[MeasureDetail] = field(default_factory=list)


@dataclass
class ProgramSection:
    """Course-report content scoped to a single program (CE/CON/ENE)."""
    program_code: str                   # "CE"
    program_label: str                  # "Civil Engineering"
    summary: List[SummaryRow] = field(default_factory=list)
    semesters: List[SemesterSection] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Flat-table content (used by Sub-Outcome Lookup, Coverage Check)
# ---------------------------------------------------------------------------


@dataclass
class NamedTable:
    """A simple titled table with string-rendered cells.

    Renderers may apply per-format styling (zebra stripes, borders) but
    the cell contents are taken as-is.
    """
    title: str
    columns: List[str]
    rows: List[List[str]]
    footnote: Optional[str] = None


@dataclass
class NarrativeBlock:
    """A free-form heading + markdown paragraph.

    Used for the Sub-Outcome Lookup tool's bulleted output and as the
    container for future LLM-generated narrative text. Body is markdown;
    each renderer is responsible for converting it to its format.
    """
    heading: Optional[str]
    body_markdown: str


# ---------------------------------------------------------------------------
# Chart data (data only; rendering decisions are per-format)
# ---------------------------------------------------------------------------


@dataclass
class ChartSeries:
    """One named line on a multi-series chart."""
    name: str
    x: List
    y: List


@dataclass
class Chart:
    """Renderer-agnostic chart description.

    The renderers will reach for sensible defaults: matplotlib for DOCX
    and PDF embedded images, native Streamlit chart for the in-app
    preview, none for plain Markdown (text-only).
    """
    title: str
    x_label: str
    y_label: str
    series: List[ChartSeries] = field(default_factory=list)
    kind: str = "line"                  # "line" | "bar"


@dataclass
class Heatmap:
    """Renderer-agnostic 2D heatmap (e.g., sub-outcome coverage by year).

    Use for "did we assess this sub-outcome this year?" style displays.
    Values are typically counts (0, 1, 2, ...); renderers interpolate
    cell colors from `low_color` to `high_color` based on `vmin`/`vmax`.

    Attributes
    ----------
    title : str
        Heatmap title (rendered as H2 above the grid).
    row_label, col_label : str
        Axis labels (e.g. "Sub-Outcome", "Year").
    rows : list of str
        Row tick labels, top to bottom (e.g. ["1.1", "1.2", "2.1", ...]).
    columns : list of str
        Column tick labels, left to right (e.g. ["2020", "2021", ...]).
    values : list of list of float
        ``values[r][c]`` is the cell at row ``r``, column ``c``.
    vmin, vmax : float, optional
        Color-scale bounds. If None, inferred from the data.
    color_scheme : str
        Named ramp: "blues" (white -> deep blue) is the default; other
        palettes can be added without changing the IR.
    value_format : str
        Python format string for cell text (e.g. "{:.0f}").
    empty_marker : str
        What to render in cells equal to zero/NaN ("" for blank text).
    highlight_zero : bool
        When True (default), cells with value == 0 are rendered with a
        distinct "no coverage" treatment (pink background, red text) so
        gaps in assessment coverage are visible at a glance. Set to
        False if zero is a normal data value rather than a gap signal.
    caption : str, optional
        One-line caption rendered as a small italic footnote.
    """
    title: str
    row_label: str
    col_label: str
    rows: List[str]
    columns: List[str]
    values: List[List[float]]
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    color_scheme: str = "blues"
    value_format: str = "{:.0f}"
    empty_marker: str = ""
    highlight_zero: bool = True
    caption: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level Report
# ---------------------------------------------------------------------------


@dataclass
class Report:
    """Top-level report container.

    Course Report tools populate ``sections``. The lighter-weight tools
    (Sub-Outcome Lookup, Coverage Check) populate ``tables``,
    ``narrative``, and ``charts`` instead. All renderers handle a Report
    with any combination of these fields populated.
    """
    title: str                          # "CE 282" or "Coverage Check"
    subtitle: Optional[str] = None      # e.g. "Spring 2020 – Spring 2026"
    generated_on: Optional[date] = None
    sections: List[ProgramSection] = field(default_factory=list)
    tables: List[NamedTable] = field(default_factory=list)
    narrative: List[NarrativeBlock] = field(default_factory=list)
    charts: List[Chart] = field(default_factory=list)
    heatmaps: List[Heatmap] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.sections or self.tables or self.narrative
                    or self.charts or self.heatmaps)
