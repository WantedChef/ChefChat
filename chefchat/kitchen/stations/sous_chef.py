"""ChefChat Sous Chef Station - The Planning & Orchestration Agent.

The Sous Chef is the Head Chef's right hand. They:
- Receive user requests and break them into tasks
- Delegate work to the Line Cook and Sommelier
- Coordinate the overall execution flow
- Report progress back to the TUI
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus, MessagePriority

if TYPE_CHECKING:
    pass


class SousChef(BaseStation):
    """The planning and orchestration station.

    Handles:
    - Task breakdown ("Mise en place")
    - Work delegation to other stations
    - Progress aggregation
    - Error recovery coordination
    """

    def __init__(self, bus: KitchenBus) -> None:
        """Initialize the Sous Chef station.

        Args:
            bus: The kitchen bus to connect to
        """
        super().__init__("sous_chef", bus)
        self._current_ticket: str | None = None
        self._pending_tasks: list[dict] = []

    async def handle(self, message: ChefMessage) -> None:
        """Process incoming messages.

        Args:
            message: The message to process
        """
        action = message.action

        if action == "new_ticket":
            # New user request - break it down and delegate
            await self._process_ticket(message.payload)

        elif action == "task_complete":
            # A station completed its work
            await self._handle_completion(message)

        elif action == "task_error":
            # A station encountered an error
            await self._handle_error(message)

        elif action == "status_request":
            # Request for current status
            await self._report_status(message.sender)

    async def _process_ticket(self, payload: dict) -> None:
        """Break down a user request into tasks.

        Args:
            payload: The ticket data from the user
        """
        self._current_ticket = payload.get("ticket_id", "unknown")
        request = payload.get("request", "")

        # TODO: Implement actual task planning with LLM
        # For now, just acknowledge and forward

        # Notify UI of planning start
        await self.send(
            recipient="tui",
            action="status_update",
            payload={
                "station": self.name,
                "status": "planning",
                "message": f"Analyzing request: {request[:50]}...",
            },
        )

        # Placeholder: Send to line cook for implementation
        await self.send(
            recipient="line_cook",
            action="implement",
            payload={"ticket_id": self._current_ticket, "task": request},
            priority=MessagePriority.HIGH,
        )

    async def _handle_completion(self, message: ChefMessage) -> None:
        """Handle task completion from a station.

        Args:
            message: The completion message
        """
        sender = message.sender
        result = message.payload.get("result", {})

        # Notify UI
        await self.send(
            recipient="tui",
            action="status_update",
            payload={"station": sender, "status": "complete", "result": result},
        )

    async def _handle_error(self, message: ChefMessage) -> None:
        """Handle errors from other stations.

        Args:
            message: The error message
        """
        error = message.payload.get("error", "Unknown error")
        sender = message.sender

        # Notify UI of error
        await self.send(
            recipient="tui",
            action="error",
            payload={"station": sender, "error": error},
            priority=MessagePriority.CRITICAL,
        )

    async def _report_status(self, requester: str) -> None:
        """Report current status to requester.

        Args:
            requester: The station requesting status
        """
        await self.send(
            recipient=requester,
            action="status_response",
            payload={
                "station": self.name,
                "current_ticket": self._current_ticket,
                "pending_tasks": len(self._pending_tasks),
                "status": "ready" if not self._current_ticket else "busy",
            },
        )
