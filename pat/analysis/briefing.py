"""Home-dashboard analysis helpers.

Pure functions that compute the inventory metrics, recent-semester
coverage, and below-threshold summaries the landing page shows. Lives
in `pat.analysis` so the dashboard logic is testable without
launching Streamlit.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .. import normalize as N
from . import coverage as cov_analysis


# ---------------------------------------------------------------------------
# A. Inventory & freshness
# ---------------------------------------------------------------------------


def inventory(df: pd.DataFrame, schedule=None) -> dict:
    """Return high-level counts for the loaded data.

    Returns a dict with: ``programs``, ``courses``, ``measurements``,
    ``year_min``, ``year_max``, ``most_recent_semester``,
    ``schedule_course_count``.
    """
    out = {
        "programs": [],
        "courses": 0,
        "measurements": 0,
        "year_min": None,
        "year_max": None,
        "most_recent_semester": None,
        "schedule_course_count": None,
    }
    if not df.empty:
        out["programs"] = sorted(df["program"].astype(str).unique().tolist())
        out["courses"] = int(
            df["course"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
        )
        out["measurements"] = int(len(df))
        years = df["semester_year"].dropna()
        if not years.empty:
            out["year_min"] = int(years.min())
            out["year_max"] = int(years.max())
        # Most recent semester = highest semester_sort_key with non-empty label.
        nonempty = df[df["semester"].astype(str).str.strip() != ""]
        if not nonempty.empty:
            top = nonempty.sort_values("semester_sort_key", ascending=False).iloc[0]
            out["most_recent_semester"] = str(top["semester"])
    if schedule is not None:
        try:
            out["schedule_course_count"] = len(schedule.all_courses())
        except Exception:
            out["schedule_course_count"] = None
    return out


# ---------------------------------------------------------------------------
# B. Recent-semester coverage
# ---------------------------------------------------------------------------


def recent_semester_coverage(df: pd.DataFrame) -> dict:
    """Coverage snapshot for the most recent semester in the data.

    Returns a dict with: ``semester`` (str or None), ``per_program``
    (list of dicts with program, total, assessed, missing, pct, missing_courses).
    """
    if df.empty:
        return {"semester": None, "per_program": []}
    nonempty = df[df["semester"].astype(str).str.strip() != ""]
    if nonempty.empty:
        return {"semester": None, "per_program": []}
    sem = str(
        nonempty.sort_values("semester_sort_key", ascending=False).iloc[0]["semester"]
    )
    sem_sum = cov_analysis.semester_summary(df, sem)
    missing = cov_analysis.missing_for_semester(df, sem)
    rows = []
    for _, r in sem_sum.iterrows():
        prog = r["program"]
        rows.append({
            "program": prog,
            "total": int(r["total_courses"]),
            "assessed": int(r["assessed_courses"]),
            "missing": int(r["missing_courses"]),
            "pct_assessed": float(r["pct_assessed"]),
            "missing_courses": list(missing.get(prog, [])),
        })
    return {"semester": sem, "per_program": rows}


# ---------------------------------------------------------------------------
# C. Below-threshold attention
# ---------------------------------------------------------------------------


def below_threshold_summary(
    df: pd.DataFrame,
    year: Optional[int] = None,
    top_n: int = 3,
) -> dict:
    """Summary of below-indicator measurements for a given year.

    If ``year`` is None, uses the most recent year present in the data.

    Returns a dict with:
    - ``year``: int or None
    - ``per_program``: list of {program, below_count, total_count}
    - ``top_items``: list of dicts with course, suboutcome, semester,
      program, performance, indicator. Sorted ascending by gap from
      indicator (worst first).
    """
    out = {"year": None, "per_program": [], "top_items": []}
    if df.empty:
        return out

    years = df["semester_year"].dropna()
    if years.empty:
        return out
    if year is None:
        year = int(years.max())
    out["year"] = int(year)

    yr_df = df[df["semester_year"] == year].copy()
    # Below-threshold filter: both performance and indicator known, performance < indicator.
    yr_df = yr_df[
        yr_df["performance"].notna() & yr_df["performance_indicator"].notna()
    ]
    yr_df["__gap"] = yr_df["performance_indicator"] - yr_df["performance"]
    below = yr_df[yr_df["__gap"] > 0]

    # Per-program counts (over the full year, not just below).
    per_program = []
    for prog in N.PROGRAM_LABELS:
        prog_yr = yr_df[yr_df["program"].astype(str) == prog]
        prog_below = below[below["program"].astype(str) == prog]
        per_program.append({
            "program": prog,
            "below_count": int(len(prog_below)),
            "total_count": int(len(prog_yr)),
        })
    out["per_program"] = per_program

    # Top items: worst (largest gap) first.
    top = below.sort_values("__gap", ascending=False).head(top_n)
    out["top_items"] = [
        {
            "course": str(r["course"]),
            "suboutcome": str(r["suboutcome"]),
            "semester": str(r["semester"]),
            "program": str(r["program"]),
            "performance": float(r["performance"]),
            "indicator": float(r["performance_indicator"]),
            "gap": float(r["__gap"]),
        }
        for _, r in top.iterrows()
    ]
    return out
