"""Git Setup Screen - Configure GitHub Token."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

if TYPE_CHECKING:
    pass


class GitSetupScreen(ModalScreen[bool]):
    """Modal screen for GitHub token configuration."""

    DEFAULT_CSS = """
    GitSetupScreen {
        align: center middle;
    }

    #git-container {
        width: 70;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }

    #git-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $accent;
    }

    #git-desc {
        text-align: center;
        margin-bottom: 2;
        color: $text-muted;
    }

    .input-label {
        margin-bottom: 1;
        text-style: bold;
    }

    .hint-text {
        margin-bottom: 2;
        color: $text-muted;
        text-style: italic;
    }

    Input {
        margin-bottom: 1;
    }

    #git-buttons {
        align: center middle;
        margin-top: 2;
    }

    Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="git-container"):
            yield Static("🔐 GitHub Token Setup", id="git-title")
            yield Static(
                "Configure your GitHub Personal Access Token for Git operations.\n"
                "This enables pushing, PR creation, and other GitHub API features.",
                id="git-desc",
            )

            # GitHub Token
            yield Static("GitHub Token:", classes="input-label")
            current_token = os.getenv("GITHUB_TOKEN", "")
            # Mask token if present
            masked = "••••" + current_token[-4:] if len(current_token) > 4 else ""
            yield Input(
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx",
                password=True,
                value=current_token if not masked else "",
                id="token-input",
            )
            yield Static(
                f"{'Current token: ' + masked if masked else 'No token configured'}",
                classes="hint-text",
            )

            # Info about token creation
            yield Static(
                "💡 Create a token at: github.com/settings/tokens", classes="hint-text"
            )

            # Buttons
            with Vertical(id="git-buttons"):
                yield Button("💾 Save Token", variant="success", id="save-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self) -> None:
        """Cancel setup."""
        self.dismiss(False)

    @on(Button.Pressed, "#save-btn")
    @on(Input.Submitted, "#token-input")
    def save(self) -> None:
        """Save the GitHub token to .env file."""
        token = self.query_one("#token-input", Input).value.strip()

        if not token:
            self.app.notify("Token cannot be empty!", severity="warning")
            return

        # Update environment variable
        os.environ["GITHUB_TOKEN"] = token

        # Save to .env file
        self._save_to_env("GITHUB_TOKEN", token)

        self.dismiss(True)

    def _save_to_env(self, key: str, value: str) -> None:
        """Save a key-value pair to the .env file."""
        env_path = Path.cwd() / ".env"

        # Read existing .env content
        lines: list[str] = []
        key_found = False

        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith(f"{key}="):
                        lines.append(f"{key}={value}\n")
                        key_found = True
                    else:
                        lines.append(line)

        # Add key if not found
        if not key_found:
            lines.append(f"{key}={value}\n")

        # Write back
        with open(env_path, "w") as f:
            f.writelines(lines)

    def on_mount(self) -> None:
        """Focus input on mount."""
        self.query_one("#token-input", Input).focus()
