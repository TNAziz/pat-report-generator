"""Unit tests for pat.render.html."""

from __future__ import annotations

from pat.render import html as H
from pat.render.model import Report
from tests.report_fixtures import (
    make_course_report, make_suboutcome_lookup, make_coverage_report,
)


def test_render_returns_full_document():
    out = H.render(make_course_report())
    assert out.startswith("<!DOCTYPE html>")
    assert "<html" in out and "</html>" in out
    assert "<title>CE 282</title>" in out


def test_render_body_skips_wrapper():
    body = H.render_body(make_course_report())
    assert "<!DOCTYPE" not in body
    assert "<html" not in body
    assert body.startswith("<h1>")


def test_render_includes_stylesheet():
    out = H.render(make_course_report())
    assert "<style>" in out
    # Print-friendly CSS markers.
    assert "@page" in out
    assert "below-threshold" in out


def test_render_marks_below_threshold():
    out = H.render(make_course_report())
    # The Spring 2021 1.1 row has below_threshold=True, so its percent
    # cells get the .below-threshold class.
    assert '<span class="below-threshold">' in out


def test_render_escapes_html_in_content():
    """User-supplied strings must not break out of HTML."""
    r = make_course_report()
    # Inject some HTML into a comment field.
    r.sections[0].semesters[0].measures[0].comments = "<script>alert('x')</script>"
    out = H.render(r)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_suboutcome_lookup():
    out = H.render(make_suboutcome_lookup())
    assert "<h1>CE 488</h1>" in out
    # The narrative markdown should be converted to a real <ul>.
    assert "<ul>" in out and "<li>" in out


def test_render_coverage_includes_svg_chart():
    out = H.render(make_coverage_report())
    # Inline SVG (no remote image refs).
    assert "<svg" in out
    assert "</svg>" in out
    # Legend includes each program.
    for prog in ("CE", "CON", "ENE"):
        assert prog in out


def test_render_empty_report():
    out = H.render(Report(title="Empty"))
    assert "<h1>Empty</h1>" in out
    # Should not crash even with no sections / tables / narrative.
