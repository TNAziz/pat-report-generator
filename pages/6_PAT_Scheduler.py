"""PAT Scheduler page.

Pick a program and a semester; the page lists everything the PAT
administrator has to create in the PAT web tool for that combination.

The list comes from the Assessment Schedule workbook alone -- the
planned course x semester grid joined to each course's program
membership and sub-outcomes. PAT exports are deliberately *not*
consulted, so this answers "what does the plan call for?", not "what has
already been entered?".

Entries in PAT are created per program and outcome, so the primary table
is grouped by sub-outcome. A by-course table follows as a cross-check,
and a CSV export gives the admin a working checklist.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date

import streamlit as st

from Home import (
    cache_signature,
    download_row,
    get_schedule_cached,
    render_sidebar,
)
from pat import normalize as N
from pat.analysis import scheduler as scheduler_analysis
from pat.render import html as html_renderer


def _safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(text).strip())


def _csv_bytes(result) -> bytes:
    """The flat one-row-per-PAT-entry checklist."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(scheduler_analysis.FLAT_COLUMNS)
    writer.writerows(result.flat_rows())
    return buf.getvalue().encode("utf-8")


def main():
    render_sidebar()
    st.title("PAT Scheduler")
    st.caption(
        "What the PAT Admin needs to add to the PAT web tool for one "
        "program and semester. Built from the Assessment Schedule "
        "workbook only -- no PAT export is consulted, so this is the "
        "plan, not a record of what is already entered."
    )

    schedule = get_schedule_cached(cache_signature())
    if schedule is None:
        st.info(
            ":arrow_left: Upload the Assessment Schedule workbook in the "
            "sidebar to use the scheduler."
        )
        return

    semesters = scheduler_analysis.semester_columns(schedule)
    if not semesters:
        st.warning(
            "The Assessment Schedule workbook has no `Assessment Schedule` "
            "sheet with semester columns (F23, S24, ...), so there is "
            "nothing to schedule from."
        )
        return

    default_code = scheduler_analysis.default_semester(schedule)
    default_index = semesters.index(default_code) if default_code in semesters else 0

    col1, col2 = st.columns(2)
    with col1:
        program = st.selectbox(
            "Program",
            options=list(N.PROGRAM_LABELS),
            format_func=lambda p: f"{p} -- {N.PROGRAM_LABELS[p]}",
            key="sched_program",
        )
    with col2:
        semester_code = st.selectbox(
            "Semester",
            options=semesters,
            index=default_index,
            format_func=scheduler_analysis.semester_label,
            key="sched_semester",
            help="Defaults to the current semester by calendar date.",
        )

    result = scheduler_analysis.collect(schedule, program, semester_code)
    report = scheduler_analysis.build(
        schedule, program, semester_code,
        generated_on=date.today(), result=result,
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("PAT entries to create", result.entry_count)
    m2.metric("Courses", len(result.courses))
    m3.metric("Sub-outcomes", len(result.groups))
    if result.tentative:
        st.warning(
            f"{len(result.tentative)} course(s) are marked **?** rather than "
            "**X** for this semester and are listed separately below. They "
            "are not counted in the totals."
        )

    stem = "pat_scheduler_{}_{}".format(
        _safe_filename(program), _safe_filename(semester_code)
    )
    download_row(report, stem)
    if result.entry_count:
        st.download_button(
            "Checklist (.csv)",
            _csv_bytes(result),
            f"{stem}.csv",
            "text/csv",
            use_container_width=True,
            help=(
                "One row per PAT entry -- program, semester, outcome, "
                "sub-outcome, course."
            ),
        )

    st.divider()
    st.subheader("Preview")
    full_html = html_renderer.render(report)
    style_match = re.search(r"<style>.*?</style>", full_html, flags=re.DOTALL)
    style_block = style_match.group(0) if style_match else ""
    body = html_renderer.render_body(report)
    st.markdown(style_block + body, unsafe_allow_html=True)


main()
