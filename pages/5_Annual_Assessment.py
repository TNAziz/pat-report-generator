"""Annual Assessment page.

Pick the programs, the assessment cycle's semesters, and the outcomes;
the page renders the report in the shape of the Anthology assessment
write-up -- program, then outcome, then sub-outcome, each with its
definition, a statistics line (courses, measures, N, weighted % meeting
threshold), the underlying measurement rows, and an Actions Taken
roll-up for the outcome.

Same four-format download pattern as the other pages.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from Home import (
    cache_signature,
    download_row,
    get_combined_cached,
    get_schedule_cached,
    render_sidebar,
)
from pat import cache
from pat import llm
from pat import normalize as N
from pat.analysis import annual as annual_analysis
from pat.render import markdown as md_renderer
from pat.render import html as html_renderer


def _safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", text.strip())


def _available_semesters(df: pd.DataFrame) -> list[str]:
    if df.empty or "semester" not in df.columns:
        return []
    pairs = df[["semester", "semester_sort_key"]].dropna().drop_duplicates()
    pairs = pairs[pairs["semester"].astype(str).str.strip() != ""]
    pairs = pairs.sort_values("semester_sort_key", ascending=False)
    return pairs["semester"].astype(str).tolist()


def _available_programs(df: pd.DataFrame) -> list[str]:
    if df.empty or "program" not in df.columns:
        return []
    present = set(df["program"].dropna().astype(str))
    return [p for p in N.PROGRAM_LABELS if p in present]


def _download_stem(programs: list[str], sems: list[str], outcomes: list[str]) -> str:
    parts = ["annual_assessment"]
    for group in (programs, sems, outcomes):
        if group:
            parts.append("_".join(_safe_filename(str(g)) for g in group))
    return "_".join(parts)


def _latest_update(df: pd.DataFrame, sems: list[str]) -> str | None:
    """Newest measurement-update date among the selected semesters.

    Faculty submit late, so a cycle keeps gaining rows after its report is
    filed. Recording this date in the packet makes it obvious later whether
    a draft predates some of its own data.
    """
    if "measurement_date" not in df.columns or not sems:
        return None
    rows = df[df["semester"].astype(str).isin(sems)]
    dates = pd.to_datetime(rows["measurement_date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return dates.max().date().isoformat()


def _packet_download(report, stem, df, progs, sems, outcomes, descriptions) -> None:
    """Offer the LLM drafting packet: the prompt and the archival record."""
    st.markdown("**Drafting packet**")
    st.caption(
        "One Markdown file holding the task, the house style, the rules, the "
        "provenance of every source export, and the data itself. Paste it "
        "into an assistant to draft the narrative, and keep the file as the "
        "record of exactly what the draft was written from."
    )
    if report.is_empty() or not report.body:
        st.caption("_Pick semesters and outcomes to build a packet._")
        return

    notes = []
    latest = _latest_update(df, sems)
    if latest:
        notes.append(
            f"Newest measurement update among these semesters: {latest} "
            "(PAT accepts late submissions, so a cycle can gain rows after "
            "its report is filed)"
        )
    # The packet carries the full column set: the narrative needs to say
    # what each measure was and quote raw counts, which the readable
    # seven-column table on screen deliberately leaves out.
    detailed = annual_analysis.build(
        df,
        semesters=sems,
        outcomes=outcomes,
        programs=progs,
        descriptions=descriptions,
        detail=True,
        generated_on=date.today(),
    )
    packet = llm.drafting_packet(
        detailed,
        md_renderer.render(detailed),
        selection={
            "Programs": progs or ["all"],
            "Semesters": sems,
            "Outcomes": outcomes,
        },
        sources=cache.load_manifest(),
        notes=notes,
        generated_on=date.today(),
    )
    st.download_button(
        "Drafting packet (.md)",
        packet.encode("utf-8"),
        f"{stem}_drafting_packet.md",
        "text/markdown",
        use_container_width=True,
    )
    with st.expander("Preview the packet's instructions (Sections 1-4)"):
        head = packet.split("## 5. Data", 1)[0]
        st.code(head, language="markdown")


def main():
    render_sidebar()
    st.title("Annual Assessment")
    st.caption(
        "Pick the programs, the semesters in the assessment cycle, and the "
        "outcomes. The report is grouped program → outcome → sub-outcome, "
        "with each sub-outcome's definition, its aggregate statistics, every "
        "underlying measurement, and an Actions Taken roll-up per outcome."
    )

    df = get_combined_cached(cache_signature())
    if df.empty:
        st.info(
            ":arrow_left: Upload PAT CSVs in the sidebar to begin. Each "
            "program (CE, ENE, CON) needs one CSV."
        )
        return

    programs = _available_programs(df)
    semesters = _available_semesters(df)
    outcomes = annual_analysis.available_outcomes(df)
    if not semesters or not outcomes:
        st.warning("Loaded data has no semesters or outcomes to pick from.")
        return

    # Sub-outcome definitions come from the Assessment Schedule workbook;
    # the report explains their absence rather than failing without it.
    descriptions = {}
    schedule = get_schedule_cached(cache_signature())
    if schedule is not None:
        descriptions = getattr(schedule, "descriptions", {}) or {}
    if not descriptions:
        st.info(
            "Upload an Assessment Schedule workbook in the sidebar to include "
            "sub-outcome definitions in the report."
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        picked_progs = st.multiselect(
            "Programs",
            options=programs,
            default=[],
            key="aa_programs",
            help="Leave empty to include every program that has data.",
        )
    with col2:
        picked_sems = st.multiselect(
            "Semesters",
            options=semesters,
            default=[],
            key="aa_semesters",
            help="The assessment cycle, e.g. Fall 2024 + Spring 2025.",
        )
    with col3:
        picked_outcomes = st.multiselect(
            "Outcomes",
            options=outcomes,
            default=[],
            key="aa_outcomes",
            help="Every sub-outcome under each picked outcome is included.",
        )

    report = annual_analysis.build(
        df,
        semesters=picked_sems,
        outcomes=picked_outcomes,
        programs=picked_progs,
        descriptions=descriptions,
        generated_on=date.today(),
    )

    stem = _download_stem(picked_progs, picked_sems, picked_outcomes)
    download_row(report, stem)
    _packet_download(report, stem, df, picked_progs, picked_sems,
                     picked_outcomes, descriptions)

    st.divider()
    st.subheader("Preview")
    full_html = html_renderer.render(report)
    style_match = re.search(r"<style>.*?</style>", full_html, flags=re.DOTALL)
    style_block = style_match.group(0) if style_match else ""
    body = html_renderer.render_body(report)
    st.markdown(style_block + body, unsafe_allow_html=True)


main()
