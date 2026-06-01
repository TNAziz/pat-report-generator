"""Unit tests for pat.normalize.

Traceability to specs/05_verification.md:
- R3 (clean PAT artifacts: whitespace, null strings, mixed types)
- R4 (course-code canonicalization)
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pat import normalize as N


# -------- is_nullish / clean_string --------


def test_is_nullish_handles_pandas_nan():
    assert N.is_nullish(float("nan"))


def test_is_nullish_handles_strings():
    for s in ("", " ", "null", "NULL", "nan", "NaN", "none", "NA"):
        assert N.is_nullish(s), f"expected {s!r} to be nullish"


def test_clean_string_strips():
    assert N.clean_string("   hello  ") == "hello"


def test_clean_string_nullish_to_empty():
    assert N.clean_string("null") == ""
    assert N.clean_string(None) == ""


# -------- clean_course_code (R3, R4) --------


def test_clean_course_code_strips_heavy_whitespace():
    # The PAT export observed up to ~300 chars of leading whitespace.
    raw = " " * 300 + "CE 464"
    assert N.clean_course_code(raw) == "CE 464"


def test_clean_course_code_normalizes_variants():
    for raw in ("CE 282", "ce 282", "ce-282", "CE_282", "  CE282 ", "CE282"):
        assert N.clean_course_code(raw) == "CE 282"


def test_clean_course_code_handles_three_letter_prefix():
    assert N.clean_course_code("ENE 300") == "ENE 300"
    assert N.clean_course_code("con-280") == "CON 280"


def test_clean_course_code_empty_on_null():
    assert N.clean_course_code(None) == ""
    assert N.clean_course_code("null") == ""


# -------- course_key (R4) --------


def test_course_key_variants_resolve_to_one_form():
    variants = ["CE 282", "ce-282", "  CE282 ", "ce_282"]
    keys = {N.course_key(v) for v in variants}
    assert keys == {"CE282"}


def test_course_key_three_letter_prefix():
    assert N.course_key("ENE 300") == "ENE300"
    assert N.course_key("con 280") == "CON280"


# -------- normalize_suboutcome (R3) --------


def test_normalize_suboutcome_handles_mixed_types():
    assert N.normalize_suboutcome(1.1) == "1.1"
    assert N.normalize_suboutcome("4.1") == "4.1"
    assert N.normalize_suboutcome("4.10") == "4.1"
    assert N.normalize_suboutcome(2) == "2"


def test_normalize_suboutcome_empty_on_null():
    assert N.normalize_suboutcome("null") == ""
    assert N.normalize_suboutcome(float("nan")) == ""


# -------- parse_percent --------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("86%", 86.0),
        ("86", 86.0),
        (86, 86.0),
        (0.86, 86.0),
        ("70 %", 70.0),
        ("100%", 100.0),
    ],
)
def test_parse_percent_accepts(raw, expected):
    assert N.parse_percent(raw) == pytest.approx(expected)


def test_parse_percent_rejects_garbage():
    assert N.parse_percent("not a number") is None


def test_parse_percent_null_returns_none():
    assert N.parse_percent("nan") is None
    assert N.parse_percent("") is None
    assert N.parse_percent(None) is None


# -------- parse_semester --------


def test_parse_semester_handles_long_form():
    assert N.parse_semester("Spring 2024") == (2024, "S")
    assert N.parse_semester("Fall 2024") == (2024, "F")
    assert N.parse_semester("spring 2020") == (2020, "S")


def test_parse_semester_handles_short_form():
    assert N.parse_semester("S24") == (2024, "S")
    assert N.parse_semester("F 23") == (2023, "F")


def test_parse_semester_unparseable_returns_none():
    assert N.parse_semester("garbage") == (None, None)
    assert N.parse_semester("") == (None, None)


def test_semester_sort_key_orders_correctly():
    # Spring < Fall of same year; later years > earlier years.
    keys = [
        N.semester_sort_key(*N.parse_semester(s))
        for s in ("Spring 2020", "Fall 2020", "Spring 2021", "Fall 2021")
    ]
    assert keys == sorted(keys)


# -------- parse_date / parse_int --------


def test_parse_date_handles_pat_format():
    assert N.parse_date("05/15/2020") == date(2020, 5, 15)


def test_parse_date_handles_iso():
    assert N.parse_date("2020-05-15") == date(2020, 5, 15)


def test_parse_date_null_returns_none():
    assert N.parse_date("null") is None
    assert N.parse_date("") is None


def test_parse_int_basic():
    assert N.parse_int("53") == 53
    assert N.parse_int(53) == 53
    assert N.parse_int(53.0) == 53


def test_parse_int_null_returns_none():
    assert N.parse_int("null") is None
    assert N.parse_int(float("nan")) is None


# -------- rename_to_canonical --------


def _raw_row():
    """A single raw-shaped row covering every required column."""
    return {
        "course": "   CE 282",
        "suboutcome": 1.1,
        "semester": "Spring 2020",
        "assigned-to": "Aziz, Tarek",
        "submitted-by": "Aziz, Tarek",
        "performance-indicator": "70%",
        "threshold": 4,
        "scale": 6,
        "performance": "82%",
        "score-data": "6 4 6",
        "scores_meeting_threshold": 28,
        "total_scores": 34,
        "measurement-result-updated": "05/15/2020",
        "comments": "ok",
        "actions-taken": "none",
        "measure-description": "Exam 2 Q2c",
    }


def test_rename_to_canonical_renames_all_columns():
    df = pd.DataFrame([_raw_row()])
    out = N.rename_to_canonical(df)
    assert set(out.columns) == set(N.RAW_TO_CANONICAL.values())


def test_rename_to_canonical_case_insensitive():
    raw = _raw_row()
    raw_upper = {k.upper(): v for k, v in raw.items()}
    out = N.rename_to_canonical(pd.DataFrame([raw_upper]))
    assert "instructor" in out.columns  # was Assigned-To


def test_rename_to_canonical_missing_column_raises():
    raw = _raw_row()
    del raw["performance"]
    with pytest.raises(N.IngestError) as exc:
        N.rename_to_canonical(pd.DataFrame([raw]))
    assert "performance" in str(exc.value)


# -------- clean_dataframe --------


def test_clean_dataframe_full_row():
    df = pd.DataFrame([_raw_row()])
    out = N.clean_dataframe(df, program="CE")

    row = out.iloc[0]
    assert row["program"] == "CE"
    assert row["course"] == "CE 282"
    assert row["course_key"] == "CE282"
    assert row["suboutcome"] == "1.1"
    assert row["semester"] == "Spring 2020"
    assert row["semester_year"] == 2020
    assert row["semester_season"] == "S"
    assert row["performance_indicator"] == pytest.approx(70.0)
    assert row["performance"] == pytest.approx(82.0)
    assert row["measurement_date"] == date(2020, 5, 15)
    assert row["instructor"] == "Aziz, Tarek"


def test_clean_dataframe_handles_null_strings():
    raw = _raw_row()
    raw["performance"] = "null"
    raw["comments"] = ""
    raw["actions-taken"] = "null"
    out = N.clean_dataframe(pd.DataFrame([raw]), program="CE")
    row = out.iloc[0]
    assert row["performance"] is None
    assert row["comments"] == ""
    assert row["actions_taken"] == ""


def test_clean_dataframe_handles_heavy_whitespace_course():
    raw = _raw_row()
    raw["course"] = " " * 300 + "CE 464"
    out = N.clean_dataframe(pd.DataFrame([raw]), program="CE")
    assert out.iloc[0]["course"] == "CE 464"
    assert out.iloc[0]["course_key"] == "CE464"


def test_clean_dataframe_handles_mixed_suboutcome_types():
    raw1 = _raw_row()
    raw1["suboutcome"] = 1.1  # float
    raw2 = _raw_row()
    raw2["suboutcome"] = "4.1"  # string
    out = N.clean_dataframe(pd.DataFrame([raw1, raw2]), program="CE")
    assert list(out["suboutcome"]) == ["1.1", "4.1"]


def test_clean_dataframe_rejects_unknown_program():
    with pytest.raises(N.IngestError):
        N.clean_dataframe(pd.DataFrame([_raw_row()]), program="XYZ")


# -------- check_invariants --------


def test_check_invariants_passes_on_clean_data():
    df = pd.DataFrame([_raw_row()])
    clean = N.clean_dataframe(df, program="CE")
    N.check_invariants(clean)  # should not raise
