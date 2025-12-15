"""Enhanced Model Manager Screen with feature filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static, TabbedContent, TabPane

from chefchat.core.config import VibeConfig
from chefchat.interface.constants import MAX_FEATURES_DISPLAY

if TYPE_CHECKING:
    pass

# MAX_FEATURES_DISPLAY imported from interface.constants
CHEAP_MODEL_PRICE_THRESHOLD = 0.5


class ModelManagerScreen(ModalScreen[str | None]):
    """Comprehensive model management screen with filtering."""

    def __init__(self, config: VibeConfig) -> None:
        super().__init__()
        self._config = config
        self._selected_model = None

    def compose(self) -> ComposeResult:
        yield Header("🤖 Model Manager")

        # Feature filter buttons
        yield Horizontal(
            Static("Filter: "),
            Button("All", id="filter-all", variant="primary"),
            Button("Speed", id="filter-speed"),
            Button("Reasoning", id="filter-reasoning"),
            Button("Multimodal", id="filter-multimodal"),
            Button("Cost", id="filter-cost"),
            id="filter-buttons",
            classes="horizontal",
        )

        # Main content with tabs
        yield TabbedContent(
            TabPane("All Models", id="all-models"),
            TabPane("Fast Models", id="speed-models"),
            TabPane("Reasoning", id="reasoning-models"),
            TabPane("Multimodal", id="multimodal-models"),
            TabPane("Cost Effective", id="cost-models"),
            id="model-tabs",
            classes="content",
        )

        # Action buttons
        yield Horizontal(
            Button("Select Model", variant="success", id="select-btn"),
            Button("Info", id="info-btn"),
            Button("Test", id="test-btn"),
            Button("Cancel", variant="error", id="cancel-btn"),
            id="action-buttons",
            classes="horizontal",
        )

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted."""
        self._populate_all_models()

    def _get_filtered_models(self, filter_type: str) -> list:
        """Get models filtered by type."""
        if filter_type == "all":
            return self._config.models
        elif filter_type == "speed":
            return [m for m in self._config.models if "speed" in m.features]
        elif filter_type == "reasoning":
            return [m for m in self._config.models if "reasoning" in m.features]
        elif filter_type == "multimodal":
            return [
                m
                for m in self._config.models
                if m.multimodal or "multimodal" in m.features
            ]
        elif filter_type == "cost":
            return sorted(
                self._config.models, key=lambda m: m.input_price + m.output_price
            )[:5]
        return []

    def _populate_all_models(self) -> None:
        """Populate all models tab initially."""
        self._apply_filter("all")

    def _create_model_widget(self, model: Any, is_active: bool) -> Vertical:
        """Create a widget for a single model."""
        status_icon = "🟢" if is_active else "⚪"
        select_status = "✅ Selected" if model.alias == self._selected_model else ""

        # Determine button variant
        if is_active:
            variant = "success"
        elif model.alias == self._selected_model:
            variant = "primary"
        else:
            variant = "default"

        btn = Button(
            f"{status_icon} {model.alias} {select_status}",
            id=f"model-{model.alias}",
            variant=variant,
            classes="model-btn",
        )

        details = [f"• Provider: {model.provider}", f"• Temp: {model.temperature}"]

        if model.input_price or model.output_price:
            details.append(f"• ${model.input_price}/{model.output_price} (in/out)")

        if model.features:
            features = ", ".join(sorted(model.features)[:MAX_FEATURES_DISPLAY])
            if len(model.features) > MAX_FEATURES_DISPLAY:
                features += "..."
            details.append(f"• {features}")

        return Vertical(
            btn,
            Static("\n".join(details), classes="model-details"),
            classes="model-container",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "cancel-btn":
            self.dismiss(None)
        elif button_id == "select-btn":
            self._handle_select()
        elif button_id == "info-btn":
            self._handle_info()
        elif button_id == "test-btn":
            self._handle_test()
        elif button_id.startswith("filter-"):
            filter_type = button_id.replace("filter-", "")
            self._apply_filter(filter_type)
        elif button_id.startswith("model-"):
            # Handle direct model selection from list
            alias = button_id.replace("model-", "")
            self._selected_model = alias
            self.notify(f"Selected: {alias}")
            # Refresh current view to update button states
            current_tab = self.query_one("#model-tabs", TabbedContent).active
            # Map tab ID back to filter type
            filter_map = {
                "all-models": "all",
                "speed-models": "speed",
                "reasoning-models": "reasoning",
                "multimodal-models": "multimodal",
                "cost-models": "cost",
            }
            if current_tab in filter_map:
                self._apply_filter(filter_map[current_tab])

    def _apply_filter(self, filter_type: str) -> None:
        """Apply filter to model list."""
        filtered_models = self._get_filtered_models(filter_type)

        # Update appropriate tab
        tab_id_map = {
            "all": "all-models",
            "speed": "speed-models",
            "reasoning": "reasoning-models",
            "multimodal": "multimodal-models",
            "cost": "cost-models",
        }

        tab_id = tab_id_map.get(filter_type, "all-models")
        tab = self.query_one(f"#{tab_id}", TabPane)

        if tab:
            tab.remove_children()
            # Use a Scrollable Container
            container = Container(classes="scrollable-list")

            for model in filtered_models:
                is_active = model.alias == self._config.active_model
                widget = self._create_model_widget(model, is_active)
                container.mount(widget)

            tab.mount(container)

            # Switch to this tab
            tabbed_content = self.query_one("#model-tabs", TabbedContent)
            tabbed_content.active = tab_id

    def _handle_select(self) -> None:
        """Handle model selection."""
        if self._selected_model:
            self.dismiss(self._selected_model)
        else:
            # Default to first available model
            self.dismiss("groq-8b")

    def _handle_info(self) -> None:
        """Show model info (placeholder - would open info modal)."""
        if self._selected_model:
            self.notify(f"Info for {self._selected_model}")

    def _handle_test(self) -> None:
        """Test model (placeholder - would run connectivity test)."""
        if self._selected_model:
            self.notify(f"Testing {self._selected_model}...")

    DEFAULT_CSS = """
    ModelManagerScreen {
        layout: grid;
        grid-size: 1 3;
        grid-rows: auto 1fr auto;
        padding: 1;
    }

    #filter-buttons {
        height: auto;
        padding: 1;
        background: $surface;
        border: round $accent;
        margin-bottom: 1;
    }

    #filter-buttons > * {
        margin: 0 1;
    }

    #model-tabs {
        height: 1fr;
    }

    #action-buttons {
        height: auto;
        padding: 1;
        background: $surface;
        border: round $accent;
        margin-top: 1;
        align: center middle;
    }

    #action-buttons > * {
        margin: 0 1;
    }

    TabPane {
        padding: 1;
        background: $panel;
        border: round $primary;
    }

    .model-container {
        border: solid $accent;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        background: $surface;
    }

    .model-btn {
        width: 100%;
        margin-top: 1;
    }

    .model-details {
        color: $text-muted;
        margin-left: 1;
        margin-bottom: 1;
    }

    .scrollable-list {
        height: 1fr;
        overflow-y: auto;
    }
    """
