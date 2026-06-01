"""PDF renderer.

WeasyPrint depends on native GTK / Pango / Cairo libraries that aren't
always present (notably on Windows machines that haven't installed the
GTK runtime). To keep the rest of the app working when WeasyPrint can't
load, this module imports WeasyPrint lazily inside ``render()`` and
exposes ``is_available()`` so UI code can disable the PDF download
button gracefully.
"""

from __future__ import annotations

from . import html as html_renderer
from .model import Report


class PDFUnavailable(RuntimeError):
    """Raised when WeasyPrint can't load its native dependencies."""


_AVAILABILITY_CACHE = None  # None = not checked yet


def is_available() -> bool:
    """Return True if WeasyPrint loads cleanly on this machine.

    Cheap to call repeatedly: the result is cached after the first
    import attempt.
    """
    global _AVAILABILITY_CACHE
    if _AVAILABILITY_CACHE is None:
        try:
            import weasyprint  # noqa: F401
            _AVAILABILITY_CACHE = True
        except Exception:
            # WeasyPrint raises OSError on missing native libs, but we
            # catch any import-time failure so the UI never crashes.
            _AVAILABILITY_CACHE = False
    return _AVAILABILITY_CACHE


def unavailable_reason() -> str:
    """Return a short human-readable explanation of why PDF isn't available.

    Returns an empty string when PDF rendering is available.
    """
    if is_available():
        return ""
    try:
        import weasyprint  # noqa: F401
        return ""
    except Exception as exc:
        msg = str(exc)
        if "libgobject" in msg or "pango" in msg.lower() or "cairo" in msg.lower():
            return (
                "WeasyPrint's native dependencies (GTK runtime) are not "
                "installed. PDF export is disabled until the GTK runtime "
                "is installed; see README for instructions."
            )
        return f"WeasyPrint failed to load: {exc}"


def render(report: Report) -> bytes:
    """Render a Report to PDF, returned as bytes.

    Raises :class:`PDFUnavailable` if WeasyPrint can't be imported on
    this machine. Callers should check ``is_available()`` first and
    surface ``unavailable_reason()`` to the user.
    """
    if not is_available():
        raise PDFUnavailable(unavailable_reason())
    # Import locally so module import never triggers native lib loading.
    from weasyprint import HTML
    html_str = html_renderer.render(report)
    return HTML(string=html_str).write_pdf()
