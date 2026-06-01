"""Hand-crafted Report fixtures used by renderer tests.

These are deliberately tiny and exercise every field of the Report IR
so renderer tests can run quickly without depending on the data layer.
"""

from __future__ import annotations

from datetime import date

from pat.render.model import (
    Chart,
    ChartSeries,
    Heatmap,
    MeasureDetail,
    NamedTable,
    NarrativeBlock,
    ProgramSection,
    Report,
    SemesterSection,
    SummaryRow,
)


def make_course_report() -> Report:
    """A Course Report for CE 282 across the CE and CON programs."""
    ce_summary = [
        SummaryRow("Spring 2020", "1.1", 70.0, 82.0, below_threshold=False),
        SummaryRow("Spring 2021", "1.1", 70.0, 60.0, below_threshold=True),
        SummaryRow("Fall 2023", "2.1", 70.0, 85.0, below_threshold=False),
    ]
    ce_semesters = [
        SemesterSection(
            semester="Fall 2023",
            instructor="Aziz, Tarek",
            measures=[
                MeasureDetail(
                    suboutcome="2.1",
                    measure_description="Exam 2 Q2c",
                    performance_indicator=70.0,
                    performance=85.0,
                    n=34,
                    comments="Solid performance.",
                    actions_taken="Continue monitoring.",
                    below_threshold=False,
                ),
            ],
        ),
        SemesterSection(
            semester="Spring 2021",
            instructor="Aziz, Tarek",
            measures=[
                MeasureDetail(
                    suboutcome="1.1",
                    measure_description="Final Exam Q15",
                    performance_indicator=70.0,
                    performance=60.0,
                    n=53,
                    comments="Many students missed step 2 of the derivation.",
                    actions_taken="Add worked example to lecture 8.",
                    below_threshold=True,
                ),
            ],
        ),
    ]
    con_summary = [
        SummaryRow("Spring 2020", "1.1", 70.0, 90.0, below_threshold=False),
    ]
    con_semesters = [
        SemesterSection(
            semester="Spring 2020",
            instructor="Han, Kook",
            measures=[
                MeasureDetail(
                    suboutcome="1.1",
                    measure_description="HW Set 4",
                    performance_indicator=70.0,
                    performance=90.0,
                    n=20,
                    comments="",
                    actions_taken="",
                    below_threshold=False,
                ),
            ],
        ),
    ]
    return Report(
        title="CE 282",
        subtitle="Spring 2020 – Spring 2026",
        generated_on=date(2026, 5, 29),
        sections=[
            ProgramSection(
                program_code="CE",
                program_label="Civil Engineering",
                summary=ce_summary,
                semesters=ce_semesters,
            ),
            ProgramSection(
                program_code="CON",
                program_label="Construction Engineering",
                summary=con_summary,
                semesters=con_semesters,
            ),
        ],
    )


def make_suboutcome_lookup() -> Report:
    """A Sub-Outcome Lookup report for CE 488."""
    return Report(
        title="CE 488",
        subtitle=None,
        generated_on=date(2026, 5, 29),
        narrative=[
            NarrativeBlock(
                heading="Programs",
                body_markdown="CE / ENE",
            ),
            NarrativeBlock(
                heading="Sub-Outcomes",
                body_markdown=(
                    "- **1.2:** Formulate the solution to engineering problems.\n"
                    "- **2.1:** Analyze engineering design with consideration of "
                    "economic, environmental, social, and/or other relevant "
                    "constraints and/or specifications.\n"
                    "- **2.2:** Develop engineering designs that meet economic, "
                    "environmental, social, and/or other relevant constraints "
                    "and/or specifications."
                ),
            ),
        ],
    )


def make_coverage_report() -> Report:
    """A Coverage Check report for Spring 2025 with trend chart."""
    missing_table = NamedTable(
        title="Missing assessments in Spring 2025",
        columns=["Program", "Course"],
        rows=[
            ["CE", "CE 339"],
            ["CE", "CE 477"],
            ["CON", "CE 469"],
            ["ENE", "CE 477"],
            ["ENE", "CE 481"],
        ],
    )
    summary_table = NamedTable(
        title="Semester summary",
        columns=["Program", "Total", "Assessed", "Missing", "% assessed"],
        rows=[
            ["CE",  "7", "5", "2", "71.4%"],
            ["CON", "3", "2", "1", "66.7%"],
            ["ENE", "4", "2", "2", "50.0%"],
        ],
        footnote="A course counts as 'missing' when every row has a blank submitter.",
    )
    chart = Chart(
        title="Coverage trend by year",
        x_label="Year",
        y_label="% assessed",
        series=[
            ChartSeries(name="CE",  x=[2020, 2021, 2022, 2023, 2024, 2025],
                                     y=[100, 100, 100, 100, 78, 71]),
            ChartSeries(name="CON", x=[2020, 2021, 2022, 2023, 2024, 2025],
                                     y=[93,  93,  100, 100, 60, 67]),
            ChartSeries(name="ENE", x=[2020, 2021, 2022, 2023, 2024, 2025],
                                     y=[100, 100, 100, 100, 57, 50]),
        ],
    )
    return Report(
        title="Coverage Check",
        subtitle="Spring 2025",
        generated_on=date(2026, 5, 29),
        tables=[missing_table, summary_table],
        charts=[chart],
    )


def make_suboutcome_coverage() -> Report:
    """Sub-outcome coverage heatmap, one per program (CE/CON/ENE).

    Sub-outcome list matches the 13 codes actually present in the NC
    State CCEE PAT exports (1.1-7.2). Year range 2020-2025.
    """
    import datetime
    years = ["2020", "2021", "2022", "2023", "2024", "2025"]
    rows = ["1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "3.3",
            "4.1", "5.1", "6.1", "6.2", "7.1", "7.2"]

    # Hand-crafted counts that mimic realistic CCEE coverage patterns:
    # core outcomes (1, 2, 6) get heavy coverage; communication (3) is
    # spread across writing-intensive courses; ethics (4) and teamwork
    # (5) appear less often; new-knowledge (7) is the lightest.
    ce_vals = [
        # 2020 21 22 23 24 25
        [3, 3, 4, 3, 3, 2],   # 1.1
        [2, 3, 2, 3, 2, 1],   # 1.2
        [4, 4, 4, 3, 4, 3],   # 2.1
        [2, 2, 1, 2, 2, 1],   # 2.2
        [2, 3, 2, 2, 2, 1],   # 3.1
        [2, 2, 2, 1, 2, 1],   # 3.2
        [1, 1, 1, 1, 1, 1],   # 3.3
        [1, 1, 1, 0, 2, 1],   # 4.1
        [1, 1, 1, 1, 1, 1],   # 5.1
        [3, 3, 3, 2, 3, 2],   # 6.1
        [2, 2, 2, 1, 2, 1],   # 6.2
        [1, 1, 0, 1, 1, 0],   # 7.1
        [0, 1, 0, 0, 1, 0],   # 7.2
    ]
    con_vals = [
        [2, 2, 2, 1, 2, 1],   # 1.1
        [1, 1, 1, 1, 1, 1],   # 1.2
        [2, 2, 2, 2, 2, 1],   # 2.1
        [1, 1, 0, 1, 1, 0],   # 2.2
        [1, 1, 1, 1, 1, 0],   # 3.1
        [1, 1, 0, 1, 1, 0],   # 3.2
        [1, 0, 1, 0, 0, 0],   # 3.3
        [0, 1, 0, 1, 1, 0],   # 4.1
        [1, 1, 0, 1, 1, 0],   # 5.1
        [1, 1, 1, 1, 1, 1],   # 6.1
        [1, 1, 1, 0, 1, 0],   # 6.2
        [0, 0, 1, 0, 1, 0],   # 7.1
        [0, 0, 0, 0, 1, 0],   # 7.2
    ]
    ene_vals = [
        [1, 1, 1, 1, 1, 1],   # 1.1
        [1, 1, 0, 1, 1, 0],   # 1.2
        [2, 2, 2, 1, 2, 1],   # 2.1
        [1, 0, 1, 1, 1, 0],   # 2.2
        [1, 1, 1, 1, 1, 0],   # 3.1
        [1, 1, 0, 0, 1, 0],   # 3.2
        [0, 0, 1, 0, 0, 0],   # 3.3
        [0, 0, 0, 1, 1, 0],   # 4.1
        [0, 1, 0, 0, 1, 0],   # 5.1
        [2, 2, 2, 1, 2, 1],   # 6.1
        [1, 1, 1, 0, 1, 0],   # 6.2
        [0, 1, 0, 0, 0, 0],   # 7.1
        [0, 0, 0, 0, 1, 0],   # 7.2
    ]

    def make_h(program, vals):
        return Heatmap(
            title=f"{program}: sub-outcome assessment counts, 2020-2025",
            row_label="Sub-Outcome",
            col_label="Year",
            rows=rows,
            columns=years,
            values=vals,
            vmin=0,
            color_scheme="blues",
            value_format="{:.0f}",
            empty_marker="",
            caption=(
                "Cell value = number of assessment measurements. "
                "Empty cells indicate no data collected for that "
                "sub-outcome in that year."
            ),
        )

    return Report(
        title="Sub-Outcome Coverage",
        subtitle="2020 - 2025",
        generated_on=datetime.date(2026, 5, 29),
        heatmaps=[
            make_h("Civil Engineering",         ce_vals),
            make_h("Construction Engineering",  con_vals),
            make_h("Environmental Engineering", ene_vals),
        ],
    )
