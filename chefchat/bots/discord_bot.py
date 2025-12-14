from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import discord
from discord.ext import commands

from chefchat.bots.manager import BotManager
from chefchat.bots.session import BotSession
from chefchat.core.config import VibeConfig
from chefchat.core.utils import ApprovalResponse

logger = logging.getLogger(__name__)

# Discord has a 2000 character limit, but we truncate at 1900 to leave room for suffix
DISCORD_MESSAGE_TRUNCATE_LIMIT = 1900


class ApprovalView(discord.ui.View):
    def __init__(self, callback: Any, tool_call_id: str) -> None:
        super().__init__(timeout=None)
        self.callback_func = callback
        self.tool_call_id = tool_call_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="✅ Approved", view=None)
        await self.callback_func(self.tool_call_id, ApprovalResponse.YES, None)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="🚫 Denied", view=None)
        await self.callback_func(
            self.tool_call_id, ApprovalResponse.NO, "User denied via Discord"
        )

    @discord.ui.button(label="Always", style=discord.ButtonStyle.blurple)
    async def always(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="⚡ Always Approved", view=None)
        await self.callback_func(self.tool_call_id, ApprovalResponse.ALWAYS, None)


class DiscordBotService:
    def __init__(self, config: VibeConfig) -> None:
        self.config = config
        self.bot_manager = BotManager(config)
        self.sessions: dict[int, BotSession] = {}

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="/", intents=intents)

    def _get_session(self, channel_id: int, user_id_str: str) -> BotSession | None:
        if channel_id not in self.sessions:
            allowed = self.bot_manager.get_allowed_users("discord")
            if user_id_str not in allowed:
                return None

            self.sessions[channel_id] = BotSession(
                self.config,
                send_message=lambda text: self._send_message(channel_id, text),
                update_message=self._update_message,
                request_approval=lambda t, a, i: self._request_approval(
                    channel_id, t, a, i
                ),
                user_id=user_id_str,
            )
        return self.sessions[channel_id]

    async def _send_message(self, channel_id: int, text: str) -> Any:
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return None
        return await channel.send(text)

    async def _update_message(self, msg_handle: discord.Message, text: str) -> None:
        try:
            if not text.strip():
                return
            if len(text) > DISCORD_MESSAGE_TRUNCATE_LIMIT:
                text = text[:DISCORD_MESSAGE_TRUNCATE_LIMIT] + "\n... (truncated)"
            await msg_handle.edit(content=text)
        except Exception as e:
            logger.warning("Failed to update message: %s", e)

    async def _request_approval(
        self, channel_id: int, tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> Any:
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        view = ApprovalView(self._handle_approval_callback, tool_call_id)
        await channel.send(
            f"✋ **Approval Required**\nTool: `{tool_name}`\nArgs: `{args!s}`",
            view=view,
        )

    async def _handle_approval_callback(
        self, tool_call_id: str, response: str, message: str | None
    ) -> None:
        # We need to find the session that owns this tool_call_id
        # Ideally we iterate or store a reverse map.
        # Since we have the channel_id context in the callback usually...
        # But here the callback is from the View, which we created in _request_approval.
        # So we can just find the session for the channel where the view was sent.
        # But wait, we don't know the channel in the callback easily unless we pass it.
        # However, BotSession.resolve_approval handles the resolution.
        # We can just broadcast to all sessions or improve mapping.
        # For now, let's iterate.
        for session in self.sessions.values():
            session.resolve_approval(tool_call_id, response, message)

    async def run(self) -> None:
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            logger.error("No DISCORD_BOT_TOKEN found")
            return

        @self.bot.event
        async def on_ready() -> None:
            logger.info("Discord Bot connected as %s", self.bot.user)

        @self.bot.event
        async def on_message(message: discord.Message) -> None:
            if message.author == self.bot.user:
                return

            user_id = str(message.author.id)
            channel_id = message.channel.id

            # Simple allowlist check
            allowed = self.bot_manager.get_allowed_users("discord")
            if user_id not in allowed:
                await message.reply(
                    f"🔒 Access Denied. Your User ID is: `{user_id}`\n"
                    f"Run `/discord allow {user_id}` in your terminal to enable."
                )
                return

            if message.content.startswith("/clear"):
                session = self.sessions.get(channel_id)
                if session:
                    await session.clear_history()
                    await message.reply("🧹 History cleared.")
                return

            session = self._get_session(channel_id, user_id)
            if session:
                asyncio.create_task(session.handle_user_message(message.content))

        try:
            await self.bot.start(token)
        except asyncio.CancelledError:
            await self.bot.close()


async def run_discord_bot(config: VibeConfig) -> None:
    service = DiscordBotService(config)
    await service.run()
