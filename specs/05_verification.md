# 05 — Verification

Status: Draft v1
Owner: Tarek Aziz
Last updated: 2026-05-29

## 1. Strategy

Three complementary checks for every requirement:

1. **Automated unit tests** (`pytest`) for all logic in `pat/`. Run on every commit.
2. **Automated integration tests** that exercise the full pipeline (ingest → analysis → render) against fixture files. Compare byte-equal Markdown output to a golden file.
3. **Manual acceptance tests** for UI behaviors that can't be unit-tested cheaply. Documented as a checklist with screenshots.

Each requirement R# / N# in `01_requirements.md` maps to one or more rows in section 4 below.

## 2. Fixture strategy

Three tiers of test data, kept in `tests/fixtures/`:

**Tier A — Synthetic minimal.** Hand-crafted CSVs with 10–20 rows per program, designed to exercise every cleaning rule (whitespace padding, `"null"` strings, mixed-type sub-outcomes, missing performance). Committed to the repo.

**Tier B — Anonymized real.** A redacted slice of `summaryReportCE_S20toS26_2026_05_29_03_05.csv` and its siblings, with instructor and comment fields scrubbed. Committed if the redaction passes the user's review; otherwise kept locally only.

**Tier C — Live real.** The actual files in `PAT Report Generator/`. Used for manual acceptance only. Not committed.

Golden output files (the markdown a known input *should* produce) live in `tests/golden/`.

## 3. Test commands

```bash
# Unit + integration
pytest

# Coverage report
pytest --cov=pat --cov-report=term-missing

# Lint (no Streamlit imports inside pat/)
python -m scripts.check_imports

# Full local check — what CI would do
make verify       # runs all of the above
```

## 4. Requirements → tests traceability

| Req | Test type | Test name / file | Pass criterion |
|---|---|---|---|
| R1  | unit | `test_ingest.py::test_accepts_three_csvs` | Three Tier A CSVs ingest without error. |
| R2  | unit | `test_ingest.py::test_program_detection_by_filename` | `summaryReportCE_*.csv` → `"CE"`; same for CON, ENE. |
| R2  | unit | `test_ingest.py::test_program_detection_by_content` | Unnamed CSV with all CE-prefixed courses → `"CE"`. |
| R2  | unit | `test_ingest.py::test_program_detection_ambiguous_returns_none` | Empty or mixed file → `None` so UI can prompt. |
| R3  | unit | `test_normalize.py::test_strips_course_whitespace` | 200-char-padded `course` → stripped. |
| R3  | unit | `test_normalize.py::test_treats_null_string_as_missing` | `"null"` and `""` both → `None`/empty. |
| R3  | unit | `test_normalize.py::test_handles_mixed_suboutcome_types` | `1.1` (float) and `"4.1"` (str) both → `"1.1"`, `"4.1"`. |
| R4  | unit | `test_normalize.py::test_course_key` | `"CE 282"`, `"ce-282"`, `"  CE282 "` → all `"CE282"`. |
| R5  | unit | `test_data.py::test_combine_adds_program_column` | Combined frame has `program` column with correct values. |
| R5  | unit | `test_data.py::test_combine_preserves_all_rows` | `len(combined) == sum(len(per_program))`. |
| R6  | unit | `test_ingest.py::test_reads_assessment_schedule` | Loads both required sheets without error. |
| R6  | unit | `test_ingest.py::test_rejects_schedule_missing_sheet` | XLSX without `CourseSubOutcomes` → `IngestError`. |
| R7  | unit | `test_cache.py::test_resolves_per_user_dir` | `cache_dir()` returns a path under the OS user data dir. |
| R7  | integration | `test_cache.py::test_round_trip` | Save → list → load returns same bytes. |
| R8  | unit | `test_cache.py::test_env_override` | `PAT_DATA_DIR=/tmp/foo` → `cache_dir() == Path("/tmp/foo")`. |
| R9  | unit | `test_cache.py::test_replace_creates_backup` | Second save of same program preserves prior file as `.bak`. |
| R10 | unit | `test_data.py::test_unique_courses` | Returns sorted set across all loaded programs. |
| R11 | unit | `test_course_report.py::test_year_range_filter` | `year_range=(2022, 2024)` excludes Spring 2020 rows. |
| R12 | unit | `test_course_report.py::test_program_filter` | `programs=["CE"]` produces sections only for CE. |
| R13 | unit | `test_course_report.py::test_below_threshold_flag` | Row with `performance=60, indicator=70` → `below_threshold=True`. |
| R13 | unit | `test_course_report.py::test_summary_groups_by_semester_and_suboutcome` | One summary row per (semester, suboutcome). |
| R13 | golden | `test_course_report.py::test_ce342_full_report_matches_golden` | Generated Markdown == `tests/golden/CE_342.md`. |
| R14 | manual | M1 (see §5) | Preview renders inside Streamlit page. |
| R15 | unit | `test_renderers.py::test_all_four_formats_produced` | All four renderers return non-empty content for a sample report. |
| R16 | unit | `test_renderers.py::test_content_parity` | Same course titles and table cell values appear in all four formats. |
| R17 | unit | `test_suboutcome.py::test_lookup_returns_programs_and_codes` | Known course → expected programs + sub-outcome codes. |
| R18 | unit | `test_suboutcome.py::test_descriptions_joined` | Each returned code has the description from the workbook. |
| R19 | unit | `test_renderers.py::test_suboutcome_report_all_formats` | All four renderers handle the Sub-Outcome report shape. |
| R20 | unit | `test_data.py::test_available_semesters_sorted` | Newest first; mixed Fall/Spring ordered correctly. |
| R21 | unit | `test_coverage.py::test_missing_courses_blank_submitter` | Course with all-blank `submitter` → flagged missing. |
| R21 | unit | `test_coverage.py::test_partially_assessed_not_flagged` | Course with ≥1 non-blank `submitter` row → not flagged. |
| R22 | unit | `test_coverage.py::test_semester_summary_counts` | Counts and percentages match hand-computed values. |
| R23 | unit | `test_coverage.py::test_per_year_summary` | One row per (program, year), counts match. |
| R24 | manual | M2 | Trend chart renders with one line per program. |
| R25 | unit | `test_renderers.py::test_coverage_report_all_formats` | All four renderers handle the Coverage report shape. |
| R26 | manual | M3 | Uploads in sidebar persist across page navigations. |
| R27 | manual | M4 | Each tool shows correct empty/error state when data missing. |
| N1  | manual | M5 | App runs on Windows + macOS + (one) Linux. |
| N2  | manual | M6 | Fresh checkout → `pip install -r requirements.txt` → `streamlit run app.py` succeeds. |
| N3  | unit | `test_requirements.py::test_no_paid_packages` | No package in `requirements.txt` matches a known paid-service list. |
| N4  | lint | `scripts/check_imports.py::test_no_network_in_pat` | No `requests`, `httpx`, `urllib` imports inside `pat/`. |
| N5  | manual + bench | M7 | Cold start measured under 5 s with current data. |
| N6  | bench | `test_perf.py::test_course_report_under_3s` | `course_report.build(...)` returns in < 3 s. |
| N7  | lint | `scripts/check_imports.py::test_no_streamlit_in_pat` | No `streamlit` imports inside `pat/`. |
| N7  | structural | `test_arch.py::test_stub_modules_present` | `pat/viz.py` and `pat/llm.py` exist and import cleanly. |
| N8  | manual | M8 | New contributor smoke test (see §5). |

## 5. Manual acceptance checklist

Run before tagging a release. Record pass/fail + notes.

**M1 — Preview renders.** Open Course Report page, select CE 282, full year range, all programs. Confirm preview shows formatted report with summary table and per-semester sections.

**M2 — Trend chart.** Open Coverage Check, select Spring 2025. Confirm chart shows three colored lines (CE/CON/ENE) with sensible y-axis (0–100%).

**M3 — Sidebar persistence.** Upload all three CSVs. Switch from Course Report → Coverage Check → Sub-Outcome Lookup. Confirm sidebar status remains green for all three.

**M4 — Empty-state handling.** Fresh launch with empty cache. Visit each page; confirm a friendly info message (not a traceback) and no crash.

**M5 — Cross-platform.** Run app on Windows 11 and macOS 14. (Linux confirmation can be deferred.)

**M6 — Install from clean.** Fresh venv, `pip install -r requirements.txt`, `streamlit run app.py`. App launches without errors. Note any platform-specific install pain (WeasyPrint GTK on Windows).

**M7 — Cold start performance.** With all three CSVs cached, measure time from `streamlit run` to first interactive page. Target: under 5 s.

**M8 — Contributor smoke test.** Hand the repo to a Python-familiar colleague (or simulate this yourself). Ask them to add a new dummy output format (e.g., `.txt`). Confirm they can find the renderer module and follow the existing pattern in under 30 minutes.

**M9 — End-to-end course report.** Generate CE 342 report (the case that originally motivated debugging in the notebook). Confirm:
  - CE 342 rows from both CE and CON sheets appear.
  - Whitespace-padded course codes are stripped.
  - Summary table reflects performance-indicator violations correctly.
  - All four downloads open in their respective applications.

**M10 — End-to-end coverage check.** Pick Spring 2025. Confirm the missing list matches what the existing notebook produces (per `CCEE-F17-S25-PAT Dump.xlsx` output in the original notebook).

## 6. Golden file maintenance

Golden output files are produced by running the analysis once and visually verifying correctness, then frozen. When a content change is intentional (e.g., the Markdown format gains a new section), regenerate via:

```bash
pytest --regenerate-golden
```

This flag must be opt-in; default `pytest` run must fail on golden mismatch.

## 7. Regression guard against the notebook

For each tool, capture the notebook's output on a known input as a frozen reference. The first integration test for each tool diffs the new tool's Markdown against the notebook's. This catches accidental behavior drift during the rewrite.

Known references to capture:
- Notebook output for CE 342 (Course Report).
- Notebook output for CE 488 (Sub-Outcome Lookup).
- Notebook output for Spring 2025 (Coverage Check, missing list and per-year summary).

## 8. Definition of done (per phase)

A build phase is "done" only when:

1. All requirements scoped to that phase have passing tests.
2. All manual checklist items for that phase have been executed.
3. The relevant section of `06_implementation_plan.md` is marked complete and dated.
4. `pytest` is green and `make verify` exits 0.
