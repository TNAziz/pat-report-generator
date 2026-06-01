# 03 — Data Model

Status: Draft v1
Owner: Tarek Aziz
Last updated: 2026-05-29

## 1. PAT raw CSV — input schema

Each program (CE, CON, ENE) exports one CSV from PAT's "Download RAW Data." Observed columns from `summaryReportCE_S20toS26_2026_05_29_03_05.csv`:

| Column (raw) | Type (observed) | Notes |
|---|---|---|
| `course` | str | **Often padded with hundreds of leading spaces.** Format: `"CE 282"`. |
| `suboutcome` | str or float | `"1.1"`, `"4.1"`. Sometimes float-typed by pandas. |
| `semester` | str | `"Spring 2020"`, `"Fall 2024"`. |
| `assigned-to` | str | Instructor: `"Aziz, Tarek"`. May be blank/`null`. |
| `submitted-by` | str | Submitter: `"Aziz, Tarek"`. **Blank = assessment not turned in.** |
| `performance-indicator` | int or str | Threshold percent: `70`, `"70%"`. |
| `threshold` | int | Cut score on the rubric, e.g., `4`. |
| `scale` | int | Max rubric score, e.g., `6`, `10`. |
| `performance` | int or str | Measured percent: `86`, `"86%"`, sometimes `nan`. |
| `score-data` | str | Space-separated raw scores: `"6 2 6 6 4 ..."`. |
| `scores_meeting_threshold` | int | Count of students at/above threshold. |
| `total_scores` | int | n. |
| `measurement-result-updated` | str (date) | `"05/15/2020"`. |
| `comments` | str | Free-text faculty comments. May be empty. |
| `actions-taken` | str | Free-text actions. May be empty. |
| `measure-description` | str | What the measure assessed: `"Final Exam Q15"`. |

**Known artifacts requiring cleaning:**

- Massive leading whitespace in `course` (observed in CE 464 rows: 200+ space chars).
- `"null"` and `""` used interchangeably for missing values.
- `performance` returned as the literal string `"nan"` in some rows.
- `suboutcome` mixed types (`float` from `1.1`, `str` from `"4.1"`).
- Column names with hyphens (`assigned-to`) and underscores (`total_scores`) — inconsistent.

## 2. Canonical cleaned schema

After `pat.normalize.clean_dataframe`, the combined frame across all programs has the following schema. This is the **only** schema that analysis code should depend on.

| Column | Type | Notes |
|---|---|---|
| `program` | category | `"CE"` \| `"CON"` \| `"ENE"`. Added during combination. |
| `course` | str | Whitespace stripped. Format: `"CE 282"`. |
| `course_key` | str | Normalized lookup key. Format: `"CE282"` (no space, uppercase). |
| `suboutcome` | str | Always string. `"1.1"`, `"4.1"`. |
| `semester` | str | Human label: `"Spring 2020"`. |
| `semester_year` | int | `2020`. |
| `semester_season` | category | `"S"` \| `"F"`. |
| `semester_sort_key` | int | `year * 2 + (1 if season=='F' else 0)`. For ordering. |
| `instructor` | str | From `assigned-to`. Empty string if missing. |
| `submitter` | str | From `submitted-by`. **Empty string = no data submitted.** |
| `performance_indicator` | float | Percent as 0–100. `None` if unparseable. |
| `threshold` | int | Rubric cut score. |
| `scale` | int | Rubric max. |
| `performance` | float | Percent as 0–100. `None` if missing/unparseable. |
| `score_data` | str | Raw scores, unchanged. |
| `scores_meeting_threshold` | int | |
| `total_scores` | int | n. |
| `measurement_date` | date | Parsed from `measurement-result-updated`. |
| `comments` | str | Empty string if missing. |
| `actions_taken` | str | Empty string if missing. |
| `measure_description` | str | |

**Type guarantees:**

- No string `"null"` values anywhere.
- No leading/trailing whitespace in any string column.
- `performance` and `performance_indicator` are numeric or `None`, never strings.

## 3. Column rename map (raw → canonical)

```python
RAW_TO_CANONICAL = {
    "course": "course",
    "suboutcome": "suboutcome",
    "semester": "semester",
    "assigned-to": "instructor",
    "submitted-by": "submitter",
    "performance-indicator": "performance_indicator",
    "threshold": "threshold",
    "scale": "scale",
    "performance": "performance",
    "score-data": "score_data",
    "scores_meeting_threshold": "scores_meeting_threshold",
    "total_scores": "total_scores",
    "measurement-result-updated": "measurement_date",
    "comments": "comments",
    "actions-taken": "actions_taken",
    "measure-description": "measure_description",
}
```

Column matching is case-insensitive and tolerant of `-` vs `_`. If a raw column is missing, `ingest.read_csv` raises with a clear listing of expected vs. found columns.

## 4. Assessment Schedule workbook

A separate `.xlsx` file used only by the Sub-Outcome Lookup tool.

### Sheet `CourseSubOutcomes`

| Column | Type | Notes |
|---|---|---|
| `Course` | str | `"CE 488"`. |
| `Programs` | str | `/`-, `,`-, or `;`-separated list: `"CE/ENE"`. |
| `1.1`, `1.2`, `2.1`, ... | str | Cell value `"X"` (also accept `"x"`, `"✓"`, `"1"`, `True`) marks the course as assessing that sub-outcome. Otherwise blank. |

The set of sub-outcome columns is determined dynamically — any column whose header matches the regex `^\d+\.\d+$` is treated as a sub-outcome.

### Sheet `OutcomeDescriptions`

| Column | Type | Notes |
|---|---|---|
| `Outcomes` | str | `"1.1"`. |
| `Description` | str | `"Formulate the solution to engineering problems."` |

## 5. Report intermediate representation

Defined in `pat/render/model.py`. All analysis functions return one of these; all renderers consume one.

```python
from dataclasses import dataclass, field
from datetime import date

@dataclass
class SummaryRow:
    semester: str                # "Spring 2020"
    suboutcome: str              # "1.1"
    performance_indicator: float | None
    performance: float | None
    below_threshold: bool        # True if performance < indicator

@dataclass
class MeasureDetail:
    suboutcome: str
    measure_description: str
    performance_indicator: float | None
    performance: float | None
    n: int | None
    comments: str
    actions_taken: str

@dataclass
class SemesterSection:
    semester: str
    instructor: str
    measures: list[MeasureDetail]

@dataclass
class ProgramSection:
    program_code: str            # "CE"
    program_label: str           # "Civil Engineering"
    summary: list[SummaryRow]
    semesters: list[SemesterSection]

@dataclass
class Report:
    title: str                   # "CE 282"
    subtitle: str | None         # "Spring 2020 – Spring 2026"
    generated_on: date
    sections: list[ProgramSection]
    # Optional flat tables for the simpler tools:
    tables: list["NamedTable"] = field(default_factory=list)
    # Optional narrative paragraphs (for future LLM-generated text):
    narrative: list["NarrativeBlock"] = field(default_factory=list)

@dataclass
class NamedTable:
    title: str
    columns: list[str]
    rows: list[list[str]]
    footnote: str | None = None

@dataclass
class NarrativeBlock:
    heading: str | None
    body_markdown: str
```

The Sub-Outcome Lookup and Coverage Check tools produce reports with `sections=[]` and content in `tables` and `narrative` instead.

## 6. Program code reference

```python
PROGRAM_LABELS = {
    "CE":  "Civil Engineering",
    "ENE": "Environmental Engineering",
    "CON": "Construction Engineering",
}
```

Extending to a new program means adding one entry. Tools iterate over `PROGRAM_LABELS.keys()` rather than hard-coding.

## 7. Cache file layout

```
<cache_dir>/
├── pat_ce.csv              # Active CE export
├── pat_ce.csv.bak          # Previous CE export (single backup)
├── pat_con.csv
├── pat_con.csv.bak
├── pat_ene.csv
├── pat_ene.csv.bak
├── assessment_schedule.xlsx
├── assessment_schedule.xlsx.bak
└── manifest.json           # { program: { original_name, uploaded_at, sha256 }, ... }
```

The manifest is read on startup to populate sidebar status (e.g., "CE: loaded, uploaded 2026-05-29, file `summaryReportCE_S20toS26_2026_05_29_03_05.csv`").

## 8. Invariants enforced at ingestion

The following invariants are checked by `pat.ingest` and `pat.normalize` and must hold before data reaches any analysis function. Violations raise `IngestError` with a remediation message.

1. All required raw columns are present (after the rename map is applied).
2. After cleaning, `course` contains no string with leading/trailing whitespace.
3. After cleaning, `course_key` matches the regex `^[A-Z]+\d+$`.
4. `semester_year` is an integer in `[2000, 2100]`.
5. `program` is one of the keys in `PROGRAM_LABELS`.
6. `performance_indicator` and `performance`, when not None, are floats in `[0, 100]`.
