"""Bash command autocompletion and execution controller.

Handles `!` prefixed commands for direct shell execution with autocomplete
suggestions from shell history.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import os
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from textual import events

from chefchat.cli.autocompletion.base import CompletionResult, CompletionView

if TYPE_CHECKING:
    pass

MAX_SUGGESTIONS_COUNT = 8
MAX_HISTORY_ENTRIES = 500


class BashCommandController:
    """Controller for bash command (`!`) autocompletion and execution.

    Detects `!` prefix and provides suggestions from shell history.
    Handles Tab for completion and Enter for execution.
    """

    _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bash-completion")

    def __init__(self, view: CompletionView) -> None:
        """Initialize the controller.

        Args:
            view: The view implementing CompletionView protocol.
        """
        self._view = view
        self._suggestions: list[tuple[str, str]] = []
        self._selected_index = 0
        self._history: list[str] = []
        self._history_loaded = False
        self._pending_future: Future | None = None
        self._last_query: tuple[str, int] | None = None
        self._query_lock = Lock()

    def can_handle(self, text: str, cursor_index: int) -> bool:
        """Check if text starts with '!' for bash commands.

        Args:
            text: Current input text.
            cursor_index: Current cursor position.

        Returns:
            True if this controller should handle the input.
        """
        return text.startswith("!") and cursor_index > 0

    def reset(self) -> None:
        """Reset the controller state and clear suggestions."""
        with self._query_lock:
            if self._pending_future and not self._pending_future.done():
                self._pending_future.cancel()
            self._pending_future = None
            self._last_query = None

        if self._suggestions:
            self._suggestions.clear()
            self._selected_index = 0
            self._view.clear_completion_suggestions()

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        """Update suggestions when text changes.

        Args:
            text: Current input text.
            cursor_index: Current cursor position.
        """
        if not self.can_handle(text, cursor_index):
            self.reset()
            return

        # Load history lazily on first use
        if not self._history_loaded:
            self._load_history()

        query = (text, cursor_index)
        with self._query_lock:
            if query == self._last_query:
                return

            if self._pending_future and not self._pending_future.done():
                self._pending_future.cancel()

            self._last_query = query

        # Get command part after !
        command_prefix = text[1:cursor_index].lower()

        # Filter history for matches
        if command_prefix:
            matches = [
                (cmd, "history")
                for cmd in self._history
                if cmd.lower().startswith(command_prefix)
            ]
        else:
            # Show recent commands when just "!" is typed
            matches = [(cmd, "recent") for cmd in self._history[:MAX_SUGGESTIONS_COUNT]]

        self._update_suggestions(matches)

    def _load_history(self) -> None:
        """Load command history from shell history file."""
        self._history_loaded = True
        history_file = self._get_history_file()

        if not history_file or not history_file.exists():
            return

        try:
            lines = history_file.read_text(errors="ignore").splitlines()
            # Parse history - handle different formats
            commands: list[str] = []
            for line in lines[-MAX_HISTORY_ENTRIES:]:
                # Skip empty lines
                line = line.strip()
                if not line:
                    continue

                # Handle zsh extended history format: : timestamp:0;command
                if line.startswith(":") and ";" in line:
                    line = line.split(";", 1)[1]

                # Skip comments and empty
                if line.startswith("#") or not line:
                    continue

                commands.append(line)

            # Deduplicate while preserving order (most recent first)
            seen: set[str] = set()
            unique_commands: list[str] = []
            for cmd in reversed(commands):
                if cmd not in seen:
                    seen.add(cmd)
                    unique_commands.append(cmd)

            self._history = unique_commands[:MAX_HISTORY_ENTRIES]

        except OSError:
            pass

    def _get_history_file(self) -> Path | None:
        """Get the shell history file path.

        Returns:
            Path to history file or None if not found.
        """
        shell = os.environ.get("SHELL", "")
        home = Path.home()

        if "zsh" in shell:
            histfile = os.environ.get("HISTFILE")
            if histfile:
                return Path(histfile)
            return home / ".zsh_history"
        elif "bash" in shell:
            histfile = os.environ.get("HISTFILE")
            if histfile:
                return Path(histfile)
            return home / ".bash_history"
        elif "fish" in shell:
            return home / ".local" / "share" / "fish" / "fish_history"

        # Fallback to bash history
        return home / ".bash_history"

    def _update_suggestions(self, suggestions: list[tuple[str, str]]) -> None:
        """Update and render suggestions.

        Args:
            suggestions: List of (command, source) tuples.
        """
        if len(suggestions) > MAX_SUGGESTIONS_COUNT:
            suggestions = suggestions[:MAX_SUGGESTIONS_COUNT]

        app = getattr(self._view, "app", None)

        if suggestions:
            self._suggestions = suggestions
            self._selected_index = 0
            if app:
                app.call_after_refresh(
                    self._view.render_completion_suggestions,
                    self._suggestions,
                    self._selected_index,
                )
            else:
                self._view.render_completion_suggestions(
                    self._suggestions, self._selected_index
                )
        elif app:
            app.call_after_refresh(self.reset)
        else:
            self.reset()

    def on_key(
        self, event: events.Key, text: str, cursor_index: int
    ) -> CompletionResult:
        """Handle key events for completion navigation.

        Args:
            event: The key event.
            text: Current input text.
            cursor_index: Current cursor position.

        Returns:
            CompletionResult indicating how the event was handled.
        """
        if not self._suggestions:
            return CompletionResult.IGNORED

        match event.key:
            case "tab":
                if self._apply_selected_completion(text, cursor_index):
                    return CompletionResult.HANDLED
                return CompletionResult.IGNORED
            case "enter":
                if self._apply_selected_completion(text, cursor_index):
                    return CompletionResult.SUBMIT
                return CompletionResult.HANDLED
            case "down":
                self._move_selection(1)
                return CompletionResult.HANDLED
            case "up":
                self._move_selection(-1)
                return CompletionResult.HANDLED
            case _:
                return CompletionResult.IGNORED

    def _move_selection(self, delta: int) -> None:
        """Move selection by delta, wrapping around.

        Args:
            delta: Amount to move (+1 for down, -1 for up).
        """
        if not self._suggestions:
            return

        count = len(self._suggestions)
        self._selected_index = (self._selected_index + delta) % count
        self._view.render_completion_suggestions(
            self._suggestions, self._selected_index
        )

    def _apply_selected_completion(self, text: str, cursor_index: int) -> bool:
        """Apply the currently selected completion.

        Args:
            text: Current input text.
            cursor_index: Current cursor position.

        Returns:
            True if completion was applied, False otherwise.
        """
        if not self._suggestions:
            return False

        command, _ = self._suggestions[self._selected_index]
        # Replace everything after ! with the selected command
        self._view.replace_completion_range(1, cursor_index, command)
        self.reset()
        return True

    def get_replacement_range(
        self, text: str, cursor_index: int
    ) -> tuple[int, int] | None:
        """Get the range to replace for completion.

        Args:
            text: Current input text.
            cursor_index: Current cursor position.

        Returns:
            Tuple of (start, end) indices or None.
        """
        if not self.can_handle(text, cursor_index):
            return None
        # Replace from after ! to cursor
        return (1, cursor_index)
