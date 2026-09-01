"""Normalization primitives.

Pure functions over strings and DataFrames. No I/O, no logging side
effects, no Streamlit. Importing this module must be cheap and safe in
any context (including unit tests).

The cleaning rules here exist because PAT exports contain known
artifacts: massive leading whitespace on `course`, the literal string
``"null"`` used in place of missing values, sub-outcome codes typed
inconsistently across rows, and column names that mix hyphens and
underscores. See specs/03_data_model.md for the full canonical schema.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROGRAM_LABELS: dict[str, str] = {
    "CE": "Civil Engineering",
    "ENE": "Environmental Engineering",
    "CON": "Construction Engineering",
}

RAW_TO_CANONICAL: dict[str, str] = {
    "course": "course",
    "suboutcome": "suboutcome",
    "semester": "semester",
    "assigned-to": "instructor",
    "submitted-by": "submitter",
    "performance-indicator": "performance_indicator",
    "threshold": "threshold",
    "scale": "scale",
    "performance": "performance",
    "score-data": "score_data",
    "scores_meeting_threshold": "scores_meeting_threshold",
    "total_scores": "total_scores",
    "measurement-result-updated": "measurement_date",
    "comments": "comments",
    "actions-taken": "actions_taken",
    "measure-description": "measure_description",
}

REQUIRED_RAW_COLUMNS: tuple[str, ...] = tuple(RAW_TO_CANONICAL.keys())

CANONICAL_COLUMNS: tuple[str, ...] = (
    "program",
    "course",
    "course_key",
    "suboutcome",
    "semester",
    "semester_year",
    "semester_season",
    "semester_sort_key",
    "instructor",
    "submitter",
    "performance_indicator",
    "threshold",
    "scale",
    "performance",
    "score_data",
    "scores_meeting_threshold",
    "total_scores",
    "measurement_date",
    "comments",
    "actions_taken",
    "measure_description",
)

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%?")
_COURSE_RE = re.compile(r"([A-Za-z]+)[ _\-]*(\d+)")
_NULLISH = {"", "null", "nan", "none", "na"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class IngestError(ValueError):
    """Raised when input data violates an invariant the pipeline depends on."""


# ---------------------------------------------------------------------------
# String normalization
# ---------------------------------------------------------------------------


def is_nullish(value) -> bool:
    """True if ``value`` is missing, blank, or a stringified null sentinel.

    PAT exports use a mix of empty string, the literal string ``"null"``,
    ``"nan"`` (from pandas float coercion), and actual ``NaN``. We treat
    all of these as missing.
    """
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _NULLISH


def clean_string(value) -> str:
    """Strip whitespace, collapse null sentinels, and undo HTML escaping.

    PAT's CSV export HTML-escapes free-text fields, so an apostrophe
    arrives as ``&#039;`` and an ampersand as ``&amp;``. Left alone those
    entities travel all the way into the generated Word/PDF report,
    where they read as corruption. ``html.unescape`` is idempotent on
    text that has no entities.

    Examples
    --------
    >>> clean_string("  a &#039;topic 0&#039; quiz  ")
    "a 'topic 0' quiz"
    >>> clean_string("Ratio &gt; 1 &amp; rising")
    'Ratio > 1 & rising'
    """
    if is_nullish(value):
        return ""
    return html.unescape(str(value)).strip()


def clean_course_code(value) -> str:
    """Normalize a course code as displayed to the user.

    Strips whitespace (PAT sometimes prefixes hundreds of spaces) and
    ensures a single space between the program prefix and number.
    Examples
    --------
    >>> clean_course_code("   CE 282   ")
    'CE 282'
    >>> clean_course_code("ce-282")
    'CE 282'
    >>> clean_course_code("CE282")
    'CE 282'
    """
    if is_nullish(value):
        return ""
    s = str(value).strip().upper()
    match = _COURSE_RE.search(s)
    if not match:
        return re.sub(r"\s+", " ", s)
    return f"{match.group(1)} {match.group(2)}"


def course_key(value) -> str:
    """Canonical lookup key for a course code: no spaces, uppercase.

    Examples
    --------
    >>> course_key("CE 282")
    'CE282'
    >>> course_key("ce-282")
    'CE282'
    >>> course_key("  CE282 ")
    'CE282'
    """
    if is_nullish(value):
        return ""
    s = str(value).strip().upper()
    match = _COURSE_RE.search(s)
    if not match:
        return re.sub(r"[ _\-]+", "", s)
    return f"{match.group(1)}{match.group(2)}"


def normalize_suboutcome(value) -> str:
    """Coerce a sub-outcome to canonical ``"major.minor"`` string form.

    Pandas sometimes reads ``1.1`` as a float; we reformat with the
    trailing zero stripped for consistency with ``"1.1"`` strings.

    Examples
    --------
    >>> normalize_suboutcome(1.1)
    '1.1'
    >>> normalize_suboutcome("4.1")
    '4.1'
    >>> normalize_suboutcome(2)
    '2'
    """
    if is_nullish(value):
        return ""
    if isinstance(value, float):
        s = f"{value:g}"
        return s
    s = str(value).strip()
    # Trim float-y representation like "1.10" → "1.1" (only when it ends in 0
    # *after* a decimal point and is otherwise the simple major.minor form).
    if re.fullmatch(r"\d+\.\d+0", s):
        s = s.rstrip("0").rstrip(".")
    return s


def parse_percent(value) -> Optional[float]:
    """Parse a percent value in 0–100 range, returning ``None`` if unparseable.

    Accepts ``"86"``, ``"86%"``, ``86``, ``0.86`` (treated as a fraction).

    Examples
    --------
    >>> parse_percent("86%")
    86.0
    >>> parse_percent(86)
    86.0
    >>> parse_percent(0.86)
    86.0
    >>> parse_percent("nan") is None
    True
    """
    if is_nullish(value):
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        v = float(value)
        return v * 100 if 0 <= v <= 1 else v
    s = str(value).strip()
    match = _PERCENT_RE.search(s)
    if not match:
        return None
    try:
        v = float(match.group(1))
    except ValueError:
        return None
    # Bare fractions like "0.86" → 86%
    if "%" not in s and 0 <= v <= 1:
        return v * 100
    return v


def parse_semester(value) -> tuple[Optional[int], Optional[str]]:
    """Parse a semester string into ``(year, season)``.

    Accepts ``"Spring 2024"``, ``"Fall 2024"``, ``"S24"``, ``"F 23"``.
    Returns ``(None, None)`` if unparseable.

    Examples
    --------
    >>> parse_semester("Spring 2024")
    (2024, 'S')
    >>> parse_semester("F23")
    (2023, 'F')
    >>> parse_semester("garbage")
    (None, None)
    """
    if is_nullish(value):
        return None, None
    s = str(value).strip()
    m = re.match(r"^([FfSs])\s*(\d{2})$", s)
    if m:
        return 2000 + int(m.group(2)), m.group(1).upper()
    m = re.search(r"(spring|fall)\s+(\d{4})", s, flags=re.IGNORECASE)
    if m:
        season = "S" if m.group(1).lower() == "spring" else "F"
        return int(m.group(2)), season
    return None, None


def semester_sort_key(year: Optional[int], season: Optional[str]) -> int:
    """Integer sort key — larger values are more recent.

    Fall sorts after Spring of the same year.
    """
    if year is None or season is None:
        return -1
    return year * 2 + (1 if season == "F" else 0)


def format_semester(year: Optional[int], season: Optional[str]) -> str:
    """Render a semester as ``"Spring 2024"`` style. Empty string on missing."""
    if year is None or season is None:
        return ""
    return f"{'Fall' if season == 'F' else 'Spring'} {year}"


def parse_date(value) -> Optional[date]:
    """Parse a date string in the PAT-observed format ``MM/DD/YYYY``.

    Returns ``None`` for missing or unparseable values. Other formats
    fall through to pandas' parser as a best effort.
    """
    if is_nullish(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, errors="raise").date()
    except (ValueError, TypeError):
        return None


def parse_int(value) -> Optional[int]:
    """Parse an int permissively; return None on missing/unparseable."""
    if is_nullish(value):
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Header / column normalization
# ---------------------------------------------------------------------------


def _norm_header(name: str) -> str:
    """Aggressive lower/snake form for matching columns case- and punct-insensitively."""
    return re.sub(r"[ \-_]+", "_", str(name).strip().lower())


def rename_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw PAT columns to canonical names.

    Matching is case-insensitive and tolerant of hyphen vs. underscore vs.
    space. Raises :class:`IngestError` if any required column is missing.
    """
    norm_to_actual = {_norm_header(c): c for c in df.columns}
    rename_map: dict[str, str] = {}
    missing: list[str] = []
    for raw, canonical in RAW_TO_CANONICAL.items():
        actual = norm_to_actual.get(_norm_header(raw))
        if actual is None:
            missing.append(raw)
        else:
            rename_map[actual] = canonical
    if missing:
        raise IngestError(
            "Missing required column(s) in PAT export: "
            + ", ".join(missing)
            + f". Found columns: {list(df.columns)}"
        )
    return df.rename(columns=rename_map)


# ---------------------------------------------------------------------------
# Frame-level cleaning
# ---------------------------------------------------------------------------


def clean_dataframe(df: pd.DataFrame, *, program: Optional[str] = None) -> pd.DataFrame:
    """Apply all normalization rules and return a frame in canonical schema.

    Parameters
    ----------
    df : pd.DataFrame
        A raw PAT export DataFrame (already passed through
        :func:`rename_to_canonical`, or with raw column names — this
        function will rename if needed).
    program : str, optional
        Program code (``"CE"``, ``"CON"``, ``"ENE"``) to attach as the
        ``program`` column. If omitted, no ``program`` column is added.

    Returns
    -------
    pd.DataFrame
        A new DataFrame with columns from :data:`CANONICAL_COLUMNS` (minus
        ``program`` if not supplied), in stable order, with the cleaning
        rules applied.
    """
    if not set(RAW_TO_CANONICAL.values()).issubset(df.columns):
        df = rename_to_canonical(df)

    out = pd.DataFrame()

    # String columns
    out["course"] = df["course"].map(clean_course_code)
    out["course_key"] = df["course"].map(course_key)
    out["suboutcome"] = df["suboutcome"].map(normalize_suboutcome)
    # Parse first, then derive the canonical display label so that short
    # forms like "S24" are stored as "Spring 2024" per the canonical
    # schema in specs/03_data_model.md.
    raw_sem = df["semester"].map(clean_string)
    parsed = raw_sem.map(parse_semester)
    years = parsed.map(lambda t: t[0])
    seasons = parsed.map(lambda t: t[1])
    canonical_labels = [
        format_semester(y, s) if (y is not None and s is not None) else raw
        for raw, y, s in zip(raw_sem, years, seasons)
    ]
    out["semester"] = canonical_labels
    out["semester_year"] = years
    out["semester_season"] = seasons
    out["semester_sort_key"] = [
        semester_sort_key(y, s) for y, s in zip(out["semester_year"], out["semester_season"])
    ]

    out["instructor"] = df["instructor"].map(clean_string)
    out["submitter"] = df["submitter"].map(clean_string)

    out["performance_indicator"] = df["performance_indicator"].map(parse_percent)
    out["threshold"] = df["threshold"].map(parse_int)
    out["scale"] = df["scale"].map(parse_int)
    out["performance"] = df["performance"].map(parse_percent)

    out["score_data"] = df["score_data"].map(clean_string)
    out["scores_meeting_threshold"] = df["scores_meeting_threshold"].map(parse_int)
    out["total_scores"] = df["total_scores"].map(parse_int)
    out["measurement_date"] = df["measurement_date"].map(parse_date)
    out["comments"] = df["comments"].map(clean_string)
    out["actions_taken"] = df["actions_taken"].map(clean_string)
    out["measure_description"] = df["measure_description"].map(clean_string)

    if program is not None:
        if program not in PROGRAM_LABELS:
            raise IngestError(
                f"Unknown program code '{program}'. Expected one of {list(PROGRAM_LABELS)}."
            )
        out.insert(0, "program", pd.Categorical([program] * len(out), categories=list(PROGRAM_LABELS)))

    return out


# ---------------------------------------------------------------------------
# Invariant checks
# ---------------------------------------------------------------------------


def check_invariants(df: pd.DataFrame) -> None:
    """Verify the invariants from specs/03_data_model.md §8.

    Raises :class:`IngestError` on any violation, with a message that
    identifies the offending rows.
    """
    if df.empty:
        return

    # 2. No leading/trailing whitespace in course
    bad_ws = df[df["course"].astype(str).str.strip() != df["course"].astype(str)]
    if not bad_ws.empty:
        raise IngestError(
            f"{len(bad_ws)} row(s) have whitespace in `course` after cleaning."
        )

    # 3. course_key matches ^[A-Z]+\d+$ when non-empty
    nonempty = df["course_key"].astype(str)
    nonempty = nonempty[nonempty != ""]
    bad_key = nonempty[~nonempty.str.match(r"^[A-Z]+\d+$")]
    if not bad_key.empty:
        raise IngestError(
            f"{len(bad_key)} row(s) have malformed `course_key`: "
            f"{bad_key.unique().tolist()[:5]}"
        )

    # 4. semester_year in [2000, 2100]
    yrs = df["semester_year"].dropna()
    bad_yr = yrs[(yrs < 2000) | (yrs > 2100)]
    if not bad_yr.empty:
        raise IngestError(
            f"{len(bad_yr)} row(s) have implausible semester_year: "
            f"{bad_yr.unique().tolist()[:5]}"
        )

    # 5. program one of PROGRAM_LABELS
    if "program" in df.columns:
        bad_prog = df["program"].dropna().astype(str)
        bad_prog = bad_prog[~bad_prog.isin(PROGRAM_LABELS.keys())]
        if not bad_prog.empty:
            raise IngestError(
                f"Unknown program codes present: {bad_prog.unique().tolist()}"
            )

    # 6. performance and performance_indicator in [0, 100] when not None
    for col in ("performance", "performance_indicator"):
        vals = df[col].dropna()
        bad = vals[(vals < 0) | (vals > 100)]
        if not bad.empty:
            raise IngestError(
                f"{len(bad)} row(s) have `{col}` outside [0, 100]: "
                f"{bad.unique().tolist()[:5]}"
            )
