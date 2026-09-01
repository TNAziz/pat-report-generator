# 04 — UI Specification

Status: Draft v1
Owner: Tarek Aziz
Last updated: 2026-05-29

## 1. Global layout

Streamlit app, sidebar always visible, three pages in the sidebar nav.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  [Sidebar]                            │  [Main content — page-specific]      │
│                                       │                                      │
│  PAT Report Generator                 │                                      │
│  ─────────────────                    │                                      │
│  Pages                                │                                      │
│   • Course Report                     │                                      │
│   • Sub-Outcome Lookup                │                                      │
│   • Coverage Check                    │                                      │
│                                       │                                      │
│  Data                                 │                                      │
│   PAT exports (drag CSV here)         │                                      │
│   [ drop zone — accepts 1–3 CSVs ]    │                                      │
│                                       │                                      │
│   Loaded:                             │                                      │
│   ✓ CE  (Spring 2020 – Spring 2026)   │                                      │
│   ✓ CON (Spring 2020 – Spring 2026)   │                                      │
│   ✗ ENE  Not loaded                   │                                      │
│                                       │                                      │
│   Assessment Schedule (.xlsx)         │                                      │
│   [ drop zone ]                       │                                      │
│   ✓ Loaded (uploaded 2026-05-29)      │                                      │
│                                       │                                      │
│   [ Clear cache ]  [ Show details ]   │                                      │
└───────────────────────────────────────┴──────────────────────────────────────┘
```

## 2. Sidebar behaviors

### File upload zone (PAT exports)

- Accepts one to three `.csv` files in a single drop.
- For each file, detect the program from the filename via regex: `summaryReport(CE|CON|ENE)_`. If no match, inspect the file's `course` column and infer from the dominant prefix (e.g., "all rows start with CE 4xx in the Construction program — assign CON only if the filename or a user prompt confirms").
- If detection is ambiguous (no filename match, no content signal), show a select widget under the drop zone: "We couldn't auto-detect program for `<filename>`. Assign to:" with options CE / CON / ENE / Skip.
- On successful detection, save to cache via `pat.cache.save_upload(program, bytes, original_name)`, replacing any prior file and creating a `.bak` of the previous version.
- Show a green check + filename + date range coverage per program. If a program is unloaded, show a gray X.

### File upload zone (Assessment Schedule)

- Accepts one `.xlsx` file.
- Validates presence of `CourseSubOutcomes` and `OutcomeDescriptions` sheets; if either missing, show a red error message and do not save.
- On success, save to cache; show green check with filename and upload date.

### Clear cache

- Confirmation dialog: "Remove all cached data files? Backups will be preserved." (Yes / Cancel)
- Removes active files but keeps `.bak` versions so a mistake is recoverable.

### Show details

- Expander reveals the full `manifest.json` contents: per-program filename, upload timestamp, SHA-256 hash, row count.

### Persistence behavior

- On app start: read manifest, auto-load all cached files. Sidebar reflects state immediately.
- User does not re-upload between sessions unless they have new data.

## 3. Page: Course Report

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Course Report                                                               │
│  ─────────────                                                               │
│                                                                              │
│  Course:           [ CE 282             ▼ ]                                  │
│  Year range:       [====•==========•=========]  2020 ─ 2026                  │
│  Programs:         [ CE ] [ CON ] [ ENE ]   (multi-select chips)             │
│  [ Generate report ]                                                         │
│                                                                              │
│  ─────────────  Preview  ─────────────                                       │
│                                                                              │
│  # CE 282                                                                    │
│  Spring 2020 – Spring 2026                                                   │
│                                                                              │
│  ## Civil Engineering                                                        │
│  | Semester | Sub-Outcome | PI | Performance |                               │
│  | ...      | ...         |...| ...         |                                │
│  ...                                                                         │
│                                                                              │
│  Download:  [ .md ]  [ .docx ]  [ .pdf ]  [ .html ]                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Inputs

- **Course dropdown.** Options = sorted unique `course` values across all loaded programs. Search-as-you-type enabled.
- **Year range slider.** Min/max = min/max year present in loaded data. Default: full range.
- **Program multi-select.** Default = programs in which the selected course appears. User can deselect a program.

### Action

- "Generate report" button is enabled when a course is selected and at least one program is loaded.
- Clicking it (or changing any input) triggers report generation. Use `st.cache_data` keyed on `(course, year_range, programs, data_hash)` so re-renders are instant.

### Preview

- Rendered HTML from `pat.render.html.render(report)`, displayed via `st.markdown(html, unsafe_allow_html=True)` inside a bordered container.

### Downloads

- Four `st.download_button` widgets, one per format. Filenames derived from course code: `CE_282_report.{md,docx,pdf,html}`.

### Empty / error states

- **No data loaded:** show info banner "Upload at least one PAT CSV in the sidebar to begin."
- **Course not in selected programs:** show warning "CE 282 has no rows in the selected programs and year range."
- **All filtered rows are invalid:** show warning "Found N rows but all have missing performance data."

## 4. Page: Sub-Outcome Lookup

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Sub-Outcome Lookup                                                          │
│  ──────────────────                                                          │
│                                                                              │
│  Course:    [ CE 488   ▼ ]                                                   │
│                                                                              │
│  Programs:  CE / ENE                                                         │
│                                                                              │
│  Sub-Outcomes:                                                               │
│   • 1.2  Formulate the solution to engineering problems.                     │
│   • 2.1  Analyze engineering design with consideration of …                  │
│   • 2.2  Develop engineering designs that meet …                             │
│                                                                              │
│  Download:  [ .md ]  [ .docx ]  [ .pdf ]  [ .html ]                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Inputs

- **Course dropdown.** Options sourced from the `CourseSubOutcomes` sheet (Schedule workbook), not from PAT data.

### Empty / error states

- **No Assessment Schedule loaded:** info banner "Upload the Assessment Schedule workbook in the sidebar to use this tool."
- **Course not on schedule:** warning "CE 999 was not found on the Assessment Schedule. Did you mean: CE 469, CE 488?"

## 5. Page: Coverage Check

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Coverage Check                                                              │
│  ──────────────                                                              │
│                                                                              │
│  Semester:     [ Spring 2025  ▼ ]                                            │
│                                                                              │
│  ── Missing assessments in Spring 2025 ──                                    │
│                                                                              │
│  CE                            CON                       ENE                 │
│   • CE 339                      • CE 342                  • CE 339           │
│   • CE 342                      • CE 469                  • CE 381           │
│   • CE 450                                                • CE 477           │
│   • CE 477                                                • CE 481           │
│                                                                              │
│  ── Semester summary ──                                                      │
│  | Program | Total | Assessed | Missing | % assessed |                       │
│  | CE      | 7     | 3        | 4       | 42.9%      |                       │
│  | CON     | 3     | 1        | 2       | 33.3%      |                       │
│  | ENE     | 4     | 0        | 4       | 0.0%       |                       │
│                                                                              │
│  ── Coverage trend by year ──                                                │
│  [ line chart, one line per program, y = % assessed, x = year ]              │
│                                                                              │
│  Download:  [ .md ]  [ .docx ]  [ .pdf ]  [ .html ]                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Inputs

- **Semester dropdown.** Options = sorted unique semesters across all loaded programs, newest first. Default: most recent.

### Chart

- `st.line_chart` with one series per program, x-axis = year, y-axis = `pct_assessed`.

### Empty / error states

- **No data loaded:** info banner directing user to sidebar.
- **No rows for selected semester:** warning "No data for Spring 2025 across any program — was the export complete?"

## 6. Page: PAT Scheduler

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PAT Scheduler                                                               │
│  ─────────────                                                               │
│  Program: [ CE -- Civil Engineering ▼ ]   Semester: [ Fall 2026 ▼ ]          │
│                                                                              │
│  [ 27 PAT entries ]  [ 7 Courses ]  [ 9 Sub-outcomes ]                       │
│                                                                              │
│  Download: [ .md ] [ .docx ] [ .pdf ] [ .html ]  [ Checklist (.csv) ]        │
│                                                                              │
│  Courses to add, by sub-outcome                                              │
│  ┌─────────┬──────────────┬──────────────┬───────────────────────────┬────┐  │
│  │ Outcome │ Sub-outcome  │ Description  │ Courses                   │ #  │  │
│  ├─────────┼──────────────┼──────────────┼───────────────────────────┼────┤  │
│  │ 1       │ 1.1          │ Apply know…  │ CE 225, CE 301, CE 325 …  │ 6  │  │
│  └─────────┴──────────────┴──────────────┴───────────────────────────┴────┘  │
│                                                                              │
│  Cross-check: by course        Needs confirmation (?)      Workbook issues   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Inputs

- **Program.** CE / ENE / CON, fixed list.
- **Semester.** Options are the `F##`/`S##` columns of the `Assessment Schedule` sheet, chronologically ordered, labeled "Fall 2026". Defaults to the current semester by calendar date, then the nearest later column, then the last column.

### Empty / error states

- **No Assessment Schedule loaded:** info banner "Upload the Assessment Schedule workbook in the sidebar to use the scheduler."
- **Workbook has no `Assessment Schedule` sheet:** warning naming the missing sheet and the expected column shape.
- **Nothing scheduled for the selection:** the report body reads "No courses are scheduled for assessment in Fall 2026 for ENE."

## 7. Cross-cutting UI rules

- Never display a Python traceback. All exceptions in `pat.*` calls are caught at the page level and shown as `st.error("Something went wrong: <one-sentence summary>")` with a `st.expander("Technical details")` containing the traceback for debugging.
- All download filenames are sanitized: spaces → underscores, no special characters.
- All dates displayed to the user are in `MMMM D, YYYY` format (e.g., `May 29, 2026`); ISO dates are reserved for filenames.
- Color usage: green for success state, red for error, gray for empty/disabled. Performance-indicator violations in the Course Report preview are bold (matching the Markdown output) rather than colored, to keep print outputs unambiguous.

## 8. Accessibility

- All form widgets have explicit labels.
- Color is never the only signal — text or icons accompany every color cue.
- Generated DOCX and PDF use heading levels (H1/H2/H3) rather than visual styling alone, so they remain navigable in screen readers.
