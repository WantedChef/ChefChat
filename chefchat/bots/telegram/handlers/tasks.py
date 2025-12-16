from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class TaskHandlers:
    """Task command handling for Telegram."""

    # Constants for argument count validation
    MIN_EDIT_ARGS = 3
    MIN_ACTION_ARGS = 2

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc

    async def task_command(  # noqa: PLR0911
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        message = update.message
        if not chat or not message:
            return
        chat_id = chat.id
        raw_text = (message.text or "").strip()
        tokens = raw_text.split(maxsplit=1)
        tail = tokens[1] if len(tokens) > 1 else ""

        if not tail:
            await self.svc._send_message(
                chat_id,
                "Gebruik:\n"
                "• `/task <omschrijving>` nieuwe taak\n"
                "• `/task list`\n"
                "• `/task edit <id> <tekst>`\n"
                "• `/task do|run <id>`\n"
                "• `/task done <id>`\n"
                "• `/task delete <id>`\n"
                "• `/task changelog`",
            )
            return

        parts = tail.split()
        action = parts[0].lower()

        if action in {"list", "ls"}:
            await self.svc._send_message(
                chat_id, self.svc.task_manager.list_text(chat_id)
            )
            return

        if action == "changelog":
            await self.svc._send_message(
                chat_id, self.svc.task_manager.changelog_text(chat_id)
            )
            return

        if action == "edit" and len(parts) >= self.MIN_EDIT_ARGS:
            try:
                task_id = int(parts[1])
            except ValueError:
                await self.svc._send_message(chat_id, "❌ Ongeldig id.")
                return
            new_text = tail.split(maxsplit=2)[2]
            task = self.svc.task_manager.edit(chat_id, task_id, new_text)
            await self.svc._send_message(
                chat_id,
                f"✏️ Bijgewerkt #{task_id}: {task.text}"
                if task
                else "❌ Niet gevonden.",
            )
            return

        if action in {"do", "run"} and len(parts) >= self.MIN_ACTION_ARGS:
            try:
                task_id = int(parts[1])
            except ValueError:
                await self.svc._send_message(chat_id, "❌ Ongeldig id.")
                return
            task = self.svc.task_manager.set_status(chat_id, task_id, "doing")
            await self.svc._send_message(
                chat_id,
                f"🏁 Gestart #{task_id}: {task.text}" if task else "❌ Niet gevonden.",
            )
            return

        if action in {"done", "close"} and len(parts) >= self.MIN_ACTION_ARGS:
            try:
                task_id = int(parts[1])
            except ValueError:
                await self.svc._send_message(chat_id, "❌ Ongeldig id.")
                return
            task = self.svc.task_manager.set_status(chat_id, task_id, "done")
            await self.svc._send_message(
                chat_id,
                f"✅ Klaar #{task_id}: {task.text}" if task else "❌ Niet gevonden.",
            )
            return

        if action in {"delete", "del"} and len(parts) >= self.MIN_ACTION_ARGS:
            try:
                task_id = int(parts[1])
            except ValueError:
                await self.svc._send_message(chat_id, "❌ Ongeldig id.")
                return
            task = self.svc.task_manager.delete(chat_id, task_id)
            await self.svc._send_message(
                chat_id,
                f"🗑️ Verwijderd #{task_id}: {task.text}"
                if task
                else "❌ Niet gevonden.",
            )
            return

        task = self.svc.task_manager.add(chat_id, tail)
        await self.svc._send_message(
            chat_id, f"🆕 Taak #{task.task_id} aangemaakt: {task.text}"
        )
