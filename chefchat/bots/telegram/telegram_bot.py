import asyncio
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from chefchat.core.config import VibeConfig
from chefchat.bots.session import BotSession
from chefchat.bots.manager import BotManager
from chefchat.core.utils import ApprovalResponse

logger = logging.getLogger(__name__)

class TelegramBotService:
    def __init__(self, config: VibeConfig):
        self.config = config
        self.bot_manager = BotManager(config)
        self.sessions: dict[int, BotSession] = {}

        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._last_activity: dict[int, float] = {}

        # Basic per-user rate limiting (burst + rolling window)
        self._rate_events: dict[str, deque[float]] = {}
        self._rate_limit_window_s = 30.0
        self._rate_limit_max_events = 6

        # Cleanup settings
        self._session_ttl_s = 60.0 * 60.0  # 1 hour
        self._approval_ttl_s = 10.0 * 60.0  # 10 minutes

        # Map short ID to full tool_call_id for callbacks
        self.approval_map: dict[str, str] = {}
        self._approval_created_at: dict[str, float] = {}

        # Optional systemd control (for switching project instances)
        self._enable_systemd_control = os.getenv(
            "CHEFCHAT_ENABLE_TELEGRAM_SYSTEMD_CONTROL", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._systemd_unit_base = os.getenv("CHEFCHAT_TELEGRAM_UNIT_BASE", "chefchat-telegram")
        self._allowed_projects = [
            p.strip()
            for p in os.getenv("CHEFCHAT_PROJECTS", "").split(",")
            if p.strip()
        ]

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
                request_approval=lambda t, a, i: self._request_approval(chat_id, t, a, i),
                user_id=user_id_str
            )
        return self.sessions[chat_id]

    def _touch_activity(self, chat_id: int) -> None:
        self._last_activity[chat_id] = time.monotonic()

    def _chat_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    def _rate_limit_ok(self, user_id: str) -> bool:
        now = time.monotonic()
        q = self._rate_events.setdefault(user_id, deque())
        while q and (now - q[0]) > self._rate_limit_window_s:
            q.popleft()
        if len(q) >= self._rate_limit_max_events:
            return False
        q.append(now)
        return True

    async def _send_message(self, chat_id: int, text: str) -> Any:
        # We need the application context or bot instance.
        # Since this is a callback, we'll store the application reference later
        # or pass it via closure.
        # But wait, send_message is called from BotSession which is async.
        # We can use self.application.bot.send_message
        # Telegram markdown can be brittle; try markdown first (better UX),
        # then fall back to plain text if Telegram rejects it.
        try:
            return await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception:
            return await self.application.bot.send_message(chat_id=chat_id, text=text)

    async def _update_message(self, msg_handle: Any, text: str) -> None:
        # msg_handle is the Message object returned by send_message
        try:
            if not text.strip():
                return

            # Telegram limit 4096
            if len(text) > 4000:
                text = text[:4000] + "\n... (truncated)"

            try:
                await msg_handle.edit_text(
                    text=text,
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            except Exception:
                await msg_handle.edit_text(text=text)
        except Exception as e:
            # Ignore "Message is not modified" errors
            if "Message is not modified" not in str(e):
                logger.warning(f"Failed to update message: {e}")

    async def _request_approval(self, chat_id: int, tool_name: str, args: dict[str, Any], tool_call_id: str) -> Any:
        short_id = tool_call_id[:8]
        self.approval_map[short_id] = tool_call_id
        self._approval_created_at[short_id] = time.monotonic()

        keyboard = [
            [
                InlineKeyboardButton("Approve", callback_data=f"app:{short_id}"),
                InlineKeyboardButton("Deny", callback_data=f"deny:{short_id}"),
            ],
            [
                InlineKeyboardButton("Always", callback_data=f"always:{short_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Do NOT use Markdown here: args can contain characters that break markdown.
        # Keep it plain text to ensure approvals always render.
        await self.application.bot.send_message(
            chat_id=chat_id,
            text=f"Approval Required\nTool: {tool_name}\nArgs: {args}",
            reply_markup=reply_markup,
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return

        user_id = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")

        if user_id in allowed:
            await update.message.reply_text(f"Welcome back, Chef {user.first_name}! 👨‍🍳\nSend me a message to start cooking.")
        else:
            await update.message.reply_text(
                f"🔒 Access Denied.\nYour User ID is: `{user_id}`\n\n"
                f"To enable access, run this in your terminal:\n"
                f"`/telegram allow {user_id}`",
                parse_mode=constants.ParseMode.MARKDOWN
            )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        user_id_str = str(user.id)

        if not self._rate_limit_ok(user_id_str):
            await self._send_message(chat_id, "⏳ Too many requests. Please wait a moment and try again.")
            return

        session = self._get_session(chat_id, user_id_str)
        if not session:
            await self.start(update, context)
            return

        self._touch_activity(chat_id)

        # Run sequentially per chat to avoid overlapping agent loops.
        async def _run_locked() -> None:
            async with self._chat_lock(chat_id):
                self._touch_activity(chat_id)
                await session.handle_user_message(update.message.text)

        asyncio.create_task(_run_locked())

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        chat_id = update.effective_chat.id
        session = self.sessions.get(chat_id)
        if not session:
            return

        self._touch_activity(chat_id)

        response = ApprovalResponse.NO
        msg = None

        if action == "app":
            response = ApprovalResponse.YES
            await query.edit_message_text(f"✅ Approved")
        elif action == "deny":
            response = ApprovalResponse.NO
            msg = "User denied via Telegram"
            await query.edit_message_text(f"🚫 Denied")
        elif action == "always":
            response = ApprovalResponse.ALWAYS
            await query.edit_message_text(f"⚡ Always Approved")

        # Unblock the waiting tool approval in the session
        session.resolve_approval(tool_call_id, response, msg)

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.effective_chat:
            return

        session = self._get_session(update.effective_chat.id, str(user.id))
        if not session:
            await self.start(update, context)
            return

        await session.clear_history()
        await update.message.reply_text("🧹 History cleared.")

    async def chefchat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Optional remote systemd control.

        Enabled only when CHEFCHAT_ENABLE_TELEGRAM_SYSTEMD_CONTROL is set.
        """
        if not self._enable_systemd_control:
            await update.message.reply_text("This command is disabled on this server.")
            return

        user = update.effective_user
        if not user:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        if not context.args:
            await update.message.reply_text(
                "Usage:\n"
                "/chefchat status\n"
                "/chefchat start\n"
                "/chefchat stop\n"
                "/chefchat restart\n"
                "/chefchat projects\n"
                "/chefchat switch <project>\n"
                "/chefchat miniapp <start|stop|restart|status> [project]\n"
                "/chefchat tunnel <start|stop|restart|status> [project]"
            )
            return

        action = context.args[0].strip().lower()

        if action in {"miniapp", "tunnel"}:
            if len(context.args) < 2:
                await update.message.reply_text(
                    f"Usage: /chefchat {action} <start|stop|restart|status> [project]"
                )
                return

            sub_action = context.args[1].strip().lower()
            if sub_action not in {"start", "stop", "restart", "status"}:
                await update.message.reply_text("Unknown action.")
                return

            project = context.args[2].strip() if len(context.args) >= 3 else "chefchat"
            if self._allowed_projects and project not in self._allowed_projects:
                await update.message.reply_text("Unknown project.")
                return

            unit_base = "chefchat-miniapp" if action == "miniapp" else "chefchat-tunnel"
            unit = f"{unit_base}@{project}.service"
            ok, out = await self._systemctl_user([sub_action, unit])
            await update.message.reply_text(out if ok else f"Failed: {out}")
            return

        if action == "projects":
            projects = (
                ", ".join(self._allowed_projects)
                if self._allowed_projects
                else "(none configured)"
            )
            await update.message.reply_text(f"Projects: {projects}")
            return

        if action == "switch":
            if len(context.args) < 2:
                await update.message.reply_text("Usage: /chefchat switch <project>")
                return

            project = context.args[1].strip()
            if self._allowed_projects and project not in self._allowed_projects:
                await update.message.reply_text("Unknown project.")
                return

            unit = f"{self._systemd_unit_base}@{project}.service"
            ok, out = await self._systemctl_user(["restart", unit])
            await update.message.reply_text(out if ok else f"Failed: {out}")
            return

        if action in {"start", "stop", "restart", "status"}:
            unit = f"{self._systemd_unit_base}.service"
            ok, out = await self._systemctl_user([action, unit])
            await update.message.reply_text(out if ok else f"Failed: {out}")
            return

        await update.message.reply_text("Unknown action.")

    async def _systemctl_user(self, args: list[str]) -> tuple[bool, str]:
        """Run `systemctl --user ...` and return (ok, output)."""
        systemctl = os.getenv("SYSTEMCTL_BIN", "/usr/bin/systemctl")
        if not Path(systemctl).exists():
            return False, f"systemctl not found: {systemctl}"

        proc = await asyncio.create_subprocess_exec(
            systemctl,
            "--user",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await proc.communicate()
        out = (out_b or b"").decode("utf-8", errors="replace").strip()
        return proc.returncode == 0, out or "OK"

    async def run(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("No TELEGRAM_BOT_TOKEN found")
            return

        # Reduce the chance of leaking sensitive request URLs in logs.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)

        self.application = ApplicationBuilder().token(token).build()

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("chefchat", self.chefchat_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

        logger.info("Starting Telegram Bot polling...")

        # Start a background cleanup loop
        asyncio.create_task(self._cleanup_loop())

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()

            expired_short_ids = [
                short_id
                for short_id, created in self._approval_created_at.items()
                if (now - created) > self._approval_ttl_s
            ]
            for short_id in expired_short_ids:
                self._approval_created_at.pop(short_id, None)
                self.approval_map.pop(short_id, None)

            expired_chats = [
                chat_id
                for chat_id, last in self._last_activity.items()
                if (now - last) > self._session_ttl_s
            ]
            for chat_id in expired_chats:
                self._last_activity.pop(chat_id, None)
                self._chat_locks.pop(chat_id, None)
                self.sessions.pop(chat_id, None)

async def run_telegram_bot(config: VibeConfig):
    service = TelegramBotService(config)
    await service.run()
