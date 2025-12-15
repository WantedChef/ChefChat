"""ChefChat App - The Main Textual Application Class."""

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
from uuid import uuid4

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.widgets import Input

from chefchat.bots.manager import BotManager
from chefchat.bots.ui import BotSetupScreen
from chefchat.cli.commands import CommandRegistry
from chefchat.core.agent import Agent
from chefchat.core.config import MissingAPIKeyError, VibeConfig, load_api_keys_from_env
from chefchat.core.types import (
    AssistantEvent,
    CompactEndEvent,
    CompactStartEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from chefchat.interface.constants import (
    MARKDOWN_SANITIZE_CHARS,
    MAX_FEATURES_DISPLAY,
    MIN_MODELS_TO_COMPARE,
    SUMMARY_PREVIEW_LENGTH,
    BusAction,
    PayloadKey,
    StationStatus,
    StatusString,
    TUILayout,
)
from chefchat.interface.screens.confirm_restart import (
    TUI_PREFS_FILE,
    ConfirmRestartScreen,
    get_saved_layout,
    save_tui_preference,
)
from chefchat.interface.screens.git_setup import GitSetupScreen
from chefchat.interface.screens.model_manager import ModelManagerScreen
from chefchat.interface.screens.onboarding import OnboardingScreen
from chefchat.interface.screens.tool_approval import ToolApprovalScreen
from chefchat.interface.widgets.command_input import CommandInput
from chefchat.interface.widgets.kitchen_ui import (
    KitchenFooter,
    KitchenHeader,
    WhiskLoader,
)
from chefchat.interface.widgets.the_pass import ThePass
from chefchat.interface.widgets.the_plate import ThePlate
from chefchat.interface.widgets.ticket_rail import TicketRail
from chefchat.kitchen.brigade import Brigade, create_default_brigade
from chefchat.kitchen.bus import ChefMessage, KitchenBus, MessagePriority
from chefchat.modes import MODE_CONFIGS, MODE_CYCLE_ORDER, ModeManager, VibeMode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Import model constants from constants module
# MIN_MODELS_TO_COMPARE, MAX_FEATURES_DISPLAY now imported from interface.constants


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
    IDLE = auto()
    RUNNING = auto()
    CANCELLING = auto()


@dataclass(frozen=True, slots=True)
class AppState:
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


class ChefChatApp(App):
    """The main ChefChat TUI application."""

    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "ChefChat"
    SUB_TITLE = "The Michelin Star AI-Engineer"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+c", "cancel", "Cancel", show=False),
        Binding("ctrl+l", "clear", "Clear Plate", show=False),
        Binding("escape", "focus_input", "Focus Input", show=False),
        # Mode cycling - priority=True to override default focus behavior
        Binding("shift+tab", "cycle_mode", "Cycle Mode", show=False, priority=True),
        Binding("ctrl+m", "cycle_mode", "Cycle Mode", show=False),  # Alternative
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
        self._command_registry = CommandRegistry()
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

    async def _initialize_agent(self) -> None:
        """Initialize the core Agent for active mode."""
        try:
            # Ensure environment variables are loaded from .env
            load_api_keys_from_env()
            self._config = VibeConfig.load()
        except MissingAPIKeyError:
            # Push onboarding screen if key is missing
            await self.push_screen(OnboardingScreen(), self._on_onboarding_complete)
            return
        except Exception as e:
            self.notify(f"Config Error: {e}", severity="error")
            return

        self._agent = Agent(
            config=self._config,
            auto_approve=self._mode_manager.auto_approve,
            enable_streaming=True,
            mode_manager=self._mode_manager,
        )
        self._agent.set_approval_callback(self._tool_approval_callback)

        # Notify user
        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"✅ **Agent Connected**\n\n"
            f"Model: `{self._config.active_model}`\n"
            f"Mode: {config.emoji} {mode.value.upper()}"
        )

    def _on_onboarding_complete(self, provider: str | None) -> None:
        """Callback when onboarding is done.

        Args:
            provider: The provider name that was configured, or None if cancelled.
        """
        if not provider:
            self.notify("Setup incomplete. Chat will be disabled.", severity="warning")
            return

        # We must ensure the active model matches the configured provider
        # to avoid immediate crash on re-init.
        try:
            # Load config (should pass now that key is in env)
            load_api_keys_from_env()
            config = VibeConfig.load()

            current_model = config.get_active_model()
            if current_model.provider != provider:
                # Switch to first model for this provider
                for model in config.models:
                    if model.provider == provider:
                        self.notify(f"Switching active model to {model.alias}...")
                        config.active_model = model.alias
                        VibeConfig.save_updates({"active_model": model.alias})
                        break
        except Exception as e:
            logger.warning(f"Error adjusting model after onboarding: {e}")

        asyncio.create_task(self._initialize_agent())

    async def _tool_approval_callback(
        self, tool_name: str, tool_args: dict | str
    ) -> tuple[str, str | None]:
        """Handle tool approval requests via modal."""
        # We need to wait for the user response, so we use a future
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def on_screen_result(result: tuple[str, str | None]) -> None:
            if not future.done():
                future.set_result(result)

        # Schedule screen push on main thread
        self.call_from_thread(
            lambda: self.push_screen(
                ToolApprovalScreen(tool_name, tool_args), on_screen_result
            )
        )

        return await future

    def compose(self) -> ComposeResult:
        """Compose the layout based on current mode."""
        # Header first (dock top)
        yield KitchenHeader()

        if self._layout == TUILayout.FULL_KITCHEN:
            # Full 3-panel kitchen layout
            with Grid(id="kitchen-grid"):
                yield TicketRail(id="ticket-rail")
                yield ThePass(id="the-pass")
                yield ThePlate(id="the-plate")
        else:
            # Clean chat-only layout
            yield TicketRail(id="ticket-rail", classes="chat-only")

        # Footer elements (dock bottom) - order matters: first yielded = bottom-most
        yield KitchenFooter(self._mode_manager, id="kitchen-footer")
        yield CommandInput(
            placeholder="🍳 What shall we cook today, Chef?", id="command-input"
        )
        yield WhiskLoader()

    async def on_mount(self) -> None:
        """Handle app mount - start workers and show welcome."""
        try:
            if self._active_mode:
                # Active mode: Full Brigade (SousChef, LineCook, etc.)
                await self._setup_brigade()
            else:
                # Standalone mode: Just the bus for local messaging
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

    async def _handle_bus_message(self, message: ChefMessage) -> None:
        """Handle incoming messages from the bus."""
        try:
            action = str(message.action).upper()
            match action:
                case BusAction.STATUS_UPDATE.value:
                    await self._update_station_status(message.payload)
                case BusAction.LOG_MESSAGE.value:
                    await self._add_log_message(message.payload)
                case BusAction.PLATE_CODE.value:
                    await self._plate_code(message.payload)
                case BusAction.STREAM_UPDATE.value:
                    await self._plate_code(message.payload, append=True)
                case BusAction.TERMINAL_LOG.value:
                    await self._add_terminal_log(message.payload)
                case BusAction.PLAN.value:
                    await self._add_plan(message.payload)
                case BusAction.TICKET_DONE.value:
                    await self._on_ticket_done(message.payload)
        except Exception as exc:
            logger.exception("Error handling bus message: %s", exc)

    def _enter_running(self, ticket_id: str | None) -> None:
        self._state = AppState.running(ticket_id)

    def _enter_cancelling(self) -> None:
        self._state = AppState.cancelling(self._state.ticket_id)

    def _enter_idle(self) -> None:
        self._state = AppState.idle()

    async def _on_ticket_done(self, payload: dict) -> None:
        """Finalize the current ticket lifecycle.

        This must be safe to call multiple times and should always end
        the "Cooking..." state.
        """
        ticket_id = str(payload.get(PayloadKey.TICKET_ID, "") or "")

        if self._state.ticket_id and ticket_id and ticket_id != self._state.ticket_id:
            return

        self._enter_idle()

        try:
            self.query_one(WhiskLoader).stop()
        except Exception:
            pass

        try:
            self.query_one("#ticket-rail", TicketRail).finish_streaming_message()
        except Exception:
            pass

    async def _update_station_status(self, payload: dict) -> None:
        # ThePass only exists in FULL_KITCHEN layout
        if self._layout != TUILayout.FULL_KITCHEN:
            return

        station_id = payload.get(PayloadKey.STATION, "")
        if not station_id:
            return

        status_raw = str(payload.get(PayloadKey.STATUS, "")).lower()
        status = self._STATUS_MAP.get(status_raw, StationStatus.IDLE)
        progress = float(payload.get(PayloadKey.PROGRESS, 0.0) or 0.0)
        message = str(payload.get(PayloadKey.MESSAGE, "")) or status.name.capitalize()

        station_board = self.query_one("#the-pass", ThePass)
        station_board.update_station(station_id, status, progress, message)

        # Failsafe: if we are processing and a station enters ERROR, force stop.
        if self._state.is_processing and status == StationStatus.ERROR:
            await self._on_ticket_done({
                PayloadKey.TICKET_ID: self._state.ticket_id or ""
            })

    async def _add_log_message(self, payload: dict) -> None:
        content = str(
            payload.get(PayloadKey.CONTENT, "") or payload.get(PayloadKey.MESSAGE, "")
        )
        if not content:
            return

        # Log to ticket rail
        self.query_one("#ticket-rail", TicketRail).add_assistant_message(content)
        # Also log to Plate log (only in FULL_KITCHEN layout)
        if self._layout == TUILayout.FULL_KITCHEN:
            self.query_one("#the-plate", ThePlate).log_message(content)

    async def _plate_code(self, payload: dict, *, append: bool = False) -> None:
        # ThePlate only exists in FULL_KITCHEN layout
        if self._layout != TUILayout.FULL_KITCHEN:
            return

        code = str(payload.get(PayloadKey.CODE, ""))
        if not code:
            return

        language = str(payload.get(PayloadKey.LANGUAGE, "python")) or "python"
        file_path = payload.get(PayloadKey.FILE_PATH)
        plate = self.query_one("#the-plate", ThePlate)
        plate.plate_code(code, language=language, file_path=file_path, append=append)

    async def _add_terminal_log(self, payload: dict) -> None:
        # ThePlate only exists in FULL_KITCHEN layout
        if self._layout != TUILayout.FULL_KITCHEN:
            return

        message = str(
            payload.get(PayloadKey.MESSAGE, "") or payload.get(PayloadKey.CONTENT, "")
        )
        if message:
            self.query_one("#the-plate", ThePlate).log_message(message)

    async def _add_plan(self, payload: dict) -> None:
        task = str(
            payload.get(PayloadKey.TASK, "") or payload.get(PayloadKey.CONTENT, "")
        )
        if task:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"🗺️ Plan updated: {task}"
            )

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

    @work(exclusive=True)
    async def _run_agent_loop(self, request: str) -> None:
        """Run the agent interaction loop in a worker (main thread async)."""
        if not self._agent:
            return

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        plate = self._get_plate_if_available()
        loader = self.query_one(WhiskLoader)

        # UI Updates directly (we are on main loop)
        loader.start("Thinking...")
        ticket_rail.start_streaming_message()
        self._enter_running(None)

        try:
            async for event in self._agent.act(request):
                self._process_tui_event(event, ticket_rail, plate, loader)
        except Exception as e:
            self.notify(f"Agent Error: {e}", severity="error")
            if plate:
                plate.log_message(f"[bold red]Error:[/] {e}\n")
            traceback.print_exc()
        finally:
            ticket_rail.finish_streaming_message()
            loader.stop()
            self._enter_idle()

    def _get_plate_if_available(self) -> ThePlate | None:
        """Get ThePlate widget if in FULL_KITCHEN layout."""
        if self._layout == TUILayout.FULL_KITCHEN:
            return self.query_one("#the-plate", ThePlate)
        return None

    def _process_tui_event(
        self,
        event: AssistantEvent | ToolCallEvent | ToolResultEvent,
        ticket_rail: TicketRail,
        plate: ThePlate | None,
        loader: WhiskLoader,
    ) -> None:
        """Process an agent event and update TUI accordingly."""
        if isinstance(event, AssistantEvent):
            if event.content:
                ticket_rail.stream_token(event.content)

        elif isinstance(event, ToolCallEvent):
            if plate:
                plate.log_message(f"[bold blue]🛠️ Calling Tool:[/] {event.tool_name}\n")
            loader.start(f"Running {event.tool_name}...")

        elif isinstance(event, ToolResultEvent):
            if not event.is_error:
                self._tools_executed += 1
            if plate:
                status = "[green]Success[/]" if not event.is_error else "[red]Error[/]"
                plate.log_message(f"[bold]Result:[/] {status}\n")

        elif isinstance(event, (CompactStartEvent, CompactEndEvent)):
            if plate:
                plate.log_message("[dim]Compacting conversation history...[/]\n")

    async def _submit_ticket(self, request: str) -> None:
        """Submit a new ticket to the kitchen via the bus."""
        # Show user message in UI immediately
        self.query_one("#ticket-rail", TicketRail).add_user_message(request)

        # ACTIVE MODE: Use Brigade via Bus
        if self._active_mode and self._brigade:
            if not self._bus:
                self.notify("Kitchen bus not ready!", severity="error")
                return

            ticket_id = str(uuid4())[:8]
            message = ChefMessage(
                sender="tui",
                recipient="sous_chef",
                action=BusAction.NEW_TICKET.value,
                payload={PayloadKey.TICKET_ID: ticket_id, PayloadKey.REQUEST: request},
                priority=MessagePriority.HIGH,
            )

            # Start the loader
            self.query_one(WhiskLoader).start("Cooking...")
            self._enter_running(ticket_id)

            await self._bus.publish(message)
            return

        # STANDALONE MODE: No brigade connected
        if not self._brigade:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "🔧 **Kitchen Not Active**\n\n"
                "The TUI is running in standalone mode. Start with `--active` flag:\n"
                "`uv run vibe --tui --active`\n\n"
                "*Available commands: `/help`, `/modes`, `/roast`, `/wisdom`*"
            )
            return

        if not self._bus:
            self.notify("Kitchen bus not ready!", severity="error")
            return

        ticket_id = str(uuid4())[:8]
        message = ChefMessage(
            sender="tui",
            recipient="sous_chef",
            action=BusAction.NEW_TICKET.value,
            payload={PayloadKey.TICKET_ID: ticket_id, PayloadKey.REQUEST: request},
            priority=MessagePriority.HIGH,
        )

        # Start the loader
        self.query_one(WhiskLoader).start("Processing ticket...")
        self._enter_running(ticket_id)

        await self._bus.publish(message)

    async def _handle_bash_command(self, command: str) -> None:
        """Execute bash command from TUI.

        Handles `!` prefixed commands by executing them via SecureCommandExecutor.
        Output is displayed in the ticket rail.
        """
        if not command.startswith("!"):
            return

        cmd = command[1:].strip()
        if not cmd:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "💡 **Usage**: `!<command>`\n\nExample: `!ls -la` or `!git status`"
            )
            return

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        ticket_rail.add_user_message(f"`!{cmd}`")

        # Start loader
        loader = self.query_one(WhiskLoader)
        loader.start(f"Running: {cmd[:30]}...")

        try:
            from pathlib import Path

            from chefchat.core.tools.executor import SecureCommandExecutor

            executor = SecureCommandExecutor(Path.cwd())
            stdout, stderr, returncode = await executor.execute(cmd, timeout=30)

            # Format output
            output_parts = []
            if stdout:
                output_parts.append(f"```\n{stdout.strip()}\n```")
            if stderr:
                output_parts.append(f"**stderr:**\n```\n{stderr.strip()}\n```")

            if output_parts:
                output = "\n\n".join(output_parts)
            else:
                output = "*(no output)*"

            if returncode == 0:
                ticket_rail.add_system_message(f"✅ **Command succeeded**\n\n{output}")
            else:
                ticket_rail.add_system_message(
                    f"⚠️ **Exit code {returncode}**\n\n{output}"
                )

        except Exception as e:
            ticket_rail.add_system_message(f"❌ **Command failed**\n\n`{e}`")

        finally:
            loader.stop()

    async def _handle_command(self, command: str) -> None:
        """Handle slash commands using the command registry."""
        if not command.startswith("/"):
            return

        parts = command.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Try command registry first
        if await self._dispatch_registered_command(name, arg):
            return

        # Fallback for TUI-specific commands not in registry
        if await self._dispatch_tui_command(name, arg):
            return

        # Unknown command
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"❓ Unknown command: `{name}`\n\nType `/help` to see available commands."
        )

    async def _dispatch_registered_command(self, name: str, arg: str) -> bool:
        """Dispatch to a command from the registry. Returns True if handled."""
        cmd_obj = self._command_registry.find_command(name)
        if not cmd_obj:
            return False

        # Map REPL handler names to TUI method names where they differ
        handler_map = {
            "_show_help": "_show_command_palette",
            "_show_status": "_show_status",
            "_show_config": "_show_config",
            "_reload_config": "_reload_config",
            "_clear_history": "_handle_clear",
            "_show_log_path": "_show_log_path",
            "_compact_history": "_compact_history",
            "_exit_app": "_handle_quit",
            "_chef_status": "_show_chef_status",
            "_chef_wisdom": "_show_wisdom",
            "_show_modes": "_show_modes",
            "_chef_roast": "_show_roast",
            "_chef_plate": "_handle_plate",
            "_chef_taste": "_chef_taste",
            "_chef_timer": "_chef_timer",
            "_handle_git_setup": "_handle_git_setup",
            "_handle_model_command": "_handle_model_command",
            "_handle_telegram": "_handle_telegram_command",
            "_handle_discord": "_handle_discord_command",
        }

        handler_name = handler_map.get(cmd_obj.handler, cmd_obj.handler)

        if hasattr(self, handler_name):
            handler = getattr(self, handler_name)
            import inspect

            sig = inspect.signature(handler)
            if len(sig.parameters) > 0:
                await handler(arg)
            else:
                await handler()
            return True
        return False

    async def _dispatch_tui_command(self, name: str, arg: str) -> bool:
        """Dispatch TUI-specific commands. Returns True if handled."""
        tui_commands = {
            "/layout": lambda: self._handle_layout_command(arg),
            "/fortune": lambda: self._show_fortune(),
            "/api": lambda: self._handle_api_command(),
            "/model": lambda: self._handle_model_command(arg),
            "/mcp": lambda: self._handle_mcp_command(),
            "/openrouter": lambda: self._handle_openrouter_command(arg),
        }

        handler = tui_commands.get(name)
        if handler:
            await handler()
            return True
        return False

    async def _handle_api_command(self) -> None:
        """Show API key onboarding screen."""
        await self.push_screen(OnboardingScreen(), self._on_onboarding_complete)

    async def _handle_git_setup(self) -> None:
        """Handle /git-setup command - configure GitHub token."""
        ticket_rail = self.query_one("#ticket-rail", TicketRail)

        def on_complete(success: bool) -> None:
            if success:
                self.notify("GitHub token saved!", title="Git Setup")
                ticket_rail.add_system_message(
                    "✅ **Git Setup Complete!**\n\nYour GitHub token was saved to `.env`."
                )
            else:
                ticket_rail.add_system_message("❌ Git setup cancelled.")

        await self.push_screen(GitSetupScreen(), on_complete)

    async def _handle_telegram_command(self, arg: str = "") -> None:
        """Handle /telegram command in TUI."""
        await self._handle_bot_command("telegram", arg)

    async def _handle_discord_command(self, arg: str = "") -> None:
        """Handle /discord command in TUI."""
        await self._handle_bot_command("discord", arg)

    async def _handle_bot_command(self, bot_type: str, arg: str) -> None:
        """Unified handler for bot commands (telegram/discord)."""
        action = arg.lower().strip() if arg else "help"

        # Get or create bot manager
        if not hasattr(self, "_bot_manager"):
            self._bot_manager = BotManager(self._config or VibeConfig.load())

        # Dispatch to action handlers
        handlers = {
            "help": self._bot_cmd_help,
            "setup": self._bot_cmd_setup,
            "start": self._bot_cmd_start,
            "stop": self._bot_cmd_stop,
            "status": self._bot_cmd_status,
        }

        handler = handlers.get(action)
        if handler:
            await handler(bot_type)
        else:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❓ Unknown: `{action}`. Try `/{bot_type}`"
            )

    async def _bot_cmd_help(self, bot_type: str) -> None:
        """Show bot help."""
        help_text = f"""## 🤖 {bot_type.title()} Bot Commands

• `/{bot_type} setup` — Configure token and user ID
• `/{bot_type} start` — Start the bot
• `/{bot_type} stop` — Stop the bot
• `/{bot_type} status` — Check status
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(help_text)

    async def _bot_cmd_setup(self, bot_type: str) -> None:
        """Handle bot setup command."""
        ticket_rail = self.query_one("#ticket-rail", TicketRail)

        def on_complete(success: bool) -> None:
            if success:
                self.notify(f"{bot_type.title()} configured!", title="Setup")
                ticket_rail.add_system_message(f"✅ {bot_type.title()} setup complete!")

        await self.push_screen(BotSetupScreen(bot_type), on_complete)

    async def _bot_cmd_start(self, bot_type: str) -> None:
        """Start the bot."""
        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        if self._bot_manager.is_running(bot_type):
            ticket_rail.add_system_message(f"⚠️ {bot_type.title()} bot already running.")
            return
        try:
            await self._bot_manager.start_bot(bot_type)
            ticket_rail.add_system_message(f"🚀 {bot_type.title()} bot started!")
        except Exception as e:
            ticket_rail.add_system_message(f"❌ Failed: {e}")

    async def _bot_cmd_stop(self, bot_type: str) -> None:
        """Stop the bot."""
        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        if not self._bot_manager.is_running(bot_type):
            ticket_rail.add_system_message(f"⚠️ {bot_type.title()} bot not running.")
            return
        await self._bot_manager.stop_bot(bot_type)
        ticket_rail.add_system_message(f"🛑 {bot_type.title()} bot stopped.")

    async def _bot_cmd_status(self, bot_type: str) -> None:
        """Show bot status."""
        running = (
            "🟢 Running" if self._bot_manager.is_running(bot_type) else "🔴 Stopped"
        )
        allowed = ", ".join(self._bot_manager.get_allowed_users(bot_type)) or "None"
        last_error = self._bot_manager.get_last_error(bot_type)
        error_line = (
            f"\n**Last error:** {last_error}"
            if (not self._bot_manager.is_running(bot_type) and last_error)
            else ""
        )
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"**{bot_type.title()}:** {running}\n**Users:** {allowed}{error_line}"
        )

    async def _handle_openrouter_command(self, arg: str = "") -> None:
        """Handle OpenRouter-specific commands."""
        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        action = arg.lower().strip() if arg else "help"

        if action == "help":
            help_text = """## 🌐 OpenRouter Commands

OpenRouter gives you access to 100+ AI models with a single API key!

### Commands
• `/openrouter` — Show this help
• `/openrouter setup` — Configure your OpenRouter API key
• `/openrouter status` — Check API key status and credit
• `/openrouter models` — List all available OpenRouter models
• `/openrouter <model>` — Quick switch to OpenRouter model

### Available Models (preconfigured)
• `or-claude-sonnet` — Claude 3.5 Sonnet (best reasoning)
• `or-claude-haiku` — Claude 3.5 Haiku (fast & cheap)
• `or-gpt4o` — GPT-4o via OpenRouter
• `or-gpt4o-mini` — GPT-4o Mini (fast)
• `or-gemini-flash` — Gemini 2.0 Flash (FREE!)
• `or-deepseek` — DeepSeek Chat (cheap + good)
• `or-deepseek-coder` — DeepSeek Coder
• `or-qwen-coder` — Qwen 2.5 Coder 32B
• `or-llama-70b` — Llama 3.3 70B
• `or-mistral-large` — Mistral Large 2411

### Quick Start
1. Get API key: https://openrouter.ai/keys
2. Run `/openrouter setup`
3. Run `/model select or-claude-sonnet`
"""
            ticket_rail.add_system_message(help_text)

        elif action == "setup":
            # Use the existing onboarding screen but pre-select openrouter
            await self._handle_api_command()

        elif action == "status":
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            if api_key:
                key_preview = (
                    f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
                )
                ticket_rail.add_system_message(
                    f"## 🌐 OpenRouter Status\n\n"
                    f"**API Key**: ✅ Configured ({key_preview})\n"
                    f"**Endpoint**: https://openrouter.ai/api/v1\n\n"
                    f"Use `/model select or-<model>` to switch to an OpenRouter model."
                )
            else:
                ticket_rail.add_system_message(
                    "## 🌐 OpenRouter Status\n\n"
                    "**API Key**: ❌ Not configured\n\n"
                    "Run `/openrouter setup` or `/api` to configure your key.\n"
                    "Get your key at: https://openrouter.ai/keys"
                )

        elif action == "models":
            if not self._config:
                self._config = VibeConfig.model_construct()

            lines = ["## 🌐 OpenRouter Models\n"]
            for m in self._config.models:
                if m.provider == "openrouter":
                    is_active = m.alias == self._config.active_model
                    status = "🟢 Active" if is_active else ""
                    price = (
                        f"${m.input_price:.2f}/${m.output_price:.2f}"
                        if m.input_price
                        else "FREE"
                    )
                    features = ", ".join(sorted(m.features)[:3]) if m.features else ""
                    lines.append(
                        f"**{m.alias}** {status}\n  `{m.name}` | {price}/M | {features}"
                    )
            ticket_rail.add_system_message("\n".join(lines))

        else:
            # Try to interpret as model switch
            target = f"or-{action}" if not action.startswith("or-") else action
            await self._model_select(target)

    async def _handle_model_command(self, arg: str = "") -> None:
        """Handle model management commands with subcommands."""
        if not self._config:
            try:
                self._config = VibeConfig.load()
            except MissingAPIKeyError:
                self.notify(
                    "API key missing. Run /api to configure keys.", severity="warning"
                )
                return
            except Exception as e:
                self.notify(f"Config Error: {e}", severity="error")
                return

        parts = arg.split(maxsplit=1)
        action = parts[0].lower() if parts else "help"
        sub_arg = parts[1].strip() if len(parts) > 1 else ""

        # Command dispatch table
        command_handlers = {
            "help": lambda: self._model_show_help(),
            "list": lambda: self._model_list(),
            "select": lambda: self._model_select(sub_arg),
            "info": lambda: self._model_info(sub_arg),
            "status": lambda: self._model_status(),
            "speed": lambda: self._model_speed(),
            "reasoning": lambda: self._model_reasoning(),
            "multimodal": lambda: self._model_multimodal(),
            "compare": lambda: self._model_compare(sub_arg),
            "manage": lambda: self._model_manage(),
        }

        handler = command_handlers.get(action)
        if handler:
            await handler()
        elif not action:
            await self._model_show_help()
        else:
            # Fallback for backward compatibility - treat as direct model selection
            await self._model_select(arg)

    def _get_llm_client(self):
        if not self._agent:
            raise RuntimeError("Agent not initialized")
        return self._agent.llm_client

    async def _model_show_help(self) -> None:
        """Show help for model commands."""
        help_text = """## 🤖 Model Management Commands

### Core Commands
• `/model` — Show model selection screen (default)
• `/model list` — List all available models with details
• `/model select <alias>` — Switch to a specific model
• `/model info <alias>` — Show detailed model information
• `/model status` — Show current model and API status
• `/model manage` — Open comprehensive model management UI

### Feature-Based Commands
• `/model speed` — List fastest models (Groq 8b, GPT-OSS 20b)
• `/model reasoning` — List reasoning models (Kimi K2, GPT-OSS 120b)
• `/model multimodal` — List multimodal models (Llama Scout/Maverick)
• `/model compare <alias1> <alias2>` — Compare models side-by-side

### Examples
• `/model select groq-8b` — Switch to Groq 8B model
• `/model info llama-scout` — Show Llama Scout details
• `/model list` — See all available models
• `/model manage` — Open enhanced model management interface

### Current Active Model
Use `/model status` to see which model is currently active.
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(help_text)

    async def _model_list(self) -> None:
        """List all available models with details, checking API availability."""
        lines = ["## 🤖 Available Models", ""]

        llm_client = None
        try:
            llm_client = self._get_llm_client()
        except Exception:
            llm_client = None

        # Group models by provider
        provider_groups = {}
        for model in self._config.models:
            provider = model.provider
            if provider not in provider_groups:
                provider_groups[provider] = []
            provider_groups[provider].append(model)

        for provider in sorted(provider_groups.keys()):
            lines.append(f"### {provider.upper()}")

            # Check if provider has API key configured
            provider_config = self._config.get_provider_for_model(
                provider_groups[provider][0]
            )
            has_api_key = (
                bool(os.getenv(provider_config.api_key_env_var))
                if provider_config.api_key_env_var
                else False
            )

            if has_api_key:
                # Try to fetch available models from API
                try:
                    if llm_client is None:
                        raise RuntimeError("LLM client not available")
                    available_models = await llm_client.list_models()
                    available_set = set(available_models)
                    lines.append(
                        f"✅ API key configured - {len(available_models)} models available"
                    )
                except Exception:
                    available_set = set()
                    lines.append("⚠️ API key configured but unable to fetch models")
            else:
                available_set = set()
                lines.append(
                    "❌ No API key configured - showing configured models only"
                )

            for model in sorted(provider_groups[provider], key=lambda m: m.alias):
                is_active = model.alias == self._config.active_model
                status = "🟢 Active" if is_active else "⚪ Configured"

                # Check if model is available via API
                if has_api_key and available_set:
                    if model.name in available_set:
                        status += " ✅ Available"
                    else:
                        status += " ❌ Not available"

                lines.append(f"**{model.alias}** {status}")
                lines.append(f"• Name: `{model.name}`")
                lines.append(f"• Temperature: {model.temperature}")

                if model.input_price or model.output_price:
                    lines.append(
                        f"• Pricing: ${model.input_price}/M in, ${model.output_price}/M out"
                    )

                # Show features
                if model.features:
                    features_str = ", ".join(sorted(model.features))
                    lines.append(f"• Features: {features_str}")

                lines.append("")

        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_select(self, model_alias: str) -> None:
        """Select a model by alias."""
        if not model_alias:
            await self._model_show_help()
            return

        if not self._config:
            self.notify("Config unavailable; cannot switch model.", severity="error")
            return

        # Find model by alias (case-insensitive)
        model = None
        target = model_alias.lower()
        for m in self._config.models:
            if target in {m.alias.lower(), m.name.lower()}:
                model = m
                break

        if not model:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❌ Model `{model_alias}` not found. Use `/model list` to see available models."
            )
            return

        try:
            self._config.active_model = model.alias
            VibeConfig.save_updates({"active_model": model.alias})

            if self._active_mode:
                asyncio.create_task(self._initialize_agent())

            self.notify(f"Switched to model: {model.alias}")
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"✅ **Model switched to `{model.alias}`**"
            )
        except Exception as e:
            self.notify(f"Failed to switch model: {e}", severity="error")

    async def _model_info(self, model_alias: str) -> None:
        """Show detailed information about a specific model."""
        if not model_alias:
            await self._model_show_help()
            return

        model = None
        target = model_alias.lower()
        for m in self._config.models:
            if target in {m.alias.lower(), m.name.lower()}:
                model = m
                break

        if not model:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❌ Model `{model_alias}` not found"
            )
            return

        is_active = model.alias == self._config.active_model
        provider = self._config.get_provider_for_model(model)
        api_key_note = (
            "✅ Set"
            if (provider.api_key_env_var and os.getenv(provider.api_key_env_var))
            else "⚠️ Missing"
        )

        info = f"""## 🤖 Model Details: {model.alias}

**Status**: {"🟢 Active" if is_active else "⚪ Available"}
**Name**: `{model.name}`
**Provider**: {model.provider}
**API Base**: {provider.api_base}

### Configuration
• **Temperature**: {model.temperature}
• **Max Tokens**: {model.max_tokens or "Default"}
• **Backend**: {provider.backend.value}

### Pricing
• **Input**: ${model.input_price}/M tokens
• **Output**: ${model.output_price}/M tokens

### API Key
• **Environment Variable**: `{provider.api_key_env_var or "None"}`
• **Status**: {api_key_note}
"""

        if model.features:
            features_str = ", ".join(sorted(model.features))
            info += f"\n### 🚀 Features\n{features_str}"

        if model.multimodal:
            info += f"\n### 🖼️ Multimodal Capabilities\n**Vision Support**: ✅\n**Max File Size**: {model.max_file_size} MB"

        if model.rate_limits:
            rate_info = []
            for limit_type, value in model.rate_limits.items():
                rate_info.append(f"{limit_type.upper()}: {value:,}")
            info += f"\n### ⚡ Rate Limits\n{', '.join(rate_info)}"

        self.query_one("#ticket-rail", TicketRail).add_system_message(info)

    async def _model_status(self) -> None:
        """Show current model status and configuration."""
        try:
            active_model = self._config.get_active_model()
            provider = self._config.get_provider_for_model(active_model)

            import os

            api_key_status = (
                "✅ Set"
                if provider.api_key_env_var and os.getenv(provider.api_key_env_var)
                else "❌ Missing"
            )

            status = f"""## 🤖 Current Model Status

**Active Model**: `{active_model.alias}`
**Provider**: {active_model.provider}
**API Key**: {api_key_status} (`{provider.api_key_env_var}`)

### Quick Actions
• `/model list` — Show all models
• `/model select <alias>` — Switch models
• `/model info {active_model.alias}` — Model details
"""
        except Exception as e:
            status = f"## 🤖 Model Status Error\n\n❌ {e}"

        self.query_one("#ticket-rail", TicketRail).add_system_message(status)

    async def _model_speed(self) -> None:
        """Show fastest models sorted by tokens/sec."""
        lines = ["## ⚡ Fastest Models", ""]

        speed_models = [
            ("gpt-oss-20b", "1000 TPS", "$0.075/$0.30"),
            ("llama-scout", "750 TPS", "$0.11/$0.34"),
            ("groq-8b", "560 TPS", "$0.05/$0.08"),
            ("qwen-32b", "400 TPS", "$0.29/$0.59"),
            ("groq-70b", "280 TPS", "$0.59/$0.79"),
        ]

        for alias, speed, pricing in speed_models:
            lines.append(f"• **{alias}** — {speed} — {pricing}")

        lines.append("\n*Use `/model select <alias>` to switch*")
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_reasoning(self) -> None:
        """Show models with reasoning capabilities."""
        lines = ["## 🧠 Reasoning Models", ""]

        reasoning_models = [
            ("kimi-k2", "Deep Reasoning", "$1.00/$3.00", "262K context"),
            ("gpt-oss-120b", "Browser + Code", "$0.15/$0.60", "131K context"),
            ("gpt-oss-20b", "Fast Reasoning", "$0.075/$0.30", "131K context"),
        ]

        for alias, capability, pricing, context in reasoning_models:
            lines.append(f"• **{alias}** — {capability} — {pricing} — {context}")

        lines.append("\n*Use `/model select <alias>` to switch*")
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_multimodal(self) -> None:
        """Show multimodal (vision) models."""
        lines = ["## 🖼️ Multimodal Models", ""]

        multimodal_models = [
            ("llama-scout", "Vision + Tools", "$0.11/$0.34", "20MB files"),
            ("llama-maverick", "Advanced Vision", "$0.20/$0.60", "20MB files"),
        ]

        for alias, capability, pricing, file_size in multimodal_models:
            lines.append(f"• **{alias}** — {capability} — {pricing} — {file_size}")

        lines.append("\n*Upload images with `@path/to/image.jpg`*")
        lines.append("*Use `/model select <alias>` to switch*")
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_compare(self, models_arg: str) -> None:
        """Compare multiple models side-by-side."""
        if not models_arg:
            await self._model_show_help()
            return

        model_aliases = models_arg.split()
        if len(model_aliases) < MIN_MODELS_TO_COMPARE:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "❌ Please provide at least 2 models to compare. Example: `/model compare groq-8b llama-scout`"
            )
            return

        lines = ["## 📊 Model Comparison", ""]

        # Find models
        models_to_compare = []
        for alias in model_aliases[:3]:  # Limit to 3 models
            model = None
            for m in self._config.models:
                if alias in {m.alias, m.name}:
                    model = m
                    break
            if model:
                models_to_compare.append(model)
            else:
                lines.append(f"❌ Model `{alias}` not found")

        if not models_to_compare:
            return

        # Create comparison table
        lines.append("| Model | Provider | Speed | Price | Features |")
        lines.append("|-------|----------|-------|--------|----------|")

        for model in models_to_compare:
            features = ", ".join(sorted(model.features)[:MAX_FEATURES_DISPLAY])
            if len(model.features) > MAX_FEATURES_DISPLAY:
                features += "..."

            price_str = f"${model.input_price}/${model.output_price}"
            lines.append(
                f"| {model.alias} | {model.provider} | N/A | {price_str} | {features} |"
            )

        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_manage(self) -> None:
        """Open comprehensive model management screen."""
        if not self._config:
            self._config = VibeConfig.load()

        def on_model_selected(model_alias: str | None) -> None:
            if model_alias and self._config:
                try:
                    # Update config active model
                    self._config.active_model = model_alias

                    # Persist change
                    VibeConfig.save_updates({"active_model": model_alias})

                    # Re-initialize agent if active
                    if self._active_mode:
                        asyncio.create_task(self._initialize_agent())

                    self.notify(f"Switched to model: {model_alias}")
                except Exception as e:
                    self.notify(f"Failed to switch model: {e}", severity="error")

        await self.push_screen(ModelManagerScreen(self._config), on_model_selected)

    async def _handle_mcp_command(self) -> None:
        """Show MCP server status and available tools."""
        if not self._config:
            self._config = VibeConfig.load()

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        mcp_servers = self._config.mcp_servers

        if not mcp_servers:
            ticket_rail.add_system_message(
                "## 🔌 MCP Servers\n\n"
                "No MCP servers configured.\n\n"
                "To add an MCP server, edit your `config.toml`:\n\n"
                "```toml\n"
                "[[mcp_servers]]\n"
                'name = "my-server"\n'
                'transport = "stdio"\n'
                'command = ["npx", "my-mcp-server"]\n'
                "```\n\n"
                "*See docs for HTTP and Streamable HTTP transports.*"
            )
            return

        # Build status display
        lines = [
            "## 🔌 MCP Servers",
            "",
            f"**{len(mcp_servers)}** server(s) configured:",
            "",
        ]

        for server in mcp_servers:
            transport = getattr(server, "transport", "unknown")
            name = getattr(server, "name", "unnamed")

            match transport:
                case "stdio":
                    cmd = getattr(server, "command", "")
                    if isinstance(cmd, list):
                        cmd = " ".join(cmd[:2])
                    lines.append(f"• **{name}** — `stdio` (`{cmd}`)")
                case "http" | "streamable-http":
                    url = getattr(server, "url", "")
                    lines.append(f"• **{name}** — `{transport}` (`{url}`)")
                case _:
                    lines.append(f"• **{name}** — `{transport}`")

        lines.extend(["", "---", "*MCP tools are loaded when the agent starts.*"])

        ticket_rail.add_system_message("\n".join(lines))

    async def _show_command_palette(self) -> None:
        """Show help directly in chat instead of separate palette."""
        layout_info = f"Current: **{self._layout.value}**"
        help_text = f"""## 📋 ChefChat Commands

**Navigation**
• `/help` — Show this menu
• `/clear` — Clear the chat
• `/quit` — Exit ChefChat

**Modes** *(Shift+Tab to cycle)*
• `/modes` — Show all available modes
• `/status` — Show current session status

**Layout** ({layout_info})
• `/layout chat` — Clean chat-only view
• `/layout kitchen` — Full 3-panel kitchen view

**Kitchen Tools**
• `/taste` — Run taste tests (QA)
• `/timer` — Kitchen timer info
• `/log` — Show log file path

**Fun Commands**
• `/chef` — Kitchen status
• `/wisdom` — Random chef wisdom
• `/roast` — Get roasted by Gordon Ramsay
• `/fortune` — Developer fortune cookie
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(help_text)

    async def _handle_layout_command(self, arg: str) -> None:
        """Handle layout switching command."""
        arg = arg.lower().strip()

        if arg == "chat":
            if self._layout == TUILayout.CHAT_ONLY:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    "Already in **chat** layout mode."
                )
            else:
                await self._confirm_layout_switch("chat")
        elif arg == "kitchen":
            if self._layout == TUILayout.FULL_KITCHEN:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    "Already in **kitchen** layout mode."
                )
            else:
                await self._confirm_layout_switch("kitchen")
        else:
            current = self._layout.value
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"## 🖼️ Layout Options\n\n"
                f"Current layout: **{current}**\n\n"
                f"• `/layout chat` — Clean chat-only view\n"
                f"• `/layout kitchen` — Full 3-panel kitchen view"
            )

    async def _handle_quit(self) -> None:
        """Handle quit command."""
        await self._shutdown()
        self.exit()

    async def _handle_plate(self) -> None:
        """Handle plate command wrapper."""
        if self._layout == TUILayout.FULL_KITCHEN:
            self.query_one("#the-plate", ThePlate).show_current_plate()
        else:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "📋 `/plate` is only available in **kitchen** layout mode.\n\n"
                "Use `/layout kitchen` to switch to full kitchen view."
            )

    async def _confirm_layout_switch(self, new_layout: str) -> None:
        """Show confirmation dialog for layout switch."""

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                # Save preference and restart
                save_tui_preference("layout", new_layout)

                # Show message and restart
                self.notify(f"Restarting with {new_layout} layout...", timeout=1)
                self.set_timer(0.5, lambda: self.exit(result="RESTART"))
            else:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    "Layout switch cancelled."
                )

        self.push_screen(ConfirmRestartScreen(new_layout), on_confirm)

    async def _handle_clear(self) -> None:
        await self.query_one("#ticket-rail", TicketRail).clear_tickets()
        if self._active_mode and self._agent:
            await self._agent.clear_history()
            self.notify("Context cleared")

        if self._layout == TUILayout.FULL_KITCHEN:
            try:
                self.query_one("#the-plate", ThePlate).clear_plate()
                self.query_one("#the-pass", ThePass).reset_all()
            except Exception:
                pass

    async def _show_modes(self) -> None:
        """Show available modes with current mode highlighted."""
        current = self._mode_manager.current_mode
        lines = [
            "## 🔄 Available Modes",
            "",
            "Press **Shift+Tab** to cycle through modes:",
            "",
        ]

        for mode in MODE_CYCLE_ORDER:
            config = MODE_CONFIGS[mode]
            marker = "▶" if mode == current else " "
            lines.append(
                f"{marker} {config.emoji} **{mode.value.upper()}**: {config.description}"
            )

        lines.extend(["", "---", f"Current: **{current.value.upper()}**"])
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _show_status(self) -> None:
        """Show session status with full statistics."""
        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]
        auto = "ON" if self._mode_manager.auto_approve else "OFF"

        # Calculate uptime
        uptime_seconds = int(time.time() - self._session_start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"{minutes}m {seconds}s"
        else:
            uptime_str = f"{seconds}s"

        # Get token count from agent if available
        token_count = 0
        if self._agent and hasattr(self._agent, "stats"):
            token_count = getattr(self._agent.stats, "total_tokens", 0)

        status = f"""## 📊 Today's Service

**⏱️  Service Time**: {uptime_str}
**🔤 Tokens Used**: {token_count:,}
**🔧 Tools Executed**: {self._tools_executed}
**🎯 Current Mode**: {config.emoji} {mode.value.upper()}
**⚡ Auto-Approve**: {auto}
**🍳 Kitchen**: {"🟢 Ready" if self._bus else "🔴 Initializing..."}
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(status)

    async def _show_wisdom(self) -> None:
        """Show chef wisdom."""
        import random

        wisdoms = [
            '🧑‍🍳 "Mise en place is not just for cooking—it\'s for coding too."',
            '🔪 "Sharp tools, sharp code. Keep your dependencies updated."',
            '🍳 "Low and slow wins the race. Don\'t rush your tests."',
            '🧂 "Season to taste. Iterate based on feedback."',
            '🍲 "A watched pot never boils. A watched CI never finishes."',
            '👨‍🍳 "Every chef was once a dishwasher. Keep refactoring."',
        ]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            random.choice(wisdoms)
        )

    async def _show_roast(self) -> None:
        """Get roasted by Gordon."""
        import random

        roasts = [
            '🔥 "This code is so raw, it\'s still mooing!"',
            '🔥 "I\'ve seen better architecture in a sandcastle!"',
            '🔥 "WHERE IS THE ERROR HANDLING?!"',
            '🔥 "This function is so long, it needs a GPS!"',
            '🔥 "You call that a commit message? Pathetic!"',
            '🔥 "My grandmother writes cleaner Python, and she\'s a COBOL developer!"',
        ]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            random.choice(roasts)
        )

    async def _show_fortune(self) -> None:
        """Developer fortune cookie."""
        import random

        fortunes = [
            "🥠 Your next merge conflict will resolve itself peacefully.",
            "🥠 The bug you've been hunting is in the file you refuse to check.",
            "🥠 A refactor is in your future. Embrace it.",
            "🥠 Your deployment will succeed on the first try (just kidding).",
            "🥠 The documentation you need has not been written yet.",
            "🥠 Someone will appreciate your comment today.",
        ]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            random.choice(fortunes)
        )

    async def _show_chef_status(self) -> None:
        """Show chef/kitchen status."""
        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]
        auto = "ON" if self._mode_manager.auto_approve else "OFF"
        bus_status = (
            "🟢 Running" if self._bus and self._bus.is_running else "🔴 Not Ready"
        )

        status = f"""## 👨‍🍳 Kitchen Status

**Current Mode**: {config.emoji} {mode.value.upper()}
**Description**: {config.description}
**Auto-Approve**: {auto}
**Kitchen Bus**: {bus_status}

---
*Press Shift+Tab to cycle modes*
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(status)

    async def _handle_model_command(self, arg: str = "") -> None:
        """Handle /model command - interactive or subcommand."""
        arg = arg.strip().lower()

        # Check for subcommands
        if arg == "status":
            await self._show_model_status()
            return

        if arg == "list":
            await self._list_available_models()
            return

        if arg.startswith("select "):
            alias = arg.replace("select ", "").strip()
            await self._switch_model(alias)
            return

        # Default: Open Interactive Manager
        await self._open_model_manager()

    async def _show_model_status(self) -> None:
        """Show realtime model status."""
        if not self._config:
            self._config = VibeConfig.load()

        active_model = self._config.get_active_model()
        provider = self._config.get_provider_for_model(active_model)

        status_text = (
            f"## 🤖 Realtime Model Status\n\n"
            f"🌟 **Active Model**: `{active_model.alias}`\n"
            f"📦 **Provider**: {provider.name}\n"
            f"🆔 **Model ID**: `{active_model.name}`\n"
            f"🌡️ **Temperature**: {active_model.temperature}\n"
            f"💰 **Cost**: ${active_model.input_price}/M in, ${active_model.output_price}/M out"
        )
        self.query_one("#ticket-rail", TicketRail).add_system_message(status_text)

    async def _list_available_models(self) -> None:
        """List all available models (realtime)."""
        if not self._config:
            self._config = VibeConfig.load()

        lines = ["## 📦 Available Models", ""]
        active = self._config.active_model

        # Sort by alias
        for m in sorted(self._config.models, key=lambda x: x.alias):
            marker = "✅" if m.alias == active else "⚪"
            lines.append(f"{marker} **{m.alias}** ({m.provider})")

        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _switch_model(self, alias: str) -> None:
        """Switch model by alias."""
        if not self._config:
            self._config = VibeConfig.load()

        target = next((m for m in self._config.models if m.alias == alias), None)
        if not target:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❌ Model `{alias}` not found. Use `/model list` to see available."
            )
            return

        self._config.active_model = target.alias
        VibeConfig.save_updates({"active_model": target.alias})

        # Update active agent if exists
        try:
            asyncio.create_task(self._initialize_agent())
        except Exception:
            pass

        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"✅ Switched active model to **{target.alias}**"
        )
        self.notify(f"Model: {target.alias}")

    async def _open_model_manager(self) -> None:
        """Open the interactive model manager screen."""
        if not self._config:
            self._config = VibeConfig.load()

        def on_complete(selected_alias: str | None) -> None:
            if selected_alias:
                asyncio.create_task(self._switch_model(selected_alias))

        await self.push_screen(ModelManagerScreen(self._config), on_complete)

    async def _show_config(self) -> None:
        """Show configuration info."""
        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]

        info = f"""## ⚙️ Configuration

**Mode**: {config.emoji} {mode.value.upper()}
**Auto-Approve**: {"ON" if self._mode_manager.auto_approve else "OFF"}

---
*Use the REPL for full configuration options*
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(info)

    async def _show_log_path(self) -> None:
        """Show the current log path."""
        log_dir = TUI_PREFS_FILE.parent / "logs"
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"## 📝 Kitchen Logs\n\n"
            f"Logs are stored in:\n`{log_dir}`\n\n"
            f"*Check these for details if the soufflé collapses.*"
        )

    async def _chef_taste(self) -> None:
        """Trigger the Expeditor to run taste tests."""
        if not self._brigade:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "⚠️ **Expeditor not available**\n\n"
                "The kitchen brigade is not fully assembled. Run with `uv run vibe` for full kitchen experience."
            )
            return

        # Trigger taste test
        ticket_id = str(uuid4())[:8]
        message = ChefMessage(
            sender="tui",
            recipient="expeditor",
            action="TASTE_TEST",  # Matches BusAction.TASTE_TEST
            # Default to running pytest and ruff on current directory
            payload={"ticket_id": ticket_id, "tests": ["pytest", "ruff"], "path": "."},
            priority=MessagePriority.HIGH,
        )

        await self._bus.publish(message)
        try:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"🥄 **Taste Test Ordered** (Ticket #{ticket_id})\n\n"
                "Expeditor is checking the dish (running tests & linting)..."
            )
        except Exception:
            # In unit tests the Textual app is not running and no screen stack exists.
            pass

    async def _chef_timer(self, arg: str) -> None:
        """Show timer info."""
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            "## ⏱️ Kitchen Timer\n\n"
            "Kitchen timer is coming soon to the TUI!\n"
            "Use it to track long-running tasks or just to boil an egg perfectly."
        )

    async def _reload_config(self) -> None:
        """Reload configuration."""
        # For TUI, most config is loaded on startup, but we can refresh modes
        self.notify("Reloading configuration...", title="System")
        self._mode_manager = ModeManager(initial_mode=self._mode_manager.current_mode)
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            "🔄 **Configuration Reloaded**"
        )

    async def _compact_history(self) -> None:
        """Compact conversation history."""
        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        ticket_rail.add_system_message(
            "🗜️ **Compacting History**\n\nCompressing the conversation context..."
        )

        try:
            # If we have an active agent, use its compact method
            if self._agent:
                summary = await self._agent.compact()
                ticket_rail.add_system_message(
                    f"✅ **History compacted successfully**\n\n"
                    f"*Summary: {summary[:SUMMARY_PREVIEW_LENGTH]}{'...' if len(summary) > SUMMARY_PREVIEW_LENGTH else ''}*"
                )
            else:
                # Fallback: simulate compaction for standalone mode
                await asyncio.sleep(1)
                ticket_rail.add_system_message(
                    "✅ **History compacted**\n\n"
                    "*Note: Full compaction requires active agent mode*"
                )
        except Exception as e:
            ticket_rail.add_system_message(
                f"❌ **Compaction failed**: {e}\n\n"
                "*The conversation history remains unchanged*"
            )

    async def _shutdown(self) -> None:
        """Gracefully shutdown the kitchen."""
        if self._brigade:
            await self._brigade.close_kitchen()
        elif self._bus:
            await self._bus.stop()

    def action_quit(self) -> None:
        if self._brigade or self._bus:
            # Schedule shutdown and then exit
            self.call_after_refresh(lambda: asyncio.create_task(self._shutdown()))
        self.exit()

    def action_cancel(self) -> None:
        if not self._state.is_processing:
            return

        self._enter_cancelling()

        # Request cancellation from backend first (best effort).
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

            # Update the KitchenFooter silently
            try:
                footer = self.query_one("#kitchen-footer", KitchenFooter)
                footer.refresh_mode()
                footer.refresh()
            except Exception:
                pass

            # Show notification (this is the most reliable feedback)
            self.notify(
                f"{config.emoji} {new_mode.value.upper()}: {config.description}",
                title="Mode Changed",
                timeout=2,
            )

        except Exception as e:
            # Catch any unexpected error so we don't crash
            self.notify(f"Mode error: {e}", severity="error", timeout=3)

    async def _setup_brigade(self) -> None:
        """Initialize the full Brigade for active mode."""
        # Load API keys from .env files
        try:
            load_api_keys_from_env()
        except Exception as e:
            logger.warning("Could not load API keys from .env: %s", e)

        # Create and start the brigade
        self._brigade = await create_default_brigade()
        self._bus = self._brigade.bus
        self._bus.subscribe("tui", self._handle_bus_message)
        await self._brigade.open_kitchen()

        # Log brigade status
        logger.info(
            "Brigade started with %d stations: %s",
            self._brigade.station_count,
            self._brigade.station_names,
        )


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
    # Ensure Textual works with colors
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
