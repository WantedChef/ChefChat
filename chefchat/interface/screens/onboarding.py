"""Onboarding Screen for API Key Setup."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

from chefchat.core.config import GLOBAL_ENV_FILE, VibeConfig

if TYPE_CHECKING:
    pass


class OnboardingScreen(ModalScreen[str | None]):
    """Modal screen for API key onboarding."""

    DEFAULT_CSS = """
    OnboardingScreen {
        align: center middle;
    }

    #onboarding-container {
        width: 60;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }

    #onboarding-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $accent;
    }

    #onboarding-desc {
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

    Select {
        margin-bottom: 2;
    }

    #onboarding-buttons {
        align: center middle;
        margin-top: 1;
    }

    Button {
        width: 100%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._config: VibeConfig | None = None
        try:
            # Try to load config without validation to get providers
            self._config = VibeConfig.model_construct()
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        with Container(id="onboarding-container"):
            yield Static("🔑 ChefChat Setup", id="onboarding-title")
            yield Static(
                "To start cooking, we need an API key for your AI provider.",
                id="onboarding-desc",
            )

            # Provider Selection
            yield Static("Select Provider:", classes="input-label")
            providers = []
            if self._config:
                providers = [
                    (p.name.capitalize(), p.name) for p in self._config.providers
                ]
            else:
                # Fallback defaults
                providers = [
                    ("Mistral", "mistral"),
                    ("OpenAI", "openai"),
                    ("Local (Llama.cpp)", "llamacpp"),
                ]

            yield Select(
                providers, allow_blank=False, value="mistral", id="provider-select"
            )

            # API Key Input
            yield Static("API Key:", classes="input-label")
            yield Input(
                placeholder="Enter your API key (sk-...)",
                password=True,
                id="api-key-input",
            )

            # Buttons
            with Vertical(id="onboarding-buttons"):
                yield Button("Save & Start Cooking", variant="success", id="save-btn")

    @on(Button.Pressed, "#save-btn")
    @on(Input.Submitted, "#api-key-input")
    def save_key(self) -> None:
        """Save the API key to .env file."""
        # Check if called from Input (event has 'value') or Button
        # We need to get values from widgets regardless
        provider = self.query_one("#provider-select", Select).value
        api_key = self.query_one("#api-key-input", Input).value

        # Local provider doesn't strictly need a key
        if not api_key and provider != "llamacpp":
            self.notify("Please enter an API key", severity="error")
            return

        if not provider:
            self.notify("Please select a provider", severity="error")
            return

        # Determine env var name based on provider
        # This is a simplification; ideally we'd look up the provider config again
        env_var_name = f"{str(provider).upper()}_API_KEY"

        try:
            # For local, we might not need to save anything if key is empty
            if not api_key and provider == "llamacpp":
                self.dismiss(str(provider))
                return

            # Save to .env file
            GLOBAL_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Read existing lines to preserve other keys
            lines = []
            if GLOBAL_ENV_FILE.exists():
                lines = GLOBAL_ENV_FILE.read_text().splitlines()

            # Remove existing key if present
            lines = [l for l in lines if not l.startswith(f"{env_var_name}=")]

            # Append new key
            lines.append(f"{env_var_name}={api_key}")

            # Write back
            GLOBAL_ENV_FILE.write_text("\n".join(lines) + "\n")

            # Set in current process for immediate use
            os.environ[env_var_name] = api_key

            self.dismiss(str(provider))

        except Exception as e:
            self.notify(f"Failed to save API key: {e}", severity="error")

    def on_mount(self) -> None:
        """Focus input on mount."""
        self.query_one("#api-key-input", Input).focus()
