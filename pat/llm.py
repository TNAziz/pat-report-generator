"""Drafting packet: the LLM input for an annual assessment narrative.

This module builds a **single self-contained Markdown document** that is
both the prompt handed to an LLM and the archival record of what that
LLM was given. Nothing here calls an API: the packet is written to disk,
the author reviews it, pastes it into whatever assistant they use, and
keeps the file. One artifact, so the draft can always be audited against
exactly the input that produced it.

Layout of the packet:

1. the task,
2. the house style and required section structure, distilled from the
   program's previous Anthology submissions,
3. the rules for using the data (what may not be invented, how the
   aggregate figures are defined),
4. provenance -- the selection, the source exports with their hashes and
   upload times, row counts, and a fingerprint of the data section, and
5. the data itself, which is the rendered Annual Assessment report.

The fingerprint is a SHA-256 of section 5. Re-running the packet later
and comparing fingerprints answers "was this draft written from this
data, or has the export changed underneath it?" -- which is the question
that matters when a reviewer asks where a number came from.

No Streamlit imports (enforced by ``scripts/check_imports.py``); no API
keys, no network.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Dict, List, Mapping, Optional, Sequence

from .render.model import NamedTable, Report


PACKET_TITLE = "Annual assessment drafting packet"


TASK = """\
Draft the program's annual assessment narrative from the data in
**Section 5** of this packet.

Produce one document per (program, outcome) pair present in the data. If
Section 5 covers three programs and two outcomes each, that is six
documents. Title each one `<PROGRAM> Assessment Report for Outcome <n>`.

Write the prose only. Do not restate the tables.\
"""


#: The structure and voice of the program's previous Anthology
#: submissions. Edit this text to change the house style; it travels
#: inside the packet, so the packet always records the style it asked for.
STYLE = """\
Each document has three top-level sections, in this order and under
these exact headings:

**Findings.** Opens with a subsection *Outcome and sub-outcome
definitions* stating what the outcome addresses and defining each
sub-outcome verbatim from the data. Then one subsection per sub-outcome,
titled *Student performance for sub-outcome X.Y*, which gives the number
of contributing courses, the total number of individual assessments, and
the aggregate percentage meeting threshold, then walks the courses one by
one -- course number and title, semester, what the measure was, the
counts, and what the faculty comment says students struggled with.
Closes with a subsection *Rubrics and performance indicators* describing
how thresholds were set and what the rubrics rewarded.

**Analysis of Findings.** Opens with *Baselines and evaluation criteria*,
which states that the program sets instructor-defined thresholds per
measure rather than one universal benchmark, so success is judged
contextually. Then *Strengths* and *Areas for improvement*, each drawing
on the disaggregated per-course data rather than the aggregate -- name
the courses that drive each conclusion, and say what pattern the data
supports (for example, that scaffolded multi-problem homework outperforms
single exam questions).

**Actions Taken to Address Areas for Improvement.** What faculty are
actually doing, course by course, drawn from the Actions Taken column and
the per-outcome roll-up. Tie each action to the finding it answers.
Distinguish courses that are changing something from courses continuing
a practice that already works. Close by noting that effectiveness will be
re-evaluated in the next assessment cycle.

Voice and mechanics: third person, no first person. Past tense for what
happened, present or future tense for planned actions. Bold course codes
on first mention in a bullet or sentence. Give counts as "X of Y
students met the threshold" and percentages with a percent sign. Prefer
"about 72 %" to a spuriously precise figure. Roughly 700-1200 words per
outcome. British or American spelling is fine, but be consistent.\
"""


#: Constraints that keep the draft auditable against Section 5.
RULES = """\
1. **Section 5 is the only source of facts.** Every number, course code,
   semester, instructor name, and quoted concern must appear there. If
   something needed for a sentence is not in Section 5, leave the
   sentence out rather than estimating.
2. **Use the aggregate percentages as given.** Each sub-outcome's
   statistics line already reports the weighted figure --
   `sum(students meeting threshold) / sum(students assessed)` across its
   measures. Do not recompute it by averaging the per-row Performance
   column: that would weight a 1-student measure the same as a
   77-student one.
3. **What the data columns mean.**
   - *Measure* — the assignment or exam question the instructor used.
   - *Measure threshold* — that measure's own cut score for one student,
     e.g. "11 of 16 points".
   - *Goal* — the share of students the instructor expected to clear that
     threshold. It is set per measure by the instructor, not
     department-wide: 50% in one course and 80% in another. Judge every
     result against the goal on its own row. A measure at 55% against a
     50% goal was met; one at 74% against an 80% goal was not.
   - *Performance* — PAT's percentage of students who did clear it. It is
     not an average score.
   - *Met / N* — the raw counts behind that percentage, e.g. "28 of 57".
     Prefer these counts to the percentage when writing about a single
     measure.
4. **A measure showing `—`** recorded nothing for that field. A `—` in
   *Met / N* means no student counts. It is
   excluded from the aggregate; do not fold it into any count, and say it
   had no counts recorded if it is worth mentioning at all.
5. **`None recorded` under Actions Taken means no action was recorded.**
   Never invent one, and never soften it into "the instructor plans to
   monitor". Naming the measures with no recorded action is useful --
   that gap is itself a finding.
6. **Do not merge programs.** Each document covers one program's rows
   only, even where two programs share a course number.
7. **Attribute concerns, don't generalize them.** "Students in CE 373
   struggled with balancing chemical equations" is supported; "students
   struggle with chemistry" is not.
8. **Say when the data is thin.** A sub-outcome carried by one
   1-student measure should be described as such, not reported as a
   percentage with no caveat.\
"""


def fingerprint(text: str) -> str:
    """SHA-256 of the data section, for matching a draft to its input."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _count_rows(report: Report) -> Dict[str, int]:
    """Measurement rows and distinct courses across the report's tables."""
    tables: List[NamedTable] = [
        item for item in report.body if isinstance(item, NamedTable)
    ] or list(report.tables)
    rows = 0
    courses = set()
    for table in tables:
        rows += len(table.rows)
        for row in table.rows:
            if row:
                courses.add(row[0])
    return {"measurements": rows, "courses": len(courses), "tables": len(tables)}


def _format_selection(selection: Optional[Mapping[str, Sequence[str]]]) -> List[str]:
    if not selection:
        return []
    lines = []
    for label, values in selection.items():
        picked = [str(v) for v in (values or ()) if str(v).strip()]
        lines.append(f"- {label}: {', '.join(picked) if picked else 'all'}")
    return lines


def _format_sources(sources: Optional[Mapping[str, Mapping]]) -> List[str]:
    """One line per cached upload: name, when, hash prefix, size."""
    if not sources:
        return ["- (no upload manifest available)"]
    lines = []
    for slot in sorted(sources):
        entry = sources[slot] or {}
        name = entry.get("original_name", "?")
        when = entry.get("uploaded_at", "?")
        digest = str(entry.get("sha256", ""))[:12] or "?"
        size = entry.get("size_bytes")
        size_text = f", {int(size):,} bytes" if isinstance(size, (int, float)) else ""
        lines.append(f"- `{slot}` — {name}, uploaded {when}, sha256 `{digest}…`{size_text}")
    return lines


def drafting_packet(
    report: Report,
    data_markdown: str,
    *,
    selection: Optional[Mapping[str, Sequence[str]]] = None,
    sources: Optional[Mapping[str, Mapping]] = None,
    notes: Optional[Sequence[str]] = None,
    task: str = TASK,
    style: str = STYLE,
    rules: str = RULES,
    generated_on: Optional[date] = None,
) -> str:
    """Assemble the drafting packet as one Markdown document.

    Parameters
    ----------
    report : Report
        The Annual Assessment report, used for the row and course counts
        that go in the provenance block.
    data_markdown : str
        The same report rendered to Markdown. Passed in rather than
        re-rendered here so the packet embeds byte-for-byte what the
        Markdown download contains, and the fingerprint covers exactly
        that text.
    selection : mapping, optional
        Filter labels to picked values, e.g.
        ``{"Programs": ["CE"], "Semesters": [...], "Outcomes": ["1"]}``.
    sources : mapping, optional
        The upload manifest: ``{slot: {original_name, uploaded_at,
        sha256, size_bytes}}``.
    notes : sequence of str, optional
        Extra provenance lines (e.g. a caveat about late submissions).
    task, style, rules : str
        Overridable prompt sections. Defaults are the module constants.
    generated_on : date, optional
        Defaults to today.

    Returns
    -------
    str
        The packet. Write it to a ``.md`` file and keep it with the draft.
    """
    if generated_on is None:
        generated_on = date.today()

    counts = _count_rows(report)
    digest = fingerprint(data_markdown)

    parts: List[str] = [
        f"# {PACKET_TITLE}",
        "",
        "This document is both the prompt and the record. Sections 1-4 say "
        "what to write and where the data came from; Section 5 is the data. "
        "Keep the file alongside the finished draft so any figure in the "
        "narrative can be traced back to its input.",
        "",
        "## 1. Task",
        "",
        task,
        "",
        "## 2. House style and required structure",
        "",
        style,
        "",
        "## 3. Rules for using the data",
        "",
        rules,
        "",
        "## 4. Provenance",
        "",
        f"- Packet generated: {generated_on.strftime('%B %d, %Y')}",
    ]
    parts.extend(_format_selection(selection))
    parts.append(
        f"- Data included: {counts['measurements']} measurement rows across "
        f"{counts['courses']} courses, in {counts['tables']} sub-outcome tables"
    )
    parts.append("- Source exports:")
    parts.extend(f"  {line}" for line in _format_sources(sources))
    for note in (notes or ()):
        parts.append(f"- {note}")
    parts.extend([
        f"- Data fingerprint (SHA-256 of Section 5): `{digest}`",
        "",
        "## 5. Data",
        "",
        data_markdown.strip(),
        "",
    ])
    return "\n".join(parts)
