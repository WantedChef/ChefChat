"""Tool Approval Screen."""

from __future__ import annotations

from typing import Any, ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea


class ToolApprovalScreen(ModalScreen[tuple[str, str | None]]):
    """Modal screen for approving tool execution."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("y", "approve", "Approve", show=True),
        Binding("n", "reject", "Reject", show=True),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    ToolApprovalScreen {
        align: center middle;
    }

    #approval-container {
        width: 70;
        height: auto;
        background: $surface;
        border: round $warning;
        padding: 1 2;
    }

    #approval-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $warning;
    }

    #tool-name {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    TextArea {
        height: 10;
        margin-bottom: 1;
        background: $primary-bg;
        border: solid $panel-border;
    }

    #approval-buttons {
        align: center middle;
        height: 3;
    }

    .approval-btn {
        margin: 0 2;
        width: 16;
    }
    """

    def __init__(self, tool_name: str, tool_args: dict[str, Any] | str) -> None:
        super().__init__()
        self.tool_name = tool_name
        # Pretty print args
        if isinstance(tool_args, dict):
            import json

            self.tool_args = json.dumps(tool_args, indent=2)
        else:
            self.tool_args = str(tool_args)

    def compose(self) -> ComposeResult:
        with Container(id="approval-container"):
            yield Static("🛡️ Tool Approval Required", id="approval-title")
            yield Static(f"Tool: {self.tool_name}", id="tool-name")

            yield TextArea(self.tool_args, language="json", read_only=True)

            with Horizontal(id="approval-buttons"):
                yield Button(
                    "Approve [Y]",
                    variant="success",
                    id="approve-btn",
                    classes="approval-btn",
                )
                yield Button(
                    "Reject [N]",
                    variant="error",
                    id="reject-btn",
                    classes="approval-btn",
                )

    def action_approve(self) -> None:
        self.dismiss(("execute", None))

    def action_reject(self) -> None:
        self.dismiss(("skip", "User rejected"))

    @on(Button.Pressed, "#approve-btn")
    def on_approve(self) -> None:
        self.action_approve()

    @on(Button.Pressed, "#reject-btn")
    def on_reject(self) -> None:
        self.action_reject()
