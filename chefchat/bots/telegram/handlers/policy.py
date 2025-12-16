from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class PolicyHandlers:
    """Manage bot-level tool policy modes (dev/chat/combo)."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc

    def get_current(self, chat_id: int) -> str:
        return self.svc.tool_policies.get(chat_id, "dev")

    def set_policy(self, chat_id: int, policy: str) -> str:
        policy = policy.lower()
        if policy not in {"dev", "chat", "combo"}:
            return "❌ Onbekende modus. Kies uit dev, chat, combo."

        self.svc.tool_policies[chat_id] = policy
        session = self.svc.sessions.get(chat_id)
        if session:
            session.set_tool_policy(policy)

        labels = {
            "dev": "Dev (alles met goedkeuring)",
            "chat": "Chat (geen tools)",
            "combo": "Combi (lezen auto, writes met approval)",
        }
        return f"🔧 Bot-modus: {labels.get(policy, policy)}"

    async def botmode_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat_id = update.effective_chat.id
        if context and getattr(context, "args", None):
            message = self.set_policy(chat_id, context.args[0])
            await self.svc._send_message(chat_id, message)
            return

        current = self.get_current(chat_id)
        buttons = [
            [
                InlineKeyboardButton("Dev", callback_data="botmode:dev"),
                InlineKeyboardButton("Chat", callback_data="botmode:chat"),
                InlineKeyboardButton("Combi", callback_data="botmode:combo"),
            ]
        ]
        await self.svc._send_message(
            chat_id,
            "🤖 Bot-modi (toolgedrag):\n"
            f"- dev (huidig: {current}): tools met approval\n"
            "- chat: LLM-only, tools uit\n"
            "- combo: lees-tools auto, writes via approval\n"
            "Gebruik `/botmode <dev|chat|combo>` of kies hieronder.",
        )
        try:
            if self.svc.application:
                await self.svc.application.bot.send_message(
                    chat_id=chat_id,
                    text="Kies modus:",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
        except Exception:
            pass

    async def handle_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, policy: str
    ) -> None:
        chat_id = update.effective_chat.id
        msg = self.set_policy(chat_id, policy)
        await self.svc._send_message(chat_id, msg)

    async def handle_callback(self, update: Update, data: str) -> None:
        chat_id = update.effective_chat.id
        _, policy = data.split(":", 1)
        msg = self.set_policy(chat_id, policy)
        try:
            await update.callback_query.edit_message_text(msg)
        except Exception:
            await self.svc._send_message(chat_id, msg)
