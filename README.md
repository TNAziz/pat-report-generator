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
- **Assessment Schedule** — the planned-vs-actual overlay for the
  schedule workbook.
- **Annual Assessment** — the assessment cycle in the shape of the
  Anthology write-up: program → outcome → sub-outcome, each
  sub-outcome carrying its definition, an aggregate statistics line
  (courses, measures, N, weighted % meeting threshold), every
  underlying measurement row, and an Actions Taken roll-up per
  outcome.

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

**PDF support.** PDF export has two backends and picks the first one
that works, so on a stock Windows machine it works out of the box:

1. **WeasyPrint** — preferred, highest fidelity, but needs native
   GTK/Pango libraries that Windows doesn't ship.
2. **Headless browser** — fallback. Prints the same HTML with
   Microsoft Edge, Google Chrome, or Chromium via `--print-to-pdf`.
   Edge is part of Windows, so this needs no installation and no
   admin rights.

PDF is built **only when you click** the "Build PDF" button, which then
turns into the download. Streamlit reruns the whole page on every widget
change, so building it eagerly meant launching a browser process each
time a filter moved. Markdown, Word and HTML are cheap enough to build
on every rerun and stay as direct downloads.

The PDF button's tooltip names the backend actually in use. It is only
disabled if neither is available (no GTK *and* no Chromium-family
browser installed), and a PDF failure surfaces as a warning rather than
taking the page down.

`PAT_PDF_TIMEOUT` (seconds, default 120) bounds a stuck browser. The
wait normally ends as soon as the PDF file is complete: Edge and Chrome
on Windows leave helper processes running after printing, so waiting on
process exit — or on its output pipes — can hang long after the file is
on disk.

*Optional — enabling the WeasyPrint backend on Windows.* WeasyPrint
needs Pango ≥ 1.44, which the project installs through MSYS2 (this is
the route WeasyPrint's own docs recommend; the older
`winget install GTK.Runtime` package ships a Pango too old for
WeasyPrint 53+):

1. Install MSYS2 from <https://www.msys2.org/>, keeping the default
   options.
2. In the MSYS2 shell that opens, run:

   ```bash
   pacman -S mingw-w64-x86_64-pango
   ```

3. Close the MSYS2 shell. Add `C:\msys64\mingw64\bin` to your `PATH`
   if WeasyPrint still doesn't load (Settings → "Edit the system
   environment variables" → Environment Variables → Path → New).
4. Open a fresh terminal and verify:

   ```powershell
   python -m weasyprint --info
   ```

   That printing a version means the backend is live; re-launch the app
   and the PDF tooltip should read "Rendered with WeasyPrint".

No GTK is needed on macOS or Linux — WeasyPrint's pip wheel bundles its
native deps there.

*Forcing a backend.* Set `PAT_PDF_BACKEND` to `weasyprint` or `browser`
to pin the choice (`auto` is the default), and `PAT_PDF_BROWSER` to an
absolute path if your browser lives somewhere unusual.

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

Four download buttons. The PDF button is only disabled (with a
tooltip) if neither PDF backend is available on the machine.

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

### Annual Assessment

Pick the programs, the semesters that make up the assessment cycle
(e.g. Fall 2024 + Spring 2025), and the outcomes. The report is
organized the way the Anthology submission is:

- **Program → Outcome → Sub-outcome.** Each outcome opens with the
  definitions of the sub-outcomes assessed in the cycle, read from the
  Assessment Schedule's `OutcomeDescriptions` sheet.
- **A statistics line per sub-outcome** — courses contributing,
  measures, total student assessments (N), and the weighted percentage
  meeting the instructor-defined threshold. That percentage is
  `sum(scores meeting threshold) / sum(total scores)`, *not* the mean
  of the per-measure percentages, so a 1-student measure doesn't
  outweigh a 77-student one. Measures with no student counts are
  excluded from the average and the exclusion is stated inline.
- **Every underlying measurement** — course, semester, instructor, the
  instructor's **goal** for that measure, performance, N, the faculty
  comment, and the corrective action. Nothing is aggregated away, so any
  number quoted in the narrative can be traced to a course and semester.
  The goal matters because the department sets no universal benchmark:
  CE alone used 50 %, 60 %, 70 %, 75 %, 80 %, 90 % and 100 % across the
  F24/S25 cycle, so 55 % can be a pass and 74 % a miss. A footnote under
  each table says so.
- **An Actions Taken roll-up per outcome** — every recorded corrective
  action grouped by course (identical text across semesters collapses
  to one entry listing each context), followed by an explicit list of
  measures where no action was recorded.

Same four downloads as the other pages, plus a **drafting packet**.

The packet is one Markdown file that is both the prompt for an LLM and
the archival record of what that LLM was given:

1. the task,
2. the house style and required section structure, distilled from
   previous Anthology submissions,
3. the rules for using the data — Section 5 is the only source of
   facts, use the weighted percentages as given rather than averaging
   the per-row values, never invent a corrective action where the data
   says `None recorded`,
4. provenance — the selection, every source export with its upload time
   and SHA-256, the row counts, the newest measurement-update date, and
   a SHA-256 fingerprint of the data section, and
5. the data, in a fuller column set than the on-screen table: measure
   description, the measure's own threshold and scale ("11 of 16
   points"), the instructor's goal, and students meeting threshold over
   students assessed ("28 of 57"). Those are the fields the narrative's
   per-course sentences are built from; they are left out of the
   readable table because they make a printed one unreadable
   (`annual.build(..., detail=True)`).

Paste it into an assistant to draft the narrative; keep the file next to
the draft. The fingerprint is what lets you answer, months later,
whether a given draft was written from the data you are now looking at.
Nothing in the app calls an LLM API — no keys, no network.

Edit `STYLE`, `TASK`, or `RULES` in `pat/llm.py` to change what the
packet asks for; the text travels inside the packet, so each packet
records the instructions it carried.

> **Reproducing a report written earlier.** PAT lets faculty submit
> measurements long after a semester closes, so a cycle can gain rows
> after its report was filed. If today's export shows more courses than
> a report you wrote months ago, check the `measurement-result-updated`
> dates before assuming the report was wrong.

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

**PDF button is disabled**
Neither PDF backend could start: WeasyPrint's native libraries are
missing *and* no Chromium-family browser was found. Installing
Microsoft Edge or Google Chrome is the quickest fix; the tooltip on the
disabled button states what was tried. See "Installation per OS →
Windows → PDF support" for the WeasyPrint route. The Markdown, Word,
and HTML downloads work regardless.

**PDF comes out looking slightly different than it used to**
You are probably on the headless-browser fallback rather than
WeasyPrint — hover the PDF button to see which backend rendered it.
Page breaks and font metrics differ a little between the two. Install
Pango (see above) to get the WeasyPrint output back.

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
│   ├── 3_Coverage_Check.py
│   ├── 4_Assessment_Schedule.py
│   └── 5_Annual_Assessment.py
├── pat/                          # Domain logic (no Streamlit imports)
│   ├── normalize.py              # String/DataFrame cleaning
│   ├── ingest.py                 # CSV + Assessment Schedule readers
│   ├── cache.py                  # Per-user file cache
│   ├── data.py                   # Public data API for pages
│   ├── analysis/
│   │   ├── course_report.py
│   │   ├── suboutcome.py
│   │   ├── coverage.py
│   │   ├── annual.py             # Annual Assessment (outcome-shaped)
│   │   └── briefing.py           # Home dashboard helpers
│   ├── render/
│   │   ├── model.py              # Report intermediate representation
│   │   ├── markdown.py
│   │   ├── html.py
│   │   ├── docx.py
│   │   └── pdf.py
│   ├── viz.py                    # Future-extension stub
│   └── llm.py                    # LLM drafting packet (offline)
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
- **LLM-assisted annual reports** — `pat/llm.py` builds the drafting
  packet (see "Annual Assessment" above). It is deliberately offline:
  it assembles prompt + data + provenance into one Markdown file and
  stops there. If you later add a direct API call, keep it in this
  module, read the key from the environment, and never commit it.

## Specifications

Design docs live in `specs/` and were written before the code. They
remain the source of truth for *intent*; the code is what's been
built. Where the code deviates from the original spec, the
implementation plan's decision log (`specs/06_implementation_plan.md`)
records the reason.

## Credits

Tarek Aziz (NC State CCEE). Original notebook workflow ported to
this Streamlit app in spring 2026.

