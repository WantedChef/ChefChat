"""ChefChat TUI State Management.

This module provides centralized state management for the TUI application.
It uses Textual's reactive system to enable widgets to observe and respond
to state changes without direct coupling.

The design follows the Strangler Fig pattern - these state classes can be
gradually adopted while existing code continues to work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING

from textual.reactive import reactive

if TYPE_CHECKING:
    pass


# ============================================================================
# Enums for State Values
# ============================================================================


class ProcessingState(Enum):
    """Processing state of the application."""

    IDLE = auto()
    RUNNING = auto()
    CANCELLING = auto()
    STREAMING = auto()


class LayoutMode(Enum):
    """Available TUI layout modes."""

    CHAT_ONLY = "chat_only"
    FULL_KITCHEN = "full_kitchen"
    FOCUSED = "focused"


# ============================================================================
# State Data Classes (Immutable Snapshots)
# ============================================================================


@dataclass(frozen=True, slots=True)
class ModelState:
    """Immutable snapshot of model-related state."""

    active_model: str
    provider: str | None = None
    temperature: float = 0.7
    available_models: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionState:
    """Immutable snapshot of session statistics."""

    start_time: datetime = field(default_factory=datetime.now)
    tools_executed: int = 0
    tokens_used: int = 0
    messages_sent: int = 0


@dataclass(frozen=True, slots=True)
class TicketState:
    """Immutable snapshot of current ticket processing state."""

    processing: ProcessingState = ProcessingState.IDLE
    ticket_id: str | None = None
    agent_name: str | None = None

    @property
    def is_active(self) -> bool:
        """Check if a ticket is being processed."""
        return self.processing in {ProcessingState.RUNNING, ProcessingState.STREAMING}

    @property
    def is_cancelling(self) -> bool:
        """Check if cancellation is in progress."""
        return self.processing == ProcessingState.CANCELLING


# ============================================================================
# TUI State Container (Observable State Store)
# ============================================================================


class TUIState:
    """Centralized reactive state container for the TUI.

    Widgets can observe state changes by watching reactive properties.
    State updates are atomic and notify all observers automatically.

    Usage in widgets:
        ```python
        class MyWidget(Static):
            def compose(self) -> ComposeResult:
                yield Static(id="status")

            def watch_app_state(self, new_state: TUIState) -> None:
                # Called automatically when state changes
                status = self.query_one("#status", Static)
                status.update(f"Processing: {new_state.ticket.is_active}")
        ```
    """

    # Reactive properties for automatic UI updates
    model_alias: reactive[str] = reactive("", init=False)
    processing: reactive[ProcessingState] = reactive(ProcessingState.IDLE, init=False)
    layout: reactive[LayoutMode] = reactive(LayoutMode.CHAT_ONLY, init=False)

    def __init__(self) -> None:
        """Initialize with default state."""
        self._ticket = TicketState()
        self._model = ModelState(active_model="")
        self._session = SessionState()

    # ==== Model State ====

    @property
    def model(self) -> ModelState:
        """Get current model state snapshot."""
        return self._model

    def update_model(
        self,
        active_model: str | None = None,
        provider: str | None = None,
        temperature: float | None = None,
    ) -> None:
        """Update model state atomically."""
        self._model = ModelState(
            active_model=active_model or self._model.active_model,
            provider=provider or self._model.provider,
            temperature=temperature or self._model.temperature,
            available_models=self._model.available_models,
        )
        self.model_alias = self._model.active_model

    # ==== Ticket/Processing State ====

    @property
    def ticket(self) -> TicketState:
        """Get current ticket state snapshot."""
        return self._ticket

    def start_processing(self, ticket_id: str, agent_name: str = "Chef") -> None:
        """Transition to processing state."""
        self._ticket = TicketState(
            processing=ProcessingState.RUNNING,
            ticket_id=ticket_id,
            agent_name=agent_name,
        )
        self.processing = ProcessingState.RUNNING

    def start_streaming(self) -> None:
        """Transition to streaming state."""
        self._ticket = TicketState(
            processing=ProcessingState.STREAMING,
            ticket_id=self._ticket.ticket_id,
            agent_name=self._ticket.agent_name,
        )
        self.processing = ProcessingState.STREAMING

    def start_cancelling(self) -> None:
        """Transition to cancelling state."""
        self._ticket = TicketState(
            processing=ProcessingState.CANCELLING,
            ticket_id=self._ticket.ticket_id,
            agent_name=self._ticket.agent_name,
        )
        self.processing = ProcessingState.CANCELLING

    def finish_processing(self) -> None:
        """Transition to idle state."""
        self._ticket = TicketState()
        self.processing = ProcessingState.IDLE

    # ==== Session State ====

    @property
    def session(self) -> SessionState:
        """Get current session state snapshot."""
        return self._session

    def increment_tools(self) -> None:
        """Increment tools executed counter."""
        self._session = SessionState(
            start_time=self._session.start_time,
            tools_executed=self._session.tools_executed + 1,
            tokens_used=self._session.tokens_used,
            messages_sent=self._session.messages_sent,
        )

    def add_tokens(self, count: int) -> None:
        """Add to token usage counter."""
        self._session = SessionState(
            start_time=self._session.start_time,
            tools_executed=self._session.tools_executed,
            tokens_used=self._session.tokens_used + count,
            messages_sent=self._session.messages_sent,
        )

    def increment_messages(self) -> None:
        """Increment messages sent counter."""
        self._session = SessionState(
            start_time=self._session.start_time,
            tools_executed=self._session.tools_executed,
            tokens_used=self._session.tokens_used,
            messages_sent=self._session.messages_sent + 1,
        )

    # ==== Layout State ====

    def set_layout(self, layout: LayoutMode) -> None:
        """Update current layout mode."""
        self.layout = layout


# ============================================================================
# Global State Instance
# ============================================================================

_tui_state: TUIState | None = None


def get_tui_state() -> TUIState:
    """Get or create the global TUI state instance."""
    global _tui_state
    if _tui_state is None:
        _tui_state = TUIState()
    return _tui_state


def reset_tui_state() -> None:
    """Reset the global TUI state (useful for testing)."""
    global _tui_state
    _tui_state = None
