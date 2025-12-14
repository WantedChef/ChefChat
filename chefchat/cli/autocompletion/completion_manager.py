"""Unified Completion Manager for TUI.

Orchestrates multiple autocompletion controllers (`/commands`, `!bash`, `@files`)
and routes events to the appropriate handler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from textual import events

from chefchat.cli.autocompletion.base import CompletionResult, CompletionView
from chefchat.cli.autocompletion.bash_command import BashCommandController
from chefchat.cli.autocompletion.path_completion import PathCompletionController
from chefchat.cli.autocompletion.slash_command import SlashCommandController
from chefchat.core.autocompletion.completers import CommandCompleter, PathCompleter

if TYPE_CHECKING:
    pass


# Default slash commands available in TUI
DEFAULT_TUI_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show available commands"),
    ("/clear", "Clear the chat"),
    ("/quit", "Exit ChefChat"),
    ("/modes", "Show available modes"),
    ("/status", "Show session status"),
    ("/model", "Switch AI model"),
    ("/config", "Show configuration"),
    ("/layout", "Switch layout (chat/kitchen)"),
    ("/taste", "Run taste tests (QA)"),
    ("/timer", "Kitchen timer info"),
    ("/log", "Show log file path"),
    ("/chef", "Kitchen status"),
    ("/wisdom", "Random chef wisdom"),
    ("/roast", "Get roasted by Gordon"),
    ("/fortune", "Developer fortune cookie"),
    ("/api", "Configure API keys"),
    ("/mcp", "MCP server management"),
    ("/compact", "Compact conversation history"),
]


class CompletionController(Protocol):
    """Protocol for completion controllers."""

    def can_handle(self, text: str, cursor_index: int) -> bool:
        """Check if this controller handles the input."""
        ...

    def reset(self) -> None:
        """Reset controller state."""
        ...

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        """Handle text change."""
        ...

    def on_key(
        self, event: events.Key, text: str, cursor_index: int
    ) -> CompletionResult:
        """Handle key event."""
        ...


class CompletionManager:
    """Orchestrates multiple completion controllers for TUI.

    Routes input events to the appropriate controller based on input prefix:
    - `/` -> SlashCommandController
    - `!` -> BashCommandController
    - `@` -> PathCompletionController

    Only one controller is active at a time to prevent conflicts.
    """

    def __init__(self, view: CompletionView) -> None:
        """Initialize the completion manager.

        Args:
            view: The view implementing CompletionView protocol.
        """
        self._view = view
        self._active_controller: CompletionController | None = None

        # Initialize controllers
        self._slash_controller = SlashCommandController(
            CommandCompleter(DEFAULT_TUI_COMMANDS), view
        )
        self._bash_controller = BashCommandController(view)
        self._path_controller = PathCompletionController(PathCompleter(), view)

        # Priority order for checking which controller to use
        self._controllers: list[CompletionController] = [
            self._slash_controller,
            self._bash_controller,
            self._path_controller,
        ]

    @property
    def active_controller(self) -> CompletionController | None:
        """Get the currently active controller."""
        return self._active_controller

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        """Route text changes to the appropriate controller.

        Args:
            text: Current input text.
            cursor_index: Current cursor position.
        """
        # Find which controller should handle this input
        new_controller: CompletionController | None = None
        for controller in self._controllers:
            if controller.can_handle(text, cursor_index):
                new_controller = controller
                break

        # If active controller changed, reset the old one
        if (
            self._active_controller is not None
            and self._active_controller != new_controller
        ):
            self._active_controller.reset()

        self._active_controller = new_controller

        # Forward event to active controller
        if self._active_controller is not None:
            self._active_controller.on_text_changed(text, cursor_index)

    def on_key(
        self, event: events.Key, text: str, cursor_index: int
    ) -> CompletionResult:
        """Route key events to the active controller.

        Args:
            event: The key event.
            text: Current input text.
            cursor_index: Current cursor position.

        Returns:
            CompletionResult from the active controller, or IGNORED.
        """
        if self._active_controller is None:
            return CompletionResult.IGNORED

        return self._active_controller.on_key(event, text, cursor_index)

    def reset(self) -> None:
        """Reset all controllers."""
        for controller in self._controllers:
            controller.reset()
        self._active_controller = None

    def has_active_suggestions(self) -> bool:
        """Check if there are active suggestions to display.

        Returns:
            True if the active controller has suggestions.
        """
        if self._active_controller is None:
            return False

        # Check if controller has suggestions (implementation detail varies)
        if hasattr(self._active_controller, "_suggestions"):
            return bool(getattr(self._active_controller, "_suggestions", []))
        return False
