from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from telegram import Update, constants
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class TerminalHandlers:
    """Terminal session commands."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc
        self.max_upload_bytes = 200 * 1024

    async def term_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id

        if not context.args:
            await update.message.reply_text(
                "Usage: `/term <command>`\n\n"
                "Examples:\n"
                "• `/term bash` - Start bash shell\n"
                "• `/term python3` - Start Python REPL\n"
                "• `/term vim test.py` - Open vim\n\n"
                "Type `/termclose` to exit terminal.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            return

        command = " ".join(context.args)
        success, message = self.svc.terminal_manager.create_session(chat_id, command)

        await update.message.reply_text(
            message, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def termstatus_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id
        status = self.svc.terminal_manager.get_session_status(chat_id)

        await update.message.reply_text(status, parse_mode=constants.ParseMode.MARKDOWN)

    async def termclose_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id
        message = self.svc.terminal_manager.close_session(chat_id)

        await update.message.reply_text(message)

    async def term_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, command: str
    ) -> None:
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id
        success, message = self.svc.terminal_manager.create_session(chat_id, command)

        await update.message.reply_text(
            message, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def term_switch_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Switch terminal CWD by restarting shell in a new path."""
        if not context.args:
            await update.message.reply_text("Usage: `/termswitch <path>`")
            return
        target = Path(context.args[0]).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            await update.message.reply_text("❌ Pad bestaat niet of is geen map.")
            return
        chat_id = update.effective_chat.id
        session = self.svc.terminal_manager.sessions.get(chat_id)
        command = session.command if session else "bash"
        self.svc.terminal_manager.close_session(chat_id)
        _, msg = self.svc.terminal_manager.create_session(chat_id, command, cwd=target)
        await update.message.reply_text(msg, parse_mode=constants.ParseMode.MARKDOWN)

    async def term_upload_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send a small file from the terminal cwd back to the user."""
        if not context.args:
            await update.message.reply_text("Usage: `/termupload <filename>`")
            return
        chat_id = update.effective_chat.id
        session = self.svc.terminal_manager.sessions.get(chat_id)
        if not session:
            await update.message.reply_text("❌ Geen actieve terminal sessie.")
            return
        path = (session.cwd / context.args[0]).expanduser().resolve()
        try:
            if not path.is_file():
                await update.message.reply_text("❌ Bestand niet gevonden.")
                return
            if path.stat().st_size > self.max_upload_bytes:
                await update.message.reply_text("❌ Bestand te groot (max 200KB).")
                return
            if self.svc.application:
                with path.open("rb") as f:
                    await self.svc.application.bot.send_document(
                        chat_id=chat_id, document=f, filename=path.name
                    )
        except Exception as e:
            await update.message.reply_text(f"❌ Upload mislukt: {e}")
