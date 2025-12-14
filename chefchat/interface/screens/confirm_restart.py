"""Confirm Restart Screen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static

# TUI Preferences File (persists layout choice etc.)
TUI_PREFS_FILE = Path.home() / ".vibe" / "tui_prefs.json"


def load_tui_preferences() -> dict:
    """Load TUI preferences from file."""
    try:
        if TUI_PREFS_FILE.exists():
            return json.loads(TUI_PREFS_FILE.read_text())
    except Exception:
        pass
    return {}


def save_tui_preference(key: str, value: str) -> None:
    """Save a TUI preference to file."""
    try:
        TUI_PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        prefs = load_tui_preferences()
        prefs[key] = value
        TUI_PREFS_FILE.write_text(json.dumps(prefs, indent=2))
    except Exception:
        pass


def get_saved_layout() -> str:
    """Get the saved layout preference, or 'chat' as default."""
    prefs = load_tui_preferences()
    return prefs.get("layout", "chat")


class ConfirmRestartScreen(ModalScreen):
    """Modal screen to confirm restart after layout change."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("y", "confirm", "Yes", show=False),
        Binding("n", "cancel", "No", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    ConfirmRestartScreen {
        align: center middle;
    }

    #confirm-dialog {
        width: 50;
        height: 12;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }

    #confirm-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #confirm-message {
        text-align: center;
        margin-bottom: 1;
    }

    #confirm-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    .confirm-button {
        width: 16;
        margin: 0 2;
    }
    """

    def __init__(self, new_layout: str) -> None:
        super().__init__()
        self.new_layout = new_layout

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Static("🔄 Restart Required", id="confirm-title")
            yield Static(
                f"Switch to **{self.new_layout}** layout?\n"
                "The TUI will restart automatically.",
                id="confirm-message",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    "Yes [Y]", variant="success", id="yes-btn", classes="confirm-button"
                )
                yield Button(
                    "No [N]", variant="error", id="no-btn", classes="confirm-button"
                )

    def action_confirm(self) -> None:
        """User confirmed restart."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """User cancelled."""
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)
