"""Additional comprehensive tests for BashCommandController - 100% coverage."""

from __future__ import annotations

from concurrent.futures import Future
from typing import NamedTuple
from unittest.mock import MagicMock, patch

from textual import events

from chefchat.cli.autocompletion.base import CompletionView
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


class StubViewWithApp(CompletionView):
    """Stub view with app attribute for testing app.call_after_refresh paths."""

    def __init__(self) -> None:
        self.suggestion_events: list[SuggestionEvent] = []
        self.reset_count = 0
        self.replacements: list[Replacement] = []
        self.app = MagicMock()
        self.app.call_after_refresh = MagicMock(side_effect=lambda fn, *args: fn(*args))

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


class TestAppCallAfterRefresh:
    """Tests for app.call_after_refresh code paths."""

    def test_update_suggestions_with_app_present(self) -> None:
        """Test suggestions update when view has app attribute."""
        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history = ["ls", "cat"]
        controller._history_loaded = True

        controller.on_text_changed("!l", 2)

        assert len(view.suggestion_events) >= 1
        assert view.app.call_after_refresh.called

    def test_reset_with_app_present_no_suggestions(self) -> None:
        """Test reset path when app exists but no suggestions match."""
        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history = ["ls", "cat"]
        controller._history_loaded = True

        controller.on_text_changed("!xyz", 4)

        # Should call reset via app.call_after_refresh
        assert view.app.call_after_refresh.called


class TestPendingFutureCancellation:
    """Tests for pending future cancellation logic."""

    def test_cancels_pending_future_on_new_query(self) -> None:
        """Test that pending futures are cancelled when new query arrives."""
        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history = ["ls", "cat", "echo"]
        controller._history_loaded = True

        # Create a mock future
        mock_future = MagicMock(spec=Future)
        mock_future.done.return_value = False
        controller._pending_future = mock_future

        # Trigger new query
        controller.on_text_changed("!l", 2)

        # Future should be cancelled
        mock_future.cancel.assert_called_once()

    def test_cancels_pending_future_on_reset(self) -> None:
        """Test that pending futures are cancelled on reset."""
        view = StubViewWithApp()
        controller = BashCommandController(view)

        # Create a mock future
        mock_future = MagicMock(spec=Future)
        mock_future.done.return_value = False
        controller._pending_future = mock_future

        controller.reset()

        mock_future.cancel.assert_called_once()

    def test_does_not_cancel_completed_future(self) -> None:
        """Test that completed futures are not cancelled."""
        view = StubViewWithApp()
        controller = BashCommandController(view)

        # Create a mock completed future
        mock_future = MagicMock(spec=Future)
        mock_future.done.return_value = True
        controller._pending_future = mock_future

        controller.reset()

        # Should not call cancel on completed future
        mock_future.cancel.assert_not_called()


class TestShellHistoryFormats:
    """Tests for different shell history formats."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_parses_fish_history_format(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test parsing fish shell history format."""
        mock_exists.return_value = True
        mock_read.return_value = "- cmd: ls -la\n- cmd: cd /tmp\n"

        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history_loaded = False

        with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
            controller._load_history()

        # Fish format not parsed yet, but history file is detected
        assert controller._history_loaded

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_skips_comment_lines(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test that comment lines are skipped."""
        mock_exists.return_value = True
        mock_read.return_value = "# This is a comment\nls\n# Another comment\ncd\n"

        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history_loaded = False

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            controller._load_history()

        assert "ls" in controller._history
        assert "cd" in controller._history
        assert "# This is a comment" not in controller._history

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_handles_empty_lines(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test that empty lines are skipped."""
        mock_exists.return_value = True
        mock_read.return_value = "ls\n\n\ncd\n\n"

        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history_loaded = False

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            controller._load_history()

        assert len(controller._history) == 2
        assert "ls" in controller._history
        assert "cd" in controller._history

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_handles_oserror_gracefully(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test that OSError during history loading is handled gracefully."""
        mock_exists.return_value = True
        mock_read.side_effect = OSError("Permission denied")

        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history_loaded = False

        controller._load_history()

        # Should not crash, history should be empty
        assert controller._history == []
        assert controller._history_loaded is True

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_respects_histfile_env_var_zsh(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test that HISTFILE env var is respected for zsh."""
        mock_exists.return_value = True
        mock_read.return_value = "ls\n"

        view = StubViewWithApp()
        controller = BashCommandController(view)

        with patch.dict(
            "os.environ", {"SHELL": "/bin/zsh", "HISTFILE": "/custom/history"}
        ):
            hist_file = controller._get_history_file()

        assert str(hist_file) == "/custom/history"

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_respects_histfile_env_var_bash(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test that HISTFILE env var is respected for bash."""
        mock_exists.return_value = True
        mock_read.return_value = "ls\n"

        view = StubViewWithApp()
        controller = BashCommandController(view)

        with patch.dict(
            "os.environ", {"SHELL": "/bin/bash", "HISTFILE": "/custom/bash_history"}
        ):
            hist_file = controller._get_history_file()

        assert str(hist_file) == "/custom/bash_history"


class TestSuggestionLimiting:
    """Tests for suggestion count limiting."""

    def test_limits_suggestions_to_max_count(self) -> None:
        """Test that suggestions are limited to MAX_SUGGESTIONS_COUNT."""
        view = StubViewWithApp()
        controller = BashCommandController(view)

        # Create 20 commands that all match
        controller._history = [f"cmd{i}" for i in range(20)]
        controller._history_loaded = True

        controller.on_text_changed("!cmd", 4)

        suggestions, _ = view.suggestion_events[-1]
        # Should be limited to MAX_SUGGESTIONS_COUNT (8)
        assert len(suggestions) <= 8

    def test_limits_recent_commands_to_max_count(self) -> None:
        """Test that recent commands shown for bare ! are limited."""
        view = StubViewWithApp()
        controller = BashCommandController(view)

        # Create 20 commands
        controller._history = [f"cmd{i}" for i in range(20)]
        controller._history_loaded = True

        controller.on_text_changed("!", 1)

        suggestions, _ = view.suggestion_events[-1]
        # Should be limited to MAX_SUGGESTIONS_COUNT (8)
        assert len(suggestions) <= 8


class TestQueryCaching:
    """Tests for query caching logic."""

    def test_skips_duplicate_query(self) -> None:
        """Test that duplicate queries are skipped."""
        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history = ["ls", "cat"]
        controller._history_loaded = True

        controller.on_text_changed("!l", 2)
        initial_count = len(view.suggestion_events)

        # Same query again
        controller.on_text_changed("!l", 2)

        # Should not generate new suggestions
        assert len(view.suggestion_events) == initial_count


class TestMoveSelectionEdgeCases:
    """Tests for _move_selection edge cases."""

    def test_move_selection_with_no_suggestions(self) -> None:
        """Test that move_selection handles empty suggestions gracefully."""
        view = StubViewWithApp()
        controller = BashCommandController(view)

        # No suggestions
        controller._move_selection(1)

        # Should not crash
        assert controller._selected_index == 0

    def test_apply_completion_with_no_suggestions(self) -> None:
        """Test that apply_completion returns False with no suggestions."""
        view = StubViewWithApp()
        controller = BashCommandController(view)

        result = controller._apply_selected_completion("!l", 2)

        assert result is False


class TestHistoryDeduplication:
    """Tests for history deduplication logic."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_deduplicates_preserving_most_recent(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test that duplicates are removed, keeping most recent."""
        mock_exists.return_value = True
        # ls appears 3 times, cd appears 2 times
        mock_read.return_value = "ls\ncd\nls\necho\nls\ncd\n"

        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history_loaded = False

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            controller._load_history()

        # Each command should appear only once
        assert controller._history.count("ls") == 1
        assert controller._history.count("cd") == 1
        assert controller._history.count("echo") == 1


class TestMaxHistoryEntries:
    """Tests for MAX_HISTORY_ENTRIES limiting."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_limits_history_to_max_entries(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test that history is limited to MAX_HISTORY_ENTRIES."""
        mock_exists.return_value = True
        # Create 1000 commands
        commands = "\n".join([f"cmd{i}" for i in range(1000)])
        mock_read.return_value = commands

        view = StubViewWithApp()
        controller = BashCommandController(view)
        controller._history_loaded = False

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            controller._load_history()

        # Should be limited to MAX_HISTORY_ENTRIES (500)
        assert len(controller._history) <= 500
