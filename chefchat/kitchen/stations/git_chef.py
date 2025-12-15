"""ChefChat Git Chef Station - The Version Control Specialist.

The Git Chef handles:
- Git configuration
- Proactive git status checks
- Executing git commands safely
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from chefchat.core.tools.executor import SecureCommandExecutor
from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus

# Import security utilities
try:
    from chefchat.kitchen.security import SecurityRedactor, enable_automatic_redaction
    enable_automatic_redaction()
except ImportError:
    SecurityRedactor = None

if TYPE_CHECKING:
    from chefchat.kitchen.manager import KitchenManager


class GitCommandValidator:
    """Validates and sanitizes git commands to prevent injection."""

    # Allowed git subcommands (whitelist approach)
    ALLOWED_SUBCOMMANDS = {
        "add",
        "branch",
        "checkout",
        "clone",
        "commit",
        "config",
        "diff",
        "fetch",
        "init",
        "log",
        "merge",
        "pull",
        "push",
        "rebase",
        "remote",
        "reset",
        "restore",
        "rm",
        "show",
        "status",
        "stash",
        "switch",
        "tag",
    }

    # Dangerous flags that should never be allowed
    FORBIDDEN_FLAGS = {
        "--exec-path",
        "--html-path",
        "--man-path",
        "--info-path",
        "--work-tree",
        "--git-dir",
        "--namespace",
        "--bare",
    }

    @classmethod
    def parse_and_validate(cls, command_str: str) -> list[str] | None:
        """Parse and validate a git command string.

        Args:
            command_str: The raw command string from user input

        Returns:
            List of validated command arguments, or None if invalid
        """
        try:
            # Use shlex to properly parse the command (handles quotes, escapes)
            if command_str.startswith("git "):
                args = shlex.split(command_str)
            else:
                # Prepend 'git' and parse
                args = shlex.split(f"git {command_str}")

            if len(args) < 2:
                return None  # Need at least 'git' + subcommand

            # Validate subcommand
            subcommand = args[1]
            if subcommand not in cls.ALLOWED_SUBCOMMANDS:
                return None

            # Check for dangerous flags
            for arg in args[2:]:
                if arg in cls.FORBIDDEN_FLAGS:
                    return None

            return args

        except (ValueError, shlex.SplitError):
            # Parsing failed - likely malformed input
            return None


class GitChef(BaseStation):
    """The git operations station.

    Handles:
    - GIT_COMMAND actions
    - Proactive suggestions based on work status
    """

    def __init__(
        self,
        bus: KitchenBus,
        manager: KitchenManager,
        project_root: str | Path | None = None,
    ) -> None:
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
        """Execute a git command safely."""
        command = message.payload.get("command")
        ticket_id = message.payload.get("ticket_id")

        if not command:
            await self._send_error("No command provided")
            return

        # Validate and parse the command
        validated_args = GitCommandValidator.parse_and_validate(command)
        if validated_args is None:
            await self._send_error(f"Invalid or unsafe git command: {command}")
            return

        # Reconstruct safe command string for display
        safe_command = " ".join(shlex.quote(arg) for arg in validated_args)

        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "cooking",
                "progress": 10,
                "message": f"🔧 Running: {safe_command}",
            },
        )

        # Get token from env (don't log it)
        token = os.environ.get("GITHUB_TOKEN")
        env = {}
        if token:
            env["GITHUB_TOKEN"] = token

try:
            # Execute using safe command string (reconstructed from validated args)
            stdout, stderr, returncode = await self.executor.execute(safe_command, env=env)

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

            # Redact any sensitive info from output
        if SecurityRedactor:
            safe_output = SecurityRedactor.redact_sensitive_data(output)
        else:
            safe_output = output

        await self.send(
            recipient="tui",
            action="LOG_MESSAGE",
            payload={
                "type": "assistant" if returncode == 0 else "system",
                "content": f"**Git Output**:\n```\n{safe_output}\n```",
            },
        )

            if ticket_id:
                await self.send(
                    recipient="sous_chef",
                    action="TASK_COMPLETE" if returncode == 0 else "TASK_ERROR",
                    payload={
                        "ticket_id": ticket_id,
                        "result": output,
                        "error": stderr if returncode != 0 else None,
                    },
                )

        except Exception as e:
            await self._send_error(str(e))
            if ticket_id:
                await self.send(
                    recipient="sous_chef",
                    action="TASK_ERROR",
                    payload={"ticket_id": ticket_id, "error": str(e)},
                )

    async def _check_new_ticket(self, message: ChefMessage) -> None:
        """Proactively check if a new ticket needs git assistance."""
        request = message.payload.get("request", "").lower()
        git_keywords = [
            "git",
            "commit",
            "push",
            "pull",
            "clone",
            "merge",
            "branch",
            "checkout",
        ]

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
        # Redact sensitive info from error messages
        if SecurityRedactor:
            safe_message = SecurityRedactor.redact_sensitive_data(message)
        else:
            safe_message = message
            
        await self.send(
            recipient="tui",
            action="LOG_MESSAGE",
            payload={"type": "system", "content": f"❌ **Git Chef Error**: {safe_message}"},
        )
