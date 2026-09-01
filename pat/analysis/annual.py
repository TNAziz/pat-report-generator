"""Annual Assessment analysis.

Builds the report that feeds NC State's Anthology assessment write-up:
one section per program, then per ABET outcome, then per sub-outcome
under it. The shape mirrors the narrative document faculty actually
submit, whose three parts are *Findings*, *Analysis of Findings*, and
*Actions Taken to Address Areas for Improvement*.

For each sub-outcome the report carries

* the sub-outcome's definition (from the Assessment Schedule's
  ``OutcomeDescriptions`` sheet, when a schedule is supplied),
* a statistics line -- courses contributing, measures, total student
  assessments, and the weighted percentage meeting the instructor's
  threshold, and
* one row per underlying measurement, unaggregated -- including the
  instructor's own goal for that measure, since the department sets no
  universal benchmark and a result is judged against the goal beside it,
  not against a fixed 50% or 70%.

Each outcome then closes with an **Actions Taken** roll-up: every
corrective action recorded for that outcome, grouped by course, plus an
explicit list of measures where no action was recorded.

The weighted percentage is ``sum(scores_meeting_threshold) /
sum(total_scores)`` across the measures in the group -- *not* the mean of
the per-measure ``performance`` values, which would weight a 1-student
measure the same as a 77-student one. This reproduces the figures in the
F24/S25 CE report (e.g. sub-outcome 1.1: 189 of 262 = 72.1%, quoted
there as "about 72 %").

Program order follows :data:`pat.normalize.PROGRAM_LABELS` (CE, ENE,
CON); outcomes and sub-outcomes sort numerically; rows within a
sub-outcome run chronologically. Groups with no matching rows are
omitted.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .. import normalize as N
from ..ingest import _sort_outcome_codes
from ..render.model import NamedTable, NarrativeBlock, Report


#: The readable table: what goes on screen and into the md/Word/PDF
#: downloads.
_COLUMNS: List[str] = [
    "Course", "Semester", "Instructor", "Goal", "Performance", "N",
    "Comment", "Actions Taken",
]

#: Explains the Goal column wherever a measurement table appears. The
#: department sets no universal benchmark -- each instructor picks the
#: share of students expected to clear their own measure's cut score, so
#: a 55% result against a 50% goal is a pass and a 74% result against an
#: 80% goal is not. Without this the Goal and Performance columns invite
#: exactly the wrong comparison.
TABLE_FOOTNOTE = (
    "Goal is the percentage of students the instructor expected to meet "
    "that measure's own threshold; it is set per measure, not "
    "department-wide. Performance is the percentage who did."
)

#: The full table, for the LLM drafting packet. The narrative describes
#: what each measure was and quotes raw counts ("5 of 14 students met the
#: 13-point threshold on an 18-point scale"), which needs PAT's
#: measure-description, threshold, scale and scores_meeting_threshold --
#: too dense for a printed table, essential for drafting from.
_DETAIL_COLUMNS: List[str] = [
    "Course", "Semester", "Instructor", "Measure", "Measure threshold",
    "Goal", "Performance", "Met / N", "Comment", "Actions Taken",
]

_NULLISH_LOWER = {"", "nan", "none", "null", "na"}

#: Placeholder shown when a measurement records no corrective action.
NO_ACTION_TEXT = "None recorded"


# ---------------------------------------------------------------------------
# Cell formatting
# ---------------------------------------------------------------------------

def _format_pct(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and pd.isna(value):
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _format_int(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and pd.isna(value):
        return "—"
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "—"


def _clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value).strip()
    if s.lower() in _NULLISH_LOWER:
        return ""
    return s


def _format_actions(value) -> str:
    """Corrective-action text, or an explicit placeholder when blank.

    PAT leaves ``actions-taken`` empty on roughly a fifth of rows. An
    empty cell is indistinguishable from a rendering glitch in the
    exported report, so say so instead.
    """
    return _clean_text(value) or NO_ACTION_TEXT


def _format_threshold(threshold, scale) -> str:
    """The measure's own cut score, e.g. ``"11 of 16 points"``."""
    lo, hi = _format_int(threshold), _format_int(scale)
    if lo == "—" and hi == "—":
        return "—"
    if hi == "—":
        return f"{lo} points"
    if lo == "—":
        return f"out of {hi} points"
    return f"{lo} of {hi} points"


def _format_met(met, total) -> str:
    """Students meeting the threshold over students assessed."""
    a, b = _format_int(met), _format_int(total)
    if a == "—" and b == "—":
        return "—"
    return f"{a} of {b}"


def _inline(text: str) -> str:
    """Collapse whitespace so long text survives inside a Markdown bullet.

    A raw newline in a list item ends the item; collapsing runs of
    whitespace keeps the full text on one logical line without dropping
    any of it.
    """
    return " ".join(str(text).split())


# ---------------------------------------------------------------------------
# Outcome / sub-outcome helpers
# ---------------------------------------------------------------------------

def outcome_of(code: str) -> str:
    """Return the outcome number for a sub-outcome code (``"1.10"`` -> ``"1"``)."""
    return str(code).strip().split(".")[0]


def _outcome_sort_key(value: str):
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def available_outcomes(df: pd.DataFrame) -> List[str]:
    """Outcome numbers present in ``df``, numerically sorted."""
    if df is None or df.empty or "suboutcome" not in df.columns:
        return []
    codes = df["suboutcome"].dropna().astype(str).map(N.normalize_suboutcome)
    outs = {outcome_of(c) for c in codes if c}
    return sorted((o for o in outs if o), key=_outcome_sort_key)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def group_stats(group: pd.DataFrame) -> Dict[str, object]:
    """Aggregate one sub-outcome group.

    Returns ``courses``, ``measures``, ``n_assessments``, ``n_meeting``,
    ``weighted_pct`` (None when no student counts exist), and
    ``measures_without_counts``.
    """
    if "total_scores" in group.columns:
        counted = group.dropna(subset=["total_scores"])
    else:
        counted = group.iloc[0:0]
    total = float(counted["total_scores"].sum()) if not counted.empty else 0.0
    met = 0.0
    if not counted.empty and "scores_meeting_threshold" in counted.columns:
        met = float(counted["scores_meeting_threshold"].fillna(0).sum())
    return {
        "courses": int(group["course"].nunique()) if "course" in group.columns else 0,
        "measures": int(len(group)),
        "n_assessments": int(total),
        "n_meeting": int(met),
        "weighted_pct": (met / total * 100.0) if total > 0 else None,
        "measures_without_counts": int(len(group) - len(counted)),
    }


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _stats_sentence(stats: Dict[str, object]) -> str:
    parts = [
        _plural(int(stats["courses"]), "course"),
        _plural(int(stats["measures"]), "measure"),
    ]
    pct = stats["weighted_pct"]
    if pct is None:
        return (
            " · ".join(parts + ["no student counts recorded"])
            + ". No weighted average can be computed for this sub-outcome."
        )
    parts.append(f"N = {stats['n_assessments']} student assessments")
    sentence = " · ".join(parts) + "."
    sentence += (
        f" **{pct:.1f}%** met the instructor-defined threshold "
        f"({stats['n_meeting']} of {stats['n_assessments']})."
    )
    missing = int(stats["measures_without_counts"])
    if missing:
        sentence += (
            f" {_plural(missing, 'measure')} reported no student counts and "
            f"{'is' if missing == 1 else 'are'} excluded from that average."
        )
    return sentence


# ---------------------------------------------------------------------------
# Actions roll-up
# ---------------------------------------------------------------------------

def _actions_rollup_markdown(frame: pd.DataFrame) -> str:
    """Bullet list of every corrective action in ``frame``, grouped by course.

    Identical action text repeated across a course's measures collapses
    to one bullet listing each context it came from, which is how the
    narrative's "Actions Taken" section reads.
    """
    recorded: Dict[Tuple[str, str], List[str]] = {}
    missing: List[str] = []

    for _, r in frame.iterrows():
        course = _clean_text(r.get("course")) or "(course not recorded)"
        context = ", ".join(
            p for p in (_clean_text(r.get("suboutcome")),
                        _clean_text(r.get("semester"))) if p
        )
        action = _clean_text(r.get("actions_taken"))
        if action:
            recorded.setdefault((course, _inline(action)), []).append(context)
        else:
            missing.append(f"{course} ({context})" if context else course)

    def _sort_key(key: Tuple[str, str]):
        contexts = sorted(dict.fromkeys(c for c in recorded[key] if c))
        return (key[0], contexts[0] if contexts else "", key[1])

    lines: List[str] = []
    for key in sorted(recorded, key=_sort_key):
        course, action = key
        contexts = sorted(dict.fromkeys(c for c in recorded[key] if c))
        label = f"**{course}**"
        if contexts:
            label += f" ({'; '.join(contexts)})"
        lines.append(f"* {label} — {action}")

    if not lines:
        lines.append("_No corrective actions were recorded for this outcome._")

    if missing:
        lines.append("")
        lines.append(
            "_No corrective action recorded: "
            + "; ".join(sorted(dict.fromkeys(missing)))
            + "._"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _row(r, detail: bool) -> List[str]:
    """One table row, in either the readable or the full column set."""
    course = _clean_text(r.get("course"))
    semester = _clean_text(r.get("semester"))
    instructor = _clean_text(r.get("instructor"))
    performance = _format_pct(r.get("performance"))
    comments = _clean_text(r.get("comments"))
    actions = _format_actions(r.get("actions_taken"))
    goal = _format_pct(r.get("performance_indicator"))
    if not detail:
        return [
            course, semester, instructor, goal, performance,
            _format_int(r.get("total_scores")), comments, actions,
        ]
    return [
        course,
        semester,
        instructor,
        _clean_text(r.get("measure_description")),
        _format_threshold(r.get("threshold"), r.get("scale")),
        goal,
        performance,
        _format_met(r.get("scores_meeting_threshold"), r.get("total_scores")),
        comments,
        actions,
    ]


def _normalized_codes(values: Iterable) -> List[str]:
    out: List[str] = []
    for v in values or ():
        if v is None:
            continue
        code = N.normalize_suboutcome(v)
        if code:
            out.append(code)
    return list(dict.fromkeys(out))


def _subtitle(
    programs: Sequence[str],
    semesters: Sequence[str],
    outcomes: Sequence[str],
) -> Optional[str]:
    parts: List[str] = []
    if programs:
        parts.append(", ".join(programs))
    if semesters:
        parts.append(", ".join(semesters))
    if outcomes:
        label = "Outcome" if len(outcomes) == 1 else "Outcomes"
        parts.append(f"{label} {', '.join(outcomes)}")
    return " — ".join(parts) if parts else None


def build(
    df: pd.DataFrame,
    semesters: Iterable[str],
    outcomes: Optional[Iterable] = None,
    suboutcomes: Optional[Iterable] = None,
    programs: Optional[Iterable[str]] = None,
    descriptions: Optional[Dict[str, str]] = None,
    detail: bool = False,
    generated_on: Optional[date] = None,
) -> Report:
    """Build the Annual Assessment report.

    Parameters
    ----------
    df : pd.DataFrame
        A canonical combined frame (as returned by ``data.get_combined``).
    semesters : iterable of str
        Semester labels forming the assessment cycle (e.g.
        ``["Fall 2024", "Spring 2025"]``). Empty yields a prompt report.
    outcomes : iterable, optional
        Outcome numbers to include (``["1", "3"]`` or ``[1, 3]``). Every
        sub-outcome under each is included.
    suboutcomes : iterable of str, optional
        Explicit sub-outcome codes. When given these are used verbatim
        and ``outcomes`` is ignored -- for callers wanting a narrower
        slice than a whole outcome.
    programs : iterable of str, optional
        Program codes to include. Defaults to every program present in
        the filtered data.
    descriptions : dict, optional
        ``{sub-outcome code: description}``, normally
        ``schedule.descriptions``. Missing entries are omitted.
    detail : bool
        When True the measurement tables carry the full column set
        (:data:`_DETAIL_COLUMNS`) -- measure description, the measure's
        own threshold and scale, the instructor's goal, and students
        meeting threshold over students assessed. Used for the LLM
        drafting packet, where those fields are what let the narrative
        say what was measured; the on-screen and printed reports use the
        readable seven-column set.
    generated_on : date, optional
        Report generation date; defaults to today.

    Returns
    -------
    Report
        ``body`` carries the ordered narrative/table sequence. When
        nothing is selected, or nothing matches, ``narrative`` carries a
        single explanatory block instead.
    """
    if generated_on is None:
        generated_on = date.today()
    descriptions = descriptions or {}

    sems = [str(s).strip() for s in semesters if s is not None and str(s).strip()]
    picked_subs = _normalized_codes(suboutcomes or ())
    picked_outcomes = list(dict.fromkeys(
        str(o).strip() for o in (outcomes or ()) if str(o).strip()
    ))
    wanted_programs = [str(p).strip() for p in (programs or ()) if str(p).strip()]

    title = "Annual Assessment"
    subtitle = _subtitle(
        wanted_programs,
        sems,
        _sort_outcome_codes(picked_subs) if picked_subs
        else sorted(picked_outcomes, key=_outcome_sort_key),
    )

    def _narrative_report(message: str) -> Report:
        return Report(
            title=title,
            subtitle=subtitle,
            generated_on=generated_on,
            narrative=[NarrativeBlock(heading=None, body_markdown=message)],
        )

    if df is None or df.empty:
        return _narrative_report(
            "_No PAT data is loaded. Upload program CSVs in the sidebar._"
        )
    if not sems or not (picked_subs or picked_outcomes):
        return _narrative_report(
            "_Pick at least one semester and one outcome to generate the report._"
        )

    working = df.copy()
    working["semester"] = working["semester"].astype(str).str.strip()
    working["suboutcome"] = working["suboutcome"].map(N.normalize_suboutcome)
    working = working[working["semester"].isin(sems)]

    if picked_subs:
        working = working[working["suboutcome"].isin(picked_subs)]
    else:
        working = working[working["suboutcome"].map(
            lambda c: bool(c) and outcome_of(c) in picked_outcomes
        )]

    if working.empty:
        return _narrative_report(
            "_No measurements matched the selected semesters and outcomes._"
        )

    present_programs = [
        p for p in N.PROGRAM_LABELS
        if (not wanted_programs or p in wanted_programs)
        and not working[working["program"].astype(str) == p].empty
    ]
    multi_program = len(present_programs) > 1

    body: List[object] = []
    for prog_code in present_programs:
        prog_df = working[working["program"].astype(str) == prog_code]

        if multi_program:
            body.append(NarrativeBlock(
                heading=f"{N.PROGRAM_LABELS[prog_code]} ({prog_code})",
                body_markdown="",
                level=1,
            ))

        prog_outcomes = sorted(
            {outcome_of(c) for c in prog_df["suboutcome"] if c},
            key=_outcome_sort_key,
        )
        for outcome in prog_outcomes:
            out_df = prog_df[prog_df["suboutcome"].map(
                lambda c: bool(c) and outcome_of(c) == outcome
            )]
            if out_df.empty:
                continue
            codes = _sort_outcome_codes(
                list(dict.fromkeys(c for c in out_df["suboutcome"] if c))
            )

            defs = [
                f"* **{code}** — {descriptions[code]}"
                for code in codes if descriptions.get(code)
            ]
            intro = (
                "Sub-outcomes assessed in this cycle:\n\n" + "\n".join(defs)
                if defs else
                "_Sub-outcome definitions are unavailable — load an "
                "Assessment Schedule workbook in the sidebar to include them._"
            )
            body.append(NarrativeBlock(
                heading=(f"Outcome {outcome}" if multi_program
                         else f"{prog_code} — Outcome {outcome}"),
                body_markdown=intro,
                level=2 if multi_program else 1,
            ))

            sub_level = 3 if multi_program else 2
            for code in codes:
                group = out_df[out_df["suboutcome"] == code]
                if group.empty:
                    continue
                sort_cols = [
                    c for c in ("semester_sort_key", "course")
                    if c in group.columns
                ]
                if sort_cols:
                    group = group.sort_values(sort_cols, kind="stable")

                lines: List[str] = []
                definition = descriptions.get(code)
                if definition:
                    lines.append(f"_{definition}_")
                    lines.append("")
                lines.append(_stats_sentence(group_stats(group)))
                body.append(NarrativeBlock(
                    heading=f"Sub-outcome {code}",
                    body_markdown="\n".join(lines),
                    level=sub_level,
                ))

                rows = [_row(r, detail) for _, r in group.iterrows()]
                body.append(NamedTable(
                    title="",
                    columns=list(_DETAIL_COLUMNS if detail else _COLUMNS),
                    rows=rows,
                    footnote=TABLE_FOOTNOTE,
                ))

            body.append(NarrativeBlock(
                heading=f"Actions Taken — Outcome {outcome}",
                body_markdown=_actions_rollup_markdown(out_df),
                level=sub_level,
            ))

    if not body:
        return _narrative_report(
            "_No measurements matched the selected semesters and outcomes._"
        )

    return Report(
        title=title,
        subtitle=subtitle,
        generated_on=generated_on,
        body=body,
    )
