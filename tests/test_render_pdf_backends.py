"""Backend-selection tests for pat.render.pdf.

These exercise the WeasyPrint / headless-browser choice without needing
either one installed, plus one real end-to-end print when a browser is
actually present on the machine running the suite.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pat.render import pdf as P
from pat.render.model import Report
from tests.report_fixtures import make_course_report


@pytest.fixture(autouse=True)
def _clean_cache():
    """Backend resolution is cached; start and end every test with it clear."""
    P.reset_cache()
    yield
    P.reset_cache()


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def test_prefers_weasyprint_when_it_loads(monkeypatch):
    monkeypatch.delenv("PAT_PDF_BACKEND", raising=False)
    monkeypatch.setattr(P, "_weasyprint_error", lambda: None)
    monkeypatch.setattr(P, "find_browser", lambda: "/usr/bin/chromium")
    assert P.active_backend() == P.WEASYPRINT
    assert P.is_available()
    assert P.unavailable_reason() == ""


def test_falls_back_to_browser_when_weasyprint_missing(monkeypatch):
    monkeypatch.delenv("PAT_PDF_BACKEND", raising=False)
    monkeypatch.setattr(P, "_weasyprint_error", lambda: "no libgobject")
    monkeypatch.setattr(P, "find_browser", lambda: "/usr/bin/msedge")
    assert P.active_backend() == P.BROWSER
    assert P.is_available()
    assert P.unavailable_reason() == ""
    assert "msedge" in P.backend_label()


def test_unavailable_when_neither_backend_exists(monkeypatch):
    monkeypatch.delenv("PAT_PDF_BACKEND", raising=False)
    monkeypatch.setattr(P, "_weasyprint_error", lambda: "no libgobject")
    monkeypatch.setattr(P, "find_browser", lambda: None)
    assert P.active_backend() is None
    assert not P.is_available()
    reason = P.unavailable_reason()
    assert "libgobject" in reason
    assert "Edge" in reason
    # The other three formats must not be implicated.
    assert "Markdown, Word, and HTML downloads are unaffected" in reason


def test_render_raises_when_unavailable(monkeypatch):
    monkeypatch.delenv("PAT_PDF_BACKEND", raising=False)
    monkeypatch.setattr(P, "_weasyprint_error", lambda: "no libgobject")
    monkeypatch.setattr(P, "find_browser", lambda: None)
    with pytest.raises(P.PDFUnavailable):
        P.render(make_course_report())


def test_env_var_forces_browser_backend(monkeypatch):
    monkeypatch.setenv("PAT_PDF_BACKEND", "browser")
    monkeypatch.setattr(P, "_weasyprint_error", lambda: None)  # would win on auto
    monkeypatch.setattr(P, "find_browser", lambda: "/usr/bin/chromium")
    assert P.active_backend() == P.BROWSER


def test_env_var_forces_weasyprint_backend(monkeypatch):
    monkeypatch.setenv("PAT_PDF_BACKEND", "weasyprint")
    monkeypatch.setattr(P, "_weasyprint_error", lambda: "no libgobject")
    monkeypatch.setattr(P, "find_browser", lambda: "/usr/bin/chromium")
    # Explicit preference must not silently fall back.
    assert P.active_backend() is None
    assert "libgobject" in P.unavailable_reason()


def test_backend_resolution_is_cached(monkeypatch):
    monkeypatch.delenv("PAT_PDF_BACKEND", raising=False)
    calls = []

    def counting_error():
        calls.append(1)
        return None

    monkeypatch.setattr(P, "_weasyprint_error", counting_error)
    P.active_backend()
    P.active_backend()
    P.is_available()
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Browser discovery
# ---------------------------------------------------------------------------

def test_pat_pdf_browser_override_accepts_absolute_path(monkeypatch, tmp_path):
    fake = tmp_path / "my-browser"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("PAT_PDF_BROWSER", str(fake))
    assert P.find_browser() == str(fake)


def test_pat_pdf_browser_override_that_does_not_exist_finds_nothing(monkeypatch):
    monkeypatch.setenv("PAT_PDF_BROWSER", str(Path("nope") / "not-a-browser"))
    assert P.find_browser() is None


def test_find_browser_skips_windows_paths_on_posix(monkeypatch):
    """The Windows candidates must never be mistaken for PATH lookups."""
    monkeypatch.delenv("PAT_PDF_BROWSER", raising=False)
    monkeypatch.setattr(P, "_BROWSER_CANDIDATES", (
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ))
    if sys.platform.startswith("win"):
        pytest.skip("path semantics differ on Windows")
    assert P.find_browser() is None


# ---------------------------------------------------------------------------
# Real end-to-end print (only where a browser exists)
# ---------------------------------------------------------------------------

def _real_browser() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    bundled = Path("/opt/pw-browsers/chromium")
    return str(bundled) if bundled.is_file() else None


@pytest.mark.skipif(_real_browser() is None, reason="no browser on this machine")
def test_browser_backend_produces_a_real_pdf(monkeypatch):
    monkeypatch.setenv("PAT_PDF_BACKEND", "browser")
    monkeypatch.setenv("PAT_PDF_BROWSER", _real_browser())
    P.reset_cache()
    blob = P.render(make_course_report())
    assert blob[:5] == b"%PDF-"
    assert b"%%EOF" in blob[-2048:]
    assert len(blob) > 3000


@pytest.mark.skipif(_real_browser() is None, reason="no browser on this machine")
def test_browser_backend_handles_empty_report(monkeypatch):
    monkeypatch.setenv("PAT_PDF_BACKEND", "browser")
    monkeypatch.setenv("PAT_PDF_BROWSER", _real_browser())
    P.reset_cache()
    blob = P.render(Report(title="Empty"))
    assert blob[:5] == b"%PDF-"


def test_browser_backend_reports_failure_clearly(monkeypatch, tmp_path):
    """A browser that runs but writes nothing must raise, not return junk."""
    stub = tmp_path / "stub-browser"
    stub.write_text("#!/bin/sh\necho 'stub failed to start' >&2\nexit 0\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PAT_PDF_BACKEND", "browser")
    monkeypatch.setenv("PAT_PDF_BROWSER", str(stub))
    monkeypatch.setenv("PAT_PDF_TIMEOUT", "5")
    P.reset_cache()
    with pytest.raises(P.PDFUnavailable, match="did not produce a PDF"):
        P.render(make_course_report())


def test_browser_that_never_exits_still_yields_its_pdf(monkeypatch, tmp_path):
    """The Windows case: the PDF is written but the process lingers.

    Edge and Chrome leave helper processes running after the print is
    done, so waiting for process exit (or for its pipes to close) can hang
    long past the point where the file is complete. The wait must key off
    the file.
    """
    stub = tmp_path / "hanging-browser"
    stub.write_text(
        "#!/bin/sh\n"
        # Pull the --print-to-pdf=<path> value out of the arguments.
        'for arg in "$@"; do\n'
        '  case "$arg" in --print-to-pdf=*) out="${arg#--print-to-pdf=}" ;; esac\n'
        "done\n"
        'printf "%%PDF-1.4\\ntiny\\n%%%%EOF\\n" > "$out"\n'
        "sleep 300\n"
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PAT_PDF_BACKEND", "browser")
    monkeypatch.setenv("PAT_PDF_BROWSER", str(stub))
    monkeypatch.setenv("PAT_PDF_TIMEOUT", "30")
    P.reset_cache()

    started = time.monotonic()
    blob = P.render(make_course_report())
    elapsed = time.monotonic() - started

    assert blob.startswith(b"%PDF-")
    # Must return as soon as the file settles, not wait out the sleep.
    assert elapsed < 15


def test_timeout_is_configurable(monkeypatch):
    monkeypatch.delenv("PAT_PDF_TIMEOUT", raising=False)
    assert P._print_timeout() == float(P._PRINT_TIMEOUT_SECONDS)
    monkeypatch.setenv("PAT_PDF_TIMEOUT", "7.5")
    assert P._print_timeout() == 7.5
    for bad in ("", "abc", "0", "-3"):
        monkeypatch.setenv("PAT_PDF_TIMEOUT", bad)
        assert P._print_timeout() == float(P._PRINT_TIMEOUT_SECONDS)


def test_a_hung_browser_is_not_left_running(monkeypatch, tmp_path):
    """After a salvaged render the browser process must be gone."""
    stub = tmp_path / "hanging-browser-2"
    stub.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in --print-to-pdf=*) out="${arg#--print-to-pdf=}" ;; esac\n'
        "done\n"
        'printf "%%PDF-1.4\\ntiny\\n%%%%EOF\\n" > "$out"\n'
        "sleep 300\n"
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PAT_PDF_BACKEND", "browser")
    monkeypatch.setenv("PAT_PDF_BROWSER", str(stub))
    monkeypatch.setenv("PAT_PDF_TIMEOUT", "30")
    P.reset_cache()

    seen = {}
    real_popen = subprocess.Popen

    def tracking_popen(*a, **kw):
        proc = real_popen(*a, **kw)
        seen["proc"] = proc
        return proc

    monkeypatch.setattr(subprocess, "Popen", tracking_popen)
    P.render(make_course_report())
    assert seen["proc"].poll() is not None


def test_render_html_takes_a_prebuilt_document(monkeypatch):
    """The page layer caches on the HTML string, so this entry point matters."""
    monkeypatch.setattr(P, "_weasyprint_error", lambda: None)
    monkeypatch.setattr(P, "_render_weasyprint", lambda html: b"%PDF-" + html.encode())
    P.reset_cache()
    assert P.render_html("<p>hi</p>") == b"%PDF-<p>hi</p>"


def test_render_html_raises_when_no_backend(monkeypatch):
    monkeypatch.setattr(P, "_weasyprint_error", lambda: "no libgobject")
    monkeypatch.setattr(P, "find_browser", lambda: None)
    P.reset_cache()
    with pytest.raises(P.PDFUnavailable):
        P.render_html("<p>hi</p>")
