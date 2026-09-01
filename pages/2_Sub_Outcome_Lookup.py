"""Sub-Outcome Lookup page.

Reads the Assessment Schedule workbook from the cache, lets the user
pick a course, and renders the list of programs + sub-outcomes (with
descriptions joined). Same four-format download pattern as the Course
Report page.
"""

from __future__ import annotations

import re
from datetime import date

import streamlit as st

from Home import (
    cache_signature,
    download_row,
    get_schedule_cached,
    render_sidebar,
)
from pat.analysis import suboutcome as suboutcome_analysis
from pat.render import html as html_renderer


def _safe_filename(course: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", course.strip())


def main():
    render_sidebar()
    st.title("Sub-Outcome Lookup")

    schedule = get_schedule_cached(cache_signature())
    if schedule is None:
        st.info(
            ":arrow_left: Upload the Assessment Schedule workbook in the "
            "sidebar to begin. The workbook needs `CourseSubOutcomes` and "
            "`OutcomeDescriptions` sheets."
        )
        return

    courses = schedule.all_courses()
    if not courses:
        st.warning("No courses found in the Assessment Schedule workbook.")
        return

    course = st.selectbox("Course", courses, key="sol_course")

    report = suboutcome_analysis.build(
        schedule, course, generated_on=date.today()
    )

    # Downloads.
    base = f"{_safe_filename(course)}_suboutcomes"
    download_row(report, base)

    st.divider()

    # Preview.
    st.subheader("Preview")
    full_html = html_renderer.render(report)
    style_match = re.search(r"<style>.*?</style>", full_html, flags=re.DOTALL)
    style_block = style_match.group(0) if style_match else ""
    body = html_renderer.render_body(report)
    st.markdown(style_block + body, unsafe_allow_html=True)


main()
