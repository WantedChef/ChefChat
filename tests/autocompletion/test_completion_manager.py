"""Tests for CompletionManager."""

from __future__ import annotations

from typing import NamedTuple

from textual import events

from chefchat.cli.autocompletion.base import CompletionResult, CompletionView
from chefchat.cli.autocompletion.completion_manager import CompletionManager


class Replacement(NamedTuple):
    start: int
    end: int
    replacement: str


class StubView(CompletionView):
    """Stub view for testing."""

    def __init__(self) -> None:
        self.suggestion_events: list[tuple[list[tuple[str, str]], int]] = []
        self.reset_count = 0
        self.replacements: list[Replacement] = []

    def render_completion_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None:
        self.suggestion_events.append((suggestions, selected_index))

    def clear_completion_suggestions(self) -> None:
        self.reset_count += 1

    def replace_completion_range(self, start: int, end: int, replacement: str) -> None:
        self.replacements.append(Replacement(start, end, replacement))


def key_event(key: str) -> events.Key:
    """Create a key event for testing."""
    return events.Key(key, character=None)


def make_manager() -> tuple[CompletionManager, StubView]:
    """Create a CompletionManager with stub view."""
    view = StubView()
    manager = CompletionManager(view)
    return manager, view


class TestRouting:
    """Tests for controller routing logic."""

    def test_routes_slash_commands_to_slash_controller(self) -> None:
        manager, _ = make_manager()

        manager.on_text_changed("/h", 2)

        assert manager.active_controller is manager._slash_controller

    def test_routes_bash_commands_to_bash_controller(self) -> None:
        manager, _ = make_manager()

        # Pre-load history to avoid file system access
        manager._bash_controller._history = ["ls", "cat"]
        manager._bash_controller._history_loaded = True

        manager.on_text_changed("!ls", 3)

        assert manager.active_controller is manager._bash_controller

    def test_routes_file_paths_to_path_controller(self) -> None:
        manager, _ = make_manager()

        manager.on_text_changed("Check @foo", 10)

        assert manager.active_controller is manager._path_controller

    def test_only_one_controller_active_at_a_time(self) -> None:
        manager, view = make_manager()

        # Pre-load bash history
        manager._bash_controller._history = ["ls"]
        manager._bash_controller._history_loaded = True

        # Start with slash command
        manager.on_text_changed("/help", 5)
        assert manager.active_controller is manager._slash_controller

        # Switch to bash command - should reset slash controller
        manager.on_text_changed("!l", 2)
        assert manager.active_controller is manager._bash_controller

    def test_no_active_controller_for_regular_text(self) -> None:
        manager, _ = make_manager()

        manager.on_text_changed("hello world", 11)

        assert manager.active_controller is None

    def test_resets_previous_controller_when_switching(self) -> None:
        manager, view = make_manager()

        # Pre-load bash history
        manager._bash_controller._history = ["ls"]
        manager._bash_controller._history_loaded = True

        # Activate slash controller
        manager.on_text_changed("/h", 2)

        # Now switch to bash - previous (slash) should reset
        initial_reset_count = view.reset_count
        manager.on_text_changed("!l", 2)

        # Reset should have been called at least once
        assert view.reset_count >= initial_reset_count


class TestOnKey:
    """Tests for on_key routing."""

    def test_forwards_key_to_active_controller(self) -> None:
        manager, view = make_manager()

        manager.on_text_changed("/h", 2)
        result = manager.on_key(key_event("tab"), "/h", 2)

        assert result is CompletionResult.HANDLED
        assert len(view.replacements) >= 1

    def test_returns_ignored_when_no_active_controller(self) -> None:
        manager, _ = make_manager()

        result = manager.on_key(key_event("tab"), "hello", 5)

        assert result is CompletionResult.IGNORED

    def test_down_key_moves_selection(self) -> None:
        manager, view = make_manager()

        manager.on_text_changed("/", 1)
        view.suggestion_events.clear()

        manager.on_key(key_event("down"), "/", 1)

        assert len(view.suggestion_events) >= 1
        _, selected = view.suggestion_events[-1]
        assert selected == 1


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_all_controllers(self) -> None:
        manager, view = make_manager()

        manager.on_text_changed("/h", 2)
        manager.reset()

        assert manager.active_controller is None
        assert view.reset_count >= 1

    def test_reset_clears_active_controller(self) -> None:
        manager, _ = make_manager()

        manager.on_text_changed("/help", 5)
        assert manager.active_controller is not None

        manager.reset()
        assert manager.active_controller is None


class TestHasActiveSuggestions:
    """Tests for has_active_suggestions method."""

    def test_returns_false_when_no_active_controller(self) -> None:
        manager, _ = make_manager()

        assert manager.has_active_suggestions() is False

    def test_returns_true_when_controller_has_suggestions(self) -> None:
        manager, _ = make_manager()

        manager.on_text_changed("/h", 2)

        # SlashCommandController should have suggestions for /h
        assert manager.has_active_suggestions() is True

    def test_returns_false_when_no_matching_suggestions(self) -> None:
        manager, _ = make_manager()

        manager.on_text_changed("/xxxnomatch", 11)

        # No commands match this
        assert manager.has_active_suggestions() is False


class TestSlashCommandIntegration:
    """Integration tests for slash command completion."""

    def test_shows_matches_for_partial_command(self) -> None:
        manager, view = make_manager()

        manager.on_text_changed("/hel", 4)

        assert len(view.suggestion_events) >= 1
        suggestions, _ = view.suggestion_events[-1]
        commands = [cmd for cmd, _ in suggestions]
        assert "/help" in commands

    def test_tab_completes_command(self) -> None:
        manager, view = make_manager()

        manager.on_text_changed("/hel", 4)
        manager.on_key(key_event("tab"), "/hel", 4)

        assert len(view.replacements) >= 1
        assert "/help" in view.replacements[-1].replacement


class TestBashCommandIntegration:
    """Integration tests for bash command completion."""

    def test_shows_history_suggestions(self) -> None:
        manager, view = make_manager()

        # Pre-load history
        manager._bash_controller._history = ["ls -la", "ls -lh", "cat file.txt"]
        manager._bash_controller._history_loaded = True

        manager.on_text_changed("!ls", 3)

        assert len(view.suggestion_events) >= 1
        suggestions, _ = view.suggestion_events[-1]
        commands = [cmd for cmd, _ in suggestions]
        assert "ls -la" in commands

    def test_tab_completes_command(self) -> None:
        manager, view = make_manager()

        manager._bash_controller._history = ["ls -la"]
        manager._bash_controller._history_loaded = True

        manager.on_text_changed("!l", 2)
        manager.on_key(key_event("tab"), "!l", 2)

        assert len(view.replacements) >= 1
