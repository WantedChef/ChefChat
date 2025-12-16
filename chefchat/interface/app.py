"""ChefChat App - The Main Textual Application Class.

This is the core TUI application class, composed from multiple mixins
that provide command handling, bus events, agent lifecycle, and more.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum, auto
import logging
import os
from pathlib import Path
import re
import sys
import time
import traceback
from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.widgets import Input

from chefchat.cli.commands import CommandRegistry
from chefchat.core.agent import Agent
from chefchat.core.config import VibeConfig
from chefchat.interface.command_registry import get_tui_command_registry
from chefchat.interface.constants import (
    MARKDOWN_SANITIZE_CHARS,
    BusAction,
    PayloadKey,
    StationStatus,
    StatusString,
    TUILayout,
)
from chefchat.interface.mixins import (
    AgentLifecycleMixin,
    BotCommandsMixin,
    BusEventHandlerMixin,
    ChefCommandsMixin,
    CommandDispatcherMixin,
)
from chefchat.interface.screens.confirm_restart import (
    get_saved_layout,
    save_tui_preference,
)
from chefchat.interface.services import ConfigService, ModelService
from chefchat.interface.widgets.command_input import CommandInput
from chefchat.interface.widgets.kitchen_ui import (
    KitchenFooter,
    KitchenHeader,
    WhiskLoader,
)
from chefchat.interface.widgets.the_pass import ThePass
from chefchat.interface.widgets.the_plate import ThePlate
from chefchat.interface.widgets.ticket_rail import TicketRail
from chefchat.kitchen.brigade import Brigade
from chefchat.kitchen.bus import ChefMessage, KitchenBus, MessagePriority
from chefchat.modes import MODE_CONFIGS, ModeManager, VibeMode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def sanitize_markdown_input(text: str) -> str:
    """Sanitize user input for safe markdown rendering."""
    if not text:
        return ""

    sanitized = text
    for char, replacement in MARKDOWN_SANITIZE_CHARS.items():
        sanitized = sanitized.replace(char, replacement)

    # Remove ANSI escape sequences
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|[0-?]*[ -/]*[@-~])")
    sanitized = ansi_escape.sub("", sanitized)
    sanitized = sanitized.replace("\0", "")

    return sanitized


class AppStateKind(Enum):
    """Enumeration of application states."""

    IDLE = auto()
    RUNNING = auto()
    CANCELLING = auto()


@dataclass(frozen=True, slots=True)
class AppState:
    """Application state with ticket tracking."""

    kind: AppStateKind
    ticket_id: str | None = None

    @classmethod
    def idle(cls) -> AppState:
        return cls(kind=AppStateKind.IDLE, ticket_id=None)

    @classmethod
    def running(cls, ticket_id: str | None) -> AppState:
        return cls(kind=AppStateKind.RUNNING, ticket_id=ticket_id)

    @classmethod
    def cancelling(cls, ticket_id: str | None) -> AppState:
        return cls(kind=AppStateKind.CANCELLING, ticket_id=ticket_id)

    @property
    def is_processing(self) -> bool:
        return self.kind in {AppStateKind.RUNNING, AppStateKind.CANCELLING}


class ChefChatApp(
    CommandDispatcherMixin,
    BotCommandsMixin,
    ChefCommandsMixin,
    BusEventHandlerMixin,
    AgentLifecycleMixin,
    App,
):
    """The main ChefChat TUI application.

    Composed from mixins:
    - CommandDispatcherMixin: Slash commands and bash execution
    - BotCommandsMixin: /telegram, /discord
    - ChefCommandsMixin: /status, /wisdom, /roast, etc.
    - BusEventHandlerMixin: Kitchen bus message handling
    - AgentLifecycleMixin: Agent init, loop, shutdown

    System commands (/config, /layout, /quit, etc.) are now handled
    via the TUICommandRegistry and system_handlers module.
    """

    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "ChefChat"
    SUB_TITLE = "The Michelin Star AI-Engineer"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+c", "cancel", "Cancel", show=False),
        Binding("ctrl+l", "clear", "Clear Plate", show=False),
        Binding("escape", "focus_input", "Focus Input", show=False),
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
        Binding("ctrl+m", "cycle_mode", "Cycle Mode", show=False),
    ]

    _STATUS_MAP: ClassVar[dict[str, StationStatus]] = {
        StatusString.IDLE.value: StationStatus.IDLE,
        StatusString.PLANNING.value: StationStatus.WORKING,
        StatusString.COOKING.value: StationStatus.WORKING,
        StatusString.TESTING.value: StationStatus.WORKING,
        StatusString.REFACTORING.value: StationStatus.WORKING,
        "verifying": StationStatus.WORKING,
        "researching": StationStatus.WORKING,
        "auditing": StationStatus.WORKING,
        StatusString.COMPLETE.value: StationStatus.COMPLETE,
        StatusString.ERROR.value: StationStatus.ERROR,
        "ready": StationStatus.COMPLETE,
    }

    def __init__(
        self, layout: TUILayout = TUILayout.CHAT_ONLY, active_mode: bool = False
    ) -> None:
        super().__init__()
        self._bus: KitchenBus | None = None
        self._brigade: Brigade | None = None
        self._state = AppState.idle()
        self._mode_manager = ModeManager(initial_mode=VibeMode.NORMAL)
        # Legacy registry (to be removed)
        self._command_registry = CommandRegistry()
        # New TUI registry
        self._tui_registry = get_tui_command_registry()

        # Initialize Services
        self._config_service = ConfigService()
        self._model_service = ModelService(self._config_service)
        self._layout = layout

        # Active Mode
        self._active_mode = active_mode
        self._agent: Agent | None = None
        self._config: VibeConfig | None = None

        # Session tracking
        self._session_start_time = time.time()
        self._tools_executed = 0

    @property
    def bus(self) -> KitchenBus:
        if self._bus is None:
            raise RuntimeError("Kitchen bus not initialized")
        return self._bus

    async def _reload_config(self) -> None:
        """Reload configuration from disk and refresh agent/models."""
        from chefchat.core.config import VibeConfig, load_api_keys_from_env
        from chefchat.interface.widgets.ticket_rail import TicketRail

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        try:
            load_api_keys_from_env()
            new_config = VibeConfig.load()

            # Update services/config snapshot
            self._config = new_config
            if self._config_service:
                self._config_service._config = new_config  # type: ignore[attr-defined]
            if self._model_service:
                self._model_service = ModelService(self._config_service or new_config)

            # Refresh agent config in-place; if none, initialize
            if self._agent:
                self._agent.config = new_config
            else:
                await self._initialize_agent()

            ticket_rail.add_system_message(
                f"✅ Config reloaded. Active model: `{new_config.active_model}`"
            )
        except Exception as exc:
            ticket_rail.add_system_message(f"❌ Reload failed: {exc}")

    @property
    def model_service(self) -> ModelService:
        return self._model_service

    @property
    def config_service(self) -> ConfigService:
        return self._config_service

    def compose(self) -> ComposeResult:
        """Compose the layout based on current mode."""
        yield KitchenHeader()

        if self._layout == TUILayout.FULL_KITCHEN:
            with Grid(id="kitchen-grid"):
                yield TicketRail(id="ticket-rail")
                yield ThePass(id="the-pass")
                yield ThePlate(id="the-plate")
        else:
            yield TicketRail(id="ticket-rail", classes="chat-only")

        yield KitchenFooter(self._mode_manager, id="kitchen-footer")
        yield CommandInput(
            placeholder="🍳 What shall we cook today, Chef?", id="command-input"
        )
        yield WhiskLoader()

    async def on_mount(self) -> None:
        """Handle app mount - start workers and show welcome."""
        try:
            if self._active_mode:
                await self._setup_brigade()
            else:
                self._bus = KitchenBus()
                await self._bus.start()
                self._bus.subscribe("tui", self._handle_bus_message)

            ticket_rail = self.query_one("#ticket-rail", TicketRail)
            mode = self._mode_manager.current_mode
            config = MODE_CONFIGS[mode]

            active_status = (
                "🟢 **Brigade Active**" if self._active_mode else "💤 *Standalone Mode*"
            )
            ticket_rail.add_system_message(
                f"🍽️ **Welcome to ChefChat!**\n\n"
                f"The kitchen is ready, Chef. What would you like to cook today?\n\n"
                f"*Current Mode: {config.emoji} {mode.value.upper()}*\n\n"
                f"{active_status}\n\n"
                f"*Commands: `/help` for menu, `/modes` to see modes, `Shift+Tab` to cycle*"
            )

            self.query_one("#command-input", CommandInput).focus()

        except Exception as e:
            logger.exception("Error in on_mount: %s", e)
            print(f"❌ Fatal Error in on_mount: {e}", file=sys.stderr)
            traceback.print_exc()
            self.notify(f"Kitchen Error: {e}", severity="error")

    async def on_unmount(self) -> None:
        await self._shutdown()

    # ==== State Management ====

    def _enter_running(self, ticket_id: str | None) -> None:
        self._state = AppState.running(ticket_id)

    def _enter_cancelling(self) -> None:
        self._state = AppState.cancelling(self._state.ticket_id)

    def _enter_idle(self) -> None:
        self._state = AppState.idle()

    # ==== Input Handler ====

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted) -> None:
        """Handle user input submission."""
        try:
            if getattr(event.input, "id", None) != "command-input":
                return

            val = event.value.strip()
            if not val:
                return

            user_input = sanitize_markdown_input(val)
            if not user_input.strip():
                return

            event.input.value = ""

            if user_input.startswith("/"):
                await self._handle_command(user_input)
            elif user_input.startswith("!"):
                await self._handle_bash_command(user_input)
            else:
                await self._submit_ticket(user_input)
        except Exception as e:
            logger.exception("Error handling input submission: %s", e)
            self.notify(f"Input error: {e}", severity="error")

    async def _handle_command(self, command: str) -> None:
        """Handle slash commands using the new TUI registry."""
        # Using local import to avoid circular dependency
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if not command.startswith("/"):
            return

        # Use new registry for dispatch
        try:
            handled = await self._tui_registry.dispatch(self, command)
            if handled:
                return
        except Exception as e:
            logger.exception("Command dispatch error: %s", e)
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❌ Error executing command: {e}"
            )
            return

        # Unknown command fallthrough
        cmd_name = command.split()[0]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"❓ Unknown command: `{cmd_name}`\n\nType `/help` to see available commands."
        )

    # ==== Layout Helper ====

    def _get_plate_if_available(self) -> ThePlate | None:
        """Get ThePlate widget if in FULL_KITCHEN layout."""
        if self._layout == TUILayout.FULL_KITCHEN:
            return self.query_one("#the-plate", ThePlate)
        return None

    # ==== Actions ====

    def action_quit(self) -> None:
        if self._brigade or self._bus:
            self.call_after_refresh(lambda: asyncio.create_task(self._shutdown()))
        self.exit()

    def action_cancel(self) -> None:
        if not self._state.is_processing:
            return

        self._enter_cancelling()

        try:
            if self._bus and self._state.ticket_id:
                cancel_msg = ChefMessage(
                    sender="tui",
                    recipient="sous_chef",
                    action=BusAction.CANCEL_TICKET.value,
                    payload={PayloadKey.TICKET_ID: self._state.ticket_id},
                    priority=MessagePriority.HIGH,
                )
                asyncio.create_task(self._bus.publish(cancel_msg))
        except Exception:
            pass

        self._enter_idle()
        try:
            self.query_one(WhiskLoader).stop()
        except Exception:
            pass

        try:
            self.query_one("#ticket-rail", TicketRail).finish_streaming_message()
        except Exception:
            pass

        try:
            self.notify("Cancelled. Kitchen stopped.", timeout=2)
        except Exception:
            pass

    def action_clear(self) -> None:
        asyncio.create_task(self._handle_clear())

    def action_focus_input(self) -> None:
        if self._state.is_processing:
            self.action_cancel()
            return

        self.query_one("#command-input", CommandInput).focus()

    def action_cycle_mode(self) -> None:
        """Cycle through available modes (Shift+Tab)."""
        try:
            _old_mode, new_mode = self._mode_manager.cycle_mode()
            config = MODE_CONFIGS.get(new_mode)

            if config is None:
                return

            if self._agent:
                self._agent.auto_approve = self._mode_manager.auto_approve

            try:
                footer = self.query_one("#kitchen-footer", KitchenFooter)
                footer.refresh_mode()
                footer.refresh()
            except Exception:
                pass

            self.notify(
                f"{config.emoji} {new_mode.value.upper()}: {config.description}",
                title="Mode Changed",
                timeout=2,
            )

        except Exception as e:
            self.notify(f"Mode error: {e}", severity="error", timeout=3)


def run(
    *, verbose: bool = False, layout: str | None = None, active: bool = False
) -> None:
    """Run the ChefChat TUI application.

    Args:
        verbose: Enable debug logging
        layout: Layout mode - 'chat' (clean) or 'kitchen' (3-panel).
                If None, uses saved preference (defaults to 'chat').
        active: Enable active mode (real Agent backend).
    """
    os.environ.setdefault("FORCE_COLOR", "1")

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if layout:
        save_tui_preference("layout", layout)

    while True:
        current_layout = get_saved_layout()
        layout_mode = (
            TUILayout.FULL_KITCHEN
            if current_layout == "kitchen"
            else TUILayout.CHAT_ONLY
        )

        app = ChefChatApp(layout=layout_mode, active_mode=active)

        try:
            result = app.run()
            if result == "RESTART":
                continue
            break
        except KeyboardInterrupt:
            print("\n👋 ChefChat kitchen closed.")
            break
        except Exception as e:
            print(f"\n❌ Application Error: {e}", file=sys.stderr)
            if verbose:
                traceback.print_exc()
            sys.exit(1)
