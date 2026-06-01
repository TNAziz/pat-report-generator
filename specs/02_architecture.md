# 02 — Architecture

Status: Draft v1
Owner: Tarek Aziz
Last updated: 2026-05-29

## 1. Guiding principles

- **Separate ingestion from analysis from rendering.** Each layer can change independently.
- **One canonical data shape.** All analysis code operates on a single cleaned DataFrame schema (defined in `03_data_model.md`). Tools never re-clean.
- **Intermediate representation for reports.** A `Report` object holds structured content; renderers emit Markdown / HTML / DOCX / PDF from it. New formats are new renderers, not new pipelines.
- **Per-tool pages.** Each Streamlit page is thin: it pulls cleaned data, calls an analysis function in `pat/`, and hands the result to a renderer. Logic worth testing lives outside Streamlit.
- **Seams for future features.** Empty-but-named modules mark planned extension points so the next contributor doesn't have to invent placement.

## 2. Top-level layout

```
pat-report-generator/
├── app.py                       # Streamlit entry: sidebar + routing
├── pages/
│   ├── 1_Course_Report.py
│   ├── 2_Sub_Outcome_Lookup.py
│   └── 3_Coverage_Check.py
├── pat/                         # Domain logic — no Streamlit imports
│   ├── __init__.py
│   ├── ingest.py                # CSV/XLSX loading, program detection
│   ├── normalize.py             # Course codes, semesters, whitespace
│   ├── data.py                  # Public API: get_combined(), get_schedule()
│   ├── cache.py                 # platformdirs-backed file cache
│   ├── analysis/
│   │   ├── course_report.py     # Builds Report IR for a course
│   │   ├── suboutcome.py        # Sub-outcome lookup logic
│   │   └── coverage.py          # Missing assessments + summaries
│   ├── render/
│   │   ├── model.py             # Report dataclasses (IR)
│   │   ├── markdown.py
│   │   ├── html.py
│   │   ├── docx.py
│   │   └── pdf.py
│   ├── viz.py                   # Stub — future data viz helpers
│   └── llm.py                   # Stub — future LLM integration
├── tests/
│   ├── fixtures/                # Sample CSVs (anonymized if needed)
│   ├── test_ingest.py
│   ├── test_normalize.py
│   ├── test_course_report.py
│   ├── test_suboutcome.py
│   ├── test_coverage.py
│   └── test_renderers.py
├── specs/                       # This folder
├── requirements.txt
├── README.md
└── .gitignore
```

## 3. Layer responsibilities

### Ingestion (`pat/ingest.py`)

Takes raw bytes or file paths, returns a per-program raw DataFrame. Detects program from filename (regex like `summaryReport(CE|CON|ENE)_`) with content-based fallback (e.g., a `program` column or inspecting unique course prefixes). Does no normalization beyond reading the file.

### Normalization (`pat/normalize.py`)

Pure functions over strings and DataFrames:

- `clean_course_code(s) -> str` — strips whitespace, collapses spacing, uppercases.
- `parse_semester(s) -> (year:int, season:'F'|'S')` — robust to `"Spring 2024"`, `"S24"`, `"F 23"`.
- `parse_percent(s) -> float | None` — handles `"86%"`, `"86"`, `0.86`, `""`.
- `clean_dataframe(df) -> df` — applies all of the above plus drops `"null"`-string rows on critical fields.
- `canonical_columns(df) -> df` — renames PAT columns to snake_case canonical form.

### Data layer (`pat/data.py`)

The only module that pages import directly when they want data. Public functions:

- `get_combined() -> pd.DataFrame` — returns the canonical, cleaned, combined frame across all loaded programs. Reads from cache if available.
- `get_schedule() -> SubOutcomeSchedule` — typed wrapper around the Assessment Schedule workbook.
- `get_loaded_programs() -> list[str]` — for sidebar status display.
- `get_loaded_semesters() -> list[str]` — for dropdown population.

Caching uses Streamlit's `@st.cache_data` keyed on file hashes so re-reads are free.

### Cache (`pat/cache.py`)

File-level persistence. Public functions:

- `cache_dir() -> Path` — resolves the per-user data directory, honoring `PAT_DATA_DIR`.
- `save_upload(program, file_bytes, original_name)` — writes to cache with one-prior backup.
- `list_cached() -> dict[program, Path]` — what's available on disk.
- `clear(program=None)` — surgical or full wipe.

### Analysis (`pat/analysis/*.py`)

Each module exports a function that takes the canonical DataFrame plus tool-specific parameters and returns a `Report` object (defined in `pat/render/model.py`). These are pure: no I/O, no Streamlit.

- `course_report.build(df, course_code, year_range, programs) -> Report`
- `suboutcome.lookup(schedule, course_code) -> Report`
- `coverage.check(df, semester) -> Report`
- `coverage.summarize_by_year(df, year_range) -> Report`

### Rendering (`pat/render/*.py`)

Each renderer is a single function: `render(report: Report) -> bytes | str`. Renderers are interchangeable; pages call whichever the user requested via download button.

- `markdown.render(report) -> str`
- `html.render(report) -> str` (used both for the in-app preview and as the source for the PDF renderer)
- `docx.render(report) -> bytes`
- `pdf.render(report) -> bytes` (HTML → PDF via WeasyPrint)

### Pages (`pages/*.py`)

Streamlit-specific. Each page:

1. Reads filters from widgets.
2. Calls `pat.data.get_combined()` or `get_schedule()`.
3. Calls the relevant `pat.analysis.*` function.
4. Renders preview via `render.html.render`.
5. Offers download buttons that call other renderers.

Pages contain no business logic. If a function in a page is worth testing, it belongs in `pat/`.

## 4. Data flow

```
PAT website
   │  user downloads CSV
   ▼
[Browser]  drag-drop into Streamlit sidebar
   │
   ▼
pat.ingest.read_csv  ──►  pat.normalize.clean_dataframe  ──►  pat.cache.save_upload
                                                              (per-user data dir)
                                                                   │
                                                                   ▼
                                       pat.data.get_combined  (Streamlit-cached)
                                                                   │
                          ┌────────────────────────────────────────┼──────────────────────┐
                          ▼                                        ▼                      ▼
              pat.analysis.course_report             pat.analysis.coverage    pat.analysis.suboutcome
                          │                                        │                      │
                          ▼                                        ▼                      ▼
                  Report (IR object) ──────────────────────────────┴──────────────────────┘
                          │
              ┌───────────┼────────────┬──────────┐
              ▼           ▼            ▼          ▼
           markdown      html         docx       pdf
              │           │            │          │
              ▼           ▼            ▼          ▼
       download.md   preview      download.docx  download.pdf
```

## 5. Key technical decisions

### D1. Multi-format output from a structured IR, not from Markdown conversion

**Decision:** Define a `Report` dataclass and write four renderers that read it. Do not generate DOCX or PDF by converting Markdown.

**Rationale:** Markdown-to-DOCX via pandoc requires an external binary; Markdown-to-PDF via the same has similar issues. Building each format from a typed IR gives full control over styling per format, keeps the build pure-Python, and means content parity is enforced by the type system rather than by string conversion fidelity.

**Cost:** Slightly more code than a single Markdown emitter would be — four renderers vs. one. Acceptable for the long-term clarity gain.

### D2. Pages contain no business logic

**Decision:** Streamlit pages call into `pat/` and render results. They do not compute.

**Rationale:** Streamlit code is hard to unit-test (it requires the runtime context). Pushing logic into `pat/` means everything that matters can be tested with `pytest` against fixtures, without launching Streamlit.

### D3. Per-user OS-appropriate cache directory

**Decision:** Use `platformdirs` to resolve cache location; honor a `PAT_DATA_DIR` env var override.

**Rationale:** Portable across operating systems with no per-machine configuration. Override path supports a power user who wants the cache on a synced OneDrive folder.

### D4. WeasyPrint for PDF, not ReportLab

**Decision:** Generate HTML with a print-oriented CSS, then convert to PDF via WeasyPrint.

**Rationale:** The HTML renderer is needed anyway for in-app preview, so PDF is essentially free. CSS gives finer control over page breaks, headers, footers, and tables than ReportLab's procedural API. WeasyPrint is pure Python on Mac/Linux and ships a Windows wheel that bundles its native dependencies, avoiding the install pain it had historically.

**Risk:** WeasyPrint install on Windows occasionally requires a one-time GTK runtime install. Mitigation: document this clearly in the README; if it becomes a real obstacle for end users, fall back to ReportLab (renderer swap, no other changes).

### D5. Stub modules for future features

**Decision:** Create `pat/viz.py` and `pat/llm.py` as empty modules with docstrings describing their purpose.

**Rationale:** Marks the architectural slot. When the user decides to add a "Trends" page or an annual-report narrative generator, the placement is unambiguous.

## 6. Dependency graph

```
app.py ─┐
        │
pages/ ─┤── pat/data.py ── pat/cache.py
        │         │
        │         └── pat/ingest.py ── pat/normalize.py
        │
        ├── pat/analysis/*.py ── pat/render/model.py
        │                                │
        │                                ▼
        └── pat/render/{markdown,html,docx,pdf}.py
```

No cycles. `pat/` has no Streamlit imports anywhere — verified by a lint rule (see verification spec).

## 7. External dependencies

| Package | Purpose | Pinned? |
|---|---|---|
| streamlit | UI framework | major |
| pandas | DataFrame ops | major |
| openpyxl | XLSX read | major |
| python-docx | DOCX render | major |
| weasyprint | PDF render | major |
| markdown | MD → HTML | major |
| platformdirs | Cache path resolution | major |
| pytest | Test runner (dev only) | major |

No paid services. No network calls in the runtime path.

## 8. Error and edge-case handling philosophy

- **At the boundary, fail loudly with context.** If a CSV is missing required columns, raise with the column names found and the column names expected.
- **In the middle, prefer empty results to exceptions.** A course with no matching rows returns an empty `Report`, not a `KeyError`.
- **In the UI, never show a Python traceback.** Wrap calls into `pat.*` in try/except and show a one-sentence message with a "details" expander.
