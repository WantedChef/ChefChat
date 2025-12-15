from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from chefchat.bots.discord.bot import DiscordBotService

DISCORD_MSG_LIMIT = 1900

logger = logging.getLogger(__name__)


class TerminalHandlers:
    def __init__(self, svc: DiscordBotService) -> None:
        self.svc = svc

    async def handle_message(self, message: discord.Message) -> bool:
        content = message.content.strip()

        if content.startswith("/term"):
            await self._handle_term_command(message)
            return True

        return False

    async def _handle_term_command(self, message: discord.Message) -> None:
        # /term <cmd>
        # /termclose

        args = message.content.split()
        cmd = args[0].lower()
        rest = " ".join(args[1:])

        chat_id = message.channel.id

        if cmd == "/termclose":
            result = self.svc.terminal_manager.close_session(chat_id)
            await message.channel.send(result)
            return

        # If just /term with no args, show status/help
        if not rest:
            status = self.svc.terminal_manager.get_session_status(chat_id)
            if "No active" in status:
                await message.channel.send(
                    "Usage: `/term <command>` to start or run command.\n`/termclose` to exit."
                )
            else:
                await message.channel.send(status)
            return

        # Check if session exists
        if not self.svc.terminal_manager.has_active_session(chat_id):
            # Create new session
            ok, msg = self.svc.terminal_manager.create_session(chat_id, rest)
            await message.channel.send(msg)
            # Fetch immediate output
            if ok:
                # Give it a splitsplit second? usually create_session starts it
                pass
        else:
            # Send input to existing session
            output = self.svc.terminal_manager.send_to_session(chat_id, rest)
            # Discord limit check
            if len(output) > DISCORD_MSG_LIMIT:
                output = output[:DISCORD_MSG_LIMIT] + "\n...(truncated)"
            await message.channel.send(output)
