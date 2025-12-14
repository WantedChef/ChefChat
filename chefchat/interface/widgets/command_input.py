"""Enhanced CommandInput with @ file tagging autocomplete for TUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from textual import on
from textual.binding import Binding
from textual.widgets import Input, OptionList

from chefchat.core.autocompletion.completers import CommandCompleter, PathCompleter


class SuggestionMenu(OptionList):
    """Dropdown menu for suggestions."""

    DEFAULT_CSS = """
    SuggestionMenu {
        layer: overlay;
        background: $surface;
        border: solid $accent;
        width: 100%;
        max-height: 10;
        display: none;
        dock: bottom;
        margin-bottom: 3; /* Height of input */
    }
    """


class CommandInput(Input):
    """Custom command input with @ file and / command autocompletion."""

    BINDINGS: ClassVar[list[Binding]] = [
        # Override default bindings to handle menu navigation
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "submit", "Submit", show=False),
        Binding("tab", "autocomplete", "Autocomplete", show=False),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._path_completer = PathCompleter(Path.cwd())

        # Standard commands matching REPL
        commands = [
            ("/help", "Show help menu"),
            ("/model", "Switch AI model"),
            ("/chef", "Kitchen status"),
            ("/wisdom", "Chef wisdom"),
            ("/roast", "Get roasted"),
            ("/fortune", "Dev fortune"),
            ("/plate", "Show plating"),
            ("/mode", "Current mode info"),
            ("/modes", "List modes"),
            ("/compact", "Compact conversation history"),
            ("/clear", "Clear history"),
            ("/status", "Show status"),
            ("/stats", "Show statistics"),
            ("/exit", "Exit application"),
            ("/quit", "Exit application"),
        ]
        self._command_completer = CommandCompleter(commands)
        self._suggestion_menu: SuggestionMenu | None = None
        self._current_completions: list[str] = []

    def on_mount(self) -> None:
        """Mount the suggestion menu to the screen/parent."""
        # accessing screen to mount overlay
        self._suggestion_menu = SuggestionMenu()
        self.screen.mount(self._suggestion_menu)
        # Trigger background indexing for path completion (warmup)
        # This prevents the first @ usage from returning empty results while preventing blocking
        self._path_completer.get_completions("@", 1)

    def on_unmount(self) -> None:
        if self._suggestion_menu:
            self._suggestion_menu.remove()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes to show suggestions."""
        if not self._suggestion_menu:
            return

        text = self.value
        cursor = self.cursor_position

        # Determine context
        completions = []

        # 1. Command completion ("/")
        if text.startswith("/") and " " not in text[:cursor]:
            completions = self._command_completer.get_completions(text, cursor)

        # 2. File completion ("@")
        elif "@" in text[:cursor]:
            # Extract relevant part (e.g. from last @)
            at_index = text[:cursor].rfind("@")
            fragment = text[at_index + 1 : cursor]
            # Simple heuristic: only complete if no spaces in fragment
            if " " not in fragment:
                # Need to simulate the text as if it starts with the fragment for PathCompleter?
                # Actually PathCompleter handles full text and cursor, or we pass context.
                # PathCompleter.get_completions expects text + cursor.
                # But our PathCompleter implementation expects standard params.
                # Let's verify PathCompleter.get_completions in completers.py
                # It calls _collect_matches(text, cursor_pos) which extracts partial logic.
                # So we can pass full text and cursor.
                completions = self._path_completer.get_completions(text, cursor)

        self._current_completions = completions

        # Update menu
        if completions:
            self._suggestion_menu.clear_options()
            self._suggestion_menu.add_options(completions)
            self._suggestion_menu.display = True
        else:
            self._suggestion_menu.display = False

    def action_cursor_up(self) -> None:
        """Move selection up in menu or standard behavior."""
        if self._suggestion_menu and self._suggestion_menu.display:
            self._suggestion_menu.action_cursor_up()
        else:
            # Input doesn't use up/down usually, maybe history?
            # For now, do nothing or let parent handle if bubble?
            pass

    def action_cursor_down(self) -> None:
        """Move selection down."""
        if self._suggestion_menu and self._suggestion_menu.display:
            self._suggestion_menu.action_cursor_down()

    def action_submit(self) -> None:
        """Handle Enter key."""
        if self._suggestion_menu and self._suggestion_menu.display:
            # Select current suggested item
            self._select_suggestion()
        else:
            # Default submit behavior (bubble up usually handled by Input, but we overrode it)
            # We need to trigger the standard submit event
            self.post_message(Input.Submitted(self, self.value))

    def action_autocomplete(self) -> None:
        """Handle Tab key."""
        if self._suggestion_menu and self._suggestion_menu.display:
            self._select_suggestion()
        else:
            # Default tab behavior (focus next)
            self.screen.focus_next()

    def _select_suggestion(self) -> None:
        """Use the currently selected suggestion."""
        if not self._suggestion_menu or not self._suggestion_menu.highlighted is None:
            # Nothing selected
            # But highlight might be int.
            # OptionList.highlighted is int index.
            pass

        idx = self._suggestion_menu.highlighted
        if idx is None and self._current_completions:
            idx = 0  # Default to first if none explicitly highlighted? OptionList highlights first by default usually.

        if idx is not None and 0 <= idx < len(self._current_completions):
            selection = self._current_completions[idx]
            self._apply_completion(selection)

        self._suggestion_menu.display = False

    def _apply_completion(self, completion: str) -> None:
        """Insert completion into text."""
        text = self.value
        cursor = self.cursor_position

        # Decide replacement range
        # Command
        if text.startswith("/") and " " not in text[:cursor]:
            # Replace full command prefix
            self.value = completion + " "
            self.cursor_position = len(self.value)

        # File
        elif "@" in text[:cursor]:
            at_index = text[:cursor].rfind("@")
            # Replacement: text[:at] + "@" + completion + text[cursor:] (if cursor matches end)
            # Note: completion from PathCompleter usually is the full path?
            # PathCompleter returns the full path relative to whatever.
            # Let's check format. _format_label adds "@".
            # But get_completions returns just path strings usually?
            # completers.py: return [path for path, _ in scored_matches]
            # scored_matches comes from _score_matches which uses _format_label -> returns "@path".
            # So completion includes "@".

            # If completion includes "@", we should replace from `at_index`.
            new_text = text[:at_index] + completion + text[cursor:]
            self.value = new_text
            self.cursor_position = at_index + len(completion)

        self._suggestion_menu.display = False
