from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class CommandPalette(ModalScreen):
    """A modal dialog showing available commands."""

    BINDINGS = [("escape", "dismiss", "Close")]

    COMMANDS = [
        ("/help", "Show this help menu"),
        ("/clear", "Clear tickets, plate, and reset stations"),
        ("/chef [task]", "Ask the Sous Chef to plan a task"),
        ("/plate", "Show current plate status"),
        ("/quit", "Exit the kitchen"),
    ]

    def action_dismiss(self) -> None:
        """Dismiss the screen."""
        self.dismiss()

    def compose(self) -> ComposeResult:
        # We gebruiken 'palette-container' om te matchen met de CSS
        with Container(id="palette-container"):
            # Title
            yield Label("👨‍🍳 ChefChat Command Menu", classes="palette-title")

            # Lijst met commando's
            with Vertical(classes="command-list"):
                for cmd, desc in self.COMMANDS:
                    with Horizontal(classes="command-row"):
                        # 'command-key' wordt blauw/info kleur in CSS
                        yield Label(cmd, classes="command-key")
                        # 'command-desc' wordt standaard tekstkleur
                        yield Label(desc, classes="command-desc")

            # Sluit knop onderaan
            yield Button("Close Menu", variant="primary", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close_btn":
            self.dismiss()
