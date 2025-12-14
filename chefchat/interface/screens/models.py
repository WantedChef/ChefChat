"""Model Selection Screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, RadioButton, RadioSet, Static

from chefchat.core.config import VibeConfig

if TYPE_CHECKING:
    pass


class ModelSelectionScreen(ModalScreen[str | None]):
    """Modal screen for selecting the active model."""

    DEFAULT_CSS = """
    ModelSelectionScreen {
        align: center middle;
    }

    #models-container {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }

    #models-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $accent;
    }

    RadioSet {
        margin: 1 0;
    }

    #models-buttons {
        align: center middle;
        margin-top: 1;
        height: 3;
    }

    .model-btn {
        margin: 0 1;
        width: 14;
    }
    """

    def __init__(self, config: VibeConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        with Container(id="models-container"):
            yield Static("🤖 Select Model", id="models-title")

            with VerticalScroll():
                with RadioSet(id="model-radios"):
                    for model in self._config.models:
                        label = f"{model.alias} ({model.provider})"
                        # Check if this is the active model
                        is_active = model.alias == self._config.active_model
                        yield RadioButton(
                            label, value=is_active, id=f"model-{model.alias}"
                        )

            with Container(id="models-buttons"):
                yield Button(
                    "Select", variant="success", id="select-btn", classes="model-btn"
                )
                yield Button(
                    "Cancel", variant="error", id="cancel-btn", classes="model-btn"
                )

    @on(Button.Pressed, "#select-btn")
    def select_model(self) -> None:
        """Confirm selection."""
        radios = self.query_one("#model-radios", RadioSet)
        if radios.pressed_button:
            # Extract alias from ID "model-alias"
            selected_id = radios.pressed_button.id
            if selected_id:
                alias = selected_id.replace("model-", "")
                self.dismiss(alias)
                return

        self.dismiss(None)

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self) -> None:
        """Cancel selection."""
        self.dismiss(None)
