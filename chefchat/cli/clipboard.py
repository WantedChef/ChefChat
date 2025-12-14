from __future__ import annotations

import pyperclip
from textual.app import App


def copy_selection_to_clipboard(app: App) -> None:
    """Copy selected text from app widgets to clipboard.

    Args:
        app: The Textual app instance.
    """
    selected_texts = []

    for widget in app.query("*"):
        if not hasattr(widget, "text_selection") or not widget.text_selection:
            continue

        selection = widget.text_selection

        try:
            result = widget.get_selection(selection)
        except Exception:
            continue

        if not result:
            continue

        selected_text, _ = result
        if selected_text.strip():
            selected_texts.append(selected_text)

    if not selected_texts:
        return

    combined_text = "\n".join(selected_texts)

    try:
        pyperclip.copy(combined_text)
        app.notify("Selection added to clipboard", severity="information", timeout=2)
    except Exception:
        app.notify(
            "Use Ctrl+c to copy selections in Vibe", severity="warning", timeout=3
        )


def paste_from_clipboard() -> str | None:
    """Get text from system clipboard.

    Returns:
        Clipboard text or None if clipboard is empty or unavailable.
    """
    try:
        text = pyperclip.paste()
        return text if text else None
    except Exception:
        return None


def copy_text_to_clipboard(text: str) -> bool:
    """Copy arbitrary text to clipboard.

    Args:
        text: Text to copy.

    Returns:
        True if copy succeeded, False otherwise.
    """
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def get_clipboard_available() -> bool:
    """Check if clipboard is available.

    Returns:
        True if clipboard operations are supported.
    """
    try:
        # Try a harmless paste operation to check availability
        pyperclip.paste()
        return True
    except Exception:
        return False
