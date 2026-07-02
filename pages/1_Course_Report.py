"""Course Report page.

Pulls the cleaned combined DataFrame from the data layer, lets the
user pick a course + year range + program filter, then renders the
result inline (HTML) and offers downloads in all four formats.

This file contains UI plumbing only. All business logic lives in
``pat.analysis.course_report`` and the renderers; this page is thin.
"""

from __future__ import annotations

import re
from datetime import date

import streamlit as st

from Home import (
    cache_signature,
    get_combined_cached,
    render_sidebar,
    year_range_slider,
)
from pat import data
from pat.analysis import course_report
from pat.render import docx as docx_renderer
from pat.render import html as html_renderer
from pat.render import markdown as md_renderer
from pat.render import pdf as pdf_renderer


def _safe_filename(course: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", course.strip())


def main():
    render_sidebar()
    st.title("Course Report")

    df = get_combined_cached(cache_signature())
    if df.empty:
        st.info(":arrow_left: Upload at least one PAT CSV in the sidebar to begin.")
        return

    # --- Inputs ---

    courses = data.get_loaded_courses()
    if not courses:
        st.warning("Loaded data has no course codes. Check the uploads.")
        return

    col_course, col_year = st.columns([2, 3])
    with col_course:
        course = st.selectbox("Course", courses, key="cr_course")
    with col_year:
        year_range = data.get_year_range()
        if year_range:
            yr_min, yr_max = year_range
        else:
            yr_min, yr_max = 2020, date.today().year
        yr_lo, yr_hi = year_range_slider(
            "Year range", yr_min, yr_max, key="cr_year_range",
        )

    # Find which programs actually contain this course before letting the
    # user pick from them.
    course_rows = data.filter_course(df, course)
    progs_with_course = sorted(course_rows["program"].astype(str).unique().tolist())
    if not progs_with_course:
        st.warning(f"{course} has no rows in the loaded data.")
        return
    selected_programs = st.multiselect(
        "Programs",
        options=progs_with_course,
        default=progs_with_course,
        key="cr_programs",
    )
    if not selected_programs:
        st.warning("Select at least one program to generate a report.")
        return

    # --- Build the report ---

    report = course_report.build(
        df,
        course,
        year_range=(yr_lo, yr_hi),
        programs=selected_programs,
        generated_on=date.today(),
    )
    if not report.sections:
        st.warning(
            f"No data for {course} in {yr_lo}-{yr_hi} for the selected programs. "
            "Try widening the year range."
        )
        return

    # --- Downloads ---

    base = _safe_filename(course)
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

    # --- Preview ---

    st.subheader("Preview")
    # Use the HTML renderer's body (no <html>/<head> wrapper) so it nests
    # cleanly inside Streamlit's chrome. The inline <style> still applies.
    body = html_renderer.render_body(report)
    style = re.search(r"<style>.*?</style>",
                      html_renderer.render(report), flags=re.DOTALL)
    style_block = style.group(0) if style else ""
    st.markdown(style_block + body, unsafe_allow_html=True)


main()
