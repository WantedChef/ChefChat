"""Additional comprehensive tests for CompletionManager - 100% coverage."""

from __future__ import annotations

from typing import NamedTuple
from unittest.mock import MagicMock

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


class TestControllerPriority:
    """Tests for controller priority and routing."""

    def test_slash_takes_priority_over_others(self) -> None:
        """Test that slash controller is checked first."""
        manager, _ = make_manager()

        manager.on_text_changed("/help", 5)
        assert manager.active_controller is manager._slash_controller

    def test_bash_takes_priority_over_path(self) -> None:
        """Test that bash controller is checked before path."""
        manager, _ = make_manager()
        manager._bash_controller._history = ["ls"]
        manager._bash_controller._history_loaded = True

        manager.on_text_changed("!ls", 3)
        assert manager.active_controller is manager._bash_controller

    def test_path_controller_activated_for_at_symbol(self) -> None:
        """Test that path controller handles @ symbol."""
        manager, _ = make_manager()

        manager.on_text_changed("Check @file", 11)
        assert manager.active_controller is manager._path_controller


class TestActiveControllerProperty:
    """Tests for active_controller property."""

    def test_active_controller_returns_current_controller(self) -> None:
        """Test that active_controller property returns current controller."""
        manager, _ = make_manager()

        manager.on_text_changed("/help", 5)
        assert manager.active_controller is not None
        assert manager.active_controller is manager._slash_controller

    def test_active_controller_none_for_regular_text(self) -> None:
        """Test that active_controller is None for regular text."""
        manager, _ = make_manager()

        manager.on_text_changed("regular text", 12)
        assert manager.active_controller is None


class TestHasActiveSuggestionsEdgeCases:
    """Tests for has_active_suggestions edge cases."""

    def test_returns_false_when_controller_has_no_suggestions_attribute(self) -> None:
        """Test handling when controller doesn't have _suggestions."""
        manager, _ = make_manager()

        # Create a mock controller without _suggestions
        mock_controller = MagicMock()
        del mock_controller._suggestions  # Remove the attribute
        manager._active_controller = mock_controller

        result = manager.has_active_suggestions()
        assert result is False

    def test_returns_false_when_suggestions_empty(self) -> None:
        """Test returns False when suggestions list is empty."""
        manager, _ = make_manager()

        manager.on_text_changed("/zzz_nonexistent", 15)

        # Should have no suggestions
        assert manager.has_active_suggestions() is False

    def test_returns_true_when_suggestions_present(self) -> None:
        """Test returns True when controller has suggestions."""
        manager, _ = make_manager()

        manager.on_text_changed("/h", 2)

        # Should have suggestions for /h
        assert manager.has_active_suggestions() is True


class TestResetAllControllers:
    """Tests for reset method."""

    def test_reset_clears_all_controllers(self) -> None:
        """Test that reset clears all controllers."""
        manager, view = make_manager()

        # Activate slash controller
        manager.on_text_changed("/help", 5)
        assert manager.active_controller is not None

        # Reset
        manager.reset()

        assert manager.active_controller is None
        assert view.reset_count >= 1

    def test_reset_with_no_active_controller(self) -> None:
        """Test that reset works when no controller is active."""
        manager, _ = make_manager()

        # No active controller
        assert manager.active_controller is None

        # Should not crash
        manager.reset()
        assert manager.active_controller is None


class TestControllerSwitching:
    """Tests for switching between controllers."""

    def test_switching_from_slash_to_bash_resets_slash(self) -> None:
        """Test that switching controllers resets the previous one."""
        manager, view = make_manager()
        manager._bash_controller._history = ["ls"]
        manager._bash_controller._history_loaded = True

        # Start with slash
        manager.on_text_changed("/help", 5)
        initial_reset_count = view.reset_count

        # Switch to bash
        manager.on_text_changed("!l", 2)

        # Reset should have been called
        assert view.reset_count > initial_reset_count

    def test_switching_from_bash_to_path_resets_bash(self) -> None:
        """Test switching from bash to path controller."""
        manager, view = make_manager()
        manager._bash_controller._history = ["ls"]
        manager._bash_controller._history_loaded = True

        # Start with bash
        manager.on_text_changed("!l", 2)
        initial_reset_count = view.reset_count

        # Switch to path
        manager.on_text_changed("Check @file", 11)

        # Reset should have been called
        assert view.reset_count > initial_reset_count

    def test_staying_with_same_controller_no_reset(self) -> None:
        """Test that staying with same controller doesn't reset."""
        manager, view = make_manager()

        # Activate slash controller
        manager.on_text_changed("/h", 2)
        initial_reset_count = view.reset_count

        # Stay with slash controller
        manager.on_text_changed("/he", 3)

        # Should not have extra resets
        assert manager.active_controller is manager._slash_controller
        assert view.reset_count == initial_reset_count


class TestOnKeyWithNoController:
    """Tests for on_key when no controller is active."""

    def test_on_key_returns_ignored_when_no_active_controller(self) -> None:
        """Test that on_key returns IGNORED when no controller is active."""
        manager, _ = make_manager()

        # No active controller
        result = manager.on_key(key_event("tab"), "hello", 5)

        assert result is CompletionResult.IGNORED

    def test_on_key_forwards_to_active_controller(self) -> None:
        """Test that on_key forwards to active controller."""
        manager, view = make_manager()

        # Activate slash controller
        manager.on_text_changed("/h", 2)

        # Send key event
        result = manager.on_key(key_event("tab"), "/h", 2)

        # Should be handled
        assert result is CompletionResult.HANDLED
        assert len(view.replacements) >= 1


class TestMultipleControllerActivations:
    """Tests for multiple controller activations."""

    def test_multiple_slash_commands(self) -> None:
        """Test handling multiple slash commands in sequence."""
        manager, _ = make_manager()

        manager.on_text_changed("/help", 5)
        assert manager.active_controller is manager._slash_controller

        manager.on_text_changed("/clear", 6)
        assert manager.active_controller is manager._slash_controller

        manager.on_text_changed("/quit", 5)
        assert manager.active_controller is manager._slash_controller

    def test_alternating_between_controllers(self) -> None:
        """Test alternating between different controllers."""
        manager, _ = make_manager()
        manager._bash_controller._history = ["ls"]
        manager._bash_controller._history_loaded = True

        # Slash
        manager.on_text_changed("/help", 5)
        assert manager.active_controller is manager._slash_controller

        # Bash
        manager.on_text_changed("!l", 2)
        assert manager.active_controller is manager._bash_controller

        # Path
        manager.on_text_changed("@file", 5)
        assert manager.active_controller is manager._path_controller

        # Back to slash
        manager.on_text_changed("/clear", 6)
        assert manager.active_controller is manager._slash_controller


class TestTextChangedEdgeCases:
    """Tests for on_text_changed edge cases."""

    def test_empty_string_clears_controller(self) -> None:
        """Test that empty string clears active controller."""
        manager, _ = make_manager()

        manager.on_text_changed("/help", 5)
        assert manager.active_controller is not None

        manager.on_text_changed("", 0)
        assert manager.active_controller is None

    def test_whitespace_only_clears_controller(self) -> None:
        """Test that whitespace-only text clears controller."""
        manager, _ = make_manager()

        manager.on_text_changed("/help", 5)
        assert manager.active_controller is not None

        manager.on_text_changed("   ", 3)
        assert manager.active_controller is None
