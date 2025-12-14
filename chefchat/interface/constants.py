"""ChefChat TUI Constants - Centralized constants for the interface.

This module provides enums and constants to replace magic strings
throughout the TUI codebase, improving maintainability and type safety.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Final

from chefchat.core.compatibility import StrEnum


class StationName(StrEnum):
    """Station identifiers used throughout the TUI."""

    SOUS_CHEF = "sous_chef"
    LINE_COOK = "line_cook"
    SOMMELIER = "sommelier"
    EXPEDITOR = "expeditor"


class BusAction(StrEnum):
    """Actions for bus messages."""

    STATUS_UPDATE = "STATUS_UPDATE"
    LOG_MESSAGE = "LOG_MESSAGE"
    PLATE_CODE = "PLATE_CODE"
    STREAM_UPDATE = "STREAM_UPDATE"
    TERMINAL_LOG = "TERMINAL_LOG"
    NEW_TICKET = "NEW_TICKET"
    CANCEL_TICKET = "CANCEL_TICKET"
    TICKET_DONE = "TICKET_DONE"
    PLAN = "PLAN"
    TASTE_TEST = "TASTE_TEST"


class StatusString(StrEnum):
    """Status strings that come from the backend/agents."""

    IDLE = "idle"
    PLANNING = "planning"
    COOKING = "cooking"
    TESTING = "testing"
    REFACTORING = "refactoring"
    COMPLETE = "complete"
    ERROR = "error"


class StationStatus(Enum):
    """Internal TUI status states for logic handling."""

    IDLE = auto()  # "At ease" - waiting for orders
    WORKING = auto()  # "Firing" - actively cooking
    COMPLETE = auto()  # "Plated" - finished the order
    ERROR = auto()  # "86'd" - something went wrong


class TicketCommand(StrEnum):
    """Slash commands available in the TUI."""

    QUIT = "quit"
    HELP = "help"
    CLEAR = "clear"
    SETTINGS = "settings"
    CHEF = "chef"
    PLATE = "plate"
    MODES = "modes"
    STATUS = "status"
    MODEL = "model"
    WISDOM = "wisdom"
    ROAST = "roast"
    FORTUNE = "fortune"
    LAYOUT = "layout"
    LOG = "log"
    TASTE = "taste"
    TIMER = "timer"


class TUILayout(StrEnum):
    """Available TUI layout modes."""

    CHAT_ONLY = "chat"  # Clean chat interface only
    FULL_KITCHEN = "kitchen"  # Full 3-panel kitchen view


class PayloadKey(StrEnum):
    """Common keys used in bus message payloads."""

    STATION = "station"
    STATUS = "status"
    PROGRESS = "progress"
    MESSAGE = "message"
    TYPE = "type"
    CONTENT = "content"
    CODE = "code"
    LANGUAGE = "language"
    FILE_PATH = "file_path"
    FULL_CONTENT = "full_content"
    TICKET_ID = "ticket_id"
    REQUEST = "request"
    TASK = "task"


class MessageType(StrEnum):
    """Types of messages in the ticket rail/logs."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# Default station configuration - (station_id, display_name)
DEFAULT_STATIONS: Final[list[tuple[str, str]]] = [
    (StationName.SOUS_CHEF.value, "Sous Chef"),
    (StationName.LINE_COOK.value, "Line Cook"),
    (StationName.SOMMELIER.value, "Sommelier"),
    (StationName.EXPEDITOR.value, "Expeditor"),
]

# Whisk animation frames
WHISK_FRAMES: Final[list[str]] = ["   🥄", "  🥄 ", " 🥄  ", "🥄   ", " 🥄  ", "  🥄 "]

# Status emoji mapping for UI display
STATUS_EMOJI: Final[dict[str, str]] = {
    StatusString.IDLE.value: "⚪",
    StatusString.PLANNING.value: "📋",
    StatusString.COOKING.value: "🔥",
    StatusString.TESTING.value: "🧪",
    StatusString.REFACTORING.value: "🔧",
    StatusString.COMPLETE.value: "✅",
    StatusString.ERROR.value: "❌",
}

# Ticket type emojis
TICKET_EMOJI: Final[dict[str, str]] = {
    "user": "👨‍🍳",
    "assistant": "🍳",
    "system": "📋",
}

# Characters to sanitize from markdown input
MARKDOWN_SANITIZE_CHARS: Final[dict[str, str]] = {
    "\x00": "",  # Null bytes
    "\x0b": "",  # Vertical tab
    "\x0c": "",  # Form feed
}
