"""
Layer 2: UIAutomation-based text capture.
Walks the accessibility tree of the currently active window
to extract all visible text without requiring manual selection.

Supported apps: Adobe/Sumatra PDF, browsers, standard Win32 apps.
Falls back gracefully for canvas-rendered or non-accessible apps.
"""
import uiautomation as auto
from ..config import MAX_CAPTURE_CHARS


def capture_active_window_text() -> str | None:
    """
    Get all text from the currently focused window via UIAutomation.
    Returns concatenated text content, or None if nothing found.
    """
    try:
        window = auto.GetForegroundControl()
        if window is None:
            return None
        texts = _collect_texts(window)
        if not texts:
            return None
        result = "\n".join(texts)
        return result[:MAX_CAPTURE_CHARS]
    except Exception:
        return None


def _collect_texts(control, depth: int = 0, max_depth: int = 12) -> list[str]:
    """Recursively collect text from all child controls."""
    if depth > max_depth:
        return []

    results = []

    # Direct text value
    try:
        name = control.Name
        if name and name.strip():
            results.append(name.strip())
    except Exception:
        pass

    # DocumentText pattern (PDF readers, rich text editors)
    try:
        text_pattern = control.GetTextPattern()
        if text_pattern:
            text = text_pattern.DocumentRange.GetText(-1)
            if text and text.strip():
                results.append(text.strip())
            return results  # no need to recurse into children
    except Exception:
        pass

    # Recurse into children
    try:
        for child in control.GetChildren():
            results.extend(_collect_texts(child, depth + 1, max_depth))
    except Exception:
        pass

    return results
