from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from chefchat.bots.manager import BotManager
from chefchat.bots.session import BotSession
from chefchat.core.config import VibeConfig
from chefchat.core.utils import ApprovalResponse

logger = logging.getLogger(__name__)

# Telegram limit is 4096, use 4000 to leave room for truncation suffix
TELEGRAM_MESSAGE_TRUNCATE_LIMIT = 4000


class TelegramBotService:
    def __init__(self, config: VibeConfig) -> None:
        self.config = config
        self.bot_manager = BotManager(config)
        self.sessions: dict[int, BotSession] = {}

        # Map short ID to full tool_call_id for callbacks
        self.approval_map: dict[str, str] = {}

    def _get_session(self, chat_id: int, user_id_str: str) -> BotSession | None:
        if chat_id not in self.sessions:
            # Check allowlist
            allowed = self.bot_manager.get_allowed_users("telegram")
            if user_id_str not in allowed:
                return None

            self.sessions[chat_id] = BotSession(
                self.config,
                send_message=lambda text: self._send_message(chat_id, text),
                update_message=self._update_message,
                request_approval=lambda t, a, i: self._request_approval(
                    chat_id, t, a, i
                ),
                user_id=user_id_str,
            )
        return self.sessions[chat_id]

    async def _send_message(self, chat_id: int, text: str) -> Any:
        # We need the application context or bot instance.
        # Since this is a callback, we'll store the application reference later
        # or pass it via closure.
        # But wait, send_message is called from BotSession which is async.
        # We can use self.application.bot.send_message
        return await self.application.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def _update_message(self, msg_handle: Any, text: str) -> None:
        # msg_handle is the Message object returned by send_message
        try:
            if not text.strip():
                return

            # Telegram limit 4096
            if len(text) > TELEGRAM_MESSAGE_TRUNCATE_LIMIT:
                text = text[:TELEGRAM_MESSAGE_TRUNCATE_LIMIT] + "\n... (truncated)"

            await msg_handle.edit_text(
                text=text, parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            # Ignore "Message is not modified" errors
            if "Message is not modified" not in str(e):
                logger.warning(f"Failed to update message: {e}")

    async def _request_approval(
        self, chat_id: int, tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> Any:
        short_id = tool_call_id[:8]
        self.approval_map[short_id] = tool_call_id

        keyboard = [
            [
                InlineKeyboardButton("Approve", callback_data=f"app:{short_id}"),
                InlineKeyboardButton("Deny", callback_data=f"deny:{short_id}"),
            ],
            [InlineKeyboardButton("Always", callback_data=f"always:{short_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.application.bot.send_message(
            chat_id=chat_id,
            text=f"✋ **Approval Required**\nTool: `{tool_name}`\nArgs: `{args!s}`",
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return

        user_id = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")

        if user_id in allowed:
            await update.message.reply_text(
                f"Welcome back, Chef {user.first_name}! 👨‍🍳\nSend me a message to start cooking."
            )
        else:
            await update.message.reply_text(
                f"🔒 Access Denied.\nYour User ID is: `{user_id}`\n\n"
                f"To enable access, run this in your terminal:\n"
                f"`/telegram allow {user_id}`",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.message or not update.message.text:
            return

        session = self._get_session(update.effective_chat.id, str(user.id))
        if not session:
            await self.start(update, context)
            return

        # Run in background to not block handling
        asyncio.create_task(session.handle_user_message(update.message.text))

    async def handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()

        data = query.data
        if not data:
            return

        action, short_id = data.split(":")
        tool_call_id = self.approval_map.get(short_id)

        if not tool_call_id:
            await query.edit_message_text("❌ Session expired or unknown request.")
            return

        session = self.sessions.get(update.effective_chat.id)
        if not session:
            return

        response = ApprovalResponse.NO
        msg = None

        if action == "app":
            response = ApprovalResponse.YES
            await query.edit_message_text("✅ Approved")
        elif action == "deny":
            response = ApprovalResponse.NO
            msg = "User denied via Telegram"
            await query.edit_message_text("🚫 Denied")
        elif action == "always":
            response = ApprovalResponse.ALWAYS
            await query.edit_message_text("⚡ Always Approved")

        session.resolve_approval(tool_call_id, response, msg)

    async def clear_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user:
            return
        session = self._get_session(update.effective_chat.id, str(user.id))
        if session:
            await session.clear_history()
            await update.message.reply_text("🧹 History cleared.")

    async def run(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("No TELEGRAM_BOT_TOKEN found")
            return

        self.application = ApplicationBuilder().token(token).build()

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

        logger.info("Starting Telegram Bot polling...")
        # run_polling is blocking. We should use start/updater if we want to run in a task?
        # Application.run_polling() blocks.
        # But we are running this inside an asyncio.create_task in manager.py?
        # No, asyncio.create_task expects a coroutine. run_polling handles the loop itself if not careful.

        # Correct way for existing loop:
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        # Keep running until cancelled
        try:
            # Wait forever
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()


async def run_telegram_bot(config: VibeConfig) -> None:
    service = TelegramBotService(config)
    await service.run()
