"""File-level ingestion: raw bytes / paths -> DataFrames.

This module knows how to:

- Detect which program (CE / CON / ENE) a CSV belongs to, from filename
  or content.
- Read a PAT CSV and apply :mod:`pat.normalize` cleaning.
- Read an Assessment Schedule workbook into a typed wrapper.

It does **no** caching, persistence, or Streamlit work -- see
``pat.cache`` and ``pat.data``.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Optional, Union

import pandas as pd

from . import normalize as N

PathOrBytes = Union[str, Path, bytes, IO[bytes]]


# ---------------------------------------------------------------------------
# Program detection
# ---------------------------------------------------------------------------

_FILENAME_UPPER_RE = re.compile(r"(?:^|[^A-Z])(CE|CON|ENE)(?:[^A-Za-z]|$)")
_FILENAME_DELIM_RE = re.compile(
    r"(?:^|[^A-Za-z])(CE|CON|ENE)(?:[^A-Za-z]|$)", re.IGNORECASE
)


def detect_program_from_filename(name):
    """Return CE / CON / ENE if `name` contains a program token, else None.

    Two-pass matching:
    1) Uppercase token in camelCase context: 'summaryReportCE_' -> CE.
    2) Delimited token in any case: 'ene_export.csv' -> ENE.
    A token buried inside a longer word ('recent', 'Construction') does
    not match.
    """
    if not name:
        return None
    base = Path(name).name
    m = _FILENAME_UPPER_RE.search(base)
    if m is None:
        m = _FILENAME_DELIM_RE.search(base)
    if m is None:
        return None
    return m.group(1).upper()


def detect_program_from_content(df):
    """Return a program code if df has a 'program' column with one value."""
    for col in df.columns:
        if str(col).strip().lower() == "program":
            vals = df[col].dropna().astype(str).str.strip().str.upper().unique()
            vals = [v for v in vals if v in N.PROGRAM_LABELS]
            if len(vals) == 1:
                return vals[0]
    return None


def detect_program(name, df=None):
    """Combined detection: filename first, content second."""
    by_name = detect_program_from_filename(name)
    if by_name is not None:
        return by_name
    if df is not None:
        return detect_program_from_content(df)
    return None


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------


def _coerce_to_io(source):
    if isinstance(source, (str, Path)):
        return open(source, "rb")
    if isinstance(source, bytes):
        return io.BytesIO(source)
    return source


def read_pat_csv(source, *, program=None, filename=None):
    """Read a PAT CSV, normalize it, return a canonical DataFrame.

    Parameters
    ----------
    source : str, Path, bytes, or file-like
        Where to read from.
    program : str, optional
        Override program detection.
    filename : str, optional
        Used for auto-detection when `source` is bytes.
    """
    handle = _coerce_to_io(source)
    try:
        # dtype=str + keep_default_na=False prevents pandas from coercing
        # "null" or "nan" string sentinels into NaN before normalization.
        df = pd.read_csv(handle, dtype=str, keep_default_na=False, na_filter=False)
    finally:
        if isinstance(source, (str, Path)):
            handle.close()

    if program is None:
        if filename is None:
            if isinstance(source, (str, Path)):
                filename = str(source)
            elif hasattr(source, "name"):
                filename = getattr(source, "name", "")
            else:
                filename = ""
        program = detect_program(filename, df)
    if program is None:
        raise N.IngestError(
            "Could not determine program for the uploaded CSV. "
            "Pass program= explicitly or rename the file so it contains "
            "'CE', 'CON', or 'ENE'."
        )
    if program not in N.PROGRAM_LABELS:
        raise N.IngestError(
            "Unknown program '" + str(program) + "'. Expected one of "
            + str(list(N.PROGRAM_LABELS)) + "."
        )

    return N.clean_dataframe(df, program=program)


# ---------------------------------------------------------------------------
# Assessment Schedule workbook
# ---------------------------------------------------------------------------


SCHEDULE_COURSE_SHEET = "CourseSubOutcomes"
SCHEDULE_DESC_SHEET = "OutcomeDescriptions"
SCHEDULE_PLANNED_SHEET = "Assessment Schedule"

_TRUEY = {"x", "true", "1", "yes"}


def _is_checked(v):
    if pd.isna(v):
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in _TRUEY


def _split_programs(v):
    if pd.isna(v):
        return []
    parts = re.split(r"[\/,;]", str(v))
    return [p.strip() for p in parts if p.strip()]


def _sort_outcome_codes(codes):
    def key(c):
        try:
            major, minor = c.split(".")
            return (int(major), int(minor))
        except ValueError:
            return (9999, c)
    return sorted(codes, key=key)


def _normalize_col_name(c):
    if isinstance(c, (int, float)) and not pd.isna(c):
        s = "{}".format(c)
        return s[:-2] if s.endswith(".0") else s
    return str(c).strip()


def _normalize_outcome_key(code):
    if isinstance(code, (int, float)) and not pd.isna(code):
        s = "{}".format(code)
        return s[:-2] if s.endswith(".0") else s
    return str(code).strip()


@dataclass
class SubOutcomeSchedule:
    """Typed wrapper around the Assessment Schedule workbook."""

    courses: pd.DataFrame
    descriptions: dict = field(default_factory=dict)
    planned: Optional[pd.DataFrame] = None

    @property
    def suboutcome_columns(self):
        return [
            c for c in self.courses.columns
            if re.fullmatch(r"\d+\.\d+", str(c).strip())
        ]

    def all_courses(self):
        return sorted(
            self.courses["Course"].dropna().astype(str).str.strip().unique().tolist()
        )

    def lookup(self, course_code):
        key = N.course_key(course_code)
        matches = self.courses[
            self.courses["Course"].apply(
                lambda v: N.course_key(v) == key if pd.notna(v) else False
            )
        ]
        if matches.empty:
            return None
        row = matches.iloc[0]
        progs = _split_programs(row.get("Programs"))
        codes = []
        for c in self.suboutcome_columns:
            if _is_checked(row[c]):
                codes.append(str(c).strip())
        codes_with_desc = [
            (c, self.descriptions.get(c, "")) for c in _sort_outcome_codes(codes)
        ]
        return {
            "course": str(row["Course"]).strip(),
            "programs": progs,
            "suboutcomes": codes_with_desc,
        }

    def courses_for_suboutcome(self, code):
        """Return {program: [course codes claiming this sub-outcome]}.

        Reads the CourseSubOutcomes sheet -- for each row whose column
        `code` is checked, split its `Programs` field and add the course
        to each program's list.
        """
        if code not in [str(c).strip() for c in self.suboutcome_columns]:
            return {}
        # Locate the column by the cleaned-string equivalent.
        col = next(
            c for c in self.suboutcome_columns if str(c).strip() == code
        )
        out = {}
        for _, row in self.courses.iterrows():
            if not _is_checked(row[col]):
                continue
            course = str(row.get("Course", "")).strip()
            if not course:
                continue
            for prog in _split_programs(row.get("Programs")):
                out.setdefault(prog, []).append(course)
        # Sort each program's course list canonically.
        def _ck(c):
            import re as _re
            m = _re.match(r"([A-Za-z]+)\s*(\d+)", c)
            return (m.group(1).upper(), int(m.group(2))) if m else ("ZZ", 99999)
        return {p: sorted(set(cs), key=_ck) for p, cs in out.items()}


def read_assessment_schedule(source):
    """Read the Assessment Schedule .xlsx into a SubOutcomeSchedule."""
    handle = _coerce_to_io(source)
    try:
        xls = pd.ExcelFile(handle, engine="openpyxl")
    except Exception as exc:
        raise N.IngestError("Could not open Excel workbook: " + str(exc)) from exc

    missing = [
        s for s in (SCHEDULE_COURSE_SHEET, SCHEDULE_DESC_SHEET)
        if s not in xls.sheet_names
    ]
    if missing:
        raise N.IngestError(
            "Assessment Schedule workbook missing required sheet(s): "
            + str(missing) + ". Found sheets: " + str(xls.sheet_names)
        )

    courses = pd.read_excel(xls, sheet_name=SCHEDULE_COURSE_SHEET)
    desc_df = pd.read_excel(xls, sheet_name=SCHEDULE_DESC_SHEET)

    for col in ("Course", "Programs"):
        if col not in courses.columns:
            raise N.IngestError(
                "Sheet '" + SCHEDULE_COURSE_SHEET + "' missing column '"
                + col + "'. Found: " + str(list(courses.columns))
            )
    for col in ("Outcomes", "Description"):
        if col not in desc_df.columns:
            raise N.IngestError(
                "Sheet '" + SCHEDULE_DESC_SHEET + "' missing column '"
                + col + "'. Found: " + str(list(desc_df.columns))
            )

    courses.columns = [_normalize_col_name(c) for c in courses.columns]

    descriptions = {}
    for _, row in desc_df.iterrows():
        code = _normalize_outcome_key(row["Outcomes"])
        desc = str(row["Description"]).strip() if pd.notna(row["Description"]) else ""
        descriptions[code] = desc

    # Planned assessment schedule sheet is optional. When present, we
    # load it as-is and let the viewer page handle formatting.
    planned = None
    if SCHEDULE_PLANNED_SHEET in xls.sheet_names:
        try:
            planned = pd.read_excel(xls, sheet_name=SCHEDULE_PLANNED_SHEET)
        except Exception:
            planned = None

    return SubOutcomeSchedule(
        courses=courses,
        descriptions=descriptions,
        planned=planned,
    )
