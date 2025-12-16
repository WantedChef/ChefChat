"""Telegram bot service for ChefChat."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from chefchat.bots.manager import BotManager
from chefchat.bots.session import BotSession
from chefchat.bots.telegram import fun_commands
from chefchat.bots.telegram.approvals import ApprovalStore
from chefchat.bots.telegram.cli_providers import CLI_PROVIDERS, CLIProviderManager
from chefchat.bots.telegram.constants import (
    APPROVAL_TTL_S,
    CHEAP_MODEL_PRICE_THRESHOLD,
    GIT_OUTPUT_MAX_LEN,
    MAX_TELEGRAM_API_RETRIES,
    MIN_COMMAND_ARGS_MINIAPP,
    MIN_COMMAND_ARGS_MODEL_SELECT,
    MIN_COMMAND_ARGS_SWITCH,
    MODEL_MENU_BUTTONS_PER_ROW,
    SESSION_IDLE_TTL_S,
    SESSION_IDLE_WARNING_S,
    TELEGRAM_API_RETRY_DELAY_S,
    TELEGRAM_MESSAGE_TRUNCATE_LIMIT,
    TELEGRAM_WORKDIR,
)
from chefchat.bots.telegram.handlers.admin import AdminHandlers
from chefchat.bots.telegram.handlers.cli import CLIHandlers
from chefchat.bots.telegram.handlers.core import CoreHandlers
from chefchat.bots.telegram.handlers.context import ContextHandlers
from chefchat.bots.telegram.handlers.models import ModelHandlers
from chefchat.bots.telegram.handlers.policy import PolicyHandlers
from chefchat.bots.telegram.handlers.tasks import TaskHandlers
from chefchat.bots.telegram.handlers.terminal import TerminalHandlers
from chefchat.bots.telegram.locks import FileLock
from chefchat.bots.telegram.rate_limit import RateLimiter
from chefchat.bots.telegram.sessions import SessionStore
from chefchat.bots.telegram.task_manager import TaskManager
from chefchat.core.config import VibeConfig
from chefchat.core.tools.executor import SecureCommandExecutor
from chefchat.core.utils import ApprovalResponse
from chefchat.interface.services import ModelService

logger = logging.getLogger(__name__)

class TelegramBotService:
    def __init__(self, config: VibeConfig) -> None:
        self.config = config
        self.bot_manager = BotManager(config)
        self.TELEGRAM_WORKDIR = TELEGRAM_WORKDIR

        self.max_sessions_per_user = (
            int(os.getenv("CHEFCHAT_TELEGRAM_MAX_SESSIONS", "0")) or None
        )
        self.session_limit_override: bool = False

        # Helper components
        self.rate_limiter = RateLimiter(window_s=30.0, max_events=6)
        self.approvals = ApprovalStore(ttl_s=APPROVAL_TTL_S)
        self.sessions = SessionStore(
            config,
            self.bot_manager,
            max_sessions_per_user=self.max_sessions_per_user,
            session_limit_override=self.session_limit_override,
        )
        self._chat_locks: dict[int, asyncio.Lock] = {}

        self._version_file = (
            Path(os.getenv("CHEFCHAT_HOME", Path.home() / ".chefchat"))
            / "telegram_bot_version"
        )

        # Optional systemd control (for switching project instances)
        self._enable_systemd_control = os.getenv(
            "CHEFCHAT_ENABLE_TELEGRAM_SYSTEMD_CONTROL", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._systemd_unit_base = os.getenv(
            "CHEFCHAT_TELEGRAM_UNIT_BASE", "chefchat-telegram"
        )
        self._allowed_projects = [
            p.strip()
            for p in os.getenv("CHEFCHAT_PROJECTS", "").split(",")
            if p.strip()
        ]

        self.application: Application | None = None

        # Ensure telegram working directory exists
        TELEGRAM_WORKDIR.mkdir(parents=True, exist_ok=True)
        self._file_lock = FileLock(TELEGRAM_WORKDIR / "telegram_bot.lock")

        # Initialize terminal manager for interactive sessions
        from chefchat.bots.terminal import TerminalManager

        self.terminal_manager = TerminalManager()
        self.executor = SecureCommandExecutor(TELEGRAM_WORKDIR)

        # Initialize CLI provider manager for AI CLI sessions (Gemini, Codex, OpenCode)
        self.cli_manager = CLIProviderManager()
        # Task tracking and per-chat tool policies
        self.task_manager = TaskManager()
        self.tool_policies: dict[int, str] = {}
        # Handler modules
        self.model_service = ModelService(self.config)
        self.models = ModelHandlers(
            self,
            MODEL_MENU_BUTTONS_PER_ROW,
            CHEAP_MODEL_PRICE_THRESHOLD,
            MIN_COMMAND_ARGS_MODEL_SELECT,
            model_service=self.model_service,
        )
        self.cli_handlers = CLIHandlers(self)
        self.task_handlers = TaskHandlers(self)
        self.policy = PolicyHandlers(self)
        self.core = CoreHandlers(self)
        self.context_handlers = ContextHandlers(self)
        self.admin = AdminHandlers(self)
        self.term_handlers = TerminalHandlers(self)

    def _acquire_lock(self) -> None:
        self._file_lock.acquire()

    def _release_lock(self) -> None:
        self._file_lock.release()

    def _forget_session(self, chat_id: int) -> None:
        self.sessions.forget(chat_id)
        self._chat_locks.pop(chat_id, None)

    def _get_session(self, chat_id: int, user_id_str: str) -> BotSession | None:
        from copy import deepcopy

        def _factory() -> BotSession:
            telegram_config = deepcopy(self.config)
            telegram_config.workdir = TELEGRAM_WORKDIR

            return BotSession(
                telegram_config,
                send_message=lambda text: self._send_message(chat_id, text),
                update_message=self._update_message,
                request_approval=lambda t, a, i: self._request_approval(
                    chat_id, t, a, i
                ),
                user_id=user_id_str,
                chat_id=chat_id,  # Enable persistent memory per chat
                tool_policy=self.tool_policies.get(chat_id, "dev"),
            )

        session = self.sessions.get_or_create(
            chat_id,
            user_id_str,
            factory=_factory,
        )
        if session:
            self.tool_policies.setdefault(chat_id, "dev")
            self._touch_activity(chat_id)
        return session

    def _touch_activity(self, chat_id: int) -> None:
        self.sessions.touch(chat_id)

    def _chat_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    def _rate_limit_ok(self, user_id: str) -> bool:
        return self.rate_limiter.allow(user_id)

    async def _send_message(self, chat_id: int, text: str) -> Any:
        """Send a message with retry logic for transient failures."""
        assert self.application is not None, "Application not initialized"

        for attempt in range(MAX_TELEGRAM_API_RETRIES):
            try:
                return await self.application.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode=constants.ParseMode.MARKDOWN
                )
            except Exception as e:
                # If markdown fails, try plain text
                if "can't parse" in str(e).lower() or "parse" in str(e).lower():
                    try:
                        return await self.application.bot.send_message(
                            chat_id=chat_id, text=text
                        )
                    except Exception:
                        pass

                # Retry on transient errors
                if attempt < MAX_TELEGRAM_API_RETRIES - 1:
                    logger.warning(
                        f"Telegram API error (attempt {attempt + 1}/{MAX_TELEGRAM_API_RETRIES}): {e}"
                    )
                    await asyncio.sleep(TELEGRAM_API_RETRY_DELAY_S)
                else:
                    logger.error(
                        f"Failed to send message after {MAX_TELEGRAM_API_RETRIES} attempts: {e}"
                    )
                    # Last resort: try plain text without retry
                    try:
                        return await self.application.bot.send_message(
                            chat_id=chat_id, text=text
                        )
                    except Exception:
                        raise

    async def _update_message(self, msg_handle: Any, text: str) -> None:
        # msg_handle is the Message object returned by send_message
        try:
            if not text.strip():
                return

            # Telegram limit 4096
            if len(text) > TELEGRAM_MESSAGE_TRUNCATE_LIMIT:
                text = text[:TELEGRAM_MESSAGE_TRUNCATE_LIMIT] + "\n... (truncated)"

            try:
                await msg_handle.edit_text(
                    text=text, parse_mode=constants.ParseMode.MARKDOWN
                )
            except Exception:
                await msg_handle.edit_text(text=text)
        except Exception as e:
            # Ignore "Message is not modified" errors
            if "Message is not modified" not in str(e):
                logger.warning("Failed to update message: %s", e)

    async def _request_approval(
        self, chat_id: int, tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> Any:
        short_id = tool_call_id[:8]
        self.approvals.register(short_id, tool_call_id, chat_id, tool_name)

        keyboard = [
            [
                InlineKeyboardButton("Approve", callback_data=f"app:{short_id}"),
                InlineKeyboardButton("Deny", callback_data=f"deny:{short_id}"),
            ],
            [
                InlineKeyboardButton("Always", callback_data=f"always:{short_id}"),
                InlineKeyboardButton("Dismiss", callback_data=f"dismiss:{short_id}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        bot_mode = self.policy.get_current(chat_id)

        # Do NOT use Markdown here: args can contain characters that break markdown.
        # Keep it plain text to ensure approvals always render.
        assert self.application is not None, "Application not initialized"
        await self.application.bot.send_message(
            chat_id=chat_id,
            text=(
                "Approval Required\n"
                f"Bot-mode: {bot_mode}\n"
                f"Tool: {tool_name}\n"
                f"Args: {args}"
            ),
            reply_markup=reply_markup,
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.core.start(update, context)

    async def _try_dispatch_text_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_text: str,
        raw_text: str,
    ) -> bool:
        """Try to dispatch message as a special text command.

        Returns True if handled, False otherwise.
        """
        # Command keyword mapping
        keyword_handlers = {
            "start": self.start,
            "stop": self.stop_command,
            "clear": self.clear_command,
            "help": self.help_command,
            "status": self.status_command,
            "stats": lambda u, c: fun_commands.stats_command(self, u, c),
            "files": self.core.files_command,
            "pwd": self.core.pwd_command,
            "model": self.models.model_command,
            "modelstatus": self.models.model_command,
            "modellist": lambda u, c: self.models._handle_model_list(u, c),
            "modelselect": lambda u, c: self.models._handle_model_select_prompt(u, c),
            "chef": lambda u, c: fun_commands.chef_command(self, u, c),
            "wisdom": lambda u, c: fun_commands.wisdom_command(self, u, c),
            "roast": lambda u, c: fun_commands.roast_command(self, u, c),
            "fortune": lambda u, c: fun_commands.fortune_command(self, u, c),
            "reload": lambda u, c: fun_commands.reload_command(self, u, c),
            "chefchat": self.admin.chefchat_command,
            "git": self.admin.git_command,
            # CLI providers (AI assistants)
            "gemini": lambda u, c: self._cli_shortcut(u, c, "gemini"),
            "codex": lambda u, c: self._cli_shortcut(u, c, "codex"),
            "opencode": lambda u, c: self._cli_shortcut(u, c, "opencode"),
            "cli": self.cli_command,
            "clistatus": self.cli_status_command,
            "cliclose": self.cli_close_command,
            "cliproviders": self.cli_providers_command,
            "clirun": self.cli_run_command,
            "clihistory": self.cli_history_command,
            "clidiag": self.cli_diag_command,
            "clisetup": self.cli_setup_command,
            "clicancel": self.cli_cancel_command,
            "cliretry": self.cli_retry_command,
            "task": self.task_command,
            "tasks": self.task_command,
            "botmode": self.botmode_command,
            "devmode": lambda u, c: self._handle_botmode_shortcut(u, c, "dev"),
            "chatmode": lambda u, c: self._handle_botmode_shortcut(u, c, "chat"),
            "combimode": lambda u, c: self._handle_botmode_shortcut(u, c, "combo"),
            "modelrefresh": self.models.model_refresh_command,
            "term": self.term_handlers.term_command,
            "termstatus": self.term_handlers.termstatus_command,
            "termclose": self.term_handlers.termclose_command,
            "termbash": lambda u, c: self.term_handlers.term_shortcut(u, c, "bash"),
            "termpython3": lambda u, c: self.term_handlers.term_shortcut(
                u, c, "python3"
            ),
            "termvim": lambda u, c: self.term_handlers.term_shortcut(u, c, "vim"),
            "termnode": lambda u, c: self.term_handlers.term_shortcut(u, c, "node"),
            "termnpm": lambda u, c: self.term_handlers.term_shortcut(u, c, "npm"),
            "termswitch": self.term_handlers.term_switch_command,
            "termupload": self.term_handlers.term_upload_command,
            "context": self.context_handlers.context_command,
        }

        mode_keywords = {
            "plan": "PLAN",
            "normal": "NORMAL",
            "auto": "AUTO",
            "yolo": "YOLO",
            "architect": "ARCHITECT",
        }

        # Check mode keyword
        if message_text == "mode":
            await self.mode_command(update, context)
            return True

        if message_text in mode_keywords:
            await self._handle_mode_switch(update, context, mode_keywords[message_text])
            return True

        if message_text in keyword_handlers:
            logger.debug(
                "dispatch: command %s -> %s",
                message_text,
                keyword_handlers[message_text],
            )
            await keyword_handlers[message_text](update, context)
            return True

        # Inline provider prefix, e.g. "gemini: build README"
        for provider_key in CLI_PROVIDERS:
            prefix_colon = f"{provider_key}:"
            prefix_arrow = f"{provider_key}>"
            if raw_text.lower().startswith(prefix_colon) or raw_text.lower().startswith(
                prefix_arrow
            ):
                prompt = (
                    raw_text[len(prefix_colon) :].strip()
                    if raw_text.lower().startswith(prefix_colon)
                    else raw_text[len(prefix_arrow) :].strip()
                )
                if not prompt:
                    await self._send_message(chat_id, "❌ No prompt provided.")
                    return True
                logger.debug("dispatch: inline cli %s", provider_key)
                await self._send_message(chat_id, "⏳ Running CLI request...")
                output = await self.cli_manager.execute_prompt(
                    chat_id, prompt, provider_override=provider_key, persist=True
                )
                await self._send_message(chat_id, output)
                return True

        # Direct git command without slash (e.g., "git clone ...")
        if raw_text.lower().startswith("git "):
            context.args = raw_text.split()[1:]
            await self.admin.git_command(update, context)
            return True

        # Direct model command without slash (e.g., "model list" or "model select X")
        if raw_text.lower().startswith("model "):
            context.args = raw_text.split()[1:]
            await self.models.model_command(update, context)
            return True

        # Check active CLI session (AI providers like Gemini, Codex, OpenCode)
        if self.cli_manager.has_active_session(chat_id):
            if not update.message or not update.message.text:
                return True
            # Show processing message
            await self._send_message(chat_id, "⏳ Processing...")
            output = await self.cli_manager.execute_prompt(chat_id, update.message.text)
            await self._send_message(chat_id, output)
            return True

        # Check active terminal session
        if self.terminal_manager.has_active_session(chat_id):
            if not update.message or not update.message.text:
                return True
            output = self.terminal_manager.send_to_session(chat_id, update.message.text)
            await self._send_message(chat_id, output)
            return True

        return False

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        chat = update.effective_chat
        message = update.message
        if not user or not chat or not message or not message.text:
            return

        chat_id = chat.id
        user_id_str = str(user.id)

        if not self._rate_limit_ok(user_id_str):
            await self._send_message(
                chat_id, "⏳ Too many requests. Please wait a moment and try again."
            )
            return

        session = self._get_session(chat_id, user_id_str)
        if not session:
            await self.start(update, context)
            return

        self._touch_activity(chat_id)

        # Check if message is a command keyword (without /)
        message_text = message.text.strip().lower()
        raw_text = message.text.strip()

        if await self._try_dispatch_text_command(
            update, context, chat_id, message_text, raw_text
        ):
            return

        # Run sequentially per chat to avoid overlapping agent loops.
        async def _run_locked() -> None:
            async with self._chat_lock(chat_id):
                self._touch_activity(chat_id)
                await session.handle_user_message(message.text or "")

        asyncio.create_task(_run_locked())

    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.exception("Telegram update handler error", exc_info=context.error)

    async def handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None:
            return

        logger.debug(
            "dispatch: callback chat=%s data=%s",
            update.effective_chat.id if update.effective_chat else "?",
            getattr(query, "data", None),
        )
        await query.answer()

        data = query.data
        if not data:
            return

        if data.startswith("botmode:"):
            await self.policy.handle_callback(update, data)
            return

        # Handle model selection callbacks
        if data.startswith(("mod:", "mcat:", "mmain")):
            await self.models._handle_model_callback(update, context)
            return

        action, short_id = data.split(":")
        info = self.approvals.pop(short_id)
        tool_call_id = info.tool_call_id if info else None

        if not tool_call_id:
            try:
                await query.edit_message_text("❌ Session expired or unknown request.")
            except Exception:
                pass
            return

        chat = update.effective_chat
        if chat is None:
            return

        chat_id = chat.id
        session = self.sessions.get(chat_id)
        if not session:
            return

        self._touch_activity(chat_id)

        response = ApprovalResponse.NO
        msg = None

        if action == "app":
            response = ApprovalResponse.YES
            await query.edit_message_text("✅ Approved")
        elif action == "deny":
            response = ApprovalResponse.NO
            msg = "User denied via Telegram"
            await query.edit_message_text("🚫 Denied")
        elif action == "dismiss":
            response = ApprovalResponse.NO
            msg = "Dismissed without feedback"
            await query.edit_message_text("ℹ️ Dismissed")
        elif action == "always":
            response = ApprovalResponse.ALWAYS
            await query.edit_message_text("⚡ Always Approved")

        # Unblock the waiting tool approval in the session
        session.resolve_approval(tool_call_id, response, msg)

    async def clear_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.effective_chat or not update.message:
            return

        session = self._get_session(update.effective_chat.id, str(user.id))
        if not session:
            await self.start(update, context)
            return

        await session.clear_history()
        await update.message.reply_text("🧹 History cleared.")

    async def context_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.context_handlers.context_command(update, context)

    async def chefchat_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.admin.chefchat_command(update, context)

    async def git_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.admin.git_command(update, context)

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

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.core.status_command(update, context)

    async def api_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show provider API key status for Telegram users."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        providers = self.model_service.list_provider_info()
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
        if not user or not update.effective_chat:
            return
        if not update.message:
            return

        chat_id = update.effective_chat.id

        session = self.sessions.get(chat_id)
        if session:
            # Clear the session
            self._forget_session(chat_id)
            await update.message.reply_text("🛑 Session stopped and cleared.")
        else:
            await update.message.reply_text("No active session to stop.")

    async def files_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.core.files_command(update, context)

    async def pwd_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.core.pwd_command(update, context)

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.core.help_command(update, context)

    async def model_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.models.model_command(update, context)

    async def _handle_model_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.models._handle_model_callback(update, context)

    async def model_refresh_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.models.model_refresh_command(update, context)

    async def mode_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show current mode and available modes."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat = update.effective_chat
        if chat is None:
            await update.message.reply_text("Access denied.")
            return

        chat_id = chat.id
        session = self.sessions.get(chat_id)

        if not session:
            await update.message.reply_text("No active session. Send a message first!")
            return

        mode_manager = getattr(session.agent, "mode_manager", None)
        if mode_manager is None:
            await update.message.reply_text("Mode manager not available.")
            return

        current = mode_manager.describe_mode()
        descriptors = mode_manager.list_modes()

        lines = [
            f"🎯 **Current Mode**: {current.emoji} {current.name}",
            f"🤖 Auto-Approve: {'ON' if current.auto_approve else 'OFF'}",
            f"🔒 Read-only: {'YES' if current.read_only else 'NO'}",
            "",
            "**Available Modes:**",
        ]

        for desc in descriptors:
            marker = "▶️" if desc.id == current.id else "  "
            perms = []
            if desc.read_only:
                perms.append("🔒 Read-only")
            if desc.auto_approve:
                perms.append("🤖 Auto-approve")
            if not perms:
                perms.append("✋ Confirm each")
            perm_str = " • ".join(perms)
            tips = desc.tips[:2] if desc.tips else []
            tips_str = "\n".join(f"   - {tip}" for tip in tips)
            lines.append(f"{marker} {desc.emoji} **{desc.name}** — {desc.description}")
            lines.append(f"   {perm_str}")
            if tips_str:
                lines.append(tips_str)
            lines.append("")

        lines.append("Type a mode name to switch (e.g., `auto`).")

        await update.message.reply_text(
            "\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN
        )

    async def _handle_mode_switch(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, mode_name: str
    ) -> None:
        """Switch to a different mode."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat = update.effective_chat
        if chat is None:
            await update.message.reply_text("Access denied.")
            return

        chat_id = chat.id
        session = self.sessions.get(chat_id)

        if not session:
            await update.message.reply_text("No active session. Send a message first!")
            return

        try:
            mode_manager = getattr(session.agent, "mode_manager", None)
            if mode_manager is None:
                await update.message.reply_text(
                    "Mode switching not available for this session."
                )
                return

            new_mode = mode_manager.set_mode_from_name(mode_name)
            desc = mode_manager.describe_mode(new_mode)
            await update.message.reply_text(
                f"{desc.emoji} **Switched to {desc.name} mode!**",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.exception("Failed to switch mode")
            await update.message.reply_text(f"❌ Failed to switch mode: {e}")

    # =========================
    # Bot tool policy (dev/chat/combo)
    # =========================

    def _current_tool_policy(self, chat_id: int) -> str:
        return self.policy.get_current(chat_id)

    def _set_tool_policy(self, chat_id: int, policy: str) -> str:
        return self.policy.set_policy(chat_id, policy)

    async def botmode_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.policy.botmode_command(update, context)

    async def _handle_botmode_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, policy: str
    ) -> None:
        await self.policy.handle_shortcut(update, context, policy)

    async def _handle_botmode_callback(self, update: Update, data: str) -> None:
        await self.policy.handle_callback(update, data)

    async def term_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.term_handlers.term_command(update, context)

    async def termstatus_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.term_handlers.termstatus_command(update, context)

    async def termclose_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.term_handlers.termclose_command(update, context)

    async def _term_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, command: str
    ) -> None:
        await self.term_handlers.term_shortcut(update, context, command)

    async def _notify_startup(self) -> None:
        """Send startup notification to allowed users."""
        allowed = self.bot_manager.get_allowed_users("telegram")
        version = self._get_version()
        signature = self._compute_bot_signature()
        prev_version, prev_sig = self._read_version_file()
        show_changelog = version is not None and prev_version != version
        changelog_text = self._get_changelog_snippet() if show_changelog else None
        code_changed_without_bump = (
            prev_sig is not None and prev_sig != signature and prev_version == version
        )

        for user_id in allowed:
            try:
                if self.application:
                    await self.application.bot.send_message(
                        chat_id=int(user_id),
                        text=(
                            "🚀 **ChefChat Bot Started!**\n"
                            f"🏷️ Version: `{version or 'unknown'}`\n\n"
                            f"📁 Working directory: `{TELEGRAM_WORKDIR}`\n"
                            f"🔧 Type /help for commands"
                            + (
                                f"\n\n🗒️ **Changelog:**\n{changelog_text}"
                                if changelog_text
                                else ""
                            )
                            + (
                                "\n\n⚠️ Bot code changed without version bump. "
                                "Update version/changelog before shipping."
                                if code_changed_without_bump
                                else ""
                            )
                        ),
                        parse_mode=constants.ParseMode.MARKDOWN,
                    )
            except Exception as e:
                logger.warning(f"Could not notify user {user_id}: {e}")

        if version:
            self._write_version_file(version, signature)

    def _get_version(self) -> str | None:
        try:
            return importlib.metadata.version("chefchat")
        except Exception:
            pass

        try:
            root = Path(__file__).resolve().parents[2]
            pyproject = root / "pyproject.toml"
            if pyproject.is_file():
                for line in pyproject.read_text().splitlines():
                    if line.startswith("version"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            return parts[1].strip().strip('"').strip("'")
        except Exception:
            pass
        return None

    def _compute_bot_signature(self) -> str:
        """Compute a hash of the telegram bot code to detect changes."""
        root = Path(__file__).resolve().parent
        paths = sorted(root.glob("**/*.py"))
        h = hashlib.sha256()
        for path in paths:
            try:
                h.update(path.read_bytes())
            except Exception:
                continue
        return h.hexdigest()

    def _read_version_file(self) -> tuple[str | None, str | None]:
        try:
            raw = self._version_file.read_text().strip()
            if not raw:
                return None, None
            if raw and not raw.startswith("{"):
                return raw, None
            data = json.loads(raw)
            return data.get("version"), data.get("signature")
        except Exception:
            return None, None

    def _write_version_file(self, version: str, signature: str) -> None:
        try:
            self._version_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": version, "signature": signature}
            self._version_file.write_text(json.dumps(payload))
        except Exception:
            logger.debug("Failed to write version file", exc_info=True)

    def _get_changelog_snippet(self) -> str:
        """Return short changelog for startup notification."""
        return (
            "• Nieuwe default: `mistral-small`\n"
            "• Providers: OpenCode Zen + NVIDIA toegevoegd\n"
            "• `/model list` toont nu live provider catalogus"
        )

    def _register_basic_handlers(self) -> None:
        """Register basic command handlers."""
        app = self.application
        if app is None:
            raise RuntimeError("Application not initialized")
        handlers = [
            ("start", self.start),
            ("stop", self.stop_command),
            ("clear", self.clear_command),
            ("status", self.status_command),
            ("files", self.files_command),
            ("pwd", self.pwd_command),
            ("help", self.help_command),
            ("api", self.api_command),
            ("model", self.model_command),
            ("mode", self.mode_command),
            ("task", self.task_command),
            ("tasks", self.task_command),
            ("botmode", self.botmode_command),
            ("chefchat", self.admin.chefchat_command),
            ("context", self.context_command),
        ]
        for cmd, handler in handlers:
            app.add_handler(CommandHandler(cmd, handler))

    def _register_fun_handlers(self) -> None:
        """Register fun/easter egg command handlers."""
        app = self.application
        if app is None:
            raise RuntimeError("Application not initialized")
        fun_handlers = [
            ("chef", fun_commands.chef_command),
            ("wisdom", fun_commands.wisdom_command),
            ("roast", fun_commands.roast_command),
            ("fortune", fun_commands.fortune_command),
            ("stats", fun_commands.stats_command),
            ("reload", fun_commands.reload_command),
        ]
        for cmd, func in fun_handlers:
            # Capture func in closure properly
            app.add_handler(CommandHandler(cmd, lambda u, c, f=func: f(self, u, c)))

    def _register_model_handlers(self) -> None:
        """Register model-related command handlers."""
        app = self.application
        if app is None:
            raise RuntimeError("Application not initialized")
        app.add_handler(
            CommandHandler(
                "modellist", lambda u, c: self.models._handle_model_list(u, c)
            )
        )
        app.add_handler(
            CommandHandler(
                "modelselect",
                lambda u, c: self.models._handle_model_select_prompt(u, c),
            )
        )
        app.add_handler(CommandHandler("modelstatus", self.model_command))
        app.add_handler(CommandHandler("modelrefresh", self.model_refresh_command))

    def _register_mode_handlers(self) -> None:
        """Register mode switch command handlers."""
        app = self.application
        if app is None:
            raise RuntimeError("Application not initialized")
        mode_commands = [
            ("plan", "PLAN"),
            ("normal", "NORMAL"),
            ("auto", "AUTO"),
            ("yolo", "YOLO"),
            ("architect", "ARCHITECT"),
        ]
        for cmd, mode in mode_commands:
            app.add_handler(
                CommandHandler(
                    cmd, lambda u, c, m=mode: self._handle_mode_switch(u, c, m)
                )
            )

    def _register_terminal_handlers(self) -> None:
        """Register terminal command handlers."""
        app = self.application
        if app is None:
            raise RuntimeError("Application not initialized")
        app.add_handler(CommandHandler("term", self.term_command))
        app.add_handler(CommandHandler("termstatus", self.termstatus_command))
        app.add_handler(CommandHandler("termclose", self.termclose_command))
        app.add_handler(CommandHandler("termswitch", self.term_handlers.term_switch_command))
        app.add_handler(CommandHandler("termupload", self.term_handlers.term_upload_command))

        # Terminal shortcut commands
        shortcuts = [
            ("termbash", "bash"),
            ("termpython3", "python3"),
            ("termvim", "vim"),
            ("termnode", "node"),
            ("termnpm", "npm"),
        ]
        for cmd, shell_cmd in shortcuts:
            app.add_handler(
                CommandHandler(cmd, lambda u, c, s=shell_cmd: self._term_shortcut(u, c, s))
            )

    # =========================================================================
    # CLI Provider Commands (Gemini, Codex, OpenCode)
    # =========================================================================

    async def cli_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_command(update, context)

    async def cli_close_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_close_command(update, context)

    async def cli_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_status_command(update, context)

    async def cli_providers_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_providers_command(update, context)

    async def cli_run_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_run_command(update, context)

    async def cli_cancel_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_cancel_command(update, context)

    async def cli_history_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_history_command(update, context)

    async def cli_diag_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_diag_command(update, context)

    async def cli_setup_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_setup_command(update, context)

    async def cli_retry_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.cli_handlers.cli_retry_command(update, context)

    # =========================================================================
    # Task commands
    # =========================================================================

    async def task_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.task_handlers.task_command(update, context)

    async def _cli_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, provider_name: str
    ) -> None:
        await self.cli_handlers.cli_shortcut(update, context, provider_name)

    def _register_cli_handlers(self) -> None:
        """Register CLI provider command handlers."""
        app = self.application
        if app is None:
            raise RuntimeError("Application not initialized")

        app.add_handler(CommandHandler("cli", self.cli_command))
        app.add_handler(CommandHandler("cliclose", self.cli_close_command))
        app.add_handler(CommandHandler("clistatus", self.cli_status_command))
        app.add_handler(CommandHandler("cliproviders", self.cli_providers_command))
        app.add_handler(CommandHandler("clirun", self.cli_run_command))
        app.add_handler(CommandHandler("clihistory", self.cli_history_command))
        app.add_handler(CommandHandler("clidiag", self.cli_diag_command))
        app.add_handler(CommandHandler("clisetup", self.cli_setup_command))
        app.add_handler(CommandHandler("cliretry", self.cli_retry_command))
        app.add_handler(CommandHandler("clicancel", self.cli_cancel_command))

        # CLI provider shortcut commands
        cli_shortcuts = [
            ("cligemini", "gemini"),
            ("clicodex", "codex"),
            ("cliopencode", "opencode"),
        ]
        for cmd, provider in cli_shortcuts:
            app.add_handler(
                CommandHandler(cmd, lambda u, c, p=provider: self._cli_shortcut(u, c, p))
            )

    def _register_message_handlers(self) -> None:
        """Register message and callback handlers."""
        app = self.application
        if app is None:
            raise RuntimeError("Application not initialized")
        # Route unknown slash-commands into the normal chat pipeline
        app.add_handler(MessageHandler(filters.COMMAND, self.handle_message))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_error_handler(self.error_handler)

    def _register_all_handlers(self) -> None:
        """Register all command, message, and callback handlers."""
        self._register_basic_handlers()
        self._register_fun_handlers()
        self._register_model_handlers()
        self._register_mode_handlers()
        self._register_terminal_handlers()
        self._register_cli_handlers()
        self._register_message_handlers()

    async def _shutdown_gracefully(self, started: bool, polling: bool) -> None:
        """Gracefully shutdown the application."""
        app = self.application
        try:
            if app is not None and polling:
                await app.updater.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Telegram updater stop failed: %s", e)

        try:
            if app is not None and started:
                await app.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Telegram application stop failed: %s", e)

        try:
            if app is not None:
                await app.shutdown()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Telegram application shutdown failed: %s", e)

        self._release_lock()

    async def run(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("No TELEGRAM_BOT_TOKEN found")
            return

        # Reduce the chance of leaking sensitive request URLs in logs.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)

        try:
            self._acquire_lock()
        except RuntimeError as exc:
            logger.error(exc)
            return

        self.application = ApplicationBuilder().token(token).build()
        self._register_all_handlers()

        logger.info("Starting Telegram Bot polling...")
        asyncio.create_task(self._cleanup_loop())

        started = False
        polling = False
        try:
            app = self.application
            if app is None:
                raise RuntimeError("Application not initialized")
            await app.initialize()
            await app.start()
            started = True
            await app.updater.start_polling(drop_pending_updates=True)
            polling = True

            await self._notify_startup()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self._shutdown_gracefully(started, polling)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()

            for info in self.approvals.expire(now):
                if self.application:
                    try:
                        await self.application.bot.send_message(
                            chat_id=info.chat_id,
                            text=f"⌛ Approval expired for {info.tool_name or 'tool'} (id {info.short_id}).",
                        )
                    except Exception:
                        pass

            # Idle session warnings/cleanup
            for chat_id in list(self.sessions.idle_sessions(SESSION_IDLE_TTL_S)):
                self._forget_session(chat_id)
                if self.application:
                    try:
                        await self.application.bot.send_message(
                            chat_id=chat_id,
                            text="⏻ Session closed after inactivity.",
                        )
                    except Exception:
                        pass

            if self.application:
                for chat_id in list(self.sessions.sessions.keys()):
                    if self.sessions.warnable(chat_id, SESSION_IDLE_WARNING_S):
                        self.sessions.mark_warned(chat_id)
                        try:
                            await self.application.bot.send_message(
                                chat_id=chat_id,
                                text="⚠️ Session idle. Will close soon if no activity.",
                            )
                        except Exception:
                            pass


async def run_telegram_bot(config: VibeConfig) -> None:
    service = TelegramBotService(config)
    await service.run()
