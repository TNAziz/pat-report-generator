"""Assessment Schedule viewer.

Displays the planned ABET assessment schedule from the workbook's
"Assessment Schedule" sheet. Each row is a course; each column after
the first two is a semester (F23, S24, ...). Cells marked ``X`` mean
the course is scheduled for assessment in that semester.

When PAT data is also loaded, the page can optionally overlay actual
coverage so the user sees planned-vs-completed at a glance.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from Home import (
    cache_signature,
    get_combined_cached,
    get_schedule_cached,
    render_sidebar,
)
from pat import normalize as N


def _semester_label(code: str) -> str:
    """Map 'F23' / 'S24' -> 'Fall 2023' / 'Spring 2024'."""
    m = re.fullmatch(r"([FS])(\d{2})", str(code).strip())
    if not m:
        return str(code)
    season, yr = m.group(1), m.group(2)
    return f"{'Fall' if season == 'F' else 'Spring'} 20{yr}"


def _sort_semester_columns(cols):
    """Order F/S columns chronologically: F23, S24, F24, S25..."""
    def key(c):
        m = re.fullmatch(r"([FS])(\d{2})", str(c).strip())
        if not m:
            return (9999, str(c))
        season, yr = m.group(1), int(m.group(2))
        return (2000 + yr, 0 if season == "S" else 1)
    return sorted(cols, key=key)


def _planned_cell_status(val) -> str:
    """Return 'planned' if cell content marks the course as scheduled."""
    if pd.isna(val):
        return ""
    s = str(val).strip().lower()
    if s in ("x", "yes", "true", "1", "✓", "✔"):
        return "planned"
    return ""


def _actual_for(df, course: str, sem_label: str) -> str:
    """Return 'completed' / 'missing' / '' for the (course, semester) pair."""
    if df.empty:
        return ""
    rows = df[(df["course"].astype(str).str.strip() == course)
              & (df["semester"].astype(str).str.strip() == sem_label)]
    if rows.empty:
        return ""
    submitted = rows["submitter"].astype(str).str.strip() != ""
    if submitted.any():
        return "completed"
    return "missing"


def _render_schedule_table(planned: pd.DataFrame, df: pd.DataFrame, overlay: bool):
    """Build the styled HTML schedule table."""
    sem_cols = [c for c in planned.columns if c not in ("Offering", "Course")]
    sem_cols = _sort_semester_columns(sem_cols)
    cols = ["Course", "Offering"] + sem_cols

    css = """
    <style>
      table.sched { border-collapse: collapse; font-size: 10pt; background:#fff; color:#222; }
      table.sched th, table.sched td { border: 1px solid #ccc; padding: 4pt 8pt; text-align:center; color:#222; }
      table.sched th { background:#f0f0f0; font-weight: 600; color:#222; }
      table.sched th.course-col, table.sched td.course-col { text-align:left; min-width: 80pt; color:#222; }
      table.sched td.offer-col { color:#555; font-style: italic; }
      table.sched td.cell-planned { background:#e3f2fd; font-weight: 700; color:#0d47a1; }
      table.sched td.cell-completed { background:#c8e6c9; font-weight: 700; color:#1b5e20; }
      table.sched td.cell-missing { background:#fce6e6; font-weight: 700; color:#a00000; }
      table.sched td.cell-bonus { background:#fff3e0; font-weight: 700; color:#bf360c; }
      table.sched td.cell-empty { color:#bbb; }
    </style>
    """

    # Header
    head = "<tr>" + "".join(
        f'<th class="course-col">{c}</th>' if c == "Course"
        else f"<th>{_e(c if c == 'Offering' else _semester_label(c))}</th>"
        for c in cols
    ) + "</tr>"

    # Body
    body_rows = []
    for _, row in planned.iterrows():
        course = str(row.get("Course", "")).strip()
        offering = str(row.get("Offering", "")).strip()
        if not course:
            continue
        cells = [
            f'<td class="course-col"><strong>{_e(course)}</strong></td>',
            f'<td class="offer-col">{_e(offering)}</td>',
        ]
        for sem in sem_cols:
            planned_status = _planned_cell_status(row.get(sem))
            actual_status = (
                _actual_for(df, course, _semester_label(sem))
                if overlay and not df.empty else ""
            )
            if planned_status == "planned" and actual_status == "completed":
                cls, glyph = "cell-completed", "✓"
            elif planned_status == "planned" and actual_status == "missing":
                cls, glyph = "cell-missing", "!"
            elif planned_status == "planned":
                cls, glyph = "cell-planned", "X"
            elif actual_status == "completed":
                # Assessed but not planned -- "bonus" coverage.
                cls, glyph = "cell-bonus", "•"
            else:
                cls, glyph = "cell-empty", ""
            cells.append(f'<td class="{cls}">{glyph}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    table_html = (
        css
        + '<div style="overflow-x:auto"><table class="sched"><thead>'
        + head + "</thead><tbody>" + "".join(body_rows)
        + "</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def _e(s) -> str:
    import html
    return html.escape(str(s), quote=True)


def main():
    render_sidebar()
    st.title("Assessment Schedule")

    schedule = get_schedule_cached(cache_signature())
    if schedule is None:
        st.info(
            ":arrow_left: Upload the Assessment Schedule workbook in the "
            "sidebar to see the planned ABET assessment schedule."
        )
        return
    if schedule.planned is None or schedule.planned.empty:
        st.warning(
            "The Assessment Schedule workbook has no `Assessment Schedule` "
            "sheet. Add one with columns: Offering, Course, F23, S24, ..."
        )
        return

    st.caption(
        "Planned assessment schedule across the current ABET cycle. "
        "Cells marked **X** are scheduled. With PAT data loaded, the "
        "overlay shows completed assessments (✓ green) and missing "
        "ones (! red); courses assessed *outside* the plan show as "
        "**•** orange."
    )

    df = get_combined_cached(cache_signature())
    overlay = st.toggle(
        "Overlay actual coverage from PAT data",
        value=not df.empty,
        disabled=df.empty,
        help=(
            "Cross-references the planned schedule with submitted PAT "
            "data. Disabled until PAT CSVs are loaded."
        ),
    )

    _render_schedule_table(schedule.planned, df, overlay)

    # Legend.
    st.markdown("**Legend.**")
    legend_html = (
        '<table class="sched" style="margin-top:4pt">'
        '<tr><td class="cell-planned">X</td><td class="course-col">Planned only</td></tr>'
        '<tr><td class="cell-completed">✓</td><td class="course-col">Planned and completed</td></tr>'
        '<tr><td class="cell-missing">!</td><td class="course-col">Planned but data missing</td></tr>'
        '<tr><td class="cell-bonus">•</td><td class="course-col">Completed outside the plan</td></tr>'
        '<tr><td class="cell-empty"></td><td class="course-col">Not scheduled</td></tr>'
        '</table>'
    )
    st.markdown(legend_html, unsafe_allow_html=True)


main()
