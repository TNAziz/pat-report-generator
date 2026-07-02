"""Annual Assessment page.

Pick a set of semesters and a set of sub-outcomes; the page renders
every matching measurement row from the loaded PAT data, grouped by
program and sub-outcome. No aggregation -- raw performance, student
count, and faculty comment per underlying course/semester row.

Same four-format download pattern as the other pages.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from Home import (
    cache_signature,
    get_combined_cached,
    render_sidebar,
)
from pat.analysis import annual as annual_analysis
from pat.ingest import _sort_outcome_codes
from pat.render import docx as docx_renderer
from pat.render import html as html_renderer
from pat.render import markdown as md_renderer
from pat.render import pdf as pdf_renderer


def _safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", text.strip())


def _available_semesters(df: pd.DataFrame) -> list[str]:
    if df.empty or "semester" not in df.columns:
        return []
    pairs = df[["semester", "semester_sort_key"]].dropna().drop_duplicates()
    pairs = pairs[pairs["semester"].astype(str).str.strip() != ""]
    pairs = pairs.sort_values("semester_sort_key", ascending=False)
    return pairs["semester"].astype(str).tolist()


def _available_suboutcomes(df: pd.DataFrame) -> list[str]:
    if df.empty or "suboutcome" not in df.columns:
        return []
    codes = df["suboutcome"].dropna().astype(str).str.strip()
    codes = codes[codes != ""].unique().tolist()
    return _sort_outcome_codes(codes)


def _download_stem(picked_sems: list[str], picked_subs: list[str]) -> str:
    parts = ["annual_assessment"]
    if picked_sems:
        parts.append("_".join(_safe_filename(s) for s in picked_sems))
    if picked_subs:
        parts.append("_".join(_safe_filename(s) for s in picked_subs))
    return "_".join(parts) if parts else "annual_assessment"


def main():
    render_sidebar()
    st.title("Annual Assessment")
    st.caption(
        "Pick a set of semesters and a set of sub-outcomes; the report "
        "lists every matching measurement grouped by program and "
        "sub-outcome (raw rows, no aggregation)."
    )

    df = get_combined_cached(cache_signature())
    if df.empty:
        st.info(
            ":arrow_left: Upload PAT CSVs in the sidebar to begin. Each "
            "program (CE, ENE, CON) needs one CSV."
        )
        return

    semesters = _available_semesters(df)
    suboutcomes = _available_suboutcomes(df)
    if not semesters or not suboutcomes:
        st.warning("Loaded data has no semesters or sub-outcomes to pick from.")
        return

    col1, col2 = st.columns(2)
    with col1:
        picked_sems = st.multiselect(
            "Semesters",
            options=semesters,
            default=[],
            key="aa_semesters",
            help="Pick one or more; only rows from these semesters appear in the report.",
        )
    with col2:
        picked_subs = st.multiselect(
            "Sub-outcomes",
            options=suboutcomes,
            default=[],
            key="aa_suboutcomes",
            help="Pick one or more; results are grouped by (program, sub-outcome).",
        )

    report = annual_analysis.build(
        df,
        semesters=picked_sems,
        suboutcomes=picked_subs,
        generated_on=date.today(),
    )

    stem = _download_stem(picked_sems, picked_subs)
    md_bytes = md_renderer.render(report).encode("utf-8")
    html_bytes = html_renderer.render(report).encode("utf-8")
    docx_bytes = docx_renderer.render(report)

    dl1, dl2, dl3, dl4 = st.columns(4)
    dl1.download_button(
        "Markdown (.md)", md_bytes, f"{stem}.md", "text/markdown",
        use_container_width=True,
    )
    dl2.download_button(
        "Word (.docx)", docx_bytes, f"{stem}.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    if pdf_renderer.is_available():
        pdf_bytes = pdf_renderer.render(report)
        dl3.download_button(
            "PDF (.pdf)", pdf_bytes, f"{stem}.pdf", "application/pdf",
            use_container_width=True,
        )
    else:
        dl3.button(
            "PDF (.pdf)", disabled=True,
            help=pdf_renderer.unavailable_reason(),
            use_container_width=True,
        )
    dl4.download_button(
        "HTML (.html)", html_bytes, f"{stem}.html", "text/html",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Preview")
    full_html = html_renderer.render(report)
    style_match = re.search(r"<style>.*?</style>", full_html, flags=re.DOTALL)
    style_block = style_match.group(0) if style_match else ""
    body = html_renderer.render_body(report)
    st.markdown(style_block + body, unsafe_allow_html=True)


main()
