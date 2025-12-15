"""Bus Event Handler Mixin for ChefChat TUI.

Handles incoming messages from the KitchenBus and updates UI accordingly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol
    from chefchat.kitchen.bus import ChefMessage

logger = logging.getLogger(__name__)


class BusEventHandlerMixin:
    """Mixin providing KitchenBus message handling for ChefChatApp.

    Requires the following attributes on self:
    - _layout: TUILayout
    - _state: AppState
    - _STATUS_MAP: dict (class variable)
    """

    # Type hint for self when used as mixin
    self: ChefAppProtocol

    # Status mapping - will be inherited from main class
    _STATUS_MAP: ClassVar[dict[str, Any]] = {}

    async def _handle_bus_message(self, message: ChefMessage) -> None:
        """Handle incoming messages from the bus."""
        from chefchat.interface.constants import BusAction

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

    async def _on_ticket_done(self, payload: dict) -> None:
        """Finalize the current ticket lifecycle.

        This must be safe to call multiple times and should always end
        the "Cooking..." state.
        """
        from chefchat.interface.constants import PayloadKey
        from chefchat.interface.widgets.kitchen_ui import WhiskLoader
        from chefchat.interface.widgets.ticket_rail import TicketRail

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
        """Update station status in ThePass widget."""
        from chefchat.interface.constants import PayloadKey, StationStatus, TUILayout
        from chefchat.interface.widgets.the_pass import ThePass

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
        """Add log message to ticket rail and plate."""
        from chefchat.interface.constants import PayloadKey, TUILayout
        from chefchat.interface.widgets.the_plate import ThePlate
        from chefchat.interface.widgets.ticket_rail import TicketRail

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
        """Display code on ThePlate widget."""
        from chefchat.interface.constants import PayloadKey, TUILayout
        from chefchat.interface.widgets.the_plate import ThePlate

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
        """Add terminal log to ThePlate."""
        from chefchat.interface.constants import PayloadKey, TUILayout
        from chefchat.interface.widgets.the_plate import ThePlate

        # ThePlate only exists in FULL_KITCHEN layout
        if self._layout != TUILayout.FULL_KITCHEN:
            return

        message = str(
            payload.get(PayloadKey.MESSAGE, "") or payload.get(PayloadKey.CONTENT, "")
        )
        if message:
            self.query_one("#the-plate", ThePlate).log_message(message)

    async def _add_plan(self, payload: dict) -> None:
        """Add plan update to ticket rail."""
        from chefchat.interface.constants import PayloadKey
        from chefchat.interface.widgets.ticket_rail import TicketRail

        task = str(
            payload.get(PayloadKey.TASK, "") or payload.get(PayloadKey.CONTENT, "")
        )
        if task:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"🗺️ Plan updated: {task}"
            )
