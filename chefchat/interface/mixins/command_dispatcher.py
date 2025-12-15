"""Command Dispatcher Mixin for ChefChat TUI.

Handles routing of user input to appropriate command handlers.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol

logger = logging.getLogger(__name__)


class CommandDispatcherMixin:
    """Mixin providing command dispatch logic for ChefChatApp.

    Requires the following attributes on self:
    - _command_registry: CommandRegistry
    """

    # Type hint for self when used as mixin
    self: ChefAppProtocol

    async def _handle_command(self, command: str) -> None:
        """Handle slash commands using the command registry."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

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

    async def _handle_bash_command(self, command: str) -> None:
        """Execute bash command from TUI.

        Handles `!` prefixed commands by executing them via SecureCommandExecutor.
        Output is displayed in the ticket rail.
        """
        from chefchat.core.tools.executor import SecureCommandExecutor
        from chefchat.interface.widgets.kitchen_ui import WhiskLoader
        from chefchat.interface.widgets.ticket_rail import TicketRail

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
