"""ChefChat Activity Logger - Logs agent activities for the Kitchen Logbook.

Provides human-readable logging of what chefs/agents are doing and which tools they use.
Logs are saved to ~/.chefchat/logs/ and displayed in the Kitchen Logbook widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class ActivityType(Enum):
    """Type of activity being logged."""

    CHEF_THINKING = "thinking"
    CHEF_RESPONDING = "responding"
    TOOL_START = "tool_start"
    TOOL_SUCCESS = "tool_success"
    TOOL_ERROR = "tool_error"
    SYSTEM = "system"


@dataclass
class ActivityEntry:
    """A single activity log entry."""

    timestamp: datetime
    activity_type: ActivityType
    chef_name: str
    message: str
    tool_name: str | None = None
    details: str | None = None

    def format_for_display(self) -> str:
        """Format for UI display (short, human-readable)."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        emoji = self._get_emoji()
        return f"[dim]{time_str}[/] {emoji} {self.message}"

    def format_for_log(self) -> str:
        """Format for file logging (detailed)."""
        time_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        details_str = f" | {self.details}" if self.details else ""
        return f"[{time_str}] [{self.activity_type.value}] {self.chef_name}: {self.message}{details_str}"

    def _get_emoji(self) -> str:
        """Get emoji for activity type."""
        return {
            ActivityType.CHEF_THINKING: "🍳",
            ActivityType.CHEF_RESPONDING: "💬",
            ActivityType.TOOL_START: "🔧",
            ActivityType.TOOL_SUCCESS: "✅",
            ActivityType.TOOL_ERROR: "❌",
            ActivityType.SYSTEM: "📋",
        }.get(self.activity_type, "•")


# Friendly names for tools
TOOL_DISPLAY_NAMES: dict[str, str] = {
    "read_file": "Bestand lezen",
    "write_file": "Bestand schrijven",
    "search_replace": "Tekst bewerken",
    "execute_command": "Commando uitvoeren",
    "list_directory": "Map bekijken",
    "glob_tool": "Bestanden zoeken",
    "grep_tool": "Tekst zoeken",
    "todo": "Takenlijst",
}


def get_tool_display_name(tool_name: str) -> str:
    """Get human-readable name for a tool."""
    return TOOL_DISPLAY_NAMES.get(tool_name, tool_name)


class ActivityLogger:
    """Logs chef/agent activities to file and memory."""

    MAX_ENTRIES = 100  # Keep last N entries in memory
    PREVIEW_MAX_LENGTH = 50  # Max characters for preview text

    def __init__(self, log_dir: Path | None = None) -> None:
        """Initialize the activity logger."""
        self._log_dir = log_dir or Path.home() / ".chefchat" / "logs"
        self._activities: list[ActivityEntry] = []
        self._tool_calls: list[ActivityEntry] = []
        self._listeners: list[Callable[[ActivityEntry], None]] = []
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        """Create log directory if it doesn't exist."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Could not create log directory: %s", e)

    def _get_log_file(self) -> Path:
        """Get today's log file path."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self._log_dir / f"activity_{date_str}.log"

    def add_listener(self, callback: Callable[[ActivityEntry], None]) -> None:
        """Add a callback to be notified of new activities."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ActivityEntry], None]) -> None:
        """Remove a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self, entry: ActivityEntry) -> None:
        """Notify all listeners of a new entry."""
        for listener in self._listeners:
            try:
                listener(entry)
            except Exception as e:
                logger.warning("Listener error: %s", e)

    def _write_to_file(self, entry: ActivityEntry) -> None:
        """Append entry to today's log file."""
        try:
            log_file = self._get_log_file()
            with log_file.open("a", encoding="utf-8") as f:
                f.write(entry.format_for_log() + "\n")
        except Exception as e:
            logger.warning("Could not write to log file: %s", e)

    def _add_entry(self, entry: ActivityEntry, is_tool: bool = False) -> None:
        """Add an entry to the appropriate list and notify listeners."""
        if is_tool:
            self._tool_calls.append(entry)
            if len(self._tool_calls) > self.MAX_ENTRIES:
                self._tool_calls.pop(0)
        else:
            self._activities.append(entry)
            if len(self._activities) > self.MAX_ENTRIES:
                self._activities.pop(0)

        self._write_to_file(entry)
        self._notify_listeners(entry)

    def log_chef_thinking(self, chef_name: str = "Chef") -> None:
        """Log that a chef is thinking/processing."""
        entry = ActivityEntry(
            timestamp=datetime.now(),
            activity_type=ActivityType.CHEF_THINKING,
            chef_name=chef_name,
            message=f"{chef_name} denkt na...",
        )
        self._add_entry(entry)

    def log_chef_responding(self, chef_name: str = "Chef", preview: str = "") -> None:
        """Log that a chef is responding."""
        msg = f"{chef_name} antwoordt"
        if preview:
            max_len = self.PREVIEW_MAX_LENGTH
            short_preview = (
                preview[:max_len] + "..." if len(preview) > max_len else preview
            )
            msg = f'{chef_name} zegt: "{short_preview}"'
        entry = ActivityEntry(
            timestamp=datetime.now(),
            activity_type=ActivityType.CHEF_RESPONDING,
            chef_name=chef_name,
            message=msg,
        )
        self._add_entry(entry)

    def log_tool_start(self, tool_name: str, chef_name: str = "Chef") -> None:
        """Log that a tool is being called."""
        display_name = get_tool_display_name(tool_name)
        entry = ActivityEntry(
            timestamp=datetime.now(),
            activity_type=ActivityType.TOOL_START,
            chef_name=chef_name,
            message=f"toolcall [{tool_name}]",
            tool_name=tool_name,
            details=display_name,
        )
        self._add_entry(entry, is_tool=True)

    def log_tool_success(self, tool_name: str, chef_name: str = "Chef") -> None:
        """Log successful tool completion."""
        entry = ActivityEntry(
            timestamp=datetime.now(),
            activity_type=ActivityType.TOOL_SUCCESS,
            chef_name=chef_name,
            message=f"toolcall [{tool_name}] ✓",
            tool_name=tool_name,
        )
        self._add_entry(entry, is_tool=True)

    def log_tool_error(
        self, tool_name: str, error: str = "", chef_name: str = "Chef"
    ) -> None:
        """Log tool error."""
        short_error = error[:100] if error else "fout"
        entry = ActivityEntry(
            timestamp=datetime.now(),
            activity_type=ActivityType.TOOL_ERROR,
            chef_name=chef_name,
            message=f"toolcall [{tool_name}] ✗",
            tool_name=tool_name,
            details=short_error,
        )
        self._add_entry(entry, is_tool=True)

    def log_system(self, message: str) -> None:
        """Log a system message."""
        entry = ActivityEntry(
            timestamp=datetime.now(),
            activity_type=ActivityType.SYSTEM,
            chef_name="Systeem",
            message=message,
        )
        self._add_entry(entry)

    @property
    def activities(self) -> list[ActivityEntry]:
        """Get recent activity entries."""
        return self._activities.copy()

    @property
    def tool_calls(self) -> list[ActivityEntry]:
        """Get recent tool call entries."""
        return self._tool_calls.copy()

    def clear(self) -> None:
        """Clear in-memory entries (logs are preserved on disk)."""
        self._activities.clear()
        self._tool_calls.clear()


# Global instance for easy access
_activity_logger: ActivityLogger | None = None


def get_activity_logger() -> ActivityLogger:
    """Get or create the global activity logger instance."""
    global _activity_logger
    if _activity_logger is None:
        _activity_logger = ActivityLogger()
    return _activity_logger
