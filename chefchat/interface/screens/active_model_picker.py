"""Active Model Picker Screen."""

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


class ActiveModelPickerScreen(ModalScreen[str | None]):
    """Modal screen for selecting the active model."""

    CSS = """
    ActiveModelPickerScreen {
        align: center middle;
    }

    #picker-container {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }

    #picker-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $accent;
    }

    #picker-desc {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    RadioSet {
        margin: 1 0;
        background: $surface;
        border: solid $panel-border;
        padding: 1;
    }

    RadioButton {
        width: 100%;
        padding: 1;
    }

    RadioButton:hover {
        background: $secondary-bg;
    }

    #picker-buttons {
        align: center middle;
        margin-top: 2;
        height: 3;
    }

    #action-buttons {
        align: center middle;
        margin-top: 1;
        height: 3;
    }

    .picker-btn {
        margin: 0 1;
        width: 14;
    }

    #manage-btn {
        width: 20;
        border: none;
        background: transparent;
        color: $text-muted;
        text-style: underline;
        margin-bottom: 1;
    }
    #manage-btn:hover {
        color: $accent;
    }
    """

    def __init__(self, config: VibeConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        with Container(id="picker-container"):
            yield Static("🤖 Select Active Model", id="picker-title")
            yield Static("Choose which AI model you want to use as the main brain.", id="picker-desc")

            with VerticalScroll():
                with RadioSet(id="model-radios"):
                    for model in self._config.models:
                        label = f"{model.alias} ({model.provider})"
                        is_active = (model.alias == self._config.active_model)
                        yield RadioButton(label, value=is_active, id=f"model-{model.alias}")

            # Separate actions
            with Container(id="action-buttons"):
                yield Button("Manage Models...", id="manage-btn", variant="default")

            with Container(id="picker-buttons"):
                yield Button("Select", variant="success", id="select-btn", classes="picker-btn")
                yield Button("Cancel", variant="error", id="cancel-btn", classes="picker-btn")

    @on(Button.Pressed, "#select-btn")
    def select_model(self) -> None:
        """Confirm selection."""
        radios = self.query_one("#model-radios", RadioSet)
        if radios.pressed_button:
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

    @on(Button.Pressed, "#manage-btn")
    def manage_models(self) -> None:
        """Open model manager."""
        from chefchat.interface.screens.models import ModelManagerScreen
        self.app.push_screen(ModelManagerScreen(self._config))
