"""PDF renderer, with a fallback so PDF export works without GTK.

Two backends produce the same PDF from the same HTML:

``weasyprint``
    Preferred. Highest fidelity, but depends on native GTK / Pango / Cairo
    libraries that aren't present by default on Windows.

``browser``
    Fallback. Drives an already-installed Chromium-family browser
    (Microsoft Edge, Google Chrome, or Chromium) in headless mode via
    ``--print-to-pdf``. Edge ships with Windows, so this backend needs no
    installation and no administrator rights.

Backend choice is resolved lazily and cached, so :func:`is_available` stays
cheap to call from Streamlit reruns. Override the automatic choice with the
``PAT_PDF_BACKEND`` environment variable (``auto`` / ``weasyprint`` /
``browser``), and point at a specific browser executable with
``PAT_PDF_BROWSER``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from . import html as html_renderer
from .model import Report


class PDFUnavailable(RuntimeError):
    """Raised when no PDF backend can run on this machine."""


WEASYPRINT = "weasyprint"
BROWSER = "browser"

# Executable names / absolute paths tried in order when locating a
# Chromium-family browser. Windows installs land in Program Files rather than
# on PATH, so the well-known locations are probed explicitly.
_BROWSER_CANDIDATES = (
    # PATH lookups (Linux, macOS via Homebrew, Windows shims)
    "msedge",
    "chrome",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    # Windows
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    # macOS
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)

#: How long to wait for the browser to produce the PDF. The wait normally
#: ends as soon as the file is written, so this only bounds a genuinely
#: stuck browser. Override with ``PAT_PDF_TIMEOUT`` (seconds).
_PRINT_TIMEOUT_SECONDS = 120

#: How often to check whether the PDF has appeared, in seconds.
_POLL_INTERVAL = 0.25

# Resolved lazily by _resolve(); None means "not checked yet".
_BACKEND_CACHE: Optional[tuple[Optional[str], str]] = None


# ---------------------------------------------------------------------------
# Backend discovery
# ---------------------------------------------------------------------------

def _weasyprint_error() -> Optional[str]:
    """Return None if WeasyPrint imports cleanly, else a short reason."""
    try:
        import weasyprint  # noqa: F401
        return None
    except Exception as exc:  # OSError on missing native libs, and anything else
        msg = str(exc)
        low = msg.lower()
        if "libgobject" in low or "pango" in low or "cairo" in low or "gobject" in low:
            return "WeasyPrint's native GTK/Pango libraries are not installed"
        return f"WeasyPrint failed to load: {msg}"


def find_browser() -> Optional[str]:
    """Return the path to a usable Chromium-family browser, or None.

    ``PAT_PDF_BROWSER`` wins if set and pointing at something runnable.
    """
    override = os.environ.get("PAT_PDF_BROWSER", "").strip()
    if override:
        found = shutil.which(override)
        if found:
            return found
        if Path(override).is_file():
            return override
        return None

    for candidate in _BROWSER_CANDIDATES:
        if os.sep in candidate or (os.altsep and os.altsep in candidate):
            if Path(candidate).is_file():
                return candidate
        else:
            found = shutil.which(candidate)
            if found:
                return found
    return None


def _resolve() -> tuple[Optional[str], str]:
    """Return ``(backend_name, reason)``; backend_name is None if unavailable.

    ``reason`` is a human-readable explanation, empty when a backend was found.
    The result is cached; call :func:`reset_cache` after changing the
    environment (tests do this).
    """
    global _BACKEND_CACHE
    if _BACKEND_CACHE is not None:
        return _BACKEND_CACHE

    preference = os.environ.get("PAT_PDF_BACKEND", "auto").strip().lower() or "auto"

    if preference == WEASYPRINT:
        err = _weasyprint_error()
        result = (WEASYPRINT, "") if err is None else (None, err)
    elif preference == BROWSER:
        exe = find_browser()
        result = (BROWSER, "") if exe else (None, _no_browser_message())
    else:
        if _weasyprint_error() is None:
            result = (WEASYPRINT, "")
        elif find_browser():
            result = (BROWSER, "")
        else:
            result = (None, f"{_weasyprint_error()}, and {_no_browser_message()}")

    _BACKEND_CACHE = result
    return result


def _no_browser_message() -> str:
    return (
        "no Chromium-family browser (Microsoft Edge, Google Chrome, or "
        "Chromium) could be found for the fallback PDF backend"
    )


def reset_cache() -> None:
    """Forget the resolved backend so the next call re-detects."""
    global _BACKEND_CACHE
    _BACKEND_CACHE = None


# ---------------------------------------------------------------------------
# Public API used by the pages
# ---------------------------------------------------------------------------

def active_backend() -> Optional[str]:
    """Return ``'weasyprint'``, ``'browser'``, or None if PDF is unavailable."""
    return _resolve()[0]


def is_available() -> bool:
    """Return True if some backend can render a PDF on this machine."""
    return active_backend() is not None


def backend_label() -> str:
    """Short description of the active backend, for UI captions."""
    backend = active_backend()
    if backend == WEASYPRINT:
        return "WeasyPrint"
    if backend == BROWSER:
        exe = find_browser() or "browser"
        return f"headless {Path(exe).stem}"
    return "unavailable"


def unavailable_reason() -> str:
    """Explain why PDF isn't available; empty string when it is."""
    backend, reason = _resolve()
    if backend is not None:
        return ""
    return (
        f"PDF export is unavailable: {reason}. Install the GTK runtime for "
        "WeasyPrint (see README), or install Microsoft Edge or Google "
        "Chrome so the fallback renderer can be used. The Markdown, Word, "
        "and HTML downloads are unaffected."
    )


def render(report: Report) -> bytes:
    """Render a Report to PDF bytes using whichever backend is available.

    Raises :class:`PDFUnavailable` if neither backend can run. Callers should
    check :func:`is_available` first and surface :func:`unavailable_reason`.
    """
    backend, _ = _resolve()
    if backend is None:
        raise PDFUnavailable(unavailable_reason())

    return render_html(html_renderer.render(report))


def render_html(html_str: str) -> bytes:
    """Render an already-rendered HTML document to PDF bytes.

    Split out from :func:`render` so callers that already hold the HTML --
    and want to cache on it, since it is a plain hashable string -- do not
    have to rebuild it.
    """
    backend, _ = _resolve()
    if backend is None:
        raise PDFUnavailable(unavailable_reason())
    if backend == WEASYPRINT:
        return _render_weasyprint(html_str)
    return _render_browser(html_str)


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def _render_weasyprint(html_str: str) -> bytes:
    # Imported locally so module import never triggers native lib loading.
    from weasyprint import HTML
    return HTML(string=html_str).write_pdf()


def _print_timeout() -> float:
    """Timeout in seconds, overridable via ``PAT_PDF_TIMEOUT``."""
    raw = os.environ.get("PAT_PDF_TIMEOUT", "").strip()
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return float(_PRINT_TIMEOUT_SECONDS)


def _popen_extras() -> dict:
    """Windows-only flags that keep a console window from flashing up."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flags} if flags else {}


def _browser_command(exe: str, tmpdir: Path, src: Path, out: Path) -> list:
    return [
        exe,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        # A throwaway profile: without it the command silently hands off to
        # an already-running Edge/Chrome window and writes no PDF.
        f"--user-data-dir={tmpdir / 'profile'}",
        # Keep the run from reaching the network or a crash-report service,
        # either of which can leave the process alive after the PDF is done.
        "--disable-crash-reporter",
        "--disable-breakpad",
        "--no-crash-upload",
        f"--crash-dumps-dir={tmpdir / 'crash'}",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-sync",
        "--no-service-autorun",
        "--metrics-recording-only",
        "--mute-audio",
        # Chrome renamed this flag; unknown flags are ignored, so pass both.
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={out}",
        src.as_uri(),
    ]


def _wait_for_pdf(proc, out: Path, timeout: float) -> bool:
    """Wait until the PDF is completely written, or the browser gives up.

    Returns True if ``out`` looks finished, False on timeout.

    Waiting on process exit alone is not enough on Windows: Edge and Chrome
    leave helper processes (the crash handler in particular) running after
    the parent returns, so a wait that keys off the pipes or the process
    tree can block long after the PDF is on disk. Watching the file itself
    and requiring its size to hold steady across two polls means the normal
    case finishes in about a second.
    """
    deadline = time.monotonic() + timeout
    last_size = -1
    while time.monotonic() < deadline:
        exited = proc.poll() is not None
        size = out.stat().st_size if out.is_file() else 0
        if size > 0 and size == last_size:
            return True
        last_size = size
        if exited:
            # The browser is gone; one more look settles whether it wrote.
            return size > 0
        time.sleep(_POLL_INTERVAL)
    return out.is_file() and out.stat().st_size > 0


def _terminate(proc) -> None:
    """Stop the browser, escalating to kill, and never raise."""
    for stop in (proc.terminate, proc.kill):
        if proc.poll() is not None:
            return
        try:
            stop()
            proc.wait(timeout=5)
        except Exception:
            continue


def _render_browser(html_str: str) -> bytes:
    """Print HTML to PDF with a headless Chromium-family browser."""
    exe = find_browser()
    if not exe:
        raise PDFUnavailable(unavailable_reason())

    timeout = _print_timeout()
    name = Path(exe).stem
    # ignore_cleanup_errors: on Windows the browser can still hold a handle
    # inside the profile directory when we let go of it.
    with tempfile.TemporaryDirectory(
        prefix="pat-pdf-", ignore_cleanup_errors=True
    ) as tmp:
        tmpdir = Path(tmp)
        src = tmpdir / "report.html"
        out = tmpdir / "report.pdf"
        log = tmpdir / "browser.log"
        src.write_text(html_str, encoding="utf-8")

        proc = None
        try:
            # Log to a file rather than a pipe. Child processes inherit pipe
            # handles, so capture_output would keep us blocked on a lingering
            # helper process even once the PDF is written.
            with open(log, "wb") as sink:
                proc = subprocess.Popen(
                    _browser_command(exe, tmpdir, src, out),
                    stdout=sink,
                    stderr=sink,
                    stdin=subprocess.DEVNULL,
                    **_popen_extras(),
                )
            finished = _wait_for_pdf(proc, out, timeout)
        except OSError as exc:
            raise PDFUnavailable(f"Could not run {exe}: {exc}") from exc
        finally:
            if proc is not None:
                _terminate(proc)

        blob = out.read_bytes() if out.is_file() else b""

        if not blob:
            detail = _log_tail(log)
            if not finished:
                raise PDFUnavailable(
                    f"{name} did not produce a PDF within {timeout:g} seconds"
                    f"{detail}. If this machine's browser is managed by policy, "
                    "try setting PAT_PDF_BROWSER to another Chromium-family "
                    "browser, raise PAT_PDF_TIMEOUT, or install WeasyPrint's "
                    "Pango dependency (see README) to use that backend instead."
                )
            raise PDFUnavailable(f"{name} produced no PDF{detail}.")

    if not blob.startswith(b"%PDF-"):
        raise PDFUnavailable(f"{name} wrote a file that is not a PDF.")
    return blob


def _log_tail(log: Path, limit: int = 200) -> str:
    """Last meaningful line of the browser's output, for an error message."""
    try:
        text = log.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return f" ({lines[-1][:limit]})" if lines else ""
