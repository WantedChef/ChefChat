"""ChefChat Git Chef Station - The Version Control Specialist.

The Git Chef handles:
- Git configuration
- Proactive git status checks
- Executing git commands safely
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from chefchat.core.tools.executor import SecureCommandExecutor
from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus

if TYPE_CHECKING:
    from chefchat.kitchen.manager import KitchenManager


class GitChef(BaseStation):
    """The git operations station.

    Handles:
    - GIT_COMMAND actions
    - Proactive suggestions based on work status
    """

    def __init__(self, bus: KitchenBus, manager: KitchenManager, project_root: str | Path | None = None) -> None:
        """Initialize the Git Chef station.

        Args:
            bus: The kitchen bus to connect to
            manager: The kitchen manager
            project_root: Root directory for git operations
        """
        super().__init__("git_chef", bus)
        self.manager = manager
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.executor = SecureCommandExecutor(self.project_root)

    async def handle(self, message: ChefMessage) -> None:
        """Process incoming messages."""
        match message.action:
            case "GIT_COMMAND":
                await self._execute_git_command(message)
            case "NEW_TICKET":
                await self._check_new_ticket(message)

    async def _execute_git_command(self, message: ChefMessage) -> None:
        """Execute a git command."""
        command = message.payload.get("command")
        ticket_id = message.payload.get("ticket_id")

        if not command:
            return

        # Ensure it starts with git
        if not command.startswith("git"):
            command = f"git {command}"

        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "cooking",
                "progress": 10,
                "message": f"🔧 Running: {command}",
            },
        )

        # Get token from env
        token = os.environ.get("GITHUB_TOKEN")
        env = {}
        if token:
            env["GITHUB_TOKEN"] = token

        try:
            stdout, stderr, returncode = await self.executor.execute(command, env=env)

            status = "complete" if returncode == 0 else "error"
            icon = "✅" if returncode == 0 else "❌"

            output = stdout if stdout else stderr
            output = output.strip()

            await self.send(
                recipient="tui",
                action="STATUS_UPDATE",
                payload={
                    "station": self.name,
                    "status": status,
                    "progress": 100,
                    "message": f"{icon} Git command finished",
                },
            )

            await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={
                    "type": "assistant" if returncode == 0 else "system",
                    "content": f"**Git Output**:\n```\n{output}\n```",
                },
            )

            if ticket_id:
                await self.send(
                    recipient="sous_chef",
                    action="TASK_COMPLETE" if returncode == 0 else "TASK_ERROR",
                    payload={
                        "ticket_id": ticket_id,
                        "result": output,
                        "error": stderr if returncode != 0 else None
                    }
                )

        except Exception as e:
            await self._send_error(str(e))
            if ticket_id:
                 await self.send(
                    recipient="sous_chef",
                    action="TASK_ERROR",
                    payload={
                        "ticket_id": ticket_id,
                        "error": str(e)
                    }
                )

    async def _check_new_ticket(self, message: ChefMessage) -> None:
        """Proactively check if a new ticket needs git assistance."""
        request = message.payload.get("request", "").lower()
        git_keywords = ["git", "commit", "push", "pull", "clone", "merge", "branch", "checkout"]

        if any(keyword in request for keyword in git_keywords):
             await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={
                    "type": "assistant",
                    "content": "👋 **Git Chef**: I noticed you mentioned git operations. I can handle that! Use `/chef git <command>` or let the Sous Chef delegate to me.",
                },
            )

    async def _send_error(self, message: str) -> None:
        await self.send(
            recipient="tui",
            action="LOG_MESSAGE",
            payload={"type": "system", "content": f"❌ **Git Chef Error**: {message}"},
        )
