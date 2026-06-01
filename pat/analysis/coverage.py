"""Coverage analysis.

Three related views over the canonical PAT data:

1. ``missing_for_semester(df, semester)`` -- courses on the schedule for
   a given semester that have no submitted data.
2. ``per_year_summary(df, year_min, year_max)`` -- counts of assessed
   vs. missing courses per program per year, with percentages.
3. ``suboutcome_coverage(df, year_min, year_max)`` -- per-program
   heatmap of (sub-outcome x year) measurement counts, with empty
   coverage cells highlighted as gaps.

``check(df, semester)`` is the convenience entrypoint that returns one
Report combining the missing list, semester summary, per-year trend,
and the coverage heatmaps.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

import pandas as pd

from .. import normalize as N
from ..render.model import (
    Chart,
    ChartSeries,
    Heatmap,
    NamedTable,
    NarrativeBlock,
    Report,
)


# ---------------------------------------------------------------------------
# Missing-by-semester
# ---------------------------------------------------------------------------


def _course_has_no_submissions(group: pd.DataFrame) -> bool:
    """True if every row in `group` has a blank submitter."""
    if group.empty:
        return True
    sub = group["submitter"].astype(str).str.strip()
    return (sub == "").all()


def missing_for_semester(df: pd.DataFrame, semester: str) -> dict:
    """Return ``{program_code: sorted list of missing courses}``.

    A course is "missing" if it appears on that program's schedule for
    ``semester`` (>= 1 row) but every row has a blank submitter.
    """
    out: dict = {p: [] for p in N.PROGRAM_LABELS}
    if df.empty:
        return out
    sem_df = df[df["semester"] == semester]
    if sem_df.empty:
        return out
    for prog, prog_df in sem_df.groupby(sem_df["program"].astype(str)):
        if prog not in out:
            continue
        missing = []
        for course, course_df in prog_df.groupby(prog_df["course"]):
            if not course or course == "":
                continue
            if _course_has_no_submissions(course_df):
                missing.append(course)
        out[prog] = sorted(missing)
    return out


def semester_summary(df: pd.DataFrame, semester: str) -> pd.DataFrame:
    """Per-program counts for one semester.

    Returns a DataFrame with columns: program, total_courses,
    assessed_courses, missing_courses, pct_assessed, pct_missing.
    """
    rows = []
    sem_df = df[df["semester"] == semester] if not df.empty else df
    for prog in N.PROGRAM_LABELS:
        prog_df = sem_df[sem_df["program"].astype(str) == prog] if not sem_df.empty else sem_df
        if prog_df.empty:
            rows.append({"program": prog, "total_courses": 0,
                         "assessed_courses": 0, "missing_courses": 0,
                         "pct_assessed": 0.0, "pct_missing": 0.0})
            continue
        total = prog_df["course"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
        missing = 0
        for course, course_df in prog_df.groupby(prog_df["course"]):
            if not course or course == "":
                continue
            if _course_has_no_submissions(course_df):
                missing += 1
        assessed = total - missing
        rows.append({
            "program": prog,
            "total_courses": int(total),
            "assessed_courses": int(assessed),
            "missing_courses": int(missing),
            "pct_assessed": (assessed / total * 100.0) if total else 0.0,
            "pct_missing": (missing / total * 100.0) if total else 0.0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Per-year summary
# ---------------------------------------------------------------------------


def per_year_summary(
    df: pd.DataFrame,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
) -> pd.DataFrame:
    """Per-(program, year) coverage counts and percentages."""
    if df.empty:
        return pd.DataFrame(
            columns=["program", "year", "total_courses", "assessed_courses",
                     "missing_courses", "pct_assessed", "pct_missing"]
        )
    yrs = df["semester_year"].dropna()
    if yrs.empty:
        return pd.DataFrame(
            columns=["program", "year", "total_courses", "assessed_courses",
                     "missing_courses", "pct_assessed", "pct_missing"]
        )
    lo = int(yrs.min()) if year_min is None else year_min
    hi = int(yrs.max()) if year_max is None else year_max
    rows = []
    for prog in N.PROGRAM_LABELS:
        prog_df = df[(df["program"].astype(str) == prog)
                     & df["semester_year"].between(lo, hi).fillna(False)]
        if prog_df.empty:
            continue
        for year, year_df in prog_df.groupby(prog_df["semester_year"]):
            if pd.isna(year):
                continue
            total = year_df["course"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
            if total == 0:
                continue
            missing = 0
            for course, course_df in year_df.groupby(year_df["course"]):
                if not course or course == "":
                    continue
                if _course_has_no_submissions(course_df):
                    missing += 1
            assessed = total - missing
            rows.append({
                "program": prog,
                "year": int(year),
                "total_courses": int(total),
                "assessed_courses": int(assessed),
                "missing_courses": int(missing),
                "pct_assessed": (assessed / total * 100.0) if total else 0.0,
                "pct_missing": (missing / total * 100.0) if total else 0.0,
            })
    return pd.DataFrame(rows).sort_values(["program", "year"], ascending=[True, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sub-outcome coverage heatmap
# ---------------------------------------------------------------------------


def _sort_sub_codes(codes):
    def key(c):
        try:
            a, b = str(c).split(".")
            return (int(a), int(b))
        except ValueError:
            return (9999, str(c))
    return sorted(codes, key=key)


def suboutcome_coverage_heatmap(
    df: pd.DataFrame,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    programs: Optional[Iterable[str]] = None,
    sub_outcomes: Optional[Iterable[str]] = None,
) -> list:
    """Build one Heatmap per program: (sub-outcome x year) measurement counts.

    Cells contain the number of measurement rows that submitted data for
    that sub-outcome in that year (i.e., rows with non-blank submitter).
    Zero cells are highlighted by the renderers as coverage gaps.

    Parameters
    ----------
    df : pd.DataFrame
        Canonical combined data.
    year_min, year_max : int, optional
        Restrict the year range. Defaults to the min/max present.
    programs : iterable of str, optional
        Restrict to specific programs (defaults to all loaded).
    sub_outcomes : iterable of str, optional
        Explicit row labels (so heatmaps include sub-outcomes that have
        zero coverage). Defaults to the union of sub-outcomes seen in
        the filtered data.
    """
    if df.empty:
        return []
    yrs = df["semester_year"].dropna()
    if yrs.empty:
        return []
    lo = int(yrs.min()) if year_min is None else year_min
    hi = int(yrs.max()) if year_max is None else year_max
    prog_list = list(programs) if programs is not None else list(N.PROGRAM_LABELS)

    filtered = df[df["semester_year"].between(lo, hi).fillna(False)]
    # Count only rows that actually have a submitted assessment.
    submitted = filtered[
        filtered["submitter"].astype(str).str.strip() != ""
    ]

    if sub_outcomes is None:
        codes_present = (
            submitted["suboutcome"].astype(str).str.strip()
            if not submitted.empty else pd.Series(dtype=str)
        )
        codes_present = codes_present[codes_present != ""].unique().tolist()
        # Sort to give the heatmap a stable, intuitive row order.
        codes = _sort_sub_codes(codes_present)
    else:
        codes = list(sub_outcomes)

    years = [str(y) for y in range(lo, hi + 1)]

    heatmaps = []
    for prog in prog_list:
        prog_df = submitted[submitted["program"].astype(str) == prog]
        # values[r][c] = count of rows for (code, year).
        matrix = []
        for code in codes:
            row = []
            for y in range(lo, hi + 1):
                cnt = int((
                    (prog_df["suboutcome"].astype(str).str.strip() == code)
                    & (prog_df["semester_year"] == y)
                ).sum())
                row.append(cnt)
            matrix.append(row)
        # Only emit a heatmap for programs with at least some data in the range.
        if any(any(r) for r in matrix) or codes:
            heatmaps.append(Heatmap(
                title=f"{N.PROGRAM_LABELS.get(prog, prog)}: sub-outcome assessment counts, {lo}-{hi}",
                row_label="Sub-Outcome",
                col_label="Year",
                rows=list(codes),
                columns=years,
                values=matrix,
                vmin=0,
                color_scheme="blues",
                value_format="{:.0f}",
                empty_marker="",
                highlight_zero=True,
                caption="Cell value = number of assessment submissions. Pink cells indicate no coverage in that year.",
            ))
    return heatmaps


# ---------------------------------------------------------------------------
# Coverage trend chart (one line per program)
# ---------------------------------------------------------------------------


def coverage_trend_chart(per_year_df: pd.DataFrame) -> Optional[Chart]:
    if per_year_df.empty:
        return None
    series = []
    for prog, prog_df in per_year_df.groupby("program"):
        prog_df = prog_df.sort_values("year")
        series.append(ChartSeries(
            name=prog,
            x=prog_df["year"].tolist(),
            y=prog_df["pct_assessed"].tolist(),
        ))
    if not series:
        return None
    return Chart(
        title="Coverage trend by year",
        x_label="Year",
        y_label="% assessed",
        series=series,
        kind="line",
    )


# ---------------------------------------------------------------------------
# Top-level: Coverage Check report
# ---------------------------------------------------------------------------


def check(
    df: pd.DataFrame,
    semester: str,
    *,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    include_heatmap: bool = True,
    sub_outcomes: Optional[Iterable[str]] = None,
    generated_on: Optional[date] = None,
) -> Report:
    """Build the Coverage Check Report for a chosen semester.

    Combines: missing-courses table, semester summary, per-year summary,
    coverage trend chart, and (if requested) sub-outcome coverage
    heatmaps.
    """
    if generated_on is None:
        generated_on = date.today()

    missing = missing_for_semester(df, semester)
    sem_sum = semester_summary(df, semester)
    per_year = per_year_summary(df, year_min, year_max)

    tables = []
    # Missing courses table.
    missing_rows = []
    for prog in N.PROGRAM_LABELS:
        for course in missing.get(prog, []):
            missing_rows.append([prog, course])
    if missing_rows:
        tables.append(NamedTable(
            title=f"Missing assessments in {semester}",
            columns=["Program", "Course"],
            rows=missing_rows,
        ))
    else:
        tables.append(NamedTable(
            title=f"Missing assessments in {semester}",
            columns=["Program", "Course"],
            rows=[],
            footnote="No missing assessments detected for this semester.",
        ))

    # Semester summary.
    if not sem_sum.empty:
        tables.append(NamedTable(
            title="Semester summary",
            columns=["Program", "Total", "Assessed", "Missing", "% assessed"],
            rows=[
                [r["program"], str(int(r["total_courses"])),
                 str(int(r["assessed_courses"])), str(int(r["missing_courses"])),
                 f"{r['pct_assessed']:.1f}%"]
                for _, r in sem_sum.iterrows()
            ],
            footnote="A course is 'missing' when every measurement row has a blank submitter.",
        ))

    charts = []
    chart = coverage_trend_chart(per_year)
    if chart is not None:
        charts.append(chart)

    heatmaps = []
    if include_heatmap:
        heatmaps = suboutcome_coverage_heatmap(
            df, year_min, year_max, sub_outcomes=sub_outcomes,
        )

    yrs = df["semester_year"].dropna() if "semester_year" in df.columns else pd.Series(dtype=float)
    if not yrs.empty:
        lo = int(yrs.min()) if year_min is None else year_min
        hi = int(yrs.max()) if year_max is None else year_max
        subtitle = f"{semester}  ({lo}-{hi})"
    else:
        subtitle = semester

    return Report(
        title="Coverage Check",
        subtitle=subtitle,
        generated_on=generated_on,
        tables=tables,
        charts=charts,
        heatmaps=heatmaps,
    )



# ---------------------------------------------------------------------------
# ABET cycle rollup
# ---------------------------------------------------------------------------


def filter_semester_range(df: pd.DataFrame, start_label: str, end_label: str) -> pd.DataFrame:
    """Restrict df to rows whose semester falls in [start_label, end_label] inclusive.

    Inputs are semester labels (e.g. "Fall 2023", "Spring 2028"); ordering
    uses the canonical semester_sort_key (Fall sorts after Spring of same year).
    Unparseable bounds raise IngestError-equivalent ValueError.
    """
    if df.empty:
        return df
    from .. import normalize as _N
    y0, s0 = _N.parse_semester(start_label)
    y1, s1 = _N.parse_semester(end_label)
    if y0 is None or s0 is None or y1 is None or s1 is None:
        raise ValueError(
            f"Could not parse cycle bounds: start={start_label!r}, end={end_label!r}"
        )
    lo = _N.semester_sort_key(y0, s0)
    hi = _N.semester_sort_key(y1, s1)
    if lo > hi:
        lo, hi = hi, lo
    mask = df["semester_sort_key"].between(lo, hi).fillna(False)
    return df[mask]


def cycle_coverage_heatmap(
    df: pd.DataFrame,
    cycle_start: str,
    cycle_end: str,
    sub_outcomes=None,
    programs=None,
) -> Heatmap:
    """Single heatmap rolling up an entire ABET cycle.

    Rows = sub-outcomes, columns = programs, cells = count of submitted
    measurements for that (sub-outcome, program) pair across all
    semesters in the cycle.

    Parameters
    ----------
    df : DataFrame
        Canonical combined data.
    cycle_start, cycle_end : str
        Semester labels bounding the cycle ("Fall 2023", "Spring 2028").
    sub_outcomes : iterable of str, optional
        Explicit row order. Defaults to the union of sub-outcomes seen
        in submitted data within the cycle.
    programs : iterable of str, optional
        Restrict to specific programs. Defaults to all in PROGRAM_LABELS.
    """
    prog_list = list(programs) if programs is not None else list(N.PROGRAM_LABELS)
    in_cycle = filter_semester_range(df, cycle_start, cycle_end)
    submitted = in_cycle[
        in_cycle["submitter"].astype(str).str.strip() != ""
    ] if not in_cycle.empty else in_cycle

    if sub_outcomes is None:
        codes_present = (
            submitted["suboutcome"].astype(str).str.strip()
            if not submitted.empty else pd.Series(dtype=str)
        )
        codes_present = codes_present[codes_present != ""].unique().tolist()
        codes = _sort_sub_codes(codes_present)
    else:
        codes = list(sub_outcomes)

    matrix = []
    for code in codes:
        row = []
        for prog in prog_list:
            cnt = int((
                (submitted["program"].astype(str) == prog)
                & (submitted["suboutcome"].astype(str).str.strip() == code)
            ).sum()) if not submitted.empty else 0
            row.append(cnt)
        matrix.append(row)

    return Heatmap(
        title=f"ABET cycle coverage: {cycle_start} - {cycle_end}",
        row_label="Sub-Outcome",
        col_label="Program",
        rows=list(codes),
        columns=prog_list,
        values=matrix,
        vmin=0,
        color_scheme="greens",
        value_format="{:.0f}",
        empty_marker="",
        highlight_zero=True,
        caption=(
            "Cell value = total submitted measurements for that "
            "(sub-outcome, program) pair across all semesters in the cycle. "
            "Pink cells indicate no coverage during the cycle."
        ),
    )
