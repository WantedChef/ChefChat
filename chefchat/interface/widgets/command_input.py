"""Enhanced CommandInput with @ file tagging autocomplete for TUI."""

from __future__ import annotations

from pathlib import Path

from textual import events, on
from textual.widgets import Input

from chefchat.core.autocompletion.completers import PathCompleter


class CommandInput(Input):
    """Custom command input with @ file tagging autocomplete."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._path_completer = PathCompleter(Path.cwd())
        self._suggestions: list[str] = []
        self._suggestion_index = 0

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes to show @ file suggestions."""
        text = self.value
        cursor = self.cursor_position

        # Check if we should show file suggestions
        if "@" in text[:cursor]:
            at_index = text[:cursor].rfind("@")
            fragment = text[at_index + 1 : cursor]

            # Only show suggestions if no spaces after @
            if " " not in fragment:
                try:
                    # Get file suggestions
                    completions = self._path_completer.complete(fragment)
                    self._suggestions = [c.text for c in completions[:5]]

                    # Show suggestions in suggester (if available)
                    if self._suggestions and hasattr(self, "suggester"):
                        # Textual Input has built-in suggester support
                        pass
                except Exception:
                    self._suggestions = []
            else:
                self._suggestions = []
        else:
            self._suggestions = []

    def on_key(self, event: events.Key) -> None:
        """Handle key events for @ autocomplete."""
        # If we have suggestions and user presses Tab
        if self._suggestions and event.key == "tab":
            text = self.value
            cursor = self.cursor_position

            if "@" in text[:cursor]:
                at_index = text[:cursor].rfind("@")
                # Replace from @ to cursor with first suggestion
                suggestion = self._suggestions[0]
                new_text = text[:at_index] + "@" + suggestion + text[cursor:]
                self.value = new_text
                self.cursor_position = at_index + len(suggestion) + 1
                self._suggestions = []
                event.prevent_default()
                event.stop()
