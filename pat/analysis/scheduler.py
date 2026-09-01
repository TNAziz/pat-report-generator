"""PAT Scheduler analysis.

Answers one question for the PAT administrator: *for this program and
this semester, what has to be created in the PAT web tool?*

The only source of truth is the Assessment Schedule workbook -- no PAT
export is consulted. Three sheets are joined:

``Assessment Schedule``
    Course x semester grid. ``X`` means the course is scheduled for
    assessment that semester; ``?`` means the plan is tentative.
``CourseSubOutcomes``
    Course -> ``Programs`` membership and the sub-outcomes the course
    is meant to assess.
``OutcomeDescriptions``
    Sub-outcome code -> text.

PAT entries are created *by program and outcome*, so the primary output
is grouped that way: for each sub-outcome, the courses to add. A
by-course table follows as a cross-check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

import pandas as pd

from .. import normalize as N
from ..ingest import SubOutcomeSchedule
from ..render.model import NamedTable, NarrativeBlock, Report

# Cells that mean "scheduled" and "scheduled, but not settled yet".
PLANNED_MARKS = frozenset({"x", "yes", "true", "1", "✓", "✔"})
TENTATIVE_MARKS = frozenset({"?", "tbd", "maybe", "x?", "?x"})

_SEMESTER_RE = re.compile(r"([FS])(\d{2})")
_NON_SEMESTER_COLUMNS = frozenset({"offering", "course", "notes"})


# ---------------------------------------------------------------------------
# Semester helpers
# ---------------------------------------------------------------------------


def parse_semester_code(code) -> Optional[tuple]:
    """``'F23'`` -> ``('F', 2023)``; anything else -> None."""
    m = _SEMESTER_RE.fullmatch(str(code).strip().upper())
    if m is None:
        return None
    return m.group(1), 2000 + int(m.group(2))


def semester_label(code) -> str:
    """``'F23'`` -> ``'Fall 2023'``. Unparseable codes pass through."""
    parsed = parse_semester_code(code)
    if parsed is None:
        return str(code).strip()
    season, year = parsed
    return "{} {}".format("Fall" if season == "F" else "Spring", year)


def _semester_sort_key(code):
    parsed = parse_semester_code(code)
    if parsed is None:
        return (9999, 9, str(code))
    season, year = parsed
    # Spring precedes Fall within an academic year label ordering by date.
    return (year, 0 if season == "S" else 1, "")


def semester_columns(schedule: SubOutcomeSchedule) -> List[str]:
    """Chronologically ordered semester column codes from the planned sheet.

    Returns ``[]`` when the workbook has no ``Assessment Schedule`` sheet.
    Columns that are not ``F##``/``S##`` (``Offering``, ``Course``, stray
    notes) are dropped rather than offered to the user as semesters.
    """
    planned = schedule.planned
    if planned is None or planned.empty:
        return []
    codes = [
        str(c).strip() for c in planned.columns
        if str(c).strip().lower() not in _NON_SEMESTER_COLUMNS
        and parse_semester_code(c) is not None
    ]
    return sorted(codes, key=_semester_sort_key)


def default_semester(schedule: SubOutcomeSchedule, today: Optional[date] = None) -> Optional[str]:
    """The semester column the app should preselect.

    Picks the current one by calendar date -- Spring is January through
    June, Fall is July through December -- and falls back to the nearest
    later column, then the last column, so the page always opens on
    something sensible.
    """
    codes = semester_columns(schedule)
    if not codes:
        return None
    if today is None:
        today = date.today()
    want = ("S" if today.month <= 6 else "F", today.year)
    for code in codes:
        if parse_semester_code(code) == want:
            return code
    later = [c for c in codes if _semester_sort_key(c) > (want[1], 0 if want[0] == "S" else 1, "")]
    return later[0] if later else codes[-1]


def cell_status(value) -> str:
    """``'planned'``, ``'tentative'``, or ``''`` for one grid cell."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(value).strip().lower()
    if not s:
        return ""
    if s in PLANNED_MARKS:
        return "planned"
    if s in TENTATIVE_MARKS:
        return "tentative"
    return ""


def parse_offering(value) -> set:
    """``'F,S'`` -> ``{'F', 'S'}``. Unrecognized text yields an empty set."""
    if value is None:
        return set()
    try:
        if pd.isna(value):
            return set()
    except (TypeError, ValueError):
        pass
    out = set()
    for part in re.split(r"[\/,;&+\s]+", str(value).strip().upper()):
        if part in ("F", "S"):
            out.add(part)
        elif part in ("FALL",):
            out.add("F")
        elif part in ("SPRING",):
            out.add("S")
    return out


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ScheduledCourse:
    """One course scheduled in the selected semester for the selected program."""

    course: str
    offering: str
    status: str                              # "planned" | "tentative"
    programs: List[str] = field(default_factory=list)
    suboutcomes: List[tuple] = field(default_factory=list)   # [(code, description)]

    @property
    def codes(self) -> List[str]:
        return [c for c, _ in self.suboutcomes]


@dataclass
class SubOutcomeGroup:
    """The courses to create in PAT for one sub-outcome."""

    code: str
    description: str
    courses: List[str] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        return self.code.split(".")[0]


@dataclass
class SchedulerResult:
    """Everything the PAT Scheduler page and report need."""

    program: str
    semester_code: str
    semester_label: str
    groups: List[SubOutcomeGroup] = field(default_factory=list)
    courses: List[ScheduledCourse] = field(default_factory=list)
    tentative: List[ScheduledCourse] = field(default_factory=list)
    unmapped_courses: List[str] = field(default_factory=list)
    offering_conflicts: List[str] = field(default_factory=list)

    @property
    def entry_count(self) -> int:
        """Rows the admin will create: one per (course, sub-outcome)."""
        return sum(len(g.courses) for g in self.groups)

    def flat_rows(self) -> List[List[str]]:
        """One row per PAT entry -- the shape of the CSV export."""
        rows = []
        for g in self.groups:
            for course in g.courses:
                rows.append([
                    self.program, self.semester_label, g.outcome,
                    g.code, g.description, course,
                ])
        return rows


FLAT_COLUMNS = [
    "Program", "Semester", "Outcome", "Sub-outcome", "Description", "Course",
]


# ---------------------------------------------------------------------------
# Core join
# ---------------------------------------------------------------------------


def _sort_code(code: str):
    try:
        major, minor = str(code).split(".")
        return (int(major), int(minor))
    except ValueError:
        return (9999, str(code))


def _sort_course(course: str):
    m = re.match(r"([A-Za-z]+)\s*(\d+)", str(course))
    return (m.group(1).upper(), int(m.group(2))) if m else ("ZZ", 99999)


def collect(
    schedule: SubOutcomeSchedule,
    program: str,
    semester_code: str,
) -> SchedulerResult:
    """Join the planned grid to course membership for one program/semester.

    A course lands in the result when its cell in ``semester_code`` is
    marked *and* its ``CourseSubOutcomes`` ``Programs`` field includes
    ``program``. Cross-listed courses are matched through
    :meth:`SubOutcomeSchedule.lookup`, which unions every row for the
    course, so a course listed once per program section is not dropped.
    """
    program = str(program).strip().upper()
    result = SchedulerResult(
        program=program,
        semester_code=str(semester_code).strip(),
        semester_label=semester_label(semester_code),
    )

    planned = schedule.planned
    if planned is None or planned.empty:
        return result

    col = next(
        (c for c in planned.columns
         if str(c).strip().upper() == result.semester_code.upper()),
        None,
    )
    if col is None:
        return result

    parsed = parse_semester_code(result.semester_code)
    season = parsed[0] if parsed else None

    for _, row in planned.iterrows():
        course = str(row.get("Course", "")).strip()
        if not course or course.lower() == "nan":
            continue
        status = cell_status(row.get(col))
        if not status:
            continue

        info = schedule.lookup(course)
        if info is None:
            # Scheduled for assessment but absent from CourseSubOutcomes:
            # nobody can say which program or sub-outcomes it serves.
            if course not in result.unmapped_courses:
                result.unmapped_courses.append(course)
            continue

        programs = [p.strip().upper() for p in info["programs"]]
        if program not in programs:
            continue

        offering_raw = str(row.get("Offering", "")).strip()
        offering = parse_offering(offering_raw)
        if season and offering and season not in offering:
            result.offering_conflicts.append(
                "{} is scheduled in {} but the workbook lists it as offered "
                "{}-only.".format(course, result.semester_label, offering_raw)
            )

        entry = ScheduledCourse(
            course=info["course"],
            offering=offering_raw,
            status=status,
            programs=programs,
            suboutcomes=list(info["suboutcomes"]),
        )
        if status == "tentative":
            result.tentative.append(entry)
        else:
            result.courses.append(entry)

    result.courses.sort(key=lambda e: _sort_course(e.course))
    result.tentative.sort(key=lambda e: _sort_course(e.course))
    result.unmapped_courses.sort(key=_sort_course)

    # Invert course -> sub-outcomes into sub-outcome -> courses, which is
    # the order the PAT web tool asks for entries in.
    by_code: dict = {}
    descriptions: dict = {}
    for entry in result.courses:
        for code, desc in entry.suboutcomes:
            by_code.setdefault(code, []).append(entry.course)
            if desc and code not in descriptions:
                descriptions[code] = desc
    result.groups = [
        SubOutcomeGroup(
            code=code,
            description=descriptions.get(code, schedule.descriptions.get(code, "")),
            courses=sorted(set(by_code[code]), key=_sort_course),
        )
        for code in sorted(by_code, key=_sort_code)
    ]
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def build(
    schedule: SubOutcomeSchedule,
    program: str,
    semester_code: str,
    generated_on: Optional[date] = None,
    result: Optional[SchedulerResult] = None,
) -> Report:
    """Build the PAT Scheduler report for one program and semester.

    Pass ``result`` to reuse a :func:`collect` call the caller already
    made; otherwise this runs the join itself.
    """
    if generated_on is None:
        generated_on = date.today()
    if result is None:
        result = collect(schedule, program, semester_code)

    program_label = N.PROGRAM_LABELS.get(result.program, result.program)
    report = Report(
        title="PAT Scheduler",
        subtitle="{} ({}) · {}".format(
            program_label, result.program, result.semester_label
        ),
        generated_on=generated_on,
    )

    if not result.groups and not result.tentative and not result.unmapped_courses:
        report.body.append(NarrativeBlock(
            heading=None,
            body_markdown=(
                "_No courses are scheduled for assessment in {} for {}._"
                .format(result.semester_label, result.program)
            ),
        ))
        return report

    report.body.append(NarrativeBlock(
        heading=None,
        body_markdown=(
            "**{} PAT entries** to create for **{}** in **{}**: "
            "{} course(s) across {} sub-outcome(s). "
            "Source: Assessment Schedule workbook; no PAT export consulted."
            .format(
                result.entry_count, result.program, result.semester_label,
                len(result.courses), len(result.groups),
            )
        ),
    ))

    if result.groups:
        report.body.append(NarrativeBlock(
            heading=None,
            body_markdown=(
                "PAT entries are created per program and outcome, so this is "
                "the working list. Each course listed under a sub-outcome is "
                "one entry."
            ),
        ))
        report.body.append(NamedTable(
            title="Courses to add, by sub-outcome",
            columns=["Outcome", "Sub-outcome", "Description", "Courses", "#"],
            rows=[
                [g.outcome, g.code, g.description,
                 ", ".join(g.courses), str(len(g.courses))]
                for g in result.groups
            ],
            footnote="{} entries total.".format(result.entry_count),
        ))

    if result.courses:
        report.body.append(NamedTable(
            title="Cross-check: by course",
            columns=["Course", "Offered", "Sub-outcomes", "#"],
            rows=[
                [e.course, e.offering, ", ".join(e.codes), str(len(e.codes))]
                for e in result.courses
            ],
        ))

    if result.tentative:
        report.body.append(NarrativeBlock(
            heading=None,
            body_markdown=(
                "These courses are marked **?** rather than **X** in the "
                "Assessment Schedule for {}. Confirm with the program "
                "coordinator before adding them to PAT."
                .format(result.semester_label)
            ),
        ))
        report.body.append(NamedTable(
            title="Needs confirmation (marked ?)",
            columns=["Course", "Offered", "Sub-outcomes", "#"],
            rows=[
                [e.course, e.offering, ", ".join(e.codes), str(len(e.codes))]
                for e in result.tentative
            ],
        ))

    warnings = []
    if result.unmapped_courses:
        warnings.append(
            "- Scheduled in {} but missing from the CourseSubOutcomes sheet, "
            "so their program and sub-outcomes are unknown: **{}**."
            .format(result.semester_label, ", ".join(result.unmapped_courses))
        )
    for msg in result.offering_conflicts:
        warnings.append("- " + msg)
    if warnings:
        report.body.append(NarrativeBlock(
            heading="Workbook issues",
            body_markdown="\n".join(warnings),
        ))

    return report
