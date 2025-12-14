"""Bot Setup Screen."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Static

from chefchat.bots.manager import BotManager
from chefchat.core.config import VibeConfig

if TYPE_CHECKING:
    pass


class BotSetupScreen(ModalScreen[bool]):
    """Modal screen for Bot setup (Telegram/Discord)."""

    DEFAULT_CSS = """
    BotSetupScreen {
        align: center middle;
    }

    #setup-container {
        width: 60;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }

    #setup-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $accent;
    }

    #setup-desc {
        text-align: center;
        margin-bottom: 2;
        color: $text-muted;
    }

    .input-label {
        margin-bottom: 1;
        text-style: bold;
    }

    Input {
        margin-bottom: 2;
    }
    Checkbox {
        margin-bottom: 2;
    }

    #setup-buttons {
        align: center middle;
        margin-top: 1;
    }

    Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def __init__(self, bot_type: str) -> None:
        super().__init__()
        self.bot_type = bot_type.lower()
        self.bot_manager = BotManager(VibeConfig.model_construct())

    def compose(self) -> ComposeResult:
        with Container(id="setup-container"):
            yield Static(f"🤖 {self.bot_type.title()} Bot Setup", id="setup-title")
            yield Static(
                f"Enter configuration for {self.bot_type.title()} bot.",
                id="setup-desc",
            )

            # Bot Token
            yield Static("Bot Token:", classes="input-label")
            env_key = f"{self.bot_type.upper()}_BOT_TOKEN"
            current_token = os.getenv(env_key, "")
            yield Input(
                placeholder="Enter Bot Token",
                password=True,
                value=current_token,
                id="token-input",
            )

            # Allowed User
            yield Static("Allowed User ID (Optional):", classes="input-label")
            yield Input(
                placeholder="User ID (e.g. 12345678)",
                id="user-input",
            )

            # Systemd Control (Telegram only)
            if self.bot_type == "telegram":
                yield Checkbox(
                    "Enable Remote Control (Systemd)",
                    value=os.getenv(
                        "CHEFCHAT_ENABLE_TELEGRAM_SYSTEMD_CONTROL", ""
                    ).lower() in {"1", "true", "yes", "on"},
                    id="systemd-control-checkbox",
                )

            # Buttons
            with Vertical(id="setup-buttons"):
                yield Button("Save & Close", variant="success", id="save-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#save-btn")
    @on(Input.Submitted, "#token-input")
    @on(Input.Submitted, "#user-input")
    def save(self) -> None:
        token = self.query_one("#token-input", Input).value.strip()
        user_id = self.query_one("#user-input", Input).value.strip()

        if token:
            self.bot_manager.update_env(f"{self.bot_type.upper()}_BOT_TOKEN", token)
        
        if user_id:
            self.bot_manager.add_allowed_user(self.bot_type, user_id)

        # Handle Systemd Control (Telegram only)
        if self.bot_type == "telegram":
            checkbox = self.query_one("#systemd-control-checkbox", Checkbox)
            self.bot_manager.update_env(
                "CHEFCHAT_ENABLE_TELEGRAM_SYSTEMD_CONTROL", "1" if checkbox.value else "0"
            )

        self.dismiss(True)

    def on_mount(self) -> None:
        """Focus input on mount."""
        self.query_one("#token-input", Input).focus()
