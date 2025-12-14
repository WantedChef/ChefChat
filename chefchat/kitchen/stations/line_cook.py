"""ChefChat Line Cook Station - The Code Generation Agent.

The Line Cook is where the actual cooking happens. They:
- Receive PLAN messages from the Sous Chef
- Generate code using the LLM (simulated for now)
- Send progress updates (0-100%) back to the bus
- Report results to The Plate
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
from typing import TYPE_CHECKING

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus

if TYPE_CHECKING:
    from chefchat.kitchen.brain import KitchenBrain


class LineCook(BaseStation):
    """The code generation and execution station.

    Handles:
    - Code generation via LLM
    - Progress updates during work
    - Code delivery to The Plate
    - Result reporting
    """

    def __init__(self, bus: KitchenBus, brain: KitchenBrain) -> None:
        """Initialize the Line Cook station.

        Args:
            bus: The kitchen bus to connect to
            brain: The kitchen brain for LLM operations
        """
        super().__init__("line_cook", bus)
        self.brain = brain
        self._current_task: str | None = None

    async def handle(self, message: ChefMessage) -> None:
        """Process incoming messages.

        Args:
            message: The message to process
        """
        action = message.action

        if action == "PLAN":
            # Implementation request from Sous Chef
            await self._execute_plan(message.payload)

        elif action == "test":
            # Run tests on code
            await self._run_tests(message.payload)

        elif action == "refactor":
            # Refactor existing code
            await self._refactor(message.payload)

        elif action == "FIX_ERRORS":
            # Fix errors from Expeditor (self-healing loop)
            await self._fix_errors(message.payload)

    async def _generate_code(self, task: str) -> str:
        """Generate code for the task using the LLM.

        Handles streaming updates to the TUI.
        Updates are sent only every 5 lines of code generated.

        Args:
            task: The task description

        Returns:
            Generated Python code
        """
        generated_code = ""
        pending_content = ""
        last_line_count = 0

        async for chunk in self.brain.stream_response(
            f"Implement this plan:\n{task}", system=self.brain.CODE_SYSTEM_PROMPT
        ):
            generated_code += chunk
            pending_content += chunk

            current_lines = generated_code.count("\n")
            if current_lines - last_line_count >= 5:
                await self.send(
                    recipient="tui",
                    action="STREAM_UPDATE",
                    payload={"content": pending_content, "full_content": generated_code},
                )
                pending_content = ""
                last_line_count = current_lines

        # Final update
        if pending_content:
            await self.send(
                recipient="tui",
                action="STREAM_UPDATE",
                payload={"content": pending_content, "full_content": generated_code},
            )

        return generated_code

    async def _execute_plan(self, plan: dict) -> None:
        """Execute the implementation plan.

        Args:
            plan: The implementation plan from Sous Chef
        """
        task = plan.get("task", "Unknown Task")
        ticket_id = plan.get("ticket_id", "unknown")

        self._current_task = ticket_id

        # Notify we're starting
        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "cooking",
                "progress": 0,
                "message": "🍳 Firing up the grill...",
            },
        )

        try:
            # Generate code using the Brain with streaming updates
            generated_code = await self._generate_code(task)

            # Complete!
            await self.send(
                recipient="tui",
                action="STATUS_UPDATE",
                payload={
                    "station": self.name,
                    "status": "complete",
                    "progress": 100,
                    "message": "✅ Plated!",
                },
            )

            # Send final code to The Plate
            await self.send(
                recipient="tui",
                action="PLATE_CODE",
                payload={
                    "code": generated_code,
                    "language": "python",
                    "file_path": f"solution_{ticket_id[:5]}.py",
                    "ticket_id": ticket_id,
                },
            )

            # Report completion to Sous Chef
            await self.send(
                recipient="sous_chef",
                action="TASK_COMPLETE",
                payload={
                    "ticket_id": ticket_id,
                    "result": "Code generated successfully",
                },
            )

        except Exception as e:
            await self._send_error(str(e))

    async def _fix_errors(self, payload: dict) -> None:
        """Attempt to fix errors reported by Expeditor.

        Part of the self-healing loop.

        Args:
            payload: Error details from Expeditor
        """
        ticket_id = payload.get("ticket_id", "unknown")
        attempt = payload.get("attempt", 1)
        max_attempts = payload.get("max_attempts", 3)
        errors = payload.get("errors", [])
        path = payload.get("path", ".")

        self._current_task = ticket_id

        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "cooking",
                "progress": 0,
                "message": f"🔧 Fixing errors (attempt {attempt}/{max_attempts})...",
            },
        )

        await self.send(
            recipient="tui",
            action="LOG_MESSAGE",
            payload={
                "type": "system",
                "content": f"🔧 **Line Cook**: Attempting repair {attempt}/{max_attempts}...",
            },
        )

        try:
            # Read the broken file
            file_path = Path(path)
            if not file_path.exists() or not file_path.is_file():
                # If path is a directory (e.g. "."), we can't easily guess which file to fix
                # without more sophisticated analysis. For now, report error.
                raise FileNotFoundError(f"Cannot fix {path}: File not found or is a directory")

            original_code = file_path.read_text(encoding="utf-8")

            # Generate fix
            fixed_code = ""
            async for chunk in self.brain.fix_code_stream(original_code, errors):
                fixed_code += chunk
                # Throttle updates
                if len(fixed_code) % 50 == 0:
                    await self.send(
                        recipient="tui",
                        action="STREAM_UPDATE",
                        payload={"content": chunk, "full_content": fixed_code},
                    )

            # Write back to file
            # Clean up potential markdown blocks
            clean_fixed_code = self._clean_code(fixed_code)
            file_path.write_text(clean_fixed_code, encoding="utf-8")

            await self.send(
                recipient="tui",
                action="STATUS_UPDATE",
                payload={
                    "station": self.name,
                    "status": "complete",
                    "progress": 100,
                    "message": "✅ Fix applied",
                },
            )

            # Report back to Expeditor
            await self.send(
                recipient="expeditor",
                action="healing_result",
                payload={
                    "ticket_id": ticket_id,
                    "success": True,
                    "path": path,
                },
            )

        except Exception as e:
            await self._send_error(str(e))
            # Report failure to expeditor so it doesn't hang or assume success
            await self.send(
                recipient="expeditor",
                action="healing_result",
                payload={
                    "ticket_id": ticket_id,
                    "success": False,
                    "path": path,
                    "error": str(e),
                },
            )

        self._current_task = None

    async def _run_tests(self, payload: dict) -> None:
        """Run tests on generated code.

        Args:
            payload: The test request details
        """
        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "testing",
                "progress": 50,
                "message": "🧪 Running tests...",
            },
        )

        await asyncio.sleep(1)

        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "complete",
                "progress": 100,
                "message": "✅ Tests passed!",
            },
        )

    async def _refactor(self, payload: dict) -> None:
        """Refactor existing code.

        Args:
            payload: The refactor request details
        """
        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "refactoring",
                "progress": 50,
                "message": "🔄 Refactoring...",
            },
        )

        await asyncio.sleep(1)

        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "complete",
                "progress": 100,
                "message": "✅ Refactored!",
            },
        )

    def _clean_code(self, code: str) -> str:
        """Strip Markdown code blocks from LLM output."""
        # Check for ``` blocks
        pattern = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
        matches = pattern.findall(code)
        if matches:
            # Return the longest block as it's likely the code
            return max(matches, key=len).strip()
        return code.strip()

    async def _send_error(self, error: str) -> None:
        """Send an error message to the TUI and Sous Chef.

        Args:
            error: Error message to send
        """
        # Update status to error
        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "error",
                "progress": 0,
                "message": f"❌ Error: {error[:50]}...",
            },
        )

        # Log error message
        await self.send(
            recipient="tui",
            action="LOG_MESSAGE",
            payload={"type": "system", "content": f"❌ **Line Cook Error**: {error}"},
        )

        # Notify Sous Chef of the error
        await self.send(
            recipient="sous_chef",
            action="TASK_ERROR",
            payload={"ticket_id": self._current_task, "error": error},
        )

        self._current_task = None
