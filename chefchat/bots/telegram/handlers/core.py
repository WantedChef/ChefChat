from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update, constants
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class CoreHandlers:
    """Core /start, /help, and status flows."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        message = update.message
        chat = update.effective_chat
        if not user or not message or not chat:
            return

        user_id = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")

        if user_id in allowed:
            await message.reply_text(
                f"Welcome back, Chef {user.first_name}! 👨‍🍳\nSend me a message to start cooking."
            )
            await self.svc.models.send_model_status_card(chat.id)
        else:
            await message.reply_text(
                f"🔒 Access Denied.\nYour User ID is: `{user_id}`\n\n"
                f"To enable access, run this in your terminal:\n"
                f"`/telegram allow {user_id}`",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return
        help_text = (
            "🤖 **ChefChat Bot Commands**\n\n"
            "💡 *Tip: Commands work with or without `/`*\n"
            "_(Type `help` or `/help`)_\n\n"
            "**Basic:**\n"
            "• start - Start the bot\n"
            "• stop - Stop current session\n"
            "• clear - Clear conversation history\n"
            "• help - Show this help\n\n"
            "**Info:**\n"
            "• status - Bot status & uptime\n"
            "• api - API key status\n"
            "• stats - Session statistics\n"
            "• files - List project files\n"
            "• pwd - Working directory\n\n"
            "**Models:**\n"
            "• model - Show current model\n"
            "• modellist - List all models\n"
            "• modelselect - Switch model\n"
            "• modelrefresh - Reload config models\n\n"
            "**Bot-modi (tools):**\n"
            "• botmode <dev|chat|combo>\n"
            "• devmode | chatmode | combimode\n\n"
            "**Modes:** 🎯\n"
            "• mode - Show/switch modes\n"
            "• plan - 📋 PLAN mode\n"
            "• normal - ✋ NORMAL mode\n"
            "• auto - ⚡ AUTO mode\n"
            "• yolo - 🚀 YOLO mode\n"
            "• architect - 🏛️ ARCHITECT mode\n\n"
            "**Fun:** 🎉\n"
            "• chef - Kitchen status report\n"
            "• wisdom - Culinary wisdom\n"
            "• roast - Gordon Ramsay roast\n"
            "• fortune - Developer fortune\n\n"
            "**Terminal:** 💻\n"
            "• termbash - Start bash shell\n"
            "• termpython3 - Python REPL\n"
            "• termvim - Vim editor\n"
            "• termstatus - Session status\n"
            "• termclose - Close session\n\n"
            "• termswitch <path> - Restart shell in path\n"
            "• termupload <file> - Send small file (<=200KB)\n\n"
            "**AI CLI Providers:** 🤖\n"
            "• gemini - ✨ Google Gemini CLI\n"
            "• codex - 🧠 OpenAI Codex CLI\n"
            "• opencode - ⚡ OpenCode CLI\n"
            "• cli <name> - Start CLI session\n"
            "• clirun [p] <prompt> - One-off run (optional provider)\n"
            "• clistatus - CLI session status\n"
            "• cliclose - Close CLI session\n"
            "• clihistory - View recent CLI runs\n"
            "• clidiag - CLI diagnostics\n"
            "• clisetup - Install/API key help\n"
            "• cliretry - Retry last prompt\n"
            "• clicancel - Cancel running CLI call\n\n"
            "**Tasks:** ✅\n"
            "• task <omschrijving> - Nieuwe taak\n"
            "• task list | edit <id> | do <id> | done <id> | delete <id>\n"
            "• task changelog - Laatste wijzigingen\n\n"
            "**Context:** 🧠\n"
            "• context status | clear\n\n"
            "**Tools:** 🛠️\n"
            "• git - Run git commands (status, log, etc)\n\n"
            "**Advanced:**\n"
            "• reload - Reload configuration\n"
            "• chefchat - Systemd controls\n\n"
            "💬 *Just send a message to chat with the AI!*"
        )
        await update.message.reply_text(
            help_text, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        chat = update.effective_chat
        message = update.message
        if not user or not chat or not message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await message.reply_text("Access denied.")
            return

        import subprocess

        uptime = "Unknown"
        try:
            result = subprocess.run(
                ["uptime", "-p"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                uptime = result.stdout.strip()
        except Exception:
            pass

        cwd = str(self.svc.TELEGRAM_WORKDIR)
        session_count = len(self.svc.sessions)
        cli_status = self.svc.cli_manager.get_session_status(chat.id)
        bot_policy = self.svc.policy.get_current(chat.id)

        status_text = (
            f"🤖 **ChefChat Bot Status**\n\n"
            f"⏱️ System uptime: {uptime}\n"
            f"📁 Working dir: `{cwd}`\n"
            f"👥 Active sessions: {session_count}\n"
            f"🔧 Bot-modus: {bot_policy}\n"
            f"🤖 CLI: {cli_status}\n"
            f"🔧 Commands: /help for list"
        )
        await message.reply_text(
            status_text, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def api_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show provider API key status for Telegram users."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        providers = self.svc.model_service.list_provider_info()
        if not providers:
            await update.message.reply_text("No providers configured.")
            return

        lines = ["🔑 API keys:"]
        for p in providers:
            key_state = "✅" if p.has_api_key else "❌"
            env_hint = f" `{p.api_key_env_var}`" if p.api_key_env_var else ""
            model_count = f"{p.model_count} models" if p.model_count else "no models"
            base = f" · {p.api_base}" if p.api_base else ""
            lines.append(f"{key_state} {p.name}{env_hint} — {model_count}{base}")

        lines.append(
            "\nSet keys in `~/.chefchat/.env` (or env vars) then run `/reload`."
        )
        await update.message.reply_text(
            "\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN
        )

    async def stop_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Stop the current agent session."""
        user = update.effective_user
        if not user or not update.effective_chat or not update.message:
            return

        chat_id = update.effective_chat.id
        session = self.svc.sessions.get(chat_id)
        if session:
            self.svc._forget_session(chat_id)
            await update.message.reply_text("🛑 Session stopped and cleared.")
        else:
            await update.message.reply_text("No active session to stop.")

    async def files_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """List project files in current directory."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        cwd = self.svc.TELEGRAM_WORKDIR
        files = []
        try:
            for item in sorted(cwd.iterdir())[:30]:  # Limit to 30 items
                if item.name.startswith("."):
                    continue
                prefix = "📁" if item.is_dir() else "📄"
                files.append(f"{prefix} {item.name}")
        except Exception as e:
            await update.message.reply_text(f"Error listing files: {e}")
            return

        if files:
            file_list = "\n".join(files)
            await update.message.reply_text(
                f"📂 **Files in** `{cwd}`:\n\n```\n{file_list}\n```",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("No files found.")

    async def pwd_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show current working directory."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        await update.message.reply_text(
            f"📁 Current directory:\n`{self.svc.TELEGRAM_WORKDIR}`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
