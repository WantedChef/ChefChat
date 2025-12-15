"""Protocols for ChefChat Interface Mixins.

This module defines the interface that ChefChatApp exposes to its mixins.
Mixins use these protocols for type hints instead of importing app.py directly,
avoiding circular imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from chefchat.cli.commands import CommandRegistry
    from chefchat.core.agent import Agent
    from chefchat.core.config import VibeConfig
    from chefchat.interface.constants import TUILayout
    from chefchat.interface.services import ConfigService, ModelService
    from chefchat.interface.widgets.the_plate import ThePlate
    from chefchat.kitchen.brigade import Brigade
    from chefchat.kitchen.bus import KitchenBus
    from chefchat.modes import ModeManager


@runtime_checkable
class ChefAppProtocol(Protocol):
    """Protocol defining the interface available to Mixins.

    This allows mixins to use `self: ChefAppProtocol` for type hints
    without importing the concrete ChefChatApp class.
    """

    # ==== Core Attributes ====
    _bus: KitchenBus | None
    _brigade: Brigade | None
    _agent: Agent | None
    _config: VibeConfig | None
    _command_registry: CommandRegistry
    _mode_manager: ModeManager
    _layout: TUILayout
    _active_mode: bool
    _active_mode: bool
    _session_start_time: float
    _tools_executed: int

    # ==== Services & Registry ====
    @property
    def model_service(self) -> ModelService: ...
    @property
    def config_service(self) -> ConfigService: ...
    @property
    def bus(self) -> KitchenBus: ...

    # ==== Textual App Methods (inherited from App) ====
    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float = 5.0,
    ) -> None:
        """Display a notification to the user."""
        ...

    def query_one(self, selector: str | type, expect_type: type | None = None) -> Any:
        """Query a single widget by selector."""
        ...

    async def push_screen(self, screen: Any, callback: Any = None) -> Any:
        """Push a screen onto the screen stack."""
        ...

    def call_from_thread(self, callback: Any) -> None:
        """Call a function from a thread."""
        ...

    # ==== State Management ====
    def _enter_running(self, ticket_id: str | None) -> None:
        """Transition to RUNNING state."""
        ...

    def _enter_cancelling(self) -> None:
        """Transition to CANCELLING state."""
        ...

    def _enter_idle(self) -> None:
        """Transition to IDLE state."""
        ...

    # ==== Helper Methods ====
    def _get_plate_if_available(self) -> ThePlate | None:
        """Get ThePlate widget if in FULL_KITCHEN layout."""
        ...
