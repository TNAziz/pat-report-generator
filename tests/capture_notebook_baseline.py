"""Capture markdown outputs from the original notebook logic.

These are committed as golden references for the rewrite. Phase 3
analysis tests will diff the new tool's output against these to catch
behavior drift.

The notebook code is reproduced almost verbatim -- only the I/O
shims (google.colab uploads, input() prompts) are replaced.

Run:
    python -m tests.capture_notebook_baseline

Writes:
    tests/golden/notebook_CE_342_course_report.md
    tests/golden/notebook_Spring_2025_coverage.md
    tests/golden/notebook_Spring_2025_semester_summary.csv
    tests/golden/notebook_per_year_summary.csv

The Sub-Outcome Lookup (CE 488) baseline is deferred -- it depends on
an Assessment Schedule workbook that is not in this repository.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
SOURCE_XLSX = Path(
    os.environ.get(
        "PAT_BASELINE_XLSX",
        "/sessions/fervent-magical-ride/mnt/ABET/PAT Report Generator/Sp2020-Sp2026.xlsx",
    )
)

# ---------------------------------------------------------------------------
# Notebook helpers (lifted verbatim from cell 2)
# ---------------------------------------------------------------------------

PROGRAM_LABELS = {
    "CE":  "Civil Engineering",
    "ENE": "Environmental Engineering",
    "CON": "Construction Engineering",
}


def _norm_name(s):
    return re.sub(r"[ _\-]+", "", str(s).strip().lower())


def _norm_course_code(s):
    s = str(s).strip().upper()
    match = re.match(r"([A-Z]+)[ _\-]*(\d+)", s)
    if match:
        return match.group(1) + match.group(2)
    return re.sub(r"[ _\-]+", "", s)


def _find_sheet(actual_names, aliases, cutoff=0.8):
    import difflib
    norm_to_actual = {_norm_name(n): n for n in actual_names}
    for a in aliases:
        key = _norm_name(a)
        if key in norm_to_actual:
            return norm_to_actual[key]
    cand = list(norm_to_actual.keys())
    for a in aliases:
        key = _norm_name(a)
        hit = difflib.get_close_matches(key, cand, n=1, cutoff=cutoff)
        if hit:
            return norm_to_actual[hit[0]]
    return None


def _normalize_headers(df):
    df = df.copy()
    df.columns = (
        df.columns.str.strip().str.lower().str.replace(r"[ \-]+", "_", regex=True)
    )
    return df


def clean_whitespace(df):
    def stripper(x):
        return x.strip() if isinstance(x, str) else x
    return df.apply(lambda col: col.map(stripper) if col.dtype == "object" else col)


def filter_invalid_rows(df):
    strict_cols = ["course", "semester", "suboutcome"]
    present_strict = [c for c in strict_cols if c in df.columns]
    df_clean = df.dropna(subset=present_strict)
    def _row_ok(row):
        for c in present_strict:
            v = str(row[c]).strip().lower()
            if v == "null" or v == "":
                return False
        return True
    return df_clean[df_clean.apply(_row_ok, axis=1)]


_percent_re = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_percent(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _percent_re.search(s)
    if m:
        try:
            return float(m.group(1))
        except:
            return None
    try:
        v = float(s)
        return v * 100 if v <= 1.0 else v
    except:
        return None


def fmt_percent(val):
    if val is None:
        return "N/A"
    return f"{int(round(val))}%" if abs(val - round(val)) < 1e-9 else f"{val:.1f}%"


def format_semester_label(raw):
    s = str(raw).strip()
    m = re.match(r"^([FfSs])\s?(\d{2})$", s)
    if m:
        season = m.group(1).upper()
        year = f"20{m.group(2)}"
        return f"{'Fall' if season == 'F' else 'Spring'} {year}"
    m2 = re.search(r"(spring|fall)\s+(\d{4})", s, flags=re.I)
    if m2:
        return f"{m2.group(1).capitalize()} {m2.group(2)}"
    return s


def semester_sort_key(raw):
    s = str(raw).strip()
    year = None
    season = None
    m = re.match(r"^([FfSs])\s?(\d{2})$", s)
    if m:
        season = 'F' if m.group(1).upper() == 'F' else 'S'
        year = 2000 + int(m.group(2))
    else:
        m2 = re.search(r"(spring|fall)\s+(\d{4})", s, flags=re.I)
        if m2:
            season = 'F' if m2.group(1).lower() == 'fall' else 'S'
            year = int(m2.group(2))
    if year is None:
        m3 = re.search(r"(\d{4})", s)
        year = int(m3.group(1)) if m3 else -1
        season = 'Z'
    season_order = 1 if season == 'F' else 0
    return (year, season_order)


def build_summary_table_markdown(df_prog):
    if df_prog.empty:
        return "_No data for this program._\n"
    semesters = sorted(df_prog["semester"].dropna().unique(), key=semester_sort_key, reverse=True)
    rows = []
    for sem in semesters:
        df_sem = df_prog[df_prog["semester"] == sem]
        for sub in sorted(df_sem["suboutcome"].dropna().astype(str).unique()):
            df_ss = df_sem[df_sem["suboutcome"].astype(str) == sub]
            pi_vals_raw = df_ss["performance_indicator"].astype(str).str.strip()
            if pi_vals_raw.empty:
                pi_num = None
            else:
                mode_series = pi_vals_raw.mode()
                mode_val = mode_series.iloc[0] if not mode_series.empty else pi_vals_raw.iloc[0]
                pi_num = parse_percent(mode_val)
            perf_vals = [parse_percent(v) for v in df_ss["performance"].tolist()]
            perf_vals = [p for p in perf_vals if p is not None]
            perf_avg = (sum(perf_vals) / len(perf_vals)) if perf_vals else None
            pi_str   = fmt_percent(pi_num)
            perf_str = fmt_percent(perf_avg)
            if pi_num is not None and perf_avg is not None and perf_avg < pi_num:
                pi_str   = f"**{pi_str}**"
                perf_str = f"**{perf_str}**"
            rows.append((format_semester_label(sem), str(sub), pi_str, perf_str))
    lines = []
    lines.append("| Semester | Sub-Outcome | Performance Indicator | Performance |")
    lines.append("|---|---|---|---|")
    for sem, sub, pi, perf in rows:
        lines.append(f"| {sem} | {sub} | {pi} | {perf} |")
    lines.append("")
    lines.append("_Cells in **bold** indicate the average performance was below the performance indicator._")
    lines.append("")
    return "\n".join(lines)


def build_detailed_markdown(df_prog):
    if df_prog.empty:
        return ""
    lines = []
    semesters = sorted(df_prog["semester"].dropna().unique(), key=semester_sort_key, reverse=True)
    for sem in semesters:
        sem_df = df_prog[df_prog["semester"] == sem]
        instructors = sem_df["assigned_to"].dropna().astype(str).unique()
        instructors = [i for i in instructors if i and i.lower() != 'nan']
        instructor_str = ", ".join(instructors) if instructors else "N/A"
        lines.append(f"## {format_semester_label(sem)}")
        lines.append(f"### Instructor: {instructor_str}")
        lines.append("")
        for sub in sorted(sem_df["suboutcome"].dropna().astype(str).unique()):
            sub_df = sem_df[sem_df["suboutcome"].astype(str) == sub]
            for _, row in sub_df.iterrows():
                perf_str = fmt_percent(parse_percent(row.get("performance", "")))
                pi_str   = fmt_percent(parse_percent(row.get("performance_indicator", "")))
                lines.append(f"#### Sub-Outcome: {sub}")
                lines.append(f"**Measure Description:** {row.get('measure_description', 'N/A')}")
                lines.append("")
                lines.append(f"**Performance Threshold:** {pi_str}")
                lines.append("")
                lines.append(f"**Student Performance:** {perf_str}")
                lines.append("")
                lines.append(f"**n =** {row.get('total_scores', 'N/A')}")
                lines.append(f"> **Comments:** {row.get('comments', '')}")
                lines.append(">")
                lines.append(f"> **Actions Taken:** {row.get('actions_taken', '')}")
                lines.append(">")
                lines.append("---")
                lines.append("")
        lines.append("")
    return "\n".join(lines)


def compose_program_section(program_code, df_prog):
    if df_prog.empty:
        return ""
    program_full = PROGRAM_LABELS.get(program_code, program_code)
    parts = [f"# {program_full}", ""]
    parts.append(build_summary_table_markdown(df_prog))
    parts.append(build_detailed_markdown(df_prog))
    return "\n".join(parts)


def capture_course_report(course_code: str, xlsx_path: Path) -> str:
    """Reproduce notebook cell 2 logic for a given course."""
    xls = pd.ExcelFile(xlsx_path)
    sheet_map = {
        "CE":  _find_sheet(xls.sheet_names, ["CE", "Civil", "Civil Engineering"]),
        "ENE": _find_sheet(xls.sheet_names, ["ENE", "Environmental", "Environmental Engineering"]),
        "CON": _find_sheet(xls.sheet_names, ["CON", "Construction", "Construction Engineering"]),
    }
    required_cols = [
        "course", "semester", "assigned_to", "suboutcome",
        "measure_description", "performance_indicator",
        "performance", "total_scores", "comments", "actions_taken",
    ]
    program_frames = {}
    for code, sheet in sheet_map.items():
        if not sheet:
            continue
        df = pd.read_excel(xls, sheet_name=sheet, keep_default_na=False)
        df = _normalize_headers(df)
        df = clean_whitespace(df)
        for c in required_cols:
            if c not in df.columns:
                raise RuntimeError(f"Missing column '{c}' in sheet {sheet}")
        program_frames[code] = df

    course_norm = _norm_course_code(course_code)
    filtered = {}
    for code, df in program_frames.items():
        df_norm = df.copy()
        df_norm["__norm_course"] = df_norm["course"].astype(str).apply(_norm_course_code)
        raw_matches = df_norm[df_norm["__norm_course"] == course_norm]
        if not raw_matches.empty:
            filtered[code] = filter_invalid_rows(raw_matches)
        else:
            filtered[code] = pd.DataFrame()

    parts = [f"# {course_code}", ""]
    for code in ["CE", "ENE", "CON"]:
        if code in filtered and not filtered[code].empty:
            parts.append(compose_program_section(code, filtered[code]))
    return "\n".join(parts).strip() + "\n"


# ---------------------------------------------------------------------------
# Coverage helpers (lifted from cells 8/9)
# ---------------------------------------------------------------------------


def _norm(s):
    return re.sub(r"[ _\-]+", "", str(s).strip().lower())


def _find_col(df, aliases):
    name_map = {_norm(c): c for c in df.columns}
    for alias in aliases:
        key = _norm(alias)
        if key in name_map:
            return name_map[key]
    for alias in aliases:
        key = _norm(alias)
        for k, actual in name_map.items():
            if key in k or k in key:
                return actual
    raise KeyError(f"Missing column; tried aliases {aliases}")


def _all_null_or_blank(series):
    return series.isna().all() or series.astype(str).str.strip().eq("").all()


def list_missing_by_program(xlsx_path: Path, semester_query: str):
    xls = pd.ExcelFile(xlsx_path)
    results = {}
    for sheet in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet)
        try:
            course_col = _find_col(df, ["course", "Course"])
            semester_col = _find_col(df, ["semester", "Semester"])
            submitted_col = _find_col(df, ["submitted-by", "submitted_by"])
        except KeyError as e:
            results[sheet] = [f"[Error: {e}]"]
            continue
        df[course_col] = df[course_col].astype(str).str.strip()
        df[semester_col] = df[semester_col].astype(str).str.strip()
        df_sem = df[df[semester_col] == semester_query]
        if df_sem.empty:
            results[sheet] = []
            continue
        missing_mask = (
            df_sem.groupby(df_sem[course_col])[submitted_col]
                 .apply(_all_null_or_blank)
        )
        missing_courses = sorted([c for c, is_missing in missing_mask.items() if is_missing and c])
        results[sheet] = missing_courses
    return results


def semester_summary_counts(xlsx_path: Path, semester_query: str) -> pd.DataFrame:
    rows = []
    xls = pd.ExcelFile(xlsx_path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet)
        try:
            course_col = _find_col(df, ["course", "Course"])
            semester_col = _find_col(df, ["semester", "Semester"])
            submitted_col = _find_col(df, ["submitted-by", "submitted_by"])
        except KeyError:
            continue
        df[course_col] = df[course_col].astype(str).str.strip()
        df[semester_col] = df[semester_col].astype(str).str.strip()
        df_sem = df[df[semester_col] == semester_query]
        if df_sem.empty:
            rows.append({"program": sheet, "semester": semester_query,
                         "total_courses": 0, "assessed_courses": 0,
                         "missing_courses": 0, "pct_assessed": 0.0, "pct_missing": 0.0})
            continue
        total_courses = df_sem[course_col].dropna().str.strip().replace("", pd.NA).dropna().nunique()
        grp = df_sem.groupby(df_sem[course_col])[submitted_col]
        missing_mask = grp.apply(_all_null_or_blank)
        assessed = int((~missing_mask).sum())
        missing = int(missing_mask.sum())
        rows.append({
            "program": sheet, "semester": semester_query,
            "total_courses": int(total_courses),
            "assessed_courses": assessed, "missing_courses": missing,
            "pct_assessed": (assessed / total_courses * 100.0) if total_courses else 0.0,
            "pct_missing": (missing / total_courses * 100.0) if total_courses else 0.0,
        })
    return pd.DataFrame(rows)


def per_year_summary_counts(xlsx_path: Path) -> pd.DataFrame:
    rows = []
    xls = pd.ExcelFile(xlsx_path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet)
        try:
            course_col = _find_col(df, ["course", "Course"])
            semester_col = _find_col(df, ["semester", "Semester"])
            submitted_col = _find_col(df, ["submitted-by", "submitted_by"])
        except KeyError:
            continue
        df[course_col] = df[course_col].astype(str).str.strip()
        df[semester_col] = df[semester_col].astype(str).str.strip()
        years = df[semester_col].dropna().astype(str).apply(
            lambda s: re.search(r"(\d{4})", s).group(1) if re.search(r"(\d{4})", s) else ""
        )
        df_year = df.assign(__year=years)
        df_year = df_year[df_year["__year"].ne("")]
        for year, chunk in df_year.groupby("__year"):
            grp = chunk.groupby(chunk[course_col])[submitted_col]
            missing_mask = grp.apply(_all_null_or_blank)
            total_courses = chunk[course_col].dropna().str.strip().replace("", pd.NA).dropna().nunique()
            missing = int(missing_mask.sum())
            assessed = int((~missing_mask).sum())
            rows.append({
                "program": sheet, "year": year,
                "total_courses": int(total_courses),
                "assessed_courses": assessed, "missing_courses": missing,
                "pct_assessed": (assessed / total_courses * 100.0) if total_courses else 0.0,
                "pct_missing": (missing / total_courses * 100.0) if total_courses else 0.0,
            })
    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out["year_num"] = pd.to_numeric(df_out["year"], errors="coerce")
        df_out = df_out.sort_values(["program", "year_num"], ascending=[True, False]).drop(columns=["year_num"])
    return df_out


def capture_coverage_markdown(xlsx_path: Path, semester: str) -> str:
    missing = list_missing_by_program(xlsx_path, semester)
    md_lines = [f"# Courses with NO data collected in {semester} (by program)", ""]
    for program in sorted(missing.keys()):
        md_lines.append(f"## {program}")
        items = missing[program]
        if not items:
            md_lines.append("(none)\n")
        else:
            md_lines.extend([f"- {c}" for c in items])
            md_lines.append("")
    return "\n".join(md_lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    GOLDEN.mkdir(parents=True, exist_ok=True)
    if not SOURCE_XLSX.exists():
        raise SystemExit(f"Baseline source not found: {SOURCE_XLSX}")

    print(f"Source: {SOURCE_XLSX}")

    course_md = capture_course_report("CE 342", SOURCE_XLSX)
    (GOLDEN / "notebook_CE_342_course_report.md").write_text(course_md, encoding="utf-8")
    print(f"  wrote notebook_CE_342_course_report.md ({len(course_md)} chars)")

    cov_md = capture_coverage_markdown(SOURCE_XLSX, "Spring 2025")
    (GOLDEN / "notebook_Spring_2025_coverage.md").write_text(cov_md, encoding="utf-8")
    print(f"  wrote notebook_Spring_2025_coverage.md ({len(cov_md)} chars)")

    sem_df = semester_summary_counts(SOURCE_XLSX, "Spring 2025")
    sem_df.to_csv(GOLDEN / "notebook_Spring_2025_semester_summary.csv", index=False)
    print(f"  wrote notebook_Spring_2025_semester_summary.csv ({len(sem_df)} rows)")

    yr_df = per_year_summary_counts(SOURCE_XLSX)
    yr_df.to_csv(GOLDEN / "notebook_per_year_summary.csv", index=False)
    print(f"  wrote notebook_per_year_summary.csv ({len(yr_df)} rows)")


if __name__ == "__main__":
    main()
