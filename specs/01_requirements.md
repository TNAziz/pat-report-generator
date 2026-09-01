# 01 — Requirements

Status: Draft v1
Owner: Tarek Aziz
Last updated: 2026-05-29

## 1. Purpose

A local-first Streamlit application that ingests raw exports from NC State's Program Assessment Tool (PAT) and produces well-formatted, ABET-ready reports for the CCEE department's three undergraduate programs: Civil Engineering (CE), Environmental Engineering (ENE), and Construction Engineering (CON).

The application replaces an existing Jupyter notebook workflow that is Colab-bound, prompt-driven, and not shareable.

## 2. Users

Primary: ABET coordinator (the spec author) — runs the tool each semester after downloading fresh PAT exports.

Secondary: faculty colleagues at NC State CCEE — may install and run the tool on their own machines to pull reports for their own courses.

Future: department chair, ABET self-study writers, accreditation reviewers (read-only consumers of generated reports).

## 3. Functional requirements

Each requirement is numbered for traceability to verification tests in `05_verification.md`.

### Data ingestion

**R1.** The app accepts three CSV files via drag-and-drop, one per program (CE, CON, ENE), exported from PAT's "Download RAW Data" feature.

**R2.** The app automatically identifies which program each uploaded CSV belongs to, using filename patterns and/or content inspection. If ambiguous, the user is prompted to assign manually.

**R3.** The app cleans known PAT artifacts on ingestion, including but not limited to: leading/trailing whitespace padding in course-code strings (which can run hundreds of characters), inconsistent semester labels, and `"null"` string values that should be treated as missing.

**R4.** The app normalizes course codes so that variants like `"CE 282"`, `"CE282"`, `"ce-282"`, and `"  CE 282  "` resolve to a single canonical form.

**R5.** The app combines the three program CSVs into a single canonical in-memory table with an added `program` column.

**R6.** The app additionally accepts an Assessment Schedule workbook (`.xlsx`) with sheets `CourseSubOutcomes` and `OutcomeDescriptions`, used by the Sub-Outcome Lookup feature only.

### Data persistence

**R7.** Uploaded files are cached to a per-user data directory, resolved via `platformdirs` (e.g., `~/AppData/Local/PAT-Report-Generator/data` on Windows). On app start, the cache is auto-loaded so the user does not re-upload between sessions.

**R8.** Cache location is overridable via the `PAT_DATA_DIR` environment variable.

**R9.** When the user uploads a new CSV for a program that already has a cached file, the new file replaces the old one. The previous file is preserved as a timestamped backup for one prior version.

### Course Report tool

**R10.** The user can select a course from a dropdown populated by the union of courses present across all loaded program CSVs.

**R11.** The user can constrain the report to a year range using a slider (default: full available range).

**R12.** The user can optionally filter to one or more programs (default: all programs in which the course appears).

**R13.** The generated report contains:
  - A title block with course code and date range.
  - For each program in which the course appears, a summary table of (semester × sub-outcome × performance indicator × average performance), with cells bolded when average performance fell below the performance indicator.
  - A per-semester detailed section with instructor, measure description, n, comments, and actions taken.

**R14.** The report is rendered to a preview pane inside the app.

**R15.** The user can download the report in four formats: Markdown (`.md`), Word (`.docx`), PDF (`.pdf`), and HTML (`.html`).

**R16.** All four formats are generated from a single intermediate representation; content parity across formats is required (styling differences are acceptable).

### Sub-Outcome Lookup tool

**R17.** The user can select a course from a dropdown populated by the Assessment Schedule workbook.

**R18.** The tool displays the programs in which the course is taught and the sub-outcomes (e.g., 1.1, 2.3) assigned to it, with the human-readable description for each sub-outcome joined from the `OutcomeDescriptions` sheet.

**R19.** The result is downloadable in the same four formats as R15.

### Coverage Check tool

**R20.** The user can select a semester from a dropdown populated by the loaded data.

**R21.** The tool lists, per program, all courses that appear on the schedule for the selected semester but have no submitted assessment data (i.e., `submitted-by` is blank for every row).

**R22.** The tool produces a per-semester summary with total scheduled courses, count assessed, count missing, and percentages.

**R23.** The tool produces a per-year summary table with the same statistics aggregated by year, for the loaded year range.

**R24.** The tool displays a simple trend chart of assessment completion rate by year, per program.

**R25.** Coverage results are downloadable in the same four formats as R15.

### PAT Scheduler tool

**R28.** The user can select one program (CE / ENE / CON) and one semester from the Assessment Schedule workbook's planned grid; the semester defaults to the current one by calendar date (January–June = Spring, July–December = Fall).

**R29.** The tool lists, for that program and semester, every course marked as scheduled in the `Assessment Schedule` sheet whose `CourseSubOutcomes` `Programs` field includes the selected program, together with the sub-outcomes that course is assigned.

**R30.** The primary grouping is by sub-outcome — for each sub-outcome, the courses to add — because PAT entries are created per program and outcome. A by-course view is offered as a cross-check. One (course, sub-outcome) pair is one PAT entry.

**R31.** Cells marked `?` rather than `X` are reported in a separate "needs confirmation" list and excluded from the entry totals.

**R32.** The tool flags workbook problems it can detect: a scheduled course absent from `CourseSubOutcomes` (program and sub-outcomes unknown), and a course scheduled in a term its `Offering` field excludes.

**R33.** The tool consults no PAT export. Its answer is what the plan calls for, not what has already been entered in PAT.

**R34.** Results are downloadable in the same four formats as R15, plus a checklist CSV with one row per PAT entry.

### Cross-cutting

**R26.** All tools share the data uploaded in the sidebar — the user uploads CSVs once per session.

**R27.** Each tool gracefully handles the case where required data is missing (e.g., no CSVs uploaded, no Assessment Schedule loaded) by showing a clear message rather than erroring.

## 4. Non-functional requirements

**N1.** Runs locally on Windows, macOS, and Linux without code changes.

**N2.** Installable via `pip install -r requirements.txt` and launchable with `streamlit run app.py` — no other setup steps required by the end user.

**N3.** No paid services or API keys required for core functionality.

**N4.** All processing happens locally; no PAT data is transmitted to external services.

**N5.** Cold start (app launch with cached data) to first interactive page render: under 5 seconds for current data sizes (~10K rows per program).

**N6.** Course report generation for a single course across all programs and years: under 3 seconds.

**N7.** The codebase is organized for extensibility (see future-extensibility seams in `02_architecture.md`) such that adding a new analysis page, a new output format, or an LLM integration does not require restructuring existing modules.

**N8.** The codebase is documented sufficiently that a new contributor with Python familiarity can find their way around using only the `README.md` and inline docstrings.

## 5. Out of scope (this version)

- Multi-user authentication or access control.
- Cloud deployment or hosted access.
- Automated nightly pulls from PAT (no API exists).
- Editing PAT data inside the tool — the app is read-only over uploaded data.
- LLM-generated narrative text (planned future extension; module seam preserved per N7).
- Visualization beyond the simple per-year trend chart in Coverage Check (planned future extension).
- Annual report generation (planned future extension).

## 6. Assumptions

- The PAT raw export schema remains stable enough that column-alias matching can absorb small renames.
- The Assessment Schedule workbook structure (two named sheets, `Course`/`Programs` plus numeric sub-outcome columns, and an optional `Assessment Schedule` grid whose columns are `F##`/`S##` semester codes) remains consistent across academic years.
- Users have Python 3.10 or newer installed.

## 7. Glossary

- **PAT**: Program Assessment Tool — NC State's web-based system for collecting course-level assessment data.
- **ABET**: Accreditation Board for Engineering and Technology — the accreditation body whose reporting requirements drive this tool.
- **Sub-outcome**: A numbered learning outcome component (e.g., `1.1`, `2.3`) used in the CCEE assessment framework.
- **Performance indicator**: The target percentage of students expected to meet the threshold on a given measure.
- **Performance**: The actual measured percentage of students who met the threshold.
