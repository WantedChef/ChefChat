"""Agent Lifecycle Mixin for ChefChat TUI.

Handles agent initialization, interaction loop, ticket submission, and brigade setup.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from chefchat.core.types import AssistantEvent, ToolCallEvent, ToolResultEvent
    from chefchat.interface.protocols import ChefAppProtocol
    from chefchat.interface.widgets.kitchen_ui import WhiskLoader
    from chefchat.interface.widgets.the_plate import ThePlate
    from chefchat.interface.widgets.ticket_rail import TicketRail

logger = logging.getLogger(__name__)


class AgentLifecycleMixin:
    """Mixin providing agent lifecycle management for ChefChatApp.

    Requires the following attributes on self:
    - _config: VibeConfig | None
    - _agent: Agent | None
    - _bus: KitchenBus | None
    - _brigade: Brigade | None
    - _mode_manager: ModeManager
    - _active_mode: bool
    - _tools_executed: int
    - _layout: TUILayout
    """

    # Type hint for self when used as mixin
    self: ChefAppProtocol

    async def _initialize_agent(self) -> None:
        """Initialize the core Agent for active mode."""
        from chefchat.core.agent import Agent
        from chefchat.core.config import (
            MissingAPIKeyError,
            VibeConfig,
            load_api_keys_from_env,
        )
        from chefchat.interface.screens.onboarding import OnboardingScreen
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.modes import MODE_CONFIGS

        try:
            load_api_keys_from_env()
            self._config = VibeConfig.load()
        except MissingAPIKeyError:
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
        from chefchat.core.config import VibeConfig, load_api_keys_from_env

        if not provider:
            self.notify("Setup incomplete. Chat will be disabled.", severity="warning")
            return

        try:
            load_api_keys_from_env()
            config = VibeConfig.load()

            current_model = config.get_active_model()
            if current_model.provider != provider:
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
        from chefchat.interface.screens.tool_approval import ToolApprovalScreen

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def on_screen_result(result: tuple[str, str | None]) -> None:
            if not future.done():
                future.set_result(result)

        self.call_from_thread(
            lambda: self.push_screen(
                ToolApprovalScreen(tool_name, tool_args), on_screen_result
            )
        )

        return await future

    async def _run_agent_loop(self, request: str) -> None:
        """Run the agent interaction loop in a worker (main thread async)."""
        from chefchat.interface.widgets.kitchen_ui import WhiskLoader
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if not self._agent:
            return

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        plate = self._get_plate_if_available()
        loader = self.query_one(WhiskLoader)

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

    def _process_tui_event(
        self,
        event: AssistantEvent | ToolCallEvent | ToolResultEvent,
        ticket_rail: TicketRail,
        plate: ThePlate | None,
        loader: WhiskLoader,
    ) -> None:
        """Process an agent event and update TUI accordingly."""
        from chefchat.core.types import (
            AssistantEvent,
            CompactEndEvent,
            CompactStartEvent,
            ToolCallEvent,
            ToolResultEvent,
        )

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
        from chefchat.interface.constants import BusAction, PayloadKey
        from chefchat.interface.widgets.kitchen_ui import WhiskLoader
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.kitchen.bus import ChefMessage, MessagePriority

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

        self.query_one(WhiskLoader).start("Processing ticket...")
        self._enter_running(ticket_id)

        await self._bus.publish(message)

    async def _setup_brigade(self) -> None:
        """Initialize the full Brigade for active mode."""
        from chefchat.core.config import load_api_keys_from_env
        from chefchat.kitchen.brigade import create_default_brigade

        try:
            load_api_keys_from_env()
        except Exception as e:
            logger.warning("Could not load API keys from .env: %s", e)

        self._brigade = await create_default_brigade()
        self._bus = self._brigade.bus
        self._bus.subscribe("tui", self._handle_bus_message)
        await self._brigade.open_kitchen()

        logger.info(
            "Brigade started with %d stations: %s",
            self._brigade.station_count,
            self._brigade.station_names,
        )

    async def _shutdown(self) -> None:
        """Gracefully shutdown the kitchen."""
        if self._brigade:
            await self._brigade.close_kitchen()
        elif self._bus:
            await self._bus.stop()
