"""Course Report analysis.

Builds a `Report` IR for a single course from the cleaned, canonical
DataFrame produced by `pat.data.get_combined()`. Mirrors the logic in
the existing notebook's cell 2 so the Markdown output is bit-for-bit
identical against the captured Phase 1 baselines.

Inputs are pre-cleaned (see ``pat.normalize.clean_dataframe``), so we
do no string-stripping or null filtering here.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

import pandas as pd

from .. import data as data_layer
from .. import normalize as N
from ..render.model import (
    MeasureDetail,
    ProgramSection,
    Report,
    SemesterSection,
    SummaryRow,
)


def _avg(values):
    """Mean of non-null numeric values, or None if no values."""
    vals = [v for v in values if v is not None and not pd.isna(v)]
    return (sum(vals) / len(vals)) if vals else None


def _mode_indicator(series: pd.Series) -> Optional[float]:
    """Most common performance indicator for a slice, or first non-null fallback.

    Matches the notebook: takes the mode of the parsed percent values
    so a column with mostly 70 and one stray 75 reports 70.
    """
    vals = [v for v in series if v is not None and not pd.isna(v)]
    if not vals:
        return None
    counts: dict[float, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _semester_sort_key(year, season) -> int:
    if year is None or season is None or pd.isna(year):
        return -1
    return int(year) * 2 + (1 if season == "F" else 0)


def _ordered_semesters(df: pd.DataFrame) -> list:
    """Return unique semesters in newest-first order, matching the notebook."""
    pairs = df[["semester", "semester_year", "semester_season"]].dropna(
        subset=["semester"]
    ).drop_duplicates()
    pairs = pairs[pairs["semester"] != ""]
    pairs = pairs.copy()
    pairs["__key"] = [
        _semester_sort_key(y, s)
        for y, s in zip(pairs["semester_year"], pairs["semester_season"])
    ]
    pairs = pairs.sort_values("__key", ascending=False)
    return pairs["semester"].astype(str).tolist()


def _build_summary(df_prog: pd.DataFrame) -> list:
    """Per-(semester, suboutcome) summary rows for one program section."""
    rows: list = []
    for sem in _ordered_semesters(df_prog):
        df_sem = df_prog[df_prog["semester"] == sem]
        suboutcomes = sorted(
            s for s in df_sem["suboutcome"].dropna().astype(str).unique() if s
        )
        for sub in suboutcomes:
            df_ss = df_sem[df_sem["suboutcome"].astype(str) == sub]
            pi = _mode_indicator(df_ss["performance_indicator"])
            perf = _avg(df_ss["performance"].tolist())
            below = (
                pi is not None
                and perf is not None
                and perf < pi
            )
            rows.append(SummaryRow(
                semester=sem,
                suboutcome=sub,
                performance_indicator=pi,
                performance=perf,
                below_threshold=bool(below),
            ))
    return rows


def _build_semesters(df_prog: pd.DataFrame) -> list:
    """Per-semester detailed sections for one program section."""
    sections: list = []
    for sem in _ordered_semesters(df_prog):
        df_sem = df_prog[df_prog["semester"] == sem]
        instructors = [
            i for i in df_sem["instructor"].dropna().astype(str).unique() if i
        ]
        instructor_str = ", ".join(instructors)
        measures: list = []
        for sub in sorted(
            s for s in df_sem["suboutcome"].dropna().astype(str).unique() if s
        ):
            df_ss = df_sem[df_sem["suboutcome"].astype(str) == sub]
            for _, row in df_ss.iterrows():
                pi = row.get("performance_indicator")
                pi = None if pd.isna(pi) else float(pi)
                perf = row.get("performance")
                perf = None if pd.isna(perf) else float(perf)
                n = row.get("total_scores")
                n = None if pd.isna(n) else int(n)
                below = (
                    pi is not None and perf is not None and perf < pi
                )
                measures.append(MeasureDetail(
                    suboutcome=str(sub),
                    measure_description=str(row.get("measure_description", "") or ""),
                    performance_indicator=pi,
                    performance=perf,
                    n=n,
                    comments=str(row.get("comments", "") or ""),
                    actions_taken=str(row.get("actions_taken", "") or ""),
                    below_threshold=bool(below),
                ))
        sections.append(SemesterSection(
            semester=sem,
            instructor=instructor_str,
            measures=measures,
        ))
    return sections


def _build_program_section(program_code: str, df_prog: pd.DataFrame):
    if df_prog.empty:
        return None
    return ProgramSection(
        program_code=program_code,
        program_label=N.PROGRAM_LABELS.get(program_code, program_code),
        summary=_build_summary(df_prog),
        semesters=_build_semesters(df_prog),
    )


def build(
    df: pd.DataFrame,
    course_code: str,
    year_range: Optional[tuple] = None,
    programs: Optional[Iterable[str]] = None,
    generated_on: Optional[date] = None,
) -> Report:
    """Build a Course Report for ``course_code`` from canonical data.

    Parameters
    ----------
    df : pd.DataFrame
        Canonical combined frame (output of ``pat.data.get_combined``).
    course_code : str
        Course code in any common form (``"CE 282"``, ``"ce-282"``).
    year_range : (int, int), optional
        Inclusive ``(min_year, max_year)`` filter. None = all years.
    programs : iterable of str, optional
        Restrict to specific programs. None = all programs in which the
        course appears.
    generated_on : date, optional
        Stamp the report with this date (default: today).

    Returns
    -------
    Report
        Report IR ready for any renderer. Empty ``sections`` if the
        course is not present in the filtered data.
    """
    if generated_on is None:
        generated_on = date.today()

    filtered = data_layer.filter_course(df, course_code)
    if year_range is not None:
        filtered = data_layer.filter_year_range(filtered, year_range[0], year_range[1])
    if programs is not None:
        filtered = data_layer.filter_programs(filtered, list(programs))

    sections = []
    # Iterate in canonical program order so the report's section order
    # is stable regardless of data ordering.
    for code in N.PROGRAM_LABELS.keys():
        df_prog = filtered[filtered["program"].astype(str) == code]
        section = _build_program_section(code, df_prog)
        if section is not None:
            sections.append(section)

    # Subtitle = the year range actually present in the filtered data.
    subtitle = None
    if not filtered.empty:
        sems = _ordered_semesters(filtered)
        if sems:
            subtitle = f"{sems[-1]} – {sems[0]}"

    return Report(
        title=course_code.strip(),
        subtitle=subtitle,
        generated_on=generated_on,
        sections=sections,
    )
