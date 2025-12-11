"""ChefChat Line Cook Station - The Code Generation Agent.

The Line Cook is where the actual cooking happens. They:
- Receive implementation tasks from the Sous Chef
- Generate code using the LLM
- Execute and test the code
- Report results back
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus

if TYPE_CHECKING:
    pass


class LineCook(BaseStation):
    """The code generation and execution station.

    Handles:
    - Code generation via LLM
    - Code execution in sandbox
    - Test running
    - Result reporting
    """

    def __init__(self, bus: KitchenBus) -> None:
        """Initialize the Line Cook station.

        Args:
            bus: The kitchen bus to connect to
        """
        super().__init__("line_cook", bus)
        self._current_task: str | None = None

    async def handle(self, message: ChefMessage) -> None:
        """Process incoming messages.

        Args:
            message: The message to process
        """
        action = message.action

        if action == "implement":
            # Implementation request from Sous Chef
            await self._implement(message.payload)

        elif action == "test":
            # Run tests on code
            await self._run_tests(message.payload)

        elif action == "refactor":
            # Refactor existing code
            await self._refactor(message.payload)

    async def _implement(self, payload: dict) -> None:
        """Generate implementation for a task.

        Args:
            payload: The task details
        """
        ticket_id = payload.get("ticket_id", "unknown")
        task = payload.get("task", "")

        self._current_task = ticket_id

        # Notify we're starting
        await self.send(
            recipient="tui",
            action="status_update",
            payload={
                "station": self.name,
                "status": "cooking",
                "message": f"Implementing: {task[:30]}...",
            },
        )

        # TODO: Actual LLM code generation goes here
        # For now, simulate with placeholder

        generated_code = f"# Generated for task: {task}\nprint('Hello from Line Cook!')"

        # Send code to plate (display)
        await self.send(
            recipient="tui",
            action="plate_code",
            payload={
                "code": generated_code,
                "language": "python",
                "ticket_id": ticket_id,
            },
        )

        # Report completion
        await self.send(
            recipient="sous_chef",
            action="task_complete",
            payload={
                "ticket_id": ticket_id,
                "result": {"code": generated_code, "status": "success"},
            },
        )

        self._current_task = None

    async def _run_tests(self, payload: dict) -> None:
        """Run tests on generated code.

        Args:
            payload: The test request details
        """
        # TODO: Implement sandboxed test execution
        await self.send(
            recipient="tui",
            action="status_update",
            payload={
                "station": self.name,
                "status": "testing",
                "message": "Running tests...",
            },
        )

    async def _refactor(self, payload: dict) -> None:
        """Refactor existing code.

        Args:
            payload: The refactor request details
        """
        # TODO: Implement code refactoring
        await self.send(
            recipient="tui",
            action="status_update",
            payload={
                "station": self.name,
                "status": "refactoring",
                "message": "Refactoring code...",
            },
        )
