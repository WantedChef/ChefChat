"""Model Management Screen."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

from chefchat.core.config import (
    GLOBAL_ENV_FILE,
    Backend,
    ModelConfig,
    ProviderConfig,
    VibeConfig,
)

if TYPE_CHECKING:
    pass


class ModelManagerScreen(ModalScreen):
    """Screen for managing API providers and models."""

    CSS = """
    ModelManagerScreen {
        align: center middle;
    }

    #manager-container {
        width: 90%;
        height: 90%;
        background: $surface;
        border: round $accent;
        padding: 1 2;
        layout: vertical;
    }

    #manager-header {
        height: 3;
        dock: top;
        content-align: center middle;
        border-bottom: solid $panel-border;
        color: $accent;
        text-style: bold;
    }

    #main-content {
        height: 1fr;
        margin-top: 1;
    }

    /* Sidebar for providers */
    #provider-list-container {
        width: 25%;
        height: 100%;
        border-right: solid $panel-border;
        padding-right: 1;
    }

    #provider-list-label {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    ListView {
        height: 1fr;
        border: solid $panel-border;
        margin-bottom: 1;
    }

    ListItem {
        padding: 1;
    }

    ListItem:hover {
        background: $secondary-bg;
    }

    /* Content Area */
    #details-container {
        width: 75%;
        height: 100%;
        padding-left: 2;
    }

    .section-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
        margin-top: 1;
    }

    .input-label {
        color: $text-muted;
        margin-bottom: 0;
        margin-top: 1;
    }

    /* Provider Details */
    #provider-form {
        height: 50%;
        border-bottom: dashed $panel-border;
        padding-bottom: 1;
        margin-bottom: 1;
    }

    #test-connection-btn {
        margin-top: 1;
        margin-right: 2;
    }

    #connection-status {
        margin-left: 2;
        margin-top: 2;
        width: 1fr;
    }
    .status-ok { color: $success; }
    .status-error { color: $error; }
    .status-loading { color: $warning; }

    /* Models Table */
    DataTable {
        height: 1fr;
        margin-top: 1;
        border: solid $panel-border;
    }

    #manager-footer {
        height: 3;
        dock: bottom;
        align: right middle;
        margin-top: 1;
    }

    Button {
        margin-left: 1;
    }
    """

    def __init__(self, config: VibeConfig) -> None:
        super().__init__()
        self._config = config
        self._selected_provider: ProviderConfig | None = None
        # Working copies
        self._providers = list(config.providers)
        self._models = list(config.models)

    def compose(self) -> ComposeResult:
        with Container(id="manager-container"):
            yield Static("⚙️ Model & API Configuration", id="manager-header")

            with Horizontal(id="main-content"):
                # Left Sidebar: Providers
                with Vertical(id="provider-list-container"):
                    yield Label("Providers", id="provider-list-label")
                    yield ListView(id="provider-list")
                    yield Button(
                        "Add Provider",
                        id="add-provider-btn",
                        variant="primary",
                        classes="full-width",
                    )

                # Right Content: Details
                with Vertical(id="details-container"):
                    # Provider Details Form
                    with VerticalScroll(id="provider-form"):
                        yield Label("Provider Details", classes="section-title")

                        yield Label("Name:", classes="input-label")
                        yield Input(id="p-name", disabled=True)

                        yield Label("API Base URL:", classes="input-label")
                        yield Input(id="p-base")

                        yield Label("Backend Type:", classes="input-label")
                        yield Select(
                            [(b.value, b.value) for b in Backend], id="p-backend"
                        )

                        yield Label(
                            "API Key Environment Variable:", classes="input-label"
                        )
                        yield Input(id="p-env-var")

                        yield Label(
                            "API Key Value (Updates .env):", classes="input-label"
                        )
                        yield Input(
                            id="p-key-value",
                            password=True,
                            placeholder="Enter new key to update...",
                        )

                        with Horizontal():
                            yield Button(
                                "Test Connection",
                                id="test-connection-btn",
                                variant="warning",
                            )
                            yield Label("", id="connection-status")

                        with Horizontal(classes="mt-2"):
                            yield Button(
                                "Save Provider",
                                id="save-provider-btn",
                                variant="success",
                            )
                            yield Button(
                                "Delete Provider",
                                id="delete-provider-btn",
                                variant="error",
                            )

                    # Associated Models
                    yield Label("Associated Models", classes="section-title")
                    yield DataTable(id="models-table", cursor_type="row")
                    with Horizontal():
                        yield Button("Add Model", id="add-model-btn")
                        yield Button(
                            "Delete Model", id="delete-model-btn", variant="error"
                        )

            # Footer
            with Horizontal(id="manager-footer"):
                yield Button("Close", variant="default", id="close-btn")

    def on_mount(self) -> None:
        """Populate initial data."""
        self._refresh_provider_list()

        # Select first provider if available
        if self._providers:
            self.query_one("#provider-list", ListView).index = 0
            self._select_provider(self._providers[0])

    def _refresh_provider_list(self) -> None:
        list_view = self.query_one("#provider-list", ListView)
        list_view.clear()
        for p in self._providers:
            list_view.append(ListItem(Label(p.name), id=f"prov-{p.name}"))

    @on(ListView.Selected, "#provider-list")
    def on_provider_selected(self, event: ListView.Selected) -> None:
        if not event.item:
            return

        provider_name = event.item.id.replace("prov-", "")
        provider = next((p for p in self._providers if p.name == provider_name), None)
        if provider:
            self._select_provider(provider)

    def _select_provider(self, provider: ProviderConfig) -> None:
        self._selected_provider = provider

        # Populate form
        self.query_one("#p-name", Input).value = provider.name
        self.query_one("#p-base", Input).value = provider.api_base
        self.query_one("#p-env-var", Input).value = provider.api_key_env_var
        self.query_one("#p-key-value", Input).value = ""  # Don't show existing key

        # Set Backend Select
        select = self.query_one("#p-backend", Select)
        select.value = (
            provider.backend.value if provider.backend else Backend.GENERIC.value
        )

        self.query_one("#connection-status", Label).update("")

        # Populate Models Table
        self._refresh_models_table()

    def _refresh_models_table(self) -> None:
        if not self._selected_provider:
            return

        table = self.query_one("#models-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Alias", "Name", "Cost (In/Out)")

        current_models = [
            m for m in self._models if m.provider == self._selected_provider.name
        ]

        for m in current_models:
            table.add_row(
                m.alias, m.name, f"${m.input_price}/${m.output_price}", key=m.alias
            )

    @on(Button.Pressed, "#test-connection-btn")
    def test_connection(self) -> None:
        """Test API connection."""
        if not self._selected_provider:
            return

        status_label = self.query_one("#connection-status", Label)
        status_label.update("Connecting...")
        status_label.classes = "status-loading"

        # Get values from inputs as they might have changed
        api_base = self.query_one("#p-base", Input).value
        env_var = self.query_one("#p-env-var", Input).value
        new_key = self.query_one("#p-key-value", Input).value

        # Resolve key
        api_key = new_key if new_key else os.getenv(env_var)

        if not api_key:
            status_label.update("Missing API Key")
            status_label.classes = "status-error"
            return

        self._run_connection_test(api_base, api_key)

    @work(exclusive=True)
    async def _run_connection_test(self, api_base: str, api_key: str) -> None:
        """Run the actual HTTP request."""
        try:
            # Most OpenAI compatible APIs have /models endpoint
            url = f"{api_base.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {api_key}"}

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    self.call_from_thread(
                        self._update_status, "Connection Successful! ✅", "status-ok"
                    )
                elif response.status_code == 401:
                    self.call_from_thread(
                        self._update_status, "Auth Failed (401) ❌", "status-error"
                    )
                else:
                    self.call_from_thread(
                        self._update_status,
                        f"Error: {response.status_code} ❌",
                        "status-error",
                    )
        except Exception as e:
            self.call_from_thread(
                self._update_status, f"Network Error: {e!s}", "status-error"
            )

=======

            with Horizontal(id="main-content"):
                # Left Sidebar: Providers
                with Vertical(id="provider-list-container"):
                    yield Label("Providers", id="provider-list-label")
                    yield ListView(id="provider-list")
                    yield Button("Add Provider", id="add-provider-btn", variant="primary", classes="full-width")

                # Right Content: Details
                with Vertical(id="details-container"):
                    # Provider Details Form
                    with VerticalScroll(id="provider-form"):
                        yield Label("Provider Details", classes="section-title")

                        yield Label("Name:", classes="input-label")
                        yield Input(id="p-name", disabled=True)

                        yield Label("API Base URL:", classes="input-label")
                        yield Input(id="p-base")

                        yield Label("Backend Type:", classes="input-label")
                        yield Select([(b.value, b.value) for b in Backend], id="p-backend")

                        yield Label("API Key Environment Variable:", classes="input-label")
                        yield Input(id="p-env-var")

                        yield Label("API Key Value (Updates .env):", classes="input-label")
                        yield Input(id="p-key-value", password=True, placeholder="Enter new key to update...")

                        with Horizontal():
                            yield Button("Test Connection", id="test-connection-btn", variant="warning")
                            yield Label("", id="connection-status")

                        with Horizontal(classes="mt-2"):
                            yield Button("Save Provider", id="save-provider-btn", variant="success")
                            yield Button("Delete Provider", id="delete-provider-btn", variant="error")

                    # Associated Models
                    yield Label("Associated Models", classes="section-title")
                    yield DataTable(id="models-table", cursor_type="row")
                    with Horizontal():
                         yield Button("Add Model", id="add-model-btn")
                         yield Button("Delete Model", id="delete-model-btn", variant="error")

            # Footer
            with Horizontal(id="manager-footer"):
                yield Button("Close", variant="default", id="close-btn")

    def on_mount(self) -> None:
        """Populate initial data."""
        self._refresh_provider_list()

        # Select first provider if available
        if self._providers:
            self.query_one("#provider-list", ListView).index = 0
            self._select_provider(self._providers[0])

    def _refresh_provider_list(self) -> None:
        list_view = self.query_one("#provider-list", ListView)
        list_view.clear()
        for p in self._providers:
            list_view.append(ListItem(Label(p.name), id=f"prov-{p.name}"))

    @on(ListView.Selected, "#provider-list")
    def on_provider_selected(self, event: ListView.Selected) -> None:
        if not event.item:
            return

        provider_name = event.item.id.replace("prov-", "")
        provider = next((p for p in self._providers if p.name == provider_name), None)
        if provider:
            self._select_provider(provider)

    def _select_provider(self, provider: ProviderConfig) -> None:
        self._selected_provider = provider

        # Populate form
        self.query_one("#p-name", Input).value = provider.name
        self.query_one("#p-base", Input).value = provider.api_base
        self.query_one("#p-env-var", Input).value = provider.api_key_env_var
        self.query_one("#p-key-value", Input).value = "" # Don't show existing key

        # Set Backend Select
        select = self.query_one("#p-backend", Select)
        select.value = provider.backend.value if provider.backend else Backend.GENERIC.value

        self.query_one("#connection-status", Label).update("")

        # Populate Models Table
        self._refresh_models_table()

    def _refresh_models_table(self) -> None:
        if not self._selected_provider:
            return

        table = self.query_one("#models-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Alias", "Name", "Cost (In/Out)")

        current_models = [m for m in self._models if m.provider == self._selected_provider.name]

        for m in current_models:
            table.add_row(
                m.alias,
                m.name,
                f"${m.input_price}/${m.output_price}",
                key=m.alias
            )

    @on(Button.Pressed, "#test-connection-btn")
    def test_connection(self) -> None:
        """Test API connection."""
        if not self._selected_provider:
            return

        status_label = self.query_one("#connection-status", Label)
        status_label.update("Connecting...")
        status_label.classes = "status-loading"

        # Get values from inputs as they might have changed
        api_base = self.query_one("#p-base", Input).value
        env_var = self.query_one("#p-env-var", Input).value
        new_key = self.query_one("#p-key-value", Input).value

        # Resolve key
        api_key = new_key if new_key else os.getenv(env_var)

        if not api_key:
             status_label.update("Missing API Key")
             status_label.classes = "status-error"
             return

        self._run_connection_test(api_base, api_key)

    @work(exclusive=True)
    async def _run_connection_test(self, api_base: str, api_key: str) -> None:
        """Run the actual HTTP request."""
        try:
            # Most OpenAI compatible APIs have /models endpoint
            url = f"{api_base.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {api_key}"}

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    self.call_from_thread(self._update_status, "Connection Successful! ✅", "status-ok")
                elif response.status_code == 401:
                    self.call_from_thread(self._update_status, "Auth Failed (401) ❌", "status-error")
                else:
                    self.call_from_thread(self._update_status, f"Error: {response.status_code} ❌", "status-error")
        except Exception as e:
            self.call_from_thread(self._update_status, f"Network Error: {str(e)}", "status-error")

>>>>>>> origin/jules-model-manager-ui-2758702392557451568
    def _update_status(self, text: str, css_class: str) -> None:
        label = self.query_one("#connection-status", Label)
        label.update(text)
        label.classes = css_class

    @on(Button.Pressed, "#save-provider-btn")
    def save_provider(self) -> None:
        """Save provider details."""
        if not self._selected_provider:
            return

        # Update in-memory object
        self._selected_provider.api_base = self.query_one("#p-base", Input).value
        self._selected_provider.api_key_env_var = self.query_one(
            "#p-env-var", Input
        ).value

        backend_val = self.query_one("#p-backend", Select).value
        if backend_val:
            self._selected_provider.backend = Backend(backend_val)

        # Update key if provided
        new_key = self.query_one("#p-key-value", Input).value
        if new_key and self._selected_provider.api_key_env_var:
            self._save_api_key(self._selected_provider.api_key_env_var, new_key)
            self.query_one("#p-key-value", Input).value = ""  # Clear after save

        # Persist config
        self._config.providers = self._providers
        # Also persist models
        self._config.models = self._models

        # Serialize and save
        updates = {
            "providers": [p.model_dump(mode="json") for p in self._providers],
            "models": [m.model_dump(mode="json") for m in self._models],
        }
        VibeConfig.save_updates(updates)

        self.notify("Settings saved successfully.")

    def _save_api_key(self, env_var: str, key: str) -> None:
        """Save key to .env file."""
        try:
            GLOBAL_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if GLOBAL_ENV_FILE.exists():
                lines = GLOBAL_ENV_FILE.read_text().splitlines()

            # Remove existing
            lines = [l for l in lines if not l.startswith(f"{env_var}=")]
            lines.append(f"{env_var}={key}")

            GLOBAL_ENV_FILE.write_text("\n".join(lines) + "\n")
            os.environ[env_var] = key
        except Exception as e:
            self.notify(f"Failed to save .env: {e}", severity="error")

    @on(Button.Pressed, "#close-btn")
    def close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#add-provider-btn")
    def add_provider(self) -> None:
        count = len(self._providers) + 1
        new_prov = ProviderConfig(
            name=f"new-provider-{count}",
            api_base="https://api.openai.com/v1",
            api_key_env_var=f"NEW_PROVIDER_{count}_KEY",
            backend=Backend.GENERIC,
        )
        self._providers.append(new_prov)
        self._refresh_provider_list()
        # Select it
        list_view = self.query_one("#provider-list", ListView)
        list_view.index = len(self._providers) - 1
        self._select_provider(new_prov)

        name_input = self.query_one("#p-name", Input)
        name_input.disabled = False
        name_input.focus()
        self.notify("New provider added. Please configure details.")

    @on(Button.Pressed, "#add-model-btn")
    def add_model(self) -> None:
        if not self._selected_provider:
            self.notify("Select a provider first.", severity="error")
            return

        # Add a default model for this provider
        count = (
            len([m for m in self._models if m.provider == self._selected_provider.name])
            + 1
        )
        new_model = ModelConfig(
            name="gpt-4",  # Default guess
            provider=self._selected_provider.name,
            alias=f"{self._selected_provider.name}-model-{count}",
            input_price=0.0,
            output_price=0.0,
        )
        self._models.append(new_model)
        self._refresh_models_table()
        self.notify(f"Added model {new_model.alias}. Edit in config.toml for details.")

    @on(Button.Pressed, "#delete-model-btn")
    def delete_model(self) -> None:
        table = self.query_one("#models-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            # Row key was set to alias
            self._models = [m for m in self._models if m.alias != row_key.value]
            self._refresh_models_table()
            self.notify(f"Deleted model {row_key.value}")

    @on(Input.Changed, "#p-name")
    def on_name_change(self, event: Input.Changed) -> None:
        if self._selected_provider and event.value:
            self._selected_provider.name = event.value


class ModelSelectionScreen(ModalScreen[str | None]):
    """Screen for selecting an active model."""

    CSS = """
    ModelSelectionScreen {
        align: center middle;
    }

    #dialog {
        width: 60;
        height: 80%;
        background: $surface;
        border: round $accent;
        padding: 1 2;
        layout: vertical;
    }

    #header {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        border-bottom: solid $panel-border;
    }

    ListView {
        height: 1fr;
        border: solid $panel-border;
        margin-bottom: 1;
    }

    Button {
        width: 100%;
    }
    """

    def __init__(self, config: VibeConfig) -> None:
        super().__init__()
        self._config = config
        self._models = config.models

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("Select Active Model", id="header")
            yield ListView(
                *[
                    ListItem(Label(f"{m.alias} ({m.provider})"), id=f"model-{m.alias}")
                    for m in self._models
                ],
                id="model-list",
            )
            yield Button("Cancel", variant="error", id="cancel-btn")

    def on_mount(self) -> None:
        # Highlight current
        list_view = self.query_one(ListView)
        for index, item in enumerate(list_view.children):
            if item.id == f"model-{self._config.active_model}":
                list_view.index = index
                break

    @on(ListView.Selected)
    def on_selection(self, event: ListView.Selected) -> None:
        if event.item and event.item.id:
            alias = event.item.id.replace("model-", "")
            self.dismiss(alias)

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self) -> None:
        self.dismiss(None)
=======
            "providers": [p.model_dump(mode='json') for p in self._providers],
            "models": [m.model_dump(mode='json') for m in self._models]
        }
        VibeConfig.save_updates(updates)

        self.notify("Settings saved successfully.")

    def _save_api_key(self, env_var: str, key: str) -> None:
        """Save key to .env file."""
        try:
            GLOBAL_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if GLOBAL_ENV_FILE.exists():
                lines = GLOBAL_ENV_FILE.read_text().splitlines()

            # Remove existing
            lines = [l for l in lines if not l.startswith(f"{env_var}=")]
            lines.append(f"{env_var}={key}")

            GLOBAL_ENV_FILE.write_text("\n".join(lines) + "\n")
            os.environ[env_var] = key
        except Exception as e:
            self.notify(f"Failed to save .env: {e}", severity="error")

    @on(Button.Pressed, "#close-btn")
    def close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#add-provider-btn")
    def add_provider(self) -> None:
        count = len(self._providers) + 1
        new_prov = ProviderConfig(
            name=f"new-provider-{count}",
            api_base="https://api.openai.com/v1",
            api_key_env_var=f"NEW_PROVIDER_{count}_KEY",
            backend=Backend.GENERIC
        )
        self._providers.append(new_prov)
        self._refresh_provider_list()
        # Select it
        list_view = self.query_one("#provider-list", ListView)
        list_view.index = len(self._providers) - 1
        self._select_provider(new_prov)

        name_input = self.query_one("#p-name", Input)
        name_input.disabled = False
        name_input.focus()
        self.notify("New provider added. Please configure details.")

    @on(Button.Pressed, "#add-model-btn")
    def add_model(self) -> None:
        if not self._selected_provider:
             self.notify("Select a provider first.", severity="error")
             return

        # Add a default model for this provider
        count = len([m for m in self._models if m.provider == self._selected_provider.name]) + 1
        new_model = ModelConfig(
            name=f"gpt-4", # Default guess
            provider=self._selected_provider.name,
            alias=f"{self._selected_provider.name}-model-{count}",
            input_price=0.0,
            output_price=0.0
        )
        self._models.append(new_model)
        self._refresh_models_table()
        self.notify(f"Added model {new_model.alias}. Edit in config.toml for details.")

    @on(Button.Pressed, "#delete-model-btn")
    def delete_model(self) -> None:
        table = self.query_one("#models-table", DataTable)
        if table.cursor_row is not None:
             row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
             # Row key was set to alias
             self._models = [m for m in self._models if m.alias != row_key.value]
             self._refresh_models_table()
             self.notify(f"Deleted model {row_key.value}")

    @on(Input.Changed, "#p-name")
    def on_name_change(self, event: Input.Changed) -> None:
        if self._selected_provider and event.value:
             self._selected_provider.name = event.value
>>>>>>> origin/jules-model-manager-ui-2758702392557451568
