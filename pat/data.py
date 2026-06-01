"""Public data API.

This is the only module that pages and analysis code import when they
want data. Everything below this line is responsible for:

- Loading cached files into canonical-schema DataFrames.
- Combining across programs.
- Surfacing the loaded state (which programs, which semesters, which
  courses) for UI dropdown population.

No Streamlit dependency. Pages add ``@st.cache_data`` over these
functions; the functions themselves are pure given their inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from . import cache, ingest, normalize as N


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_program(key: str, dir_: Optional[Path] = None) -> pd.DataFrame:
    """Load a single program's cached CSV into a canonical DataFrame.

    Returns an empty DataFrame (with no columns) if not cached.
    """
    if not cache.is_cached(key, dir_):
        return pd.DataFrame()
    path = cache.list_cached(dir_)[key]
    return ingest.read_pat_csv(path, program=key)


def load_schedule(dir_: Optional[Path] = None):
    """Load the cached Assessment Schedule workbook.

    Returns None if not cached.
    """
    if not cache.is_cached(cache.SCHEDULE_KEY, dir_):
        return None
    path = cache.list_cached(dir_)[cache.SCHEDULE_KEY]
    return ingest.read_assessment_schedule(path)


def get_combined(dir_: Optional[Path] = None) -> pd.DataFrame:
    """Return the canonical combined frame across all loaded programs.

    Empty DataFrame if no programs are loaded.
    """
    frames = []
    for key in N.PROGRAM_LABELS:
        df = load_program(key, dir_)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Surfacing loaded state for UI controls
# ---------------------------------------------------------------------------


def get_loaded_programs(dir_: Optional[Path] = None) -> list:
    """List of program codes currently in cache, sorted."""
    cached = cache.list_cached(dir_)
    return sorted(k for k in cached if k in N.PROGRAM_LABELS)


def get_loaded_courses(dir_: Optional[Path] = None) -> list:
    """Sorted unique course codes across all loaded program data.

    Each entry is the display form (e.g. 'CE 282'), not the lookup key.
    """
    df = get_combined(dir_)
    if df.empty:
        return []
    courses = df["course"].dropna().astype(str).str.strip()
    courses = courses[courses != ""].unique().tolist()
    # Sort by (program_prefix, number).
    def _sort_key(c):
        import re
        m = re.match(r"([A-Za-z]+)\s*(\d+)", c)
        if not m:
            return ("Z", 99999)
        return (m.group(1).upper(), int(m.group(2)))
    return sorted(courses, key=_sort_key)


def get_loaded_semesters(dir_: Optional[Path] = None) -> list:
    """Semester labels found in loaded data, newest first."""
    df = get_combined(dir_)
    if df.empty or "semester" not in df.columns:
        return []
    pairs = df[["semester", "semester_sort_key"]].dropna().drop_duplicates()
    pairs = pairs[pairs["semester"] != ""]
    pairs = pairs.sort_values("semester_sort_key", ascending=False)
    return pairs["semester"].astype(str).tolist()


def get_year_range(dir_: Optional[Path] = None):
    """Return (min_year, max_year) across loaded data, or None if empty."""
    df = get_combined(dir_)
    if df.empty or "semester_year" not in df.columns:
        return None
    years = df["semester_year"].dropna()
    if years.empty:
        return None
    return int(years.min()), int(years.max())


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def filter_course(df: pd.DataFrame, course_code: str) -> pd.DataFrame:
    """Restrict to rows matching a course code (using canonical key)."""
    if df.empty:
        return df
    key = N.course_key(course_code)
    return df[df["course_key"] == key]


def filter_year_range(df: pd.DataFrame, year_min: int, year_max: int) -> pd.DataFrame:
    """Restrict to rows whose semester_year falls within [year_min, year_max]."""
    if df.empty:
        return df
    mask = df["semester_year"].between(year_min, year_max)
    return df[mask.fillna(False)]


def filter_programs(df: pd.DataFrame, programs) -> pd.DataFrame:
    """Restrict to rows whose program is in the given iterable."""
    if df.empty:
        return df
    allowed = set(programs)
    return df[df["program"].astype(str).isin(allowed)]
