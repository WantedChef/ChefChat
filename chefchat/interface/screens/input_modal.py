"""Generic Input Modal for simple data entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

if TYPE_CHECKING:
    pass


class InputModal(ModalScreen[str | None]):
    """Modal screen for generic text input."""

    DEFAULT_CSS = """
    InputModal {
        align: center middle;
    }

    #input-container {
        width: 60;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }

    #input-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $accent;
    }

    #input-desc {
        text-align: center;
        margin-bottom: 2;
        color: $text-muted;
    }

    Input {
        margin-bottom: 2;
    }

    #input-buttons {
        align: center middle;
        margin-top: 1;
    }

    Button {
        width: 100%;
    }
    """

    def __init__(
        self,
        title: str,
        description: str,
        placeholder: str = "",
        password: bool = False,
        default_value: str = "",
        save_label: str = "Save",
    ) -> None:
        super().__init__()
        self._title = title
        self._desc = description
        self._placeholder = placeholder
        self._password = password
        self._default = default_value
        self._save_label = save_label

    def compose(self) -> ComposeResult:
        with Container(id="input-container"):
            yield Static(self._title, id="input-title")
            yield Static(self._desc, id="input-desc")

            yield Input(
                value=self._default,
                placeholder=self._placeholder,
                password=self._password,
                id="modal-input",
            )

            with Vertical(id="input-buttons"):
                yield Button(self._save_label, variant="success", id="save-btn")

    @on(Button.Pressed, "#save-btn")
    @on(Input.Submitted, "#modal-input")
    def save_value(self) -> None:
        """Return the value."""
        val = self.query_one("#modal-input", Input).value
        self.dismiss(val)

    def on_mount(self) -> None:
        """Focus input on mount."""
        self.query_one("#modal-input", Input).focus()
