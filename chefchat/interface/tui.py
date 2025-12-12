"""ChefChat TUI - The Main Textual Application.

This is the culinary-themed Terminal User Interface for ChefChat.
The 3-pane layout represents a professional kitchen:
- The Ticket (left): Where orders (chat) come in
- The Pass (right): Where the brigade reports status
- The Plate (bottom): Where the finished dish (code) is presented
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import re
import sys
import traceback
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal
from textual.widgets import Footer, Input, Static
from textual.worker import Worker

# Assuming these imports exist in your project structure
from chefchat.interface.constants import (
    MARKDOWN_SANITIZE_CHARS,
    WHISK_FRAMES,
    BusAction,
    PayloadKey,
    StationStatus,
    StatusString,
    TicketCommand,
)
from chefchat.interface.screens.command_palette import CommandPalette
from chefchat.interface.widgets.the_pass import ThePass
from chefchat.interface.widgets.the_plate import ThePlate
from chefchat.interface.widgets.ticket_rail import TicketRail
from chefchat.kitchen.brigade import Brigade, create_default_brigade
from chefchat.kitchen.bus import ChefMessage, KitchenBus, MessagePriority

if TYPE_CHECKING:
    pass

# Configure logging for TUI module
logger = logging.getLogger(__name__)


class WhiskLoader(Horizontal):
    """Animated loading indicator with kitchen flair."""

    # CSS defined in styles.tcss

    def __init__(self) -> None:
        super().__init__()
        self._frame_index = 0
        self._message = "Cooking..."
        self._worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        yield Static(WHISK_FRAMES[0], classes="whisk-spinner")
        yield Static(self._message, classes="whisk-message")

    async def on_unmount(self) -> None:
        self.stop()

    def start(self, message: str = "Cooking...") -> None:
        self._message = message
        try:
            msg_widget = self.query_one(".whisk-message", Static)
            msg_widget.update(message)
        except Exception:
            pass

        if self._worker and not self._worker.is_finished:
            return

        self.add_class("visible")
        self._worker = self.run_worker(
            self._animate(),
            exclusive=True,
            group="whisk_animation",
            exit_on_error=False,
        )

    async def _animate(self) -> None:
        try:
            while True:
                self._frame_index = (self._frame_index + 1) % len(WHISK_FRAMES)
                try:
                    spinner = self.query_one(".whisk-spinner", Static)
                    spinner.update(WHISK_FRAMES[self._frame_index])
                except Exception:
                    break
                await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            pass
        finally:
            self.remove_class("visible")

    def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._worker = None
        self.remove_class("visible")
        self._frame_index = 0


class KitchenHeader(Static):
    """Custom header with kitchen branding."""

    #  CSS defined in styles.tcss

    def compose(self) -> ComposeResult:
        yield Static(
            "👨‍🍳 [bold]ChefChat[/] • The Michelin Star AI-Engineer",
            classes="header-title",
        )


class CommandInput(Input):
    """Custom command input with kitchen styling."""

    # CSS defined in styles.tcss


def sanitize_markdown_input(text: str) -> str:
    """Sanitize user input for safe markdown rendering."""
    if not text:
        return ""

    sanitized = text
    for char, replacement in MARKDOWN_SANITIZE_CHARS.items():
        sanitized = sanitized.replace(char, replacement)

    # Remove ANSI escape sequences
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    sanitized = ansi_escape.sub("", sanitized)
    sanitized = sanitized.replace("\0", "")

    return sanitized


class ChefChatApp(App):
    """The main ChefChat TUI application."""

    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "ChefChat"
    SUB_TITLE = "The Michelin Star AI-Engineer"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+c", "cancel", "Cancel", show=True),
        Binding("ctrl+l", "clear", "Clear Plate", show=True),
        Binding("escape", "focus_input", "Focus Input", show=False),
    ]

    _STATUS_MAP: ClassVar[dict[str, StationStatus]] = {
        StatusString.IDLE.value: StationStatus.IDLE,
        StatusString.PLANNING.value: StationStatus.WORKING,
        StatusString.COOKING.value: StationStatus.WORKING,
        StatusString.TESTING.value: StationStatus.WORKING,
        StatusString.REFACTORING.value: StationStatus.WORKING,
        StatusString.COMPLETE.value: StationStatus.COMPLETE,
        StatusString.ERROR.value: StationStatus.ERROR,
    }

    def __init__(self) -> None:
        super().__init__()
        self._bus: KitchenBus | None = None
        self._brigade: Brigade | None = None
        self._processing = False

    @property
    def bus(self) -> KitchenBus:
        if self._bus is None:
            raise RuntimeError("Kitchen bus not initialized")
        return self._bus

    def compose(self) -> ComposeResult:
        """Compose the 3-pane kitchen layout."""
        # Header first (dock top)
        yield KitchenHeader()

        # Main Grid Area
        with Grid(id="kitchen-grid"):
            yield TicketRail(id="ticket-rail")
            yield ThePass(id="the-pass")
            yield ThePlate(id="the-plate")

        # Footer elements (dock bottom)
        # Yield WhiskLoader first, then CommandInput.
        # Since both are dock: bottom, CommandInput will appear BELOW WhiskLoader.
        yield WhiskLoader()
        yield CommandInput(
            placeholder="🍳 What shall we cook today, Chef?", id="command-input"
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Handle app mount - start workers and show welcome."""
        try:
            ticket_rail = self.query_one("#ticket-rail", TicketRail)
            ticket_rail.add_system_message(
                "🍽️ **Welcome to ChefChat!**\n\n"
                "The kitchen is ready, Chef. What would you like to cook today?\n\n"
                "*Commands: `/help` for menu, `/clear` to reset*"
            )

            self.query_one("#command-input", CommandInput).focus()
            # await self._setup_brigade()

        except Exception as e:
            logger.exception("Error in on_mount: %s", e)
            self.notify(f"Kitchen Error: {e}", severity="error")

    async def on_unmount(self) -> None:
        await self._shutdown()

    async def _handle_bus_message(self, message: ChefMessage) -> None:
        """Handle incoming messages from the bus."""
        try:
            match message.action:
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
        except Exception as exc:
            logger.exception("Error handling bus message: %s", exc)

    async def _update_station_status(self, payload: dict) -> None:
        station_id = payload.get(PayloadKey.STATION, "")
        if not station_id:
            return

        status_raw = str(payload.get(PayloadKey.STATUS, "")).lower()
        status = self._STATUS_MAP.get(status_raw, StationStatus.IDLE)
        progress = float(payload.get(PayloadKey.PROGRESS, 0.0) or 0.0)
        message = str(payload.get(PayloadKey.MESSAGE, "")) or status.name.capitalize()

        station_board = self.query_one("#the-pass", ThePass)
        station_board.update_station(station_id, status, progress, message)

    async def _add_log_message(self, payload: dict) -> None:
        content = str(
            payload.get(PayloadKey.CONTENT, "") or payload.get(PayloadKey.MESSAGE, "")
        )
        if not content:
            return

        # Log to ticket rail
        self.query_one("#ticket-rail", TicketRail).add_assistant_message(content)
        # Also log to Plate log
        self.query_one("#the-plate", ThePlate).log_message(content)

    async def _plate_code(self, payload: dict, *, append: bool = False) -> None:
        code = str(payload.get(PayloadKey.CODE, ""))
        if not code:
            return

        language = str(payload.get(PayloadKey.LANGUAGE, "python")) or "python"
        file_path = payload.get(PayloadKey.FILE_PATH)
        plate = self.query_one("#the-plate", ThePlate)
        plate.plate_code(code, language=language, file_path=file_path, append=append)

    async def _add_terminal_log(self, payload: dict) -> None:
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
        val = event.value.strip()
        if not val:
            return

        user_input = sanitize_markdown_input(val)
        if not user_input.strip():
            return

        # Clear input immediately for better UX
        self.query_one("#command-input", CommandInput).value = ""

        if user_input.startswith("/"):
            await self._handle_command(user_input)
        else:
            await self._submit_ticket(user_input)

    async def _submit_ticket(self, request: str) -> None:
        """Submit a new ticket to the kitchen via the bus."""
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

        # Show user message in UI immediately
        self.query_one("#ticket-rail", TicketRail).add_user_message(request)

        # Start the loader
        self.query_one(WhiskLoader).start("Processing ticket...")
        self._processing = True

        await self._bus.publish(message)

    async def _handle_command(self, command: str) -> None:
        if not command.startswith("/"):
            return

        parts = command.lstrip("/").split(maxsplit=1)
        name = parts[0].strip().lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        match name:
            case TicketCommand.HELP.value:
                await self._show_command_palette()
            case TicketCommand.CLEAR.value:
                await self._handle_clear()
            case TicketCommand.QUIT.value:
                await self._shutdown()
                self.exit()
            case TicketCommand.CHEF.value:
                await self._submit_ticket(arg or "chef: plan this task")
            case TicketCommand.PLATE.value:
                self.query_one("#the-plate", ThePlate).show_current_plate()
            case _:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    f"Unknown command: /{name}"
                )

    async def _show_command_palette(self) -> None:
        self.push_screen(CommandPalette())

    async def _handle_clear(self) -> None:
        self.query_one("#ticket-rail", TicketRail).clear_tickets()
        self.query_one("#the-plate", ThePlate).clear_plate()
        self.query_one("#the-pass", ThePass).reset_all()

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
        self._processing = False
        try:
            self.query_one(WhiskLoader).stop()
        except Exception:
            pass

    def action_clear(self) -> None:
        asyncio.create_task(self._handle_clear())

    def action_focus_input(self) -> None:
        self.query_one("#command-input", CommandInput).focus()

    async def _setup_brigade(self) -> None:
        self._brigade = await create_default_brigade()
        self._bus = self._brigade.bus
        self._bus.subscribe("tui", self._handle_bus_message)
        await self._brigade.open_kitchen()


def run(*, verbose: bool = False) -> None:
    """Run the ChefChat TUI application."""
    # Ensure Textual works with colors
    os.environ.setdefault("FORCE_COLOR", "1")

    # Compatibility check for IDEs/Non-standard terminals
    is_tty = sys.stdout.isatty()
    term = os.environ.get("TERM", "").lower()

    if not is_tty and not os.environ.get("FORCE_TTY"):
        # If explicitly not a TTY and no TERM set, warn but attempt to run
        if not term or term == "dumb":
            print("⚠️  Warning: Non-interactive terminal detected.", file=sys.stderr)
            # Default to xterm-256color to allow Textual to try rendering
            os.environ["TERM"] = "xterm-256color"

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    app = ChefChatApp()

    try:
        app.run()
    except KeyboardInterrupt:
        print("\n👋 ChefChat kitchen closed.")
    except Exception as e:
        print(f"\n❌ Application Error: {e}", file=sys.stderr)
        if verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
