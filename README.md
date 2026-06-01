# PAT Report Generator

A local Streamlit application for generating ABET-ready reports from
NC State's Program Assessment Tool (PAT) raw exports. Built for the
CCEE department's three undergraduate programs: Civil Engineering
(CE), Environmental Engineering (ENE), and Construction Engineering
(CON).

The app replaces a Colab-bound Jupyter notebook workflow with a
local-first browser UI that does drag-and-drop uploads, persists data
across sessions, and produces reports in Markdown, Word, PDF, and
HTML.

## What it does

- **Home dashboard** — at-a-glance briefing: data inventory, recent-semester
  coverage per program, top below-threshold measurements.
- **Course Report** — per-course assessment narrative with semester
  trends and below-threshold flagging. Filter by year range and program.
- **Sub-Outcome Lookup** — for a course, list the programs and
  sub-outcomes the course is intended to assess, with descriptions.
- **Coverage Check** — missing-data list per semester, per-program
  semester summary, per-year completion trend chart, sub-outcome
  coverage heatmaps per program, an ABET cycle rollup heatmap
  (default Fall 2023 → Spring 2028), and a sub-outcome detail panel
  showing which courses claim each sub-outcome.

Every page produces downloads in **Markdown / Word / PDF / HTML** —
all four formats are generated from the same typed intermediate
representation, so content parity is enforced.

## Quick start

```powershell
# From inside the project folder:
python -m pip install -r requirements.txt
python -m streamlit run Home.py
```

Or double-click `run.bat` (Windows) / `./run.sh` (macOS, Linux).

The app opens in your browser at <http://localhost:8501>. Drag your
three PAT CSV exports onto the sidebar — they're auto-detected by
filename and cached in a per-user data directory so you only upload
once per semester.

## Installation per OS

### Windows

1. Install Python 3.10 or newer from <https://www.python.org/downloads/>.
   Tick **"Add Python to PATH"** in the installer.
2. Open PowerShell in the project folder (Shift + right-click →
   "Open PowerShell window here").
3. `python -m pip install -r requirements.txt`
4. `python -m streamlit run Home.py` (or double-click `run.bat`).

**PDF support (optional).** The PDF download uses WeasyPrint, which
needs the GTK runtime on Windows. Without GTK, the PDF button is
disabled and tooltipped with the reason; the other three formats
work fine. To enable PDF:

```powershell
winget install --id GTK.Runtime
```

Then restart your terminal and re-launch the app. (No GTK is needed
on macOS or Linux — WeasyPrint's pip wheel bundles its native deps
there.)

### macOS

```bash
python3 -m pip install -r requirements.txt
./run.sh
```

### Linux

```bash
python3 -m pip install -r requirements.txt
./run.sh
```

## File uploads

### PAT CSV exports

From PAT's "Download RAW Data" feature, download one CSV per program.
Drop all three onto the sidebar's "PAT exports" zone. The app:

- Auto-detects program from filename (`summaryReportCE_*.csv` → CE,
  etc.).
- Falls back to content inspection if the filename is ambiguous;
  prompts you to assign manually if both fail.
- Validates that all required columns are present, with a clear error
  if the schema changed.
- Strips PAT artifacts (notably the hundreds of whitespace characters
  that prefix the `course` column) before caching.

You only upload again when new data arrives. The cache persists
across sessions.

### Assessment Schedule workbook (optional, recommended)

The Sub-Outcome Lookup page and the Coverage Check page's cycle view
read from your `Assessment Schedule - YYYY.xlsx`. The workbook must
have two sheets:

- **`CourseSubOutcomes`** — columns `Course`, `Programs`, and one
  column per sub-outcome code (`1.1`, `1.2`, …). Cells marked `X` (or
  `✓`, `1`, `true`) indicate the course claims that sub-outcome. The
  `Programs` field is `/`-, `,`-, or `;`-separated (e.g.
  `"CE, ENE, CON"`).
- **`OutcomeDescriptions`** — columns `Outcomes` and `Description`,
  one row per sub-outcome code.

The workbook is cached the same way as the PAT CSVs.

## Cache location

By default the app stores cached uploads in the OS-appropriate
per-user data directory:

| OS | Path |
| --- | --- |
| Windows | `C:\Users\<you>\AppData\Local\PAT-Report-Generator\data` |
| macOS | `~/Library/Application Support/PAT-Report-Generator/data` |
| Linux | `~/.local/share/PAT-Report-Generator/data` |

Override with the `PAT_DATA_DIR` environment variable — useful if you
want the cache on a shared OneDrive folder so multiple machines can
share it.

The sidebar shows the active path and per-slot upload timestamps.
"Clear cache" preserves the previous version as a `.bak` so a mistaken
clear is recoverable.

## Tour of the pages

### Home

Top metrics: programs / courses / measurements / year range. Then a
"Recent semester coverage" row (one column per program, with a
progress bar, color-coded assessed/total, and an expandable list of
missing courses), followed by a "Below-threshold attention" row for
the most recent year (count per program plus the top three largest
gaps from indicator).

### Course Report

Pick a course, set the year range, optionally narrow to specific
programs. The report shows:

- A summary table per program with semester × sub-outcome ×
  performance indicator × measured performance, with below-threshold
  rows bolded.
- A per-semester detailed section with instructor, measure
  description, n, comments, and actions taken.

Four download buttons. The PDF button is disabled (with a tooltip)
if WeasyPrint can't load its native dependencies.

### Sub-Outcome Lookup

Pick a course from the Assessment Schedule's course list. See the
programs that teach it and the sub-outcomes it claims to assess
(joined to their descriptions). Same four downloads.

### Coverage Check

Pick a focus semester. Year-range slider drives the per-year trend
and the per-program coverage heatmaps. The page shows:

- **Missing assessments** in the focus semester, grouped by program.
- **Semester summary** table with totals and percentages.
- **Coverage trend by year** — line chart, one line per program,
  y-axis = % assessed, with year labels rendered as plain integers
  (not `2,020`).
- **ABET cycle coverage** — start/end semester selectboxes (default
  Fall 2023 → Spring 2028), and a rollup heatmap with rows =
  sub-outcomes, columns = programs, cells = total submitted
  measurements during the cycle. Pink cells flag zero-coverage
  combinations.
- **Sub-outcome detail** — pick a sub-outcome to see its description
  and which courses (per program) claim to assess it.
- **Per-program heatmaps** — one heatmap per program, rows =
  sub-outcomes, columns = years in the selected range, cells =
  measurement counts. The same pink "not assessed" highlight applies.

## Troubleshooting

**"streamlit: command not found"**
Use the module form: `python -m streamlit run Home.py`. The pip
`Scripts` directory isn't on `PATH` by default on Windows.

**"No module named streamlit"**
You probably have multiple Python installs and pip put the package
into the wrong one. Run with the explicit interpreter, e.g.:

```powershell
& 'C:\Program Files\Python313\python.exe' -m pip install -r requirements.txt
& 'C:\Program Files\Python313\python.exe' -m streamlit run Home.py
```

**PDF button is disabled / "WeasyPrint failed to load"**
Install the GTK runtime (see "Installation per OS → Windows"). The
other three formats still work without GTK.

**"Could not determine program for the uploaded CSV"**
Rename the file so it contains `CE`, `CON`, or `ENE` as a word
(e.g., `summaryReportCE_S25.csv`), or set the program manually via
the dropdown that appears under the uploader when detection is
ambiguous.

**The sidebar shows old data after I uploaded new files**
Streamlit's data cache is keyed on the upload manifest, so new
uploads should invalidate it automatically. If you suspect stale
state, hit the "Clear cache" button in the sidebar (your backups
are preserved) and re-upload.

**Sidebar only shows "app" / "Course Report" after I added pages**
Streamlit auto-discovers `pages/*.py` only at startup. Ctrl+C the
running server and re-run `python -m streamlit run Home.py`.

## Project layout

```
pat-report-generator/
├── Home.py                      # Streamlit entry point
├── pages/
│   ├── 1_Course_Report.py
│   ├── 2_Sub_Outcome_Lookup.py
│   └── 3_Coverage_Check.py
├── pat/                          # Domain logic (no Streamlit imports)
│   ├── normalize.py              # String/DataFrame cleaning
│   ├── ingest.py                 # CSV + Assessment Schedule readers
│   ├── cache.py                  # Per-user file cache
│   ├── data.py                   # Public data API for pages
│   ├── analysis/
│   │   ├── course_report.py
│   │   ├── suboutcome.py
│   │   ├── coverage.py
│   │   └── briefing.py           # Home dashboard helpers
│   ├── render/
│   │   ├── model.py              # Report intermediate representation
│   │   ├── markdown.py
│   │   ├── html.py
│   │   ├── docx.py
│   │   └── pdf.py
│   ├── viz.py                    # Future-extension stub
│   └── llm.py                    # Future-extension stub
├── scripts/
│   └── check_imports.py          # Architectural lint
├── specs/                        # Design documents (read these first
│   ├── README.md                 #  before touching the code)
│   ├── 01_requirements.md
│   ├── 02_architecture.md
│   ├── 03_data_model.md
│   ├── 04_ui_spec.md
│   ├── 05_verification.md
│   └── 06_implementation_plan.md
├── tests/                        # Pytest suite (>200 tests)
├── samples/                      # Pre-generated example outputs
├── requirements.txt
├── pyproject.toml
├── run.bat / run.sh              # Launchers
└── README.md                     # This file
```

## Architecture in one paragraph

`pat/` is pure domain logic — no Streamlit imports anywhere under it,
enforced by `scripts/check_imports.py`. Pages call into
`pat.data.get_combined()` and `pat.data.load_schedule()` to pull the
cleaned, combined frame, then hand it to `pat.analysis.*` functions
that return a typed `Report` (see `pat/render/model.py`). The four
renderers in `pat/render/{markdown,html,docx,pdf}.py` each consume a
Report and emit one format. Adding a new output format = a new
renderer file. Adding a new analysis view = a new module under
`pat/analysis/` plus a new page under `pages/`. See
`specs/02_architecture.md` for the long form.

## Development

```bash
# Install dev dependencies (pytest + coverage)
python -m pip install -r requirements-dev.txt

# Run the test suite
python -m pytest

# With coverage report
python -m pytest --cov=pat --cov-report=term-missing

# Architectural lint
python scripts/check_imports.py

# Regenerate test fixtures
python -m tests.fixtures.build_fixtures

# Regenerate the notebook regression baselines (only after intentional
# format changes; otherwise the existing baselines should match):
python -m tests.capture_notebook_baseline
```

## Extending

- **New analysis view** — add a module under `pat/analysis/`, write
  pure functions that return a `Report`. Tests live in
  `tests/test_<module>.py`. Then a new page in `pages/` that calls
  it.
- **New output format** — add a renderer under `pat/render/`. It
  takes a `Report` and returns bytes (or str). Wire it into pages'
  download buttons.
- **Data viz beyond what's in the app** — `pat/viz.py` is a
  documented stub; that's the home for matplotlib/altair helpers
  shared across pages.
- **LLM-assisted annual reports** — `pat/llm.py` is a stub; that's
  the seam for an Anthropic API integration that turns a filtered
  `Report` into a narrative paragraph for the annual-report writeup.
  Don't commit API keys; read from environment.

## Specifications

Design docs live in `specs/` and were written before the code. They
remain the source of truth for *intent*; the code is what's been
built. Where the code deviates from the original spec, the
implementation plan's decision log (`specs/06_implementation_plan.md`)
records the reason.

## Credits

Tarek Aziz (NC State CCEE). Original notebook workflow ported to
this Streamlit app in spring 2026.

