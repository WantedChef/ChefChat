"""ActivityPanel Widget - Display agent activities and tool calls.

Extracted from ThePlate for reusability and cleaner separation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

if TYPE_CHECKING:
    from chefchat.interface.activity_logger import ActivityEntry


class ActivityPanel(Static):
    """Panel displaying agent activities (Activiteiten).

    Shows a scrollable log of chef/agent activities in a readable format.
    Can receive ActivityEntry objects and format them for display.
    """

    DEFAULT_CSS = """
    ActivityPanel {
        height: 100%;
        width: 100%;
    }

    ActivityPanel RichLog {
        height: 100%;
    }
    """

    def __init__(
        self,
        title: str = "📓 Activiteiten",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the activity panel.

        Args:
            title: Panel title
            name: Widget name
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(name=name, id=id, classes=classes)
        self._title = title

    def compose(self) -> ComposeResult:
        """Compose the panel content."""
        with Vertical():
            yield RichLog(id="activity-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        """Initialize with welcome message."""
        self._get_log().write(f"[dim]{self._title} gestart...[/]")

    def _get_log(self) -> RichLog:
        """Get the internal RichLog widget."""
        return self.query_one("#activity-log", RichLog)

    def log_activity(self, entry: ActivityEntry) -> None:
        """Add an activity entry to the log.

        Args:
            entry: The activity entry to display
        """
        formatted = entry.format_for_display()
        self._get_log().write(formatted)

    def log_message(self, message: str) -> None:
        """Add a plain message to the log.

        Args:
            message: The message to display
        """
        self._get_log().write(message)

    def clear(self) -> None:
        """Clear the activity log."""
        self._get_log().clear()


class ToolPanel(Static):
    """Panel displaying tool calls (Gereedschap).

    Shows a scrollable log of tool executions with success/failure status.
    """

    DEFAULT_CSS = """
    ToolPanel {
        height: 100%;
        width: 100%;
    }

    ToolPanel RichLog {
        height: 100%;
    }
    """

    def __init__(
        self,
        title: str = "🔧 Gereedschap",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the tool panel.

        Args:
            title: Panel title
            name: Widget name
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(name=name, id=id, classes=classes)
        self._title = title

    def compose(self) -> ComposeResult:
        """Compose the panel content."""
        with Vertical():
            yield RichLog(id="tool-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        """Initialize with welcome message."""
        self._get_log().write(f"[dim]{self._title} - Wachtend op tool calls...[/]")

    def _get_log(self) -> RichLog:
        """Get the internal RichLog widget."""
        return self.query_one("#tool-log", RichLog)

    def log_tool_start(self, tool_name: str, chef_name: str = "Chef") -> None:
        """Log the start of a tool execution.

        Args:
            tool_name: Name of the tool being executed
            chef_name: Name of the chef/agent using the tool
        """
        self._get_log().write(
            f"[cyan]⚙️[/] {chef_name} gebruikt [bold]{tool_name}[/]..."
        )

    def log_tool_success(self, tool_name: str) -> None:
        """Log successful tool completion.

        Args:
            tool_name: Name of the tool that completed
        """
        self._get_log().write(f"[green]✅[/] {tool_name} [green]voltooid[/]")

    def log_tool_error(self, tool_name: str, error: str = "") -> None:
        """Log tool failure.

        Args:
            tool_name: Name of the tool that failed
            error: Error message
        """
        msg = f"[red]❌[/] {tool_name} [red]gefaald[/]"
        if error:
            msg += f": {error}"
        self._get_log().write(msg)

    def log_entry(self, entry: ActivityEntry) -> None:
        """Log an activity entry (for tools).

        Args:
            entry: The activity entry to display
        """
        self._get_log().write(entry.format_for_display())

    def clear(self) -> None:
        """Clear the tool log."""
        self._get_log().clear()
