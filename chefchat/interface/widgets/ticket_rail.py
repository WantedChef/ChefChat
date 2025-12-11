"""ChefChat Ticket Rail Widget - The Chat History Panel.

'The Ticket' in kitchen terms is the order slip. This widget displays
the conversation history between the Head Chef (user) and the Brigade (AI).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static


class TicketType(Enum):
    """Type of message in the ticket rail."""

    USER = auto()  # Head Chef's order
    ASSISTANT = auto()  # Kitchen's response
    SYSTEM = auto()  # Kitchen announcements


@dataclass
class TicketMessage:
    """A single message in the ticket rail."""

    content: str
    ticket_type: TicketType
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        """Set default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()


class Ticket(Static):
    """A single ticket (message bubble) in the rail."""

    DEFAULT_CSS = """
    Ticket {
        width: 100%;
        margin: 0 0 1 0;
        padding: 1;
        background: $surface;
        border: round $panel-border;
    }

    Ticket.user {
        border-left: thick $accent;
    }

    Ticket.assistant {
        border-left: thick $primary;
    }

    Ticket.system {
        border-left: thick $warning;
        background: $secondary-bg;
    }
    """

    def __init__(
        self,
        content: str,
        ticket_type: TicketType = TicketType.USER,
        timestamp: datetime | None = None,
    ) -> None:
        """Initialize a ticket.

        Args:
            content: The message content (supports markdown)
            ticket_type: Type of ticket (user/assistant/system)
            timestamp: When the message was sent
        """
        super().__init__()
        self.content = content
        self.ticket_type = ticket_type
        self.timestamp = timestamp or datetime.now()

        # Apply CSS class based on type
        self.add_class(ticket_type.name.lower())

    def render(self) -> RenderableType:
        """Render the ticket content."""
        time_str = self.timestamp.strftime("%H:%M")

        # Create header
        type_emoji = {
            TicketType.USER: "👨‍🍳",
            TicketType.ASSISTANT: "🍳",
            TicketType.SYSTEM: "📋",
        }

        header = Text()
        header.append(f"{type_emoji.get(self.ticket_type, '')} ", style="bold")
        header.append(f"[{time_str}]", style="dim")

        # Try to render as markdown, fall back to plain text
        try:
            content = Markdown(self.content)
        except Exception:
            content = Text(self.content)

        return content


class TicketRail(VerticalScroll):
    """The scrollable chat history container.

    Displays tickets (messages) in chronological order,
    with the most recent at the bottom.
    """

    DEFAULT_CSS = """
    TicketRail {
        background: $secondary-bg;
        border: solid $panel-border;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 1 2;
    }

    TicketRail:focus {
        border: solid $accent;
    }
    """

    BORDER_TITLE = "📋 The Ticket"

    # Reactive list of messages
    messages: reactive[list[TicketMessage]] = reactive(list, init=False)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the ticket rail.

        Args:
            name: Widget name
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(name=name, id=id, classes=classes)
        self._messages: list[TicketMessage] = []

    def compose(self) -> ComposeResult:
        """Compose the initial empty state."""
        yield Static(
            "[dim italic]Waiting for orders...[/]", id="empty-state", classes="muted"
        )

    def add_ticket(
        self, content: str, ticket_type: TicketType = TicketType.USER
    ) -> Ticket:
        """Add a new ticket to the rail.

        Args:
            content: The message content
            ticket_type: Type of message

        Returns:
            The created Ticket widget
        """
        # Remove empty state on first message
        empty_state = self.query_one("#empty-state", Static)
        if empty_state:
            empty_state.remove()

        message = TicketMessage(content=content, ticket_type=ticket_type)
        self._messages.append(message)

        ticket = Ticket(
            content=content, ticket_type=ticket_type, timestamp=message.timestamp
        )
        self.mount(ticket)

        # Scroll to bottom
        self.scroll_end(animate=True)

        return ticket

    def add_user_message(self, content: str) -> Ticket:
        """Add a user message (Head Chef's order).

        Args:
            content: The message content

        Returns:
            The created Ticket widget
        """
        return self.add_ticket(content, TicketType.USER)

    def add_assistant_message(self, content: str) -> Ticket:
        """Add an assistant message (Kitchen's response).

        Args:
            content: The message content

        Returns:
            The created Ticket widget
        """
        return self.add_ticket(content, TicketType.ASSISTANT)

    def add_system_message(self, content: str) -> Ticket:
        """Add a system message (Kitchen announcement).

        Args:
            content: The message content

        Returns:
            The created Ticket widget
        """
        return self.add_ticket(content, TicketType.SYSTEM)

    def clear_tickets(self) -> None:
        """Clear all tickets from the rail."""
        self._messages.clear()
        # Remove all ticket widgets
        for ticket in self.query(Ticket):
            ticket.remove()
        # Restore empty state
        self.mount(
            Static(
                "[dim italic]Waiting for orders...[/]",
                id="empty-state",
                classes="muted",
            )
        )
