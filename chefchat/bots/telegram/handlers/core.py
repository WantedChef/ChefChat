from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update, constants

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class CoreHandlers:
    """Core /start, /help, and status flows."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc

    async def start(self, update: Update, context: object) -> None:
        user = update.effective_user
        if not user:
            return

        user_id = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")

        if user_id in allowed:
            await update.message.reply_text(
                f"Welcome back, Chef {user.first_name}! 👨‍🍳\nSend me a message to start cooking."
            )
            await self.svc.models.send_model_status_card(update.effective_chat.id)
        else:
            await update.message.reply_text(
                f"🔒 Access Denied.\nYour User ID is: `{user_id}`\n\n"
                f"To enable access, run this in your terminal:\n"
                f"`/telegram allow {user_id}`",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

    async def help_command(self, update: Update, context: object) -> None:
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

    async def status_command(self, update: Update, context: object) -> None:
        user = update.effective_user
        if not user:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
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
        cli_status = self.svc.cli_manager.get_session_status(update.effective_chat.id)
        bot_policy = self.svc.policy.get_current(update.effective_chat.id)

        status_text = (
            f"🤖 **ChefChat Bot Status**\n\n"
            f"⏱️ System uptime: {uptime}\n"
            f"📁 Working dir: `{cwd}`\n"
            f"👥 Active sessions: {session_count}\n"
            f"🔧 Bot-modus: {bot_policy}\n"
            f"🤖 CLI: {cli_status}\n"
            f"🔧 Commands: /help for list"
        )
        await update.message.reply_text(
            status_text, parse_mode=constants.ParseMode.MARKDOWN
        )
