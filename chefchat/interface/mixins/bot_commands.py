"""Bot Commands Mixin for ChefChat TUI.

Provides Telegram and Discord bot management commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol


class BotCommandsMixin:
    """Mixin providing bot management commands for ChefChatApp.

    Requires the following attributes on self:
    - _config: VibeConfig | None
    """

    # Type hint for self when used as mixin
    self: ChefAppProtocol

    # Bot manager is lazily initialized
    _bot_manager: Any = None

    async def _handle_telegram_command(self, arg: str = "") -> None:
        """Handle /telegram command in TUI."""
        await self._handle_bot_command("telegram", arg)

    async def _handle_discord_command(self, arg: str = "") -> None:
        """Handle /discord command in TUI."""
        await self._handle_bot_command("discord", arg)

    async def _handle_bot_command(self, bot_type: str, arg: str) -> None:
        """Unified handler for bot commands (telegram/discord)."""
        from chefchat.bots.manager import BotManager
        from chefchat.core.config import MissingAPIKeyError, VibeConfig
        from chefchat.interface.widgets.ticket_rail import TicketRail

        action = arg.lower().strip() if arg else "help"

        # Get or create bot manager
        if not hasattr(self, "_bot_manager") or self._bot_manager is None:
            try:
                self._bot_manager = BotManager(self._config or VibeConfig.load())
            except MissingAPIKeyError as exc:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    f"❌ Missing API key: {exc}. Please set the required env var."
                )
                return

        # Dispatch to action handlers
        handlers = {
            "help": self._bot_cmd_help,
            "setup": self._bot_cmd_setup,
            "start": self._bot_cmd_start,
            "stop": self._bot_cmd_stop,
            "status": self._bot_cmd_status,
        }

        handler = handlers.get(action)
        if handler:
            await handler(bot_type)
        else:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❓ Unknown: `{action}`. Try `/{bot_type}`"
            )

    async def _bot_cmd_help(self, bot_type: str) -> None:
        """Show bot help."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        base_help = [
            f"## 🤖 {bot_type.title()} Bot Commands",
            "",
            f"• `/{bot_type} setup` — Configure token and user ID",
            f"• `/{bot_type} start` — Start the bot",
            f"• `/{bot_type} stop` — Stop the bot",
            f"• `/{bot_type} status` — Check status",
        ]

        if bot_type == "telegram":
            base_help.extend(
                [
                    "",
                    "### In-chat Telegram commands",
                    "• `/start`, `/help`, `/status`, `/stop`, `/clear`",
                    "• `/model`, `/modellist`, `/modelselect`, `/modelrefresh`",
                    "• `/botmode <dev|chat|combo>`; shortcuts: `devmode`, `chatmode`, `combimode`",
                    "• `/mode`, `plan`, `normal`, `auto`, `yolo`, `architect`",
                    "• `/task <...>` (list/edit/do/done/delete/changelog)",
                    "• `/term...` (term, termstatus, termclose, termupload, termswitch, termbash, termpython3, termvim, termnode, termnpm)",
                    "• `/cli <provider>`, `/clirun`, `/cliproviders`, `/clistatus`, `/cliclose`, `/clidiag`, `/clihistory`, `/clisetup`, `/cliretry`, `/clicancel`",
                    "• `/git <cmd>` (validated), `/chefchat ...` (systemd controls where enabled)",
                    "• Fun: `/chef`, `/wisdom`, `/roast`, `/fortune`, `/stats`, `/reload`",
                ]
            )

        help_text = "\n".join(base_help)
        self.query_one("#ticket-rail", TicketRail).add_system_message(help_text)

    async def _bot_cmd_setup(self, bot_type: str) -> None:
        """Handle bot setup command."""
        from chefchat.bots.ui import BotSetupScreen
        from chefchat.interface.widgets.ticket_rail import TicketRail

        ticket_rail = self.query_one("#ticket-rail", TicketRail)

        def on_complete(success: bool) -> None:
            if success:
                self.notify(f"{bot_type.title()} configured!", title="Setup")
                ticket_rail.add_system_message(f"✅ {bot_type.title()} setup complete!")

        await self.push_screen(BotSetupScreen(bot_type), on_complete)

    async def _bot_cmd_start(self, bot_type: str) -> None:
        """Start the bot."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        if self._bot_manager.is_running(bot_type):
            ticket_rail.add_system_message(f"⚠️ {bot_type.title()} bot already running.")
            return
        try:
            await self._bot_manager.start_bot(bot_type)
            ticket_rail.add_system_message(f"🚀 {bot_type.title()} bot started!")
        except Exception as e:
            ticket_rail.add_system_message(f"❌ Failed: {e}")

    async def _bot_cmd_stop(self, bot_type: str) -> None:
        """Stop the bot."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        if not self._bot_manager.is_running(bot_type):
            ticket_rail.add_system_message(f"⚠️ {bot_type.title()} bot not running.")
            return
        await self._bot_manager.stop_bot(bot_type)
        ticket_rail.add_system_message(f"🛑 {bot_type.title()} bot stopped.")

    async def _bot_cmd_status(self, bot_type: str) -> None:
        """Show bot status."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        running = (
            "🟢 Running" if self._bot_manager.is_running(bot_type) else "🔴 Stopped"
        )
        allowed = ", ".join(self._bot_manager.get_allowed_users(bot_type)) or "None"
        last_error = self._bot_manager.get_last_error(bot_type)
        error_line = (
            f"\n**Last error:** {last_error}"
            if (not self._bot_manager.is_running(bot_type) and last_error)
            else ""
        )
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"**{bot_type.title()}:** {running}\n**Users:** {allowed}{error_line}"
        )
