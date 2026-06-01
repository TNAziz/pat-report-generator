# 06 — Implementation Plan

Status: Draft v1
Owner: Tarek Aziz
Last updated: 2026-05-29

## 1. Approach

Build in six phases, gated by verification. Each phase has explicit entry criteria (what must be true before starting), exit criteria (what must be true to declare it done), and a tight scope. No phase begins until the prior phase's exit criteria are met.

The earliest phases stand alone — they produce running, testable code without any Streamlit. Streamlit only enters in Phase 4. This is deliberate: it forces the domain logic to be testable in isolation.

## 2. Phase 1 — Project scaffold and data layer

**Goal.** A Python package that can read three PAT CSVs and an Assessment Schedule workbook, clean them, combine them, and hand back a canonical DataFrame. No UI yet.

**Entry criteria.** Specs 01–05 approved.

**Tasks.**
1. Create `pyproject.toml` / `requirements.txt` with the dependencies listed in `02_architecture.md` §7.
2. Create the folder structure from `02_architecture.md` §2.
3. Implement `pat/normalize.py` — all pure functions per `02_architecture.md` §3.
4. Implement `pat/ingest.py` — CSV reading, program detection, schedule workbook reading.
5. Implement `pat/cache.py` — `platformdirs`-backed file cache with manifest.
6. Implement `pat/data.py` — the public API: `get_combined`, `get_schedule`, etc.
7. Create Tier A synthetic fixtures in `tests/fixtures/`.
8. Write unit tests for every public function. Aim for >90% coverage on `pat/normalize.py` and `pat/ingest.py`.
9. Create `scripts/check_imports.py` — fails if `pat/` imports `streamlit` or any network library.
10. Capture notebook reference outputs (CE 342, CE 488, Spring 2025) for regression guards (per `05_verification.md` §7).

**Exit criteria.**
- All R1–R9 tests in `05_verification.md` pass.
- `make verify` exits 0.
- Running a one-off CLI script (`python -m pat.data.get_combined --data-dir tests/fixtures/`) prints the cleaned, combined DataFrame head.

**Estimated effort.** 4–6 hours.

## 3. Phase 2 — Report intermediate representation and renderers

**Goal.** Convert any `Report` object into four output formats. No analysis logic yet — Phase 2 works against hand-constructed `Report` instances.

**Entry criteria.** Phase 1 exit criteria met.

**Tasks.**
1. Implement `pat/render/model.py` with all dataclasses from `03_data_model.md` §5.
2. Implement `pat/render/markdown.py` — must reproduce the notebook's output byte-for-byte on a known input. This is the spec's regression guard.
3. Implement `pat/render/html.py` — Markdown rendered via the `markdown` library plus a print-friendly inline CSS.
4. Implement `pat/render/pdf.py` — WeasyPrint over the HTML output. Page numbers in footer, generous margins, table borders.
5. Implement `pat/render/docx.py` — direct construction via `python-docx`. Heading levels, real tables (not just text), bold cells for below-threshold rows.
6. Build hand-crafted `Report` fixtures covering: a course report with mixed-program sections; a sub-outcome lookup; a coverage check with chart data.
7. Write renderer tests for content parity across formats (`05_verification.md` R16).

**Exit criteria.**
- All R13, R15, R16, R19, R25 tests pass.
- For a fixture `Report`, all four outputs open without error in their target applications (manual check: VS Code for .md/.html, Word for .docx, Acrobat/Preview for .pdf).

**Estimated effort.** 6–8 hours. The DOCX and PDF renderers are the bulk of this.

## 4. Phase 3 — Analysis modules

**Goal.** Convert filtered, cleaned data into `Report` objects. Three analysis functions, one per tool.

**Entry criteria.** Phases 1 and 2 exit criteria met.

**Tasks.**
1. Implement `pat/analysis/course_report.py` per `03_data_model.md` §5 and the existing notebook logic in cell 2.
2. Implement `pat/analysis/suboutcome.py` per the notebook logic in cell 6.
3. Implement `pat/analysis/coverage.py` per the notebook logic in cells 8 and 9.
4. Add the chart-data accessor (`coverage.summary_chart_data`) returning a DataFrame the Streamlit chart can consume directly.
5. Run regression tests against the notebook reference outputs captured in Phase 1.
6. Add `test_perf.py` benchmarks for N6.

**Exit criteria.**
- All R10–R13, R17–R18, R20–R23 tests pass.
- Regression diff against notebook output for CE 342, CE 488, Spring 2025 is zero (per `05_verification.md` §7).
- N6 benchmark under 3 seconds.

**Estimated effort.** 4–6 hours. Most of this is porting existing notebook logic into clean functions.

## 5. Phase 4 — Streamlit shell and Course Report page

**Goal.** The user can launch the app, drag in CSVs, and produce a Course Report end-to-end. The most-used page, first.

**Entry criteria.** Phases 1–3 exit criteria met.

**Tasks.**
1. Implement `app.py` — sidebar, navigation, session state for loaded data.
2. Implement the sidebar upload zones with program auto-detection and the ambiguity fallback dropdown.
3. Implement sidebar status display (per-program load state, date range coverage).
4. Wire up `pat.cache` to the sidebar: drops update cache; cache state drives display.
5. Implement `pages/1_Course_Report.py` per `04_ui_spec.md` §3.
6. Wire `st.cache_data` keyed on filters + data hash for snappy re-renders.
7. Implement download buttons calling the renderers.

**Exit criteria.**
- Manual checks M1, M3, M4, M9 pass.
- Visual review: CE 342 report in all four formats matches expectations.
- App handles missing-data states without traceback.

**Estimated effort.** 5–7 hours.

## 6. Phase 5 — Sub-Outcome Lookup and Coverage Check pages

**Goal.** The remaining two tools.

**Entry criteria.** Phase 4 exit criteria met.

**Tasks.**
1. Implement `pages/2_Sub_Outcome_Lookup.py` per `04_ui_spec.md` §4.
2. Implement `pages/3_Coverage_Check.py` per `04_ui_spec.md` §5, including the trend chart.
3. Add download buttons on both pages.

**Exit criteria.**
- Manual checks M2, M4, M10 pass.
- Spring 2025 coverage output matches the notebook's output exactly.

**Estimated effort.** 3–4 hours.

## 7. Phase 6 — Polish and handoff

**Goal.** Production-ready state for personal use; clean enough to hand to a colleague.

**Entry criteria.** Phase 5 exit criteria met.

**Tasks.**
1. Write `README.md` — install instructions, first-run walkthrough, troubleshooting, structure overview, contribution pointer to `specs/`.
2. Create `pat/viz.py` and `pat/llm.py` as documented stubs (per N7).
3. Run M6 (clean install) on Windows and macOS; document any platform-specific install steps in the README.
4. Run M5 (cross-platform smoke test).
5. Run M8 (contributor smoke test) — ask a colleague to add a `.txt` output format and time how long it takes.
6. Add `.gitignore` (cache dir, `__pycache__`, etc.).
7. Tag v0.1.0.

**Exit criteria.**
- All manual checks M1–M10 pass on at least Windows + macOS.
- Fresh clone → install → launch documented and verified.
- Tag pushed; spec docs updated with "v0.1.0 released" stamps.

**Estimated effort.** 3–4 hours.

## 8. Total estimate

25–35 hours of focused work. Plausible to compress into a long weekend if uninterrupted, or spread across two to three weeks part-time.

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| WeasyPrint install pain on Windows | Medium | Medium | Document GTK install in README; fall back to ReportLab if it bites real users. |
| PAT export schema drift between semesters | Low | High | Column-alias matching; explicit error listing missing columns; manual schema review of each new export. |
| DOCX → Word styling regressions | Medium | Low | Visual review on Mac + Windows Word; ship `.docx` as canonical and treat PDF as a render of the same content. |
| Notebook → tool behavior drift | Medium | Medium | Phase 1 captures notebook reference outputs; Phase 3 regresses against them. |
| Streamlit version churn | Low | Low | Pin major version; revisit annually. |
| User outgrows the tool (wants annual reports, viz, LLM) | High (eventually) | Low | Stub modules + IR architecture already accommodate this; no remediation needed now. |

## 10. Decision log

Decisions made during planning (with rationale) — append new ones as the build proceeds.

### Planning (pre-build)

- **2026-05-29.** Use platformdirs for cache, not project-local. Tool intended for handoff to colleagues; per-user OS directory is more portable.
- **2026-05-29.** All four output formats from a typed IR rather than Markdown conversion. Cleaner long-term; avoids pandoc dependency.
- **2026-05-29.** WeasyPrint over ReportLab for PDF. HTML renderer is needed for preview anyway; CSS gives finer styling control.
- **2026-05-29.** Streamlit pages contain no business logic. Domain code in `pat/` is testable without launching Streamlit.
- **2026-05-29.** Stub `pat/viz.py` and `pat/llm.py` from day one. Marks the seams for planned future extensions (data viz, annual report narrative, LLM).

### Phase 1 (data layer)

- **2026-05-29.** Normalized `semester` column stores the human display label ("Spring 2024"), not the raw input. Short-form labels like `"S24"` are reformatted at ingestion so downstream code never sees them. Source: data-model spec §2 requires the display form; bug surfaced in Course Report semester ordering.
- **2026-05-29.** Bypass OneDrive-mounted paths for source-file writes during development by staging into a regular filesystem first and copying. OneDrive sync occasionally truncates mid-write and injects null bytes. Documented in Phase 6 README as a dev-environment caveat; not a user-facing issue.

### Phase 2 (renderers)

- **2026-05-29.** Render zero cells in heatmaps with a distinct pink/red treatment (`#fce6e6` background, bold dark-red text), separate from the blue color ramp. The default color ramp puts zero at the near-white end, hiding coverage gaps; the special treatment makes "not assessed" visually unambiguous against the blue scale. Added `Heatmap.highlight_zero` field, default True. Empty-cell marker semantics changed: `empty_marker` now applies only to true missing data (None/NaN), not to literal zero.
- **2026-05-29.** Add `Heatmap` to the Report IR (originally not in the spec). Driven by the user's request for a sub-outcome × year coverage view; folds in cleanly as a new IR element + per-renderer handler. All four renderers handle it (Markdown as a counts table, HTML/PDF as colored cells with an SVG gradient legend, DOCX as a colored Word table).

### Phase 3 (analysis)

- **2026-05-29.** Course Report intentionally diverges from the original notebook in one place: the notebook displays literal `"null"` strings where data is missing (a bug). The new tool displays `"N/A"` for missing numeric values and blank for missing text. Regression strategy: byte-exact match against a corrected golden file (`tests/golden/CE_342_course_report.md`); separate logical-equivalence test confirms the only diffs vs. the notebook are the null-display fix.

### Phase 4 (Streamlit shell)

- **2026-05-29.** PDF renderer imports WeasyPrint lazily inside `render()`, not at module import time. Surfaces `is_available()` so pages can disable the PDF button gracefully on machines without GTK (common on Windows). Other formats keep working. Driven by a real user blocker: a `libgobject-2.0-0` load error crashed the whole Course Report page on first launch.
- **2026-05-29.** Streamlit entry point renamed from `app.py` to `Home.py`. Streamlit derives the sidebar label from the entry-point filename; `app.py` produced an "app" entry that read as developer-y. `Home.py` reads as a user-friendly landing label. Launchers (`run.bat`, `run.sh`) updated accordingly.

### Phase 5 / 6 (remaining pages + polish)

- **2026-05-29.** Coverage Check year-axis chart uses Altair with explicit `format="d"`, not `st.line_chart`. Streamlit's default chart applies locale formatting to numeric axes (`2,020` instead of `2020`). Altair gives explicit control and the chart looks cleaner.
- **2026-05-29.** Home page is a dashboard, not a welcome screen. Three sections: inventory metrics, recent-semester coverage per program (with missing-course expanders), below-threshold attention for the most recent year (with top-3 largest gaps). Logic in `pat/analysis/briefing.py` so the dashboard is testable without Streamlit.
- **2026-05-29.** ABET cycle view added to Coverage Check (originally not in spec). User-requested admin tool: pick two semesters bounding a cycle (default Fall 2023 → Spring 2028), see a single rollup heatmap of sub-outcome × program with the same highlight-zero treatment. Sub-outcome detail panel beneath the cycle view shows description + per-program course list when the Assessment Schedule is loaded.
