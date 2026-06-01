"""Unit tests for pat.ingest.

Traceability to specs/05_verification.md: R1, R2, R6.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from pat import ingest, normalize as N

FIXTURES = Path(__file__).parent / "fixtures"


# -------- detect_program_from_filename (R2) --------


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("summaryReportCE_S20toS26_2026_05_29_03_05.csv", "CE"),
        ("summaryReportCON_S20toS26.csv", "CON"),
        ("summaryReportENE_2026.csv", "ENE"),
        ("CE-Spring2025.csv", "CE"),
        ("ene_export.csv", "ENE"),
        ("/some/long/path/with/CE_in_dir/summaryReport.csv", None),
        ("ConstructionSpring.csv", None),
        ("export.csv", None),
    ],
)
def test_detect_program_from_filename(filename, expected):
    assert ingest.detect_program_from_filename(filename) == expected


def test_detect_program_from_content_uses_program_column():
    df = pd.DataFrame({"program": ["ENE", "ENE", "ENE"], "course": ["a", "b", "c"]})
    assert ingest.detect_program_from_content(df) == "ENE"


def test_detect_program_from_content_mixed_returns_none():
    df = pd.DataFrame({"program": ["CE", "CON"], "course": ["a", "b"]})
    assert ingest.detect_program_from_content(df) is None


def test_detect_program_ambiguous_returns_none():
    df = pd.DataFrame({"course": ["CE 282"]})
    assert ingest.detect_program("export.csv", df) is None


# -------- read_pat_csv (R1, R3) --------


def test_read_pat_csv_accepts_path():
    df = ingest.read_pat_csv(FIXTURES / "summaryReportCE_TierA.csv")
    assert not df.empty
    assert set(df["program"].unique()) == {"CE"}


def test_read_pat_csv_strips_whitespace_padded_course():
    df = ingest.read_pat_csv(FIXTURES / "summaryReportCE_TierA.csv")
    ce464 = df[df["course_key"] == "CE464"]
    assert not ce464.empty
    for course in ce464["course"]:
        assert course == "CE 464"


def test_read_pat_csv_handles_null_strings():
    df = ingest.read_pat_csv(FIXTURES / "summaryReportCE_TierA.csv")
    ce464 = df[df["course_key"] == "CE464"]
    # CE 464 fixture row used performance="null" and actions-taken="null".
    # Numeric pandas columns store missing as NaN, not Python None.
    assert pd.isna(ce464.iloc[0]["performance"])
    assert ce464.iloc[0]["actions_taken"] == ""


def test_read_pat_csv_handles_short_form_semester():
    df = ingest.read_pat_csv(FIXTURES / "summaryReportCE_TierA.csv")
    s24 = df[(df["course_key"] == "CE282") & (df["semester_year"] == 2024)]
    assert not s24.empty
    assert s24.iloc[0]["semester_season"] == "S"


def test_read_pat_csv_accepts_bytes_with_filename():
    data = (FIXTURES / "summaryReportCE_TierA.csv").read_bytes()
    df = ingest.read_pat_csv(data, filename="summaryReportCE_TierA.csv")
    assert set(df["program"].unique()) == {"CE"}


def test_read_pat_csv_accepts_explicit_program_override():
    data = (FIXTURES / "summaryReportCE_TierA.csv").read_bytes()
    df = ingest.read_pat_csv(data, program="CE", filename="random.csv")
    assert set(df["program"].unique()) == {"CE"}


def test_read_pat_csv_raises_when_program_undetectable():
    data = (FIXTURES / "summaryReportCE_TierA.csv").read_bytes()
    with pytest.raises(N.IngestError):
        ingest.read_pat_csv(data, filename="random.csv")


def test_read_pat_csv_missing_column_raises():
    df = pd.read_csv(FIXTURES / "summaryReportCE_TierA.csv")
    df = df.drop(columns=["performance"])
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    with pytest.raises(N.IngestError) as exc:
        ingest.read_pat_csv(buf.read(), program="CE", filename="missing_col.csv")
    assert "performance" in str(exc.value)


# -------- read_assessment_schedule (R6) --------


def test_read_assessment_schedule_succeeds():
    sched = ingest.read_assessment_schedule(FIXTURES / "assessment_schedule_TierA.xlsx")
    assert "CE 282" in sched.all_courses()
    assert "1.1" in sched.suboutcome_columns


def test_read_assessment_schedule_lookup():
    sched = ingest.read_assessment_schedule(FIXTURES / "assessment_schedule_TierA.xlsx")
    result = sched.lookup("CE 488")
    assert result is not None
    assert sorted(result["programs"]) == ["CE", "ENE"]
    codes = [c for c, _ in result["suboutcomes"]]
    assert codes == ["1.2", "2.1"]
    descs = dict(result["suboutcomes"])
    assert "Formulate" in descs["1.2"]


def test_read_assessment_schedule_lookup_unknown_course():
    sched = ingest.read_assessment_schedule(FIXTURES / "assessment_schedule_TierA.xlsx")
    assert sched.lookup("CE 999") is None


def test_read_assessment_schedule_normalizes_course_query():
    sched = ingest.read_assessment_schedule(FIXTURES / "assessment_schedule_TierA.xlsx")
    for q in ("CE 488", "ce488", "ce-488", "  CE488 "):
        result = sched.lookup(q)
        assert result is not None, f"failed for {q!r}"
        assert result["course"] == "CE 488"


def test_read_assessment_schedule_rejects_missing_sheet(tmp_path):
    bad = tmp_path / "bad.xlsx"
    pd.DataFrame({"a": [1]}).to_excel(bad, sheet_name="NotTheRightSheet", index=False)
    with pytest.raises(N.IngestError) as exc:
        ingest.read_assessment_schedule(bad)
    assert "CourseSubOutcomes" in str(exc.value)



def test_read_assessment_schedule_planned_when_present(tmp_path):
    """If the workbook has an 'Assessment Schedule' sheet, it's loaded."""
    import pandas as pd
    path = tmp_path / "with_planned.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame({"Course": ["CE 214"], "Programs": ["CE/CON"], "1.1": ["X"]}).to_excel(
            xw, sheet_name="CourseSubOutcomes", index=False)
        pd.DataFrame({"Outcomes": ["1.1"], "Description": ["d"]}).to_excel(
            xw, sheet_name="OutcomeDescriptions", index=False)
        pd.DataFrame({
            "Offering": ["F,S"], "Course": ["CE 214"],
            "F23": [None], "S24": ["X"], "F24": [None],
        }).to_excel(xw, sheet_name="Assessment Schedule", index=False)
    sched = ingest.read_assessment_schedule(path)
    assert sched.planned is not None
    assert list(sched.planned.columns) == ["Offering", "Course", "F23", "S24", "F24"]
    assert len(sched.planned) == 1


def test_read_assessment_schedule_planned_none_when_absent():
    """Workbook without the planned sheet still loads fine; planned is None."""
    sched = ingest.read_assessment_schedule(FIXTURES / "assessment_schedule_TierA.xlsx")
    assert sched.planned is None
