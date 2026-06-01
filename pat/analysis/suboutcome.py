"""Sub-Outcome Lookup analysis.

Given an Assessment Schedule wrapper and a course code, build a Report
listing the programs that teach the course and the sub-outcomes the
course is meant to assess (joined to their descriptions).

The source-of-truth here is the Assessment Schedule workbook
(``CourseSubOutcomes`` + ``OutcomeDescriptions`` sheets), not the PAT
data dumps.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..ingest import SubOutcomeSchedule
from ..render.model import NarrativeBlock, Report


def build(
    schedule: SubOutcomeSchedule,
    course_code: str,
    generated_on: Optional[date] = None,
) -> Report:
    """Build a Sub-Outcome Lookup report for ``course_code``.

    Returns a Report whose ``narrative`` blocks list the programs and
    the sub-outcomes (with descriptions joined). If the course is not on
    the schedule, returns a Report with a single "not found" narrative.
    """
    if generated_on is None:
        generated_on = date.today()

    result = schedule.lookup(course_code)
    if result is None:
        # Suggest near-matches if the user fat-fingered.
        all_courses = schedule.all_courses()
        from .. import normalize as N
        norm = N.course_key(course_code)
        suggestions = [
            c for c in all_courses
            if norm and (norm in N.course_key(c) or N.course_key(c) in norm)
        ][:5]
        hint = ""
        if suggestions:
            hint = " Did you mean: " + ", ".join(suggestions) + "?"
        return Report(
            title=course_code.strip(),
            subtitle="Not on the Assessment Schedule",
            generated_on=generated_on,
            narrative=[NarrativeBlock(
                heading=None,
                body_markdown=f"_Course {course_code!r} was not found in the Assessment Schedule workbook." + hint + "_",
            )],
        )

    course = result["course"]
    programs = result["programs"]
    suboutcomes = result["suboutcomes"]

    programs_block = NarrativeBlock(
        heading="Programs",
        body_markdown=" / ".join(programs) if programs else "_(none listed)_",
    )

    if suboutcomes:
        bullets = []
        for code, desc in suboutcomes:
            if desc:
                bullets.append(f"- **{code}:** {desc}")
            else:
                bullets.append(f"- **{code}**")
        suboutcomes_block = NarrativeBlock(
            heading="Sub-Outcomes",
            body_markdown="\n".join(bullets),
        )
    else:
        suboutcomes_block = NarrativeBlock(
            heading="Sub-Outcomes",
            body_markdown=f"_No sub-outcomes found for {course}_",
        )

    return Report(
        title=course,
        subtitle=None,
        generated_on=generated_on,
        narrative=[programs_block, suboutcomes_block],
    )
