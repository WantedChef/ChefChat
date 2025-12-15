"""ChefChat TUI Events - Textual Messages for Widget Communication.

This module defines custom Textual Messages that enable decoupled
communication between widgets. Instead of widgets directly calling
methods on other widgets, they can post messages that the App
(or parent containers) handle and route appropriately.

The design follows Textual's event system and enables the Strangler Fig
pattern - new event-driven code can coexist with existing direct calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.message import Message

# ============================================================================
# Model Events
# ============================================================================


@dataclass
class ModelSwitchRequested(Message):
    """Request to switch to a different model.

    Sent by: ModelManagerScreen, CommandInput
    Handled by: ChefChatApp
    """

    model_alias: str
    bubble: bool = True  # Bubble up to app


@dataclass
class ModelSwitchCompleted(Message):
    """Notification that model switch is complete.

    Sent by: ChefChatApp
    Listened by: KitchenFooter, TicketRail
    """

    model_alias: str
    success: bool
    error_message: str | None = None


# ============================================================================
# Processing Events
# ============================================================================


@dataclass
class TicketSubmitted(Message):
    """User submitted a new ticket/prompt.

    Sent by: CommandInput
    Handled by: ChefChatApp
    """

    content: str
    ticket_id: str | None = None


@dataclass
class ProcessingStarted(Message):
    """Processing has started for a ticket.

    Sent by: ChefChatApp
    Listened by: WhiskLoader, TicketRail, ThePass
    """

    ticket_id: str
    agent_name: str = "Chef"


@dataclass
class StreamingStarted(Message):
    """Streaming response has begun.

    Sent by: ChefChatApp
    Listened by: TicketRail
    """

    ticket_id: str


@dataclass
class StreamingToken(Message):
    """A token has been received during streaming.

    Sent by: ChefChatApp
    Listened by: TicketRail
    """

    token: str


@dataclass
class StreamingFinished(Message):
    """Streaming response is complete.

    Sent by: ChefChatApp
    Listened by: TicketRail, WhiskLoader
    """

    ticket_id: str
    full_content: str | None = None


@dataclass
class ProcessingCancelled(Message):
    """Processing was cancelled.

    Sent by: ChefChatApp (after user Ctrl+C)
    Listened by: WhiskLoader, TicketRail, ThePass
    """

    ticket_id: str | None = None


@dataclass
class ProcessingFinished(Message):
    """Processing is complete (success or error).

    Sent by: ChefChatApp
    Listened by: WhiskLoader, TicketRail, ThePass
    """

    ticket_id: str
    success: bool = True
    error_message: str | None = None


# ============================================================================
# Tool Events
# ============================================================================


@dataclass
class ToolExecutionStarted(Message):
    """A tool has started executing.

    Sent by: AgentLifecycleMixin
    Listened by: ThePlate (Activities tab), ThePass
    """

    tool_name: str
    chef_name: str = "Chef"


@dataclass
class ToolExecutionFinished(Message):
    """A tool has finished executing.

    Sent by: AgentLifecycleMixin
    Listened by: ThePlate (Activities tab), ThePass
    """

    tool_name: str
    success: bool
    output: str | None = None
    error: str | None = None


# ============================================================================
# Code Output Events
# ============================================================================


@dataclass
class CodeOutputReceived(Message):
    """Code output to display in ThePlate.

    Sent by: ChefChatApp (via bus handler)
    Listened by: ThePlate
    """

    code: str
    language: str = "python"
    file_path: str | None = None
    append: bool = False


@dataclass
class TerminalOutputReceived(Message):
    """Terminal output to display.

    Sent by: ChefChatApp (via bash command or bus)
    Listened by: ThePlate (Terminal tab)
    """

    output: str
    is_error: bool = False


# ============================================================================
# Station Status Events
# ============================================================================


@dataclass
class StationStatusChanged(Message):
    """A kitchen station's status has changed.

    Sent by: ChefChatApp (via bus handler)
    Listened by: ThePass
    """

    station_id: str
    status: str  # "idle", "working", "complete", "error"
    message: str | None = None


# ============================================================================
# Layout Events
# ============================================================================


@dataclass
class LayoutSwitchRequested(Message):
    """Request to switch TUI layout.

    Sent by: SystemCommandsMixin
    Handled by: ChefChatApp
    """

    layout: str  # "chat_only", "kitchen", "focused"
    require_restart: bool = True


# ============================================================================
# Mode Events
# ============================================================================


@dataclass
class ModeCycleRequested(Message):
    """Request to cycle to next mode.

    Sent by: Key binding handler
    Handled by: ChefChatApp
    """

    pass  # No payload needed


@dataclass
class ModeChanged(Message):
    """Mode has changed.

    Sent by: ChefChatApp
    Listened by: KitchenFooter
    """

    old_mode: str
    new_mode: str
    auto_approve: bool
