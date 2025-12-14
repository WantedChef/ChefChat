"""Tests for BashCommandController."""

from __future__ import annotations

from typing import NamedTuple
from unittest.mock import MagicMock, patch

from textual import events

from chefchat.cli.autocompletion.base import CompletionResult, CompletionView
from chefchat.cli.autocompletion.bash_command import BashCommandController


class Suggestion(NamedTuple):
    command: str
    source: str


class SuggestionEvent(NamedTuple):
    suggestions: list[Suggestion]
    selected_index: int


class Replacement(NamedTuple):
    start: int
    end: int
    replacement: str


class StubView(CompletionView):
    """Stub view for testing."""

    def __init__(self) -> None:
        self.suggestion_events: list[SuggestionEvent] = []
        self.reset_count = 0
        self.replacements: list[Replacement] = []

    def render_completion_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None:
        typed = [Suggestion(cmd, source) for cmd, source in suggestions]
        self.suggestion_events.append(SuggestionEvent(typed, selected_index))

    def clear_completion_suggestions(self) -> None:
        self.reset_count += 1

    def replace_completion_range(self, start: int, end: int, replacement: str) -> None:
        self.replacements.append(Replacement(start, end, replacement))


def key_event(key: str) -> events.Key:
    """Create a key event for testing."""
    return events.Key(key, character=None)


def make_controller(
    *, history: list[str] | None = None
) -> tuple[BashCommandController, StubView]:
    """Create a controller with optional history preloaded."""
    view = StubView()
    controller = BashCommandController(view)

    if history is not None:
        controller._history = history
        controller._history_loaded = True

    return controller, view


class TestCanHandle:
    """Tests for can_handle method."""

    def test_handles_exclamation_prefix(self) -> None:
        controller, _ = make_controller()
        assert controller.can_handle("!ls", 2) is True

    def test_handles_just_exclamation(self) -> None:
        controller, _ = make_controller()
        assert controller.can_handle("!", 1) is True

    def test_does_not_handle_empty_string(self) -> None:
        controller, _ = make_controller()
        assert controller.can_handle("", 0) is False

    def test_does_not_handle_regular_text(self) -> None:
        controller, _ = make_controller()
        assert controller.can_handle("hello", 5) is False

    def test_does_not_handle_slash_commands(self) -> None:
        controller, _ = make_controller()
        assert controller.can_handle("/help", 5) is False

    def test_does_not_handle_at_symbol(self) -> None:
        controller, _ = make_controller()
        assert controller.can_handle("@file", 5) is False

    def test_does_not_handle_cursor_at_zero(self) -> None:
        controller, _ = make_controller()
        assert controller.can_handle("!", 0) is False


class TestOnTextChanged:
    """Tests for on_text_changed method."""

    def test_shows_matching_history_commands(self) -> None:
        controller, view = make_controller(
            history=["ls -la", "ls -lh", "cat file.txt", "grep pattern"]
        )

        controller.on_text_changed("!ls", 3)

        assert len(view.suggestion_events) == 1
        suggestions, selected = view.suggestion_events[-1]
        assert len(suggestions) == 2
        assert suggestions[0].command == "ls -la"
        assert suggestions[1].command == "ls -lh"
        assert selected == 0

    def test_shows_recent_commands_for_bare_exclamation(self) -> None:
        controller, view = make_controller(history=["cmd1", "cmd2", "cmd3"])

        controller.on_text_changed("!", 1)

        suggestions, _ = view.suggestion_events[-1]
        assert len(suggestions) == 3
        assert suggestions[0].command == "cmd1"
        assert suggestions[1].command == "cmd2"

    def test_clears_suggestions_when_no_matches(self) -> None:
        controller, view = make_controller(history=["ls", "cat"])

        controller.on_text_changed("!xyz", 4)

        assert view.reset_count >= 1 or len(view.suggestion_events) == 0

    def test_resets_on_non_bash_input(self) -> None:
        controller, view = make_controller(history=["ls", "cat"])

        # First trigger suggestions
        controller.on_text_changed("!ls", 3)
        # Then change to non-bash input
        controller.on_text_changed("hello", 5)

        assert view.reset_count >= 1

    def test_case_insensitive_matching(self) -> None:
        controller, view = make_controller(history=["LS", "ls -la", "Cat"])

        controller.on_text_changed("!ls", 3)

        suggestions, _ = view.suggestion_events[-1]
        commands = [s.command for s in suggestions]
        assert "LS" in commands
        assert "ls -la" in commands


class TestOnKey:
    """Tests for on_key method."""

    def test_tab_applies_completion(self) -> None:
        controller, view = make_controller(history=["ls -la", "cat"])

        controller.on_text_changed("!l", 2)
        result = controller.on_key(key_event("tab"), "!l", 2)

        assert result is CompletionResult.HANDLED
        assert len(view.replacements) == 1
        assert view.replacements[0] == Replacement(1, 2, "ls -la")

    def test_enter_submits_completion(self) -> None:
        controller, view = make_controller(history=["ls -la"])

        controller.on_text_changed("!l", 2)
        result = controller.on_key(key_event("enter"), "!l", 2)

        assert result is CompletionResult.SUBMIT
        assert len(view.replacements) == 1

    def test_down_key_moves_selection(self) -> None:
        controller, view = make_controller(history=["cmd1", "cmd2", "cmd3"])

        controller.on_text_changed("!cmd", 4)
        view.suggestion_events.clear()

        controller.on_key(key_event("down"), "!cmd", 4)

        suggestions, selected = view.suggestion_events[-1]
        assert selected == 1

    def test_up_key_moves_selection(self) -> None:
        controller, view = make_controller(history=["cmd1", "cmd2", "cmd3"])

        controller.on_text_changed("!cmd", 4)
        view.suggestion_events.clear()

        controller.on_key(key_event("up"), "!cmd", 4)

        suggestions, selected = view.suggestion_events[-1]
        # Should wrap to last item
        assert selected == 2

    def test_selection_wraps_around(self) -> None:
        controller, view = make_controller(history=["cmd1", "cmd2"])

        controller.on_text_changed("!cmd", 4)

        # Move down twice to wrap to first
        controller.on_key(key_event("down"), "!cmd", 4)
        controller.on_key(key_event("down"), "!cmd", 4)

        suggestions, selected = view.suggestion_events[-1]
        assert selected == 0

    def test_returns_ignored_for_unknown_keys(self) -> None:
        controller, view = make_controller(history=["cmd"])

        controller.on_text_changed("!c", 2)
        result = controller.on_key(key_event("a"), "!c", 2)

        assert result is CompletionResult.IGNORED

    def test_returns_ignored_when_no_suggestions(self) -> None:
        controller, _ = make_controller(history=[])

        result = controller.on_key(key_event("tab"), "!", 1)

        assert result is CompletionResult.IGNORED


class TestGetReplacementRange:
    """Tests for get_replacement_range method."""

    def test_returns_range_after_exclamation(self) -> None:
        controller, _ = make_controller()

        result = controller.get_replacement_range("!ls -la", 7)

        assert result == (1, 7)

    def test_returns_none_for_non_bash_input(self) -> None:
        controller, _ = make_controller()

        result = controller.get_replacement_range("hello", 5)

        assert result is None


class TestHistoryLoading:
    """Tests for shell history loading."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_loads_bash_history(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = "ls\ncd /tmp\necho hello\n"

        controller, view = make_controller()

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            controller.on_text_changed("!", 1)

        assert controller._history_loaded

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_parses_zsh_extended_history(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = ": 1234567890:0;ls -la\n: 1234567891:0;cd /tmp\n"

        controller, _ = make_controller()
        controller._history_loaded = False

        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
            controller._load_history()

        assert "ls -la" in controller._history
        assert "cd /tmp" in controller._history

    @patch("pathlib.Path.exists")
    def test_handles_missing_history_file(self, mock_exists: MagicMock) -> None:
        mock_exists.return_value = False

        controller, _ = make_controller()
        controller._history_loaded = False

        controller._load_history()

        assert controller._history == []


class TestReset:
    """Tests for reset method."""

    def test_clears_suggestions(self) -> None:
        controller, view = make_controller(history=["ls", "cat"])

        controller.on_text_changed("!l", 2)
        controller.reset()

        assert controller._suggestions == []
        assert controller._selected_index == 0
        assert view.reset_count >= 1
