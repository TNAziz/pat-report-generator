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
    get_schedule_cached,
    render_sidebar,
)
from pat.analysis import suboutcome as suboutcome_analysis
from pat.render import docx as docx_renderer
from pat.render import html as html_renderer
from pat.render import markdown as md_renderer
from pat.render import pdf as pdf_renderer


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
    md_bytes = md_renderer.render(report).encode("utf-8")
    html_bytes = html_renderer.render(report).encode("utf-8")
    docx_bytes = docx_renderer.render(report)

    dl1, dl2, dl3, dl4 = st.columns(4)
    dl1.download_button("Markdown (.md)", md_bytes, f"{base}.md", "text/markdown",
                        use_container_width=True)
    dl2.download_button("Word (.docx)", docx_bytes, f"{base}.docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True)
    if pdf_renderer.is_available():
        pdf_bytes = pdf_renderer.render(report)
        dl3.download_button("PDF (.pdf)", pdf_bytes, f"{base}.pdf",
                            "application/pdf", use_container_width=True)
    else:
        dl3.button("PDF (.pdf)", disabled=True,
                   help=pdf_renderer.unavailable_reason(),
                   use_container_width=True)
    dl4.download_button("HTML (.html)", html_bytes, f"{base}.html", "text/html",
                        use_container_width=True)

    st.divider()

    # Preview.
    st.subheader("Preview")
    full_html = html_renderer.render(report)
    style_match = re.search(r"<style>.*?</style>", full_html, flags=re.DOTALL)
    style_block = style_match.group(0) if style_match else ""
    body = html_renderer.render_body(report)
    st.markdown(style_block + body, unsafe_allow_html=True)


main()
