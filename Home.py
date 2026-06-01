"""PAT Report Generator -- Streamlit entry point.

Lives at the top level so `streamlit run app.py` works. Any file under
`pages/` becomes a sidebar nav entry automatically (Streamlit's
multi-page convention).

This module owns the shared sidebar (uploads, status, cache controls).
Pages import from `app` to render the sidebar consistently. All actual
business logic lives in `pat/` -- this file is pure UI plumbing.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import streamlit as st

from pat import cache, data
from pat import ingest, normalize as N

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="PAT Report Generator",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _human_date(iso: str) -> str:
    """Render an ISO datetime as a short human label, falling back gracefully."""
    if not iso:
        return ""
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return iso


def _detect_or_prompt(upload, key_widget_prefix: str):
    """Determine which program slot an uploaded CSV belongs to.

    Returns the program code or None. Shows an inline selectbox when
    detection is ambiguous so the user can resolve it.
    """
    detected = ingest.detect_program_from_filename(upload.name)
    if detected is not None:
        return detected
    # Read the file head to try content detection, then rewind.
    upload.seek(0)
    try:
        import pandas as pd
        head = pd.read_csv(upload, nrows=20)
        content_hit = ingest.detect_program_from_content(head)
    except Exception:
        content_hit = None
    upload.seek(0)
    if content_hit is not None:
        return content_hit
    # Ask the user.
    choice = st.selectbox(
        f"Which program does **{upload.name}** belong to?",
        options=["Skip", "CE", "CON", "ENE"],
        key=f"{key_widget_prefix}_choice",
    )
    return None if choice == "Skip" else choice


def _save_pat_uploads(uploads):
    """Process the multi-file uploader for PAT CSVs."""
    if not uploads:
        return
    saved = []
    errors = []
    for upload in uploads:
        prog = _detect_or_prompt(upload, key_widget_prefix=f"detect_{upload.name}")
        if prog is None:
            continue
        try:
            upload.seek(0)
            data_bytes = upload.read()
            # Validate by parsing once -- raises IngestError with a clear
            # message if columns are missing, so the user finds out now.
            ingest.read_pat_csv(data_bytes, program=prog, filename=upload.name)
            cache.save_upload(prog, data_bytes, upload.name)
            saved.append(f"{prog}: `{upload.name}`")
        except N.IngestError as exc:
            errors.append(f"{upload.name}: {exc}")
    for msg in saved:
        st.success("Saved " + msg)
    for msg in errors:
        st.error(msg)


def _save_schedule_upload(upload):
    if not upload:
        return
    try:
        # Validate by reading once.
        upload.seek(0)
        data_bytes = upload.read()
        ingest.read_assessment_schedule(data_bytes)
        cache.save_upload(cache.SCHEDULE_KEY, data_bytes, upload.name)
        st.success(f"Saved Assessment Schedule: `{upload.name}`")
    except N.IngestError as exc:
        st.error(f"{upload.name}: {exc}")


def render_sidebar() -> None:
    """Sidebar layout: file uploaders + per-slot status display + cache controls.

    Called from every page (via st.Page) -- Streamlit re-runs the script
    on every interaction, so this function is idempotent.
    """
    st.sidebar.title("PAT Report Generator")
    st.sidebar.caption("Generate ABET-ready reports from PAT exports.")

    # --- PAT CSVs ---
    st.sidebar.subheader("PAT exports")
    pat_uploads = st.sidebar.file_uploader(
        "Drop one to three CSVs (CE, CON, ENE)",
        type=["csv"],
        accept_multiple_files=True,
        key="pat_uploader",
    )
    if pat_uploads:
        _save_pat_uploads(pat_uploads)

    # Status display -- one line per program slot.
    manifest = cache.load_manifest()
    cached = cache.list_cached()
    year_range = data.get_year_range()
    for prog in N.PROGRAM_LABELS:
        if prog in cached:
            label = manifest.get(prog, {}).get("original_name", cached[prog].name)
            date_str = _human_date(manifest.get(prog, {}).get("uploaded_at", ""))
            extra = f" ({year_range[0]}-{year_range[1]})" if year_range else ""
            st.sidebar.markdown(f"OK **{prog}** -- {label}<br><span style='color:#888;font-size:0.85em'>uploaded {date_str}{extra}</span>", unsafe_allow_html=True)
        else:
            st.sidebar.markdown(f":small_red_triangle_down: **{prog}** -- not loaded")

    # --- Schedule ---
    st.sidebar.subheader("Assessment Schedule")
    schedule_upload = st.sidebar.file_uploader(
        "Workbook with CourseSubOutcomes + OutcomeDescriptions sheets",
        type=["xlsx"],
        accept_multiple_files=False,
        key="schedule_uploader",
    )
    if schedule_upload:
        _save_schedule_upload(schedule_upload)
    if cache.SCHEDULE_KEY in cached:
        meta = manifest.get(cache.SCHEDULE_KEY, {})
        st.sidebar.markdown(
            f"OK **Schedule** -- {meta.get('original_name', 'loaded')}<br>"
            f"<span style='color:#888;font-size:0.85em'>uploaded "
            f"{_human_date(meta.get('uploaded_at',''))}</span>",
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(":small_red_triangle_down: **Schedule** -- not loaded")

    st.sidebar.divider()

    # --- Cache controls ---
    col1, col2 = st.sidebar.columns(2)
    if col1.button("Clear cache", use_container_width=True):
        st.session_state["_confirm_clear"] = True
    if col2.button("Details", use_container_width=True):
        st.session_state["_show_details"] = not st.session_state.get("_show_details", False)

    if st.session_state.get("_confirm_clear"):
        st.sidebar.warning("Remove all cached data files? Backups will be preserved.")
        c1, c2 = st.sidebar.columns(2)
        if c1.button("Yes, clear", use_container_width=True, type="primary"):
            cache.clear()
            st.session_state["_confirm_clear"] = False
            st.rerun()
        if c2.button("Cancel", use_container_width=True):
            st.session_state["_confirm_clear"] = False
            st.rerun()

    if st.session_state.get("_show_details"):
        with st.sidebar.expander("Manifest", expanded=True):
            st.json(manifest)

    st.sidebar.caption(f"Cache: `{cache.cache_dir()}`")


# ---------------------------------------------------------------------------
# Cached data accessors (thin wrappers for Streamlit's caching)
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def get_combined_cached(_cache_signature: str):
    """Return the canonical combined DataFrame.

    The ``_cache_signature`` argument is just a hash of the manifest --
    Streamlit invalidates the cache when it changes (i.e., when uploads
    happen).
    """
    return data.get_combined()


@st.cache_data(show_spinner=False)
def get_schedule_cached(_cache_signature: str):
    return data.load_schedule()


def cache_signature() -> str:
    """Stable string derived from manifest so cache invalidates on uploads."""
    import hashlib
    m = cache.load_manifest()
    return hashlib.sha256(repr(sorted(m.items())).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------


def main():
    render_sidebar()
    st.title("PAT Report Generator")
    st.caption(
        "Briefing across all loaded programs. Use the sidebar to navigate "
        "to per-course reports, sub-outcome lookups, and the full coverage view."
    )

    cached = cache.list_cached()
    loaded_progs = [p for p in N.PROGRAM_LABELS if p in cached]

    if not loaded_progs:
        st.info(
            ":arrow_left: Drop your PAT CSV exports into the sidebar to begin. "
            "Files are auto-detected by program (CE / CON / ENE) and cached "
            "on this machine so you only upload once per semester."
        )
        st.markdown("### What's next")
        st.markdown(
            "- **Course Report** -- per-course assessment summary with "
            "semester trends and below-threshold flags.\n"
            "- **Sub-Outcome Lookup** -- programs and sub-outcomes for a "
            "course (requires the Assessment Schedule workbook).\n"
            "- **Coverage Check** -- missing-data list per semester, "
            "year-over-year trend, and sub-outcome coverage heatmaps."
        )
        return

    from pat.analysis import briefing
    df = get_combined_cached(cache_signature())
    schedule = get_schedule_cached(cache_signature())
    inv = briefing.inventory(df, schedule=schedule)
    rc = briefing.recent_semester_coverage(df)
    bt = briefing.below_threshold_summary(df)

    # --- A. Inventory metrics ---
    st.subheader("Data inventory")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Programs", len(inv["programs"]))
    m2.metric("Courses", inv["courses"])
    m3.metric("Measurements", f"{inv['measurements']:,}")
    year_label = (
        f"{inv['year_min']}-{inv['year_max']}"
        if inv["year_min"] is not None else "-"
    )
    m4.metric("Year range", year_label)

    inv_cols = st.columns([3, 2])
    with inv_cols[0]:
        st.caption(
            "Most recent semester in data: **"
            + (inv["most_recent_semester"] or "(none)") + "**"
        )
    with inv_cols[1]:
        if inv["schedule_course_count"] is not None:
            st.caption(
                f"Assessment Schedule loaded ({inv['schedule_course_count']} courses)"
            )
        else:
            st.caption("Assessment Schedule: not loaded")

    st.divider()

    # --- B. Recent-semester coverage ---
    st.subheader("Recent semester coverage")
    if rc["semester"] is None:
        st.caption("(no semesters detected)")
    else:
        st.caption(f"For **{rc['semester']}**:")
        cov_cols = st.columns(len(rc["per_program"]) or 1)
        for col, row in zip(cov_cols, rc["per_program"]):
            with col:
                total = row["total"]
                pct = row["pct_assessed"] / 100.0 if total else 0.0
                label_color = "green" if pct >= 0.8 else (
                    "orange" if pct >= 0.5 else "red"
                )
                st.markdown(f"**{row['program']}**")
                st.progress(min(max(pct, 0.0), 1.0))
                st.markdown(
                    f":{label_color}[**{row['assessed']}** of {row['total']} "
                    f"assessed ({row['pct_assessed']:.0f}%)]"
                )
                if row["missing_courses"]:
                    with st.expander(
                        f"{row['missing']} missing course(s)", expanded=False
                    ):
                        for c in row["missing_courses"]:
                            st.markdown(f"- {c}")

    st.divider()

    # --- C. Below-threshold attention ---
    st.subheader(f"Below-threshold attention ({bt['year'] or '-'})")
    if bt["year"] is None:
        st.caption("(no data)")
    else:
        st.caption(
            "Measurements in the most recent year where student "
            "performance fell below the indicator threshold."
        )
        bt_cols = st.columns(len(bt["per_program"]) or 1)
        for col, row in zip(bt_cols, bt["per_program"]):
            with col:
                st.metric(
                    row["program"],
                    f"{row['below_count']}",
                    delta=(
                        None if row["total_count"] == 0
                        else f"of {row['total_count']} measured"
                    ),
                    delta_color="off",
                )
        if bt["top_items"]:
            st.markdown("**Largest gaps from indicator:**")
            for it in bt["top_items"]:
                st.markdown(
                    f"- **{it['course']}** ({it['program']}) sub-outcome "
                    f"**{it['suboutcome']}** in {it['semester']}: "
                    f"{it['performance']:.0f}% vs. indicator "
                    f"{it['indicator']:.0f}% (gap {it['gap']:.0f} pts)"
                )
        else:
            st.caption("(no below-threshold measurements in this year)")

    st.divider()
    st.caption(
        "Drill into the **Course Report**, **Sub-Outcome Lookup**, or "
        "**Coverage Check** pages via the sidebar."
    )


if __name__ == "__main__":
    main()
