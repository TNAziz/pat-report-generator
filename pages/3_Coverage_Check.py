"""Coverage Check page.

Pulls the cleaned combined DataFrame from the data layer and the
Assessment Schedule (optional) and renders:

- A picker for the focus semester.
- A year-range slider for the per-year trend + heatmaps.
- The missing-assessment table for the picked semester.
- The semester summary (counts and percentages).
- A line chart of per-year completion rate per program.
- A coverage heatmap per program (sub-outcome x year).
- Four-format download buttons.
"""

from __future__ import annotations

import re
from datetime import date

import streamlit as st

from Home import (
    cache_signature,
    get_combined_cached,
    get_schedule_cached,
    render_sidebar,
)
from pat import data as data_layer
from pat.analysis import coverage as coverage_analysis
from pat.render import docx as docx_renderer
from pat.render import html as html_renderer
from pat.render import markdown as md_renderer
from pat.render import pdf as pdf_renderer


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", s.strip())


def main():
    render_sidebar()
    st.title("Coverage Check")

    df = get_combined_cached(cache_signature())
    if df.empty:
        st.info(":arrow_left: Upload at least one PAT CSV in the sidebar to begin.")
        return

    semesters = data_layer.get_loaded_semesters()
    if not semesters:
        st.warning("Loaded data has no recognizable semesters.")
        return

    year_range = data_layer.get_year_range()
    yr_min, yr_max = year_range if year_range else (2020, date.today().year)

    col_sem, col_year = st.columns([2, 3])
    with col_sem:
        semester = st.selectbox("Focus semester", semesters, key="cc_semester")
    with col_year:
        yr_lo, yr_hi = st.slider(
            "Year range (for trend chart and heatmaps)",
            min_value=int(yr_min), max_value=int(yr_max),
            value=(int(yr_min), int(yr_max)),
            step=1, key="cc_year_range",
        )

    # Use the Assessment Schedule to determine the canonical sub-outcome
    # list (so heatmap rows include sub-outcomes with no coverage at all).
    schedule = get_schedule_cached(cache_signature())
    sub_outcomes = None
    if schedule is not None:
        sub_outcomes = schedule.suboutcome_columns

    report = coverage_analysis.check(
        df, semester,
        year_min=yr_lo, year_max=yr_hi,
        sub_outcomes=sub_outcomes,
        generated_on=date.today(),
    )

    # --- Downloads (top of page so they're easy to find) ---
    base = f"coverage_{_safe(semester)}"
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

    # --- Missing assessments ---
    st.subheader(f"Missing assessments in {semester}")
    missing = coverage_analysis.missing_for_semester(df, semester)
    cols = st.columns(3)
    for col_widget, prog in zip(cols, ["CE", "CON", "ENE"]):
        with col_widget:
            st.markdown(f"**{prog}**")
            items = missing.get(prog, [])
            if not items:
                st.caption("(none)")
            else:
                for course in items:
                    st.markdown(f"- {course}")

    # --- Semester summary ---
    st.subheader("Semester summary")
    sem_sum = coverage_analysis.semester_summary(df, semester)
    if not sem_sum.empty:
        display = sem_sum.copy()
        display["pct_assessed"] = display["pct_assessed"].map(lambda v: f"{v:.1f}%")
        display["pct_missing"] = display["pct_missing"].map(lambda v: f"{v:.1f}%")
        st.dataframe(
            display.rename(columns={
                "program": "Program",
                "total_courses": "Total",
                "assessed_courses": "Assessed",
                "missing_courses": "Missing",
                "pct_assessed": "% Assessed",
                "pct_missing": "% Missing",
            }),
            hide_index=True, use_container_width=True,
        )

    # --- Per-year trend ---
    st.subheader("Coverage trend by year")
    yr_sum = coverage_analysis.per_year_summary(df, yr_lo, yr_hi)
    if yr_sum.empty:
        st.caption("(no data in the selected year range)")
    else:
        # Use altair so the year axis renders as plain integers ("2020"),
        # not Streamlit's default locale-formatted "2,020".
        import altair as alt
        long_df = yr_sum[["year", "program", "pct_assessed"]].copy()
        chart = (
            alt.Chart(long_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("year:O", title="Year",
                        axis=alt.Axis(labelAngle=0, format="d")),
                y=alt.Y("pct_assessed:Q", title="% Assessed",
                        scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("program:N", title="Program"),
                tooltip=[
                    alt.Tooltip("year:O", title="Year", format="d"),
                    alt.Tooltip("program:N", title="Program"),
                    alt.Tooltip("pct_assessed:Q", title="% Assessed",
                                format=".1f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)

    # --- ABET cycle rollup ---
    st.divider()
    st.subheader("ABET cycle coverage")

    # Default cycle: F23 - S28 (NC State CCEE 2023-2028). Customizable.
    semesters_sorted_old_first = list(reversed(data_layer.get_loaded_semesters()))
    if not semesters_sorted_old_first:
        st.caption("(no semesters detected)")
    else:
        # Sensible default if those semesters are in the loaded data.
        default_start = "Fall 2023" if "Fall 2023" in semesters_sorted_old_first else semesters_sorted_old_first[0]
        default_end_pref = "Spring 2028"
        end_options = semesters_sorted_old_first[:]
        # If the canonical end isn't present, fall back to the most recent loaded semester.
        default_end = default_end_pref if default_end_pref in end_options else end_options[-1]
        # User can also pick a future semester not yet in data -- present a
        # union of (loaded semesters + canonical future ones) for flexibility.
        future_candidates = ["Fall 2026", "Spring 2027", "Fall 2027", "Spring 2028"]
        full_end_options = list(dict.fromkeys(semesters_sorted_old_first + future_candidates))

        c_start, c_end = st.columns(2)
        with c_start:
            cycle_start = st.selectbox(
                "Cycle start", semesters_sorted_old_first,
                index=semesters_sorted_old_first.index(default_start),
                key="cc_cycle_start",
            )
        with c_end:
            cycle_end = st.selectbox(
                "Cycle end", full_end_options,
                index=full_end_options.index(default_end) if default_end in full_end_options else len(full_end_options) - 1,
                key="cc_cycle_end",
            )

        # Canonical sub-outcome list comes from the Schedule when available.
        cycle_sub_outcomes = schedule.suboutcome_columns if schedule is not None else None
        cycle_heatmap = coverage_analysis.cycle_coverage_heatmap(
            df, cycle_start, cycle_end, sub_outcomes=cycle_sub_outcomes,
        )
        # Render inline using the HTML renderer's heatmap function.
        from pat.render.html import _render_heatmap_html  # type: ignore
        full_html_cycle = html_renderer.render(
            html_renderer.Report(title="cycle", heatmaps=[cycle_heatmap])
        ) if False else ""
        # Simpler: inject just the stylesheet from a small rendered report.
        from pat.render.model import Report as _R
        cycle_full = html_renderer.render(_R(title="cycle", heatmaps=[cycle_heatmap]))
        style_match = re.search(r"<style>.*?</style>", cycle_full, flags=re.DOTALL)
        style_block = style_match.group(0) if style_match else ""
        st.markdown(style_block + _render_heatmap_html(cycle_heatmap),
                    unsafe_allow_html=True)

        # --- Sub-outcome detail ---
        st.markdown("**Sub-outcome detail**")
        if schedule is None:
            st.caption(
                "Upload the Assessment Schedule in the sidebar to see "
                "sub-outcome descriptions and the courses that assess each."
            )
        else:
            sel = st.selectbox(
                "Select a sub-outcome",
                schedule.suboutcome_columns,
                key="cc_sub_select",
            )
            if sel:
                desc = schedule.descriptions.get(sel, "")
                if desc:
                    st.markdown(f"**{sel}** -- {desc}")
                else:
                    st.markdown(f"**{sel}**")
                courses_by_prog = schedule.courses_for_suboutcome(sel)
                if not courses_by_prog:
                    st.caption("(no courses on the schedule claim to assess this sub-outcome)")
                else:
                    course_cols = st.columns(3)
                    # Display in canonical program order CE, CON, ENE.
                    for col, prog in zip(course_cols, ["CE", "CON", "ENE"]):
                        with col:
                            st.markdown(f"**{prog}**")
                            lst = courses_by_prog.get(prog, [])
                            if not lst:
                                st.caption("(none)")
                            else:
                                for c in lst:
                                    st.markdown(f"- {c}")

    # --- Heatmaps (one per program) ---
    if report.heatmaps:
        st.subheader("Sub-outcome coverage")
        full_html = html_renderer.render(report)
        style_match = re.search(r"<style>.*?</style>", full_html, flags=re.DOTALL)
        style_block = style_match.group(0) if style_match else ""
        # Render only the heatmap sections of the body via a small dedicated build.
        from pat.render.html import _render_heatmap_html  # type: ignore
        heatmap_html = "".join(_render_heatmap_html(h) for h in report.heatmaps)
        st.markdown(style_block + heatmap_html, unsafe_allow_html=True)
        if schedule is None:
            st.caption(
                ":warning: Without the Assessment Schedule uploaded, "
                "heatmaps only show sub-outcomes that have at least one "
                "measurement in the data. Upload the schedule to see all "
                "sub-outcomes (including ones with zero coverage)."
            )


main()
