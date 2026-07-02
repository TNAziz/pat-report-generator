"""Annual Assessment analysis.

Given a set of picked semesters and a set of picked sub-outcomes, build
a Report that lists every matching PAT measurement grouped by
(program, sub-outcome). No aggregation -- each underlying row is shown
as-is so faculty can see exactly which course/semester produced which
performance and comment.

Program order follows :data:`pat.normalize.PROGRAM_LABELS`
(CE, ENE, CON); sub-outcome order follows numeric-major/minor.
Groups with zero matching rows are omitted.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional

import pandas as pd

from .. import normalize as N
from ..ingest import _sort_outcome_codes
from ..render.model import NamedTable, NarrativeBlock, Report


_COLUMNS: List[str] = ["Course", "Semester", "Instructor", "Performance", "N", "Comment"]

_NULLISH_LOWER = {"", "nan", "none", "null", "na"}


def _format_pct(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and pd.isna(value):
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _format_int(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and pd.isna(value):
        return "—"
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "—"


def _clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value).strip()
    if s.lower() in _NULLISH_LOWER:
        return ""
    return s


def build(
    df: pd.DataFrame,
    semesters: Iterable[str],
    suboutcomes: Iterable[str],
    generated_on: Optional[date] = None,
) -> Report:
    """Build the Annual Assessment report.

    Parameters
    ----------
    df : pd.DataFrame
        A canonical combined frame (as returned by ``data.get_combined``).
    semesters : iterable of str
        Semester labels the user picked (e.g. ``["Spring 2025", "Fall 2025"]``).
        Empty means "no selection" and yields a friendly prompt report.
    suboutcomes : iterable of str
        Sub-outcome codes the user picked (e.g. ``["1.1", "2.1"]``).
        Empty means "no selection" and yields a friendly prompt report.
    generated_on : date, optional
        Report generation date; defaults to today.

    Returns
    -------
    Report
        ``tables`` is one :class:`NamedTable` per non-empty
        ``(program, sub-outcome)`` pair. When no filter is provided, or
        no rows match, the report carries a single narrative block
        explaining what happened.
    """
    if generated_on is None:
        generated_on = date.today()

    sems = [str(s).strip() for s in semesters if s is not None and str(s).strip()]
    subs_norm: List[str] = []
    for s in suboutcomes:
        if s is None:
            continue
        code = N.normalize_suboutcome(s)
        if code:
            subs_norm.append(code)
    subs_norm = list(dict.fromkeys(subs_norm))  # dedupe, preserve order

    subtitle_parts: List[str] = []
    if sems:
        subtitle_parts.append(", ".join(sems))
    if subs_norm:
        subtitle_parts.append(", ".join(_sort_outcome_codes(list(subs_norm))))
    subtitle = " — ".join(subtitle_parts) if subtitle_parts else None
    title = "Annual Assessment"

    def _narrative_report(message: str) -> Report:
        return Report(
            title=title,
            subtitle=subtitle,
            generated_on=generated_on,
            narrative=[NarrativeBlock(heading=None, body_markdown=message)],
        )

    if df is None or df.empty:
        return _narrative_report(
            "_No PAT data is loaded. Upload program CSVs in the sidebar._"
        )
    if not sems or not subs_norm:
        return _narrative_report(
            "_Pick at least one semester and one sub-outcome to generate the report._"
        )

    working = df.copy()
    working["semester"] = working["semester"].astype(str).str.strip()
    working["suboutcome"] = working["suboutcome"].map(N.normalize_suboutcome)

    filtered = working[
        working["semester"].isin(sems) & working["suboutcome"].isin(subs_norm)
    ]
    if filtered.empty:
        return _narrative_report(
            "_No measurements matched the selected semesters and sub-outcomes._"
        )

    sorted_subs = _sort_outcome_codes(list(subs_norm))
    tables: List[NamedTable] = []

    for prog_code in N.PROGRAM_LABELS:
        prog_df = filtered[filtered["program"].astype(str) == prog_code]
        if prog_df.empty:
            continue
        for sub in sorted_subs:
            group = prog_df[prog_df["suboutcome"] == sub]
            if group.empty:
                continue
            sort_cols = [c for c in ("semester_sort_key", "course") if c in group.columns]
            if sort_cols:
                ascending = [False if c == "semester_sort_key" else True for c in sort_cols]
                group = group.sort_values(sort_cols, ascending=ascending, kind="stable")
            rows: List[List[str]] = []
            for _, r in group.iterrows():
                rows.append([
                    _clean_text(r.get("course")),
                    _clean_text(r.get("semester")),
                    _clean_text(r.get("instructor")),
                    _format_pct(r.get("performance")),
                    _format_int(r.get("total_scores")),
                    _clean_text(r.get("comments")),
                ])
            tables.append(NamedTable(
                title=f"{prog_code} — {sub}",
                columns=list(_COLUMNS),
                rows=rows,
            ))

    if not tables:
        return _narrative_report(
            "_No measurements matched the selected semesters and sub-outcomes._"
        )

    return Report(
        title=title,
        subtitle=subtitle,
        generated_on=generated_on,
        tables=tables,
    )
