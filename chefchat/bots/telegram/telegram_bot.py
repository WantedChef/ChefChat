"""Telegram bot service for ChefChat."""

from __future__ import annotations

import asyncio
from collections import deque
import fcntl
import logging
import os
from pathlib import Path
import time
from typing import Any

# Telegram bot working directory
TELEGRAM_WORKDIR = Path.home() / "chefchat_output_"

import shlex

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
from chefchat.core.config import VibeConfig
from chefchat.core.tools.executor import SecureCommandExecutor
from chefchat.core.utils import ApprovalResponse
from chefchat.kitchen.stations.git_chef import GitCommandValidator

logger = logging.getLogger(__name__)

# Constants
TELEGRAM_MESSAGE_TRUNCATE_LIMIT = 4000
MIN_COMMAND_ARGS_MINIAPP = 2
MIN_COMMAND_ARGS_SWITCH = 3
MAX_TELEGRAM_API_RETRIES = 3
TELEGRAM_API_RETRY_DELAY_S = 1.0
MIN_COMMAND_ARGS_MODEL_SELECT = 2
GIT_OUTPUT_MAX_LEN = 3000
MODEL_MENU_BUTTONS_PER_ROW = 2
CHEAP_MODEL_PRICE_THRESHOLD = 0.5


class TelegramBotService:
    def __init__(self, config: VibeConfig) -> None:
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
        self._lock_path = TELEGRAM_WORKDIR / "telegram_bot.lock"
        self._lock_handle: int | None = None

        # Initialize terminal manager for interactive sessions
        from chefchat.bots.telegram.terminal_manager import TerminalManager

        self.terminal_manager = TerminalManager()
        self.executor = SecureCommandExecutor(TELEGRAM_WORKDIR)

    def _acquire_lock(self) -> None:
        if self._lock_handle is not None:
            return

        fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise RuntimeError(
                f"Telegram bot already running (lock busy): {self._lock_path}"
            )

        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        self._lock_handle = fd

    def _release_lock(self) -> None:
        if self._lock_handle is None:
            return

        try:
            fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_handle)
            self._lock_handle = None

    def _get_session(self, chat_id: int, user_id_str: str) -> BotSession | None:
        if chat_id not in self.sessions:
            # Check allowlist
            allowed = self.bot_manager.get_allowed_users("telegram")
            if user_id_str not in allowed:
                return None

            # Create a modified config with telegram-specific working directory
            from copy import deepcopy

            telegram_config = deepcopy(self.config)
            telegram_config.workdir = TELEGRAM_WORKDIR

            self.sessions[chat_id] = BotSession(
                telegram_config,
                send_message=lambda text: self._send_message(chat_id, text),
                update_message=self._update_message,
                request_approval=lambda t, a, i: self._request_approval(
                    chat_id, t, a, i
                ),
                user_id=user_id_str,
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
        self.approval_map[short_id] = tool_call_id
        self._approval_created_at[short_id] = time.monotonic()

        keyboard = [
            [
                InlineKeyboardButton("Approve", callback_data=f"app:{short_id}"),
                InlineKeyboardButton("Deny", callback_data=f"deny:{short_id}"),
            ],
            [InlineKeyboardButton("Always", callback_data=f"always:{short_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Do NOT use Markdown here: args can contain characters that break markdown.
        # Keep it plain text to ensure approvals always render.
        assert self.application is not None, "Application not initialized"
        await self.application.bot.send_message(
            chat_id=chat_id,
            text=f"Approval Required\nTool: {tool_name}\nArgs: {args}",
            reply_markup=reply_markup,
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

    async def _try_dispatch_text_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_text: str,
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
            "files": self.files_command,
            "pwd": self.pwd_command,
            "model": self.model_command,
            "modelstatus": self.model_command,
            "modellist": lambda u, c: self._handle_model_list(u, c),
            "modelselect": lambda u, c: self._handle_model_select_prompt(u, c),
            "chef": lambda u, c: fun_commands.chef_command(self, u, c),
            "wisdom": lambda u, c: fun_commands.wisdom_command(self, u, c),
            "roast": lambda u, c: fun_commands.roast_command(self, u, c),
            "fortune": lambda u, c: fun_commands.fortune_command(self, u, c),
            "reload": lambda u, c: fun_commands.reload_command(self, u, c),
            "chefchat": self.chefchat_command,
            "git": self.git_command,
        }

        # Check mode keyword
        if message_text == "mode":
            await self.mode_command(update, context)
            return True

        # Check mode switch keywords
        mode_keywords = {
            "plan": "PLAN",
            "normal": "NORMAL",
            "auto": "AUTO",
            "yolo": "YOLO",
            "architect": "ARCHITECT",
        }
        if message_text in mode_keywords:
            await self._handle_mode_switch(update, context, mode_keywords[message_text])
            return True

        # Check single-word command
        if message_text in keyword_handlers:
            await keyword_handlers[message_text](update, context)
            return True

        # Check active terminal session
        if self.terminal_manager.has_active_session(chat_id):
            output = self.terminal_manager.send_to_session(chat_id, update.message.text)
            await self._send_message(chat_id, output)
            return True

        return False

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
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
        message_text = update.message.text.strip().lower()

        if await self._try_dispatch_text_command(
            update, context, chat_id, message_text
        ):
            return

        # Run sequentially per chat to avoid overlapping agent loops.
        async def _run_locked() -> None:
            async with self._chat_lock(chat_id):
                self._touch_activity(chat_id)
                await session.handle_user_message(update.message.text)

        asyncio.create_task(_run_locked())

    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.exception("Telegram update handler error", exc_info=context.error)

    async def handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()

        data = query.data
        if not data:
            return

        # Handle model selection callbacks
        if data.startswith(("mod:", "mcat:", "mmain")):
            await self._handle_model_callback(update, context)
            return

        action, short_id = data.split(":")
        tool_call_id = self.approval_map.get(short_id)

        if not tool_call_id:
            try:
                await query.edit_message_text("❌ Session expired or unknown request.")
            except Exception:
                pass
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
            await query.edit_message_text("✅ Approved")
        elif action == "deny":
            response = ApprovalResponse.NO
            msg = "User denied via Telegram"
            await query.edit_message_text("🚫 Denied")
        elif action == "always":
            response = ApprovalResponse.ALWAYS
            await query.edit_message_text("⚡ Always Approved")

        # Unblock the waiting tool approval in the session
        session.resolve_approval(tool_call_id, response, msg)

    async def clear_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.effective_chat:
            return

        session = self._get_session(update.effective_chat.id, str(user.id))
        if not session:
            await self.start(update, context)
            return

        await session.clear_history()
        await update.message.reply_text("🧹 History cleared.")

    async def chefchat_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
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
            await self._show_chefchat_help(update)
            return

        action = context.args[0].strip().lower()
        await self._dispatch_chefchat_action(update, context, action)

    async def _show_chefchat_help(self, update: Update) -> None:
        """Show help for /chefchat command."""
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

    async def _dispatch_chefchat_action(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str
    ) -> None:
        """Dispatch to the appropriate action handler."""
        if action in {"miniapp", "tunnel"}:
            await self._handle_service_action(update, context, action)
        elif action == "projects":
            await self._handle_projects_action(update)
        elif action == "switch":
            await self._handle_switch_action(update, context)
        elif action in {"start", "stop", "restart", "status"}:
            await self._handle_systemd_action(update, action)
        else:
            await update.message.reply_text("Unknown action.")

    async def _handle_service_action(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str
    ) -> None:
        """Handle miniapp/tunnel service actions."""
        if len(context.args) < MIN_COMMAND_ARGS_MINIAPP:
            await update.message.reply_text(
                f"Usage: /chefchat {action} <start|stop|restart|status> [project]"
            )
            return

        sub_action = context.args[1].strip().lower()
        if sub_action not in {"start", "stop", "restart", "status"}:
            await update.message.reply_text("Unknown action.")
            return

        project = (
            context.args[2].strip()
            if len(context.args) >= MIN_COMMAND_ARGS_SWITCH
            else "chefchat"
        )
        if self._allowed_projects and project not in self._allowed_projects:
            await update.message.reply_text("Unknown project.")
            return

        unit_base = "chefchat-miniapp" if action == "miniapp" else "chefchat-tunnel"
        unit = f"{unit_base}@{project}.service"
        ok, out = await self._systemctl_user([sub_action, unit])
        await update.message.reply_text(out if ok else f"Failed: {out}")

    async def _handle_projects_action(self, update: Update) -> None:
        """Handle projects listing action."""
        projects = (
            ", ".join(self._allowed_projects)
            if self._allowed_projects
            else "(none configured)"
        )
        await update.message.reply_text(f"Projects: {projects}")

    async def _handle_switch_action(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle project switch action."""
        if len(context.args) < MIN_COMMAND_ARGS_MINIAPP:
            await update.message.reply_text("Usage: /chefchat switch <project>")
            return

        project = context.args[1].strip()
        if self._allowed_projects and project not in self._allowed_projects:
            await update.message.reply_text("Unknown project.")
            return

        unit = f"{self._systemd_unit_base}@{project}.service"
        ok, out = await self._systemctl_user(["restart", unit])
        await update.message.reply_text(out if ok else f"Failed: {out}")

    async def _handle_systemd_action(self, update: Update, action: str) -> None:
        """Handle basic systemd actions (start/stop/restart/status)."""
        unit = f"{self._systemd_unit_base}.service"
        ok, out = await self._systemctl_user([action, unit])
        await update.message.reply_text(out if ok else f"Failed: {out}")

    async def git_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /git commands safely."""
        user = update.effective_user
        if not user:
            return

        user_id_str = str(user.id)
        if user_id_str not in self.bot_manager.get_allowed_users("telegram"):
            await update.message.reply_text("Access denied.")
            return

        # Get the full command arguments
        if not context.args:
            await update.message.reply_text(
                "Usage: /git <command> (e.g., status, log, diff)"
            )
            return

        raw_args = " ".join(context.args)

        # Validate using GitChef's validator
        validated_args = GitCommandValidator.parse_and_validate(raw_args)
        if validated_args is None:
            await update.message.reply_text("❌ Invalid or unsafe git command.")
            return

        # Execute
        await update.message.reply_text(f"🔧 Running git {validated_args[1]}...")

        try:
            # Reconstruct safe command string for executor
            safe_command = " ".join(shlex.quote(arg) for arg in validated_args)

            # Pass GITHUB_TOKEN if available
            env = {}
            if token := os.environ.get("GITHUB_TOKEN"):
                env["GITHUB_TOKEN"] = token

            stdout, stderr, returncode = await self.executor.execute(
                safe_command, timeout=30, env=env
            )

            output = (stdout if stdout else stderr).strip()
            if not output:
                output = "(No output)"

            icon = "✅" if returncode == 0 else "❌"
            header = f"{icon} Git {validated_args[1]} finished (code {returncode})"

            # Truncate if too long for Telegram
            if len(output) > GIT_OUTPUT_MAX_LEN:
                output = output[:GIT_OUTPUT_MAX_LEN] + "\n...(truncated)"

            await update.message.reply_text(
                f"**{header}**\n```\n{output}\n```",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error executing git: {e}")

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
        """Show bot status and uptime."""
        user = update.effective_user
        if not user:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
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

        cwd = str(TELEGRAM_WORKDIR)
        session_count = len(self.sessions)

        status_text = (
            f"🤖 **ChefChat Bot Status**\n\n"
            f"⏱️ System uptime: {uptime}\n"
            f"📁 Working dir: `{cwd}`\n"
            f"👥 Active sessions: {session_count}\n"
            f"🔧 Commands: /help for list"
        )
        await update.message.reply_text(
            status_text, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def stop_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Stop the current agent session."""
        user = update.effective_user
        if not user or not update.effective_chat:
            return

        chat_id = update.effective_chat.id

        session = self.sessions.get(chat_id)
        if session:
            # Clear the session
            del self.sessions[chat_id]
            self._last_activity.pop(chat_id, None)
            self._chat_locks.pop(chat_id, None)
            await update.message.reply_text("🛑 Session stopped and cleared.")
        else:
            await update.message.reply_text("No active session to stop.")

    async def files_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """List project files in current directory."""
        user = update.effective_user
        if not user:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        cwd = TELEGRAM_WORKDIR
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
        if not user:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        await update.message.reply_text(
            f"📁 Current directory:\n`{TELEGRAM_WORKDIR}`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show available commands."""
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
            "• stats - Session statistics\n"
            "• files - List project files\n"
            "• pwd - Working directory\n\n"
            "**Models:**\n"
            "• model - Show current model\n"
            "• modellist - List all models\n"
            "• modelselect - Switch model\n\n"
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

    async def _perform_model_list(self, update: Update) -> None:
        """Helper to list available models."""
        lines = ["Available models:"]
        active = (self.config.active_model or "").lower()
        for m in sorted(self.config.models, key=lambda x: x.alias):
            is_active = m.alias.lower() == active or m.name.lower() == active
            marker = "✅" if is_active else "•"
            lines.append(f"{marker} {m.alias} ({m.provider})")
        await update.message.reply_text("\n".join(lines))

    async def _perform_model_select(self, update: Update, args: list[str]) -> None:
        """Helper to select a model."""
        if len(args) < MIN_COMMAND_ARGS_MODEL_SELECT:
            await update.message.reply_text("Usage: /model select <alias>")
            return

        target = args[1].lower()
        model = next(
            (
                m
                for m in self.config.models
                if target in {m.alias.lower(), m.name.lower()}
            ),
            None,
        )
        if model is None:
            await update.message.reply_text(
                f"Model '{args[1]}' not found. Use /model list."
            )
            return

        self.config.active_model = model.alias
        VibeConfig.save_updates({"active_model": model.alias})
        await update.message.reply_text(f"✅ Switched model to: {model.alias}")

    async def _handle_model_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle model selection callbacks."""
        query = update.callback_query
        data = query.data

        if data == "mmain":
            await self._show_model_root_menu(update)
            return

        if data.startswith("mcat:"):
            category = data.split(":", 1)[1]
            await self._show_model_category(update, category)
            return

        if data.startswith("mod:"):
            alias = data.split(":", 1)[1]
            await self._select_model_and_confirm(update, alias)
            return

    async def _show_model_root_menu(self, update: Update) -> None:
        """Show the root model selection menu."""
        active_model = self.config.get_active_model()

        # Categories
        categories = [
            ("👨‍💻 Coding", "coding"),
            ("🧠 Reasoning", "reasoning"),
            ("⚡ Speed", "speed"),
            ("👁️ Vision", "vision"),
            ("💰 Free/Cheap", "cost_effective"),
            ("📦 All Models", "all"),
        ]

        buttons = []
        row = []
        for label, tag in categories:
            row.append(InlineKeyboardButton(label, callback_data=f"mcat:{tag}"))
            if len(row) == MODEL_MENU_BUTTONS_PER_ROW:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        text = (
            f"🧠 **Model Control Strategy**\n\n"
            f"Current Active Model:\n"
            f"🌟 **{active_model.alias}**\n"
            f"Testing: {active_model.name}\n"
            f"Provider: {active_model.provider}\n\n"
            f"👇 **Select a specialized fleet:**"
        )

        reply_markup = InlineKeyboardMarkup(buttons)
        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception:
            # Fallback if message is same
            pass

    async def _show_model_category(self, update: Update, category: str) -> None:
        """Show models in a specific category."""
        models = []
        active = (self.config.active_model or "").lower()

        # Filter models
        for m in self.config.models:
            if category == "all":
                models.append(m)
                continue

            # Feature matching
            has_feature = False
            if m.features and category in m.features:
                has_feature = True

            # Special logic for "free/cheap" if not explicitly tagged but low price
            if category == "cost_effective":
                if (m.input_price or 0) < CHEAP_MODEL_PRICE_THRESHOLD:
                    has_feature = True

            if has_feature:
                models.append(m)

        # Sort: Active first, then by alias
        models.sort(key=lambda x: (x.alias != active, x.alias))

        buttons = []
        for m in models:
            marker = "✅" if m.alias == active else ""
            label = f"{marker} {m.alias} [{m.provider}]"
            buttons.append([
                InlineKeyboardButton(label, callback_data=f"mod:{m.alias}")
            ])

        buttons.append([
            InlineKeyboardButton("🔙 Back to Fleets", callback_data="mmain")
        ])

        reply_markup = InlineKeyboardMarkup(buttons)

        cat_names = {
            "coding": "👨‍💻 Coding Specialists",
            "reasoning": "🧠 Reasoning Engines",
            "speed": "⚡ High Speed Models",
            "vision": "👁️ Multimodal/Vision",
            "cost_effective": "💰 High Efficiency",
            "all": "📦 All Available Models",
        }
        cat_title = cat_names.get(category, "Models")

        text = f"**{cat_title}**\nSelect a model to deploy:"

        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def _select_model_and_confirm(self, update: Update, alias: str) -> None:
        """Switch model and show confirmation."""
        # Find model
        model = next((m for m in self.config.models if m.alias == alias), None)
        if not model:
            await update.callback_query.answer("Model not found!", show_alert=True)
            return

        # Switch
        self.config.active_model = model.alias
        VibeConfig.save_updates({"active_model": model.alias})

        # Update sessions
        for session in self.sessions.values():
            session.config.active_model = model.alias
            session.agent.config.active_model = model.alias

        await update.callback_query.answer(f"Switched to {model.alias}")

        # Return to root menu to show updated status
        await self._show_model_root_menu(update)

    async def model_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /model commands in Telegram."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        args = [a.strip() for a in (context.args or []) if a.strip()]
        action = args[0].lower() if args else ""

        if action in {"list", "select", "status"}:
            # Legacy handling if user types specific args
            await self._legacy_model_handler(update, context, action, args[1:])
            return

        # Default: Show Interactive Menu
        active_model = self.config.get_active_model()

        # Categories
        categories = [
            ("👨‍💻 Coding", "coding"),
            ("🧠 Reasoning", "reasoning"),
            ("⚡ Speed", "speed"),
            ("👁️ Vision", "vision"),
            ("💰 Free/Cheap", "cost_effective"),
            ("📦 All Models", "all"),
        ]

        buttons = []
        row = []
        for label, tag in categories:
            row.append(InlineKeyboardButton(label, callback_data=f"mcat:{tag}"))
            if len(row) == MODEL_MENU_BUTTONS_PER_ROW:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        text = (
            f"🧠 **Model Control Strategy**\n\n"
            f"Current Active Model:\n"
            f"🌟 **{active_model.alias}**\n"
            f"Testing: {active_model.name}\n"
            f"Provider: {active_model.provider}\n\n"
            f"👇 **Select a specialized fleet:**"
        )

        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def _legacy_model_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        action: str,
        args: list[str],
    ) -> None:
        """Keep old logic for specific subcommands if needed."""
        if action == "list":
            await self._perform_model_list(update)
        elif action == "select":
            # Need to reconstruct args for helper
            full_args = ["select"] + args
            await self._perform_model_select(update, full_args)
        elif action == "status":
            # Just show status text, no menu
            active_model = self.config.get_active_model()
            provider = self.config.get_provider_for_model(active_model)
            await update.message.reply_text(
                "Current model:\n"
                f"• Alias: {active_model.alias}\n"
                f"• Provider: {provider.name}\n"
                f"• Model ID: {active_model.name}"
            )

    async def _handle_model_list(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'modellist' keyword."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        lines = ["Available models:"]
        active = (self.config.active_model or "").lower()
        for m in sorted(self.config.models, key=lambda x: x.alias):
            is_active = m.alias.lower() == active or m.name.lower() == active
            marker = "✅" if is_active else "•"
            lines.append(f"{marker} {m.alias} ({m.provider})")
        await update.message.reply_text("\n".join(lines))

    async def _handle_model_select_prompt(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'modelselect' keyword - prompt user for model name."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        await update.message.reply_text(
            "Please use: `/model select <alias>`\n\n"
            "Or type `modellist` to see available models.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

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

        chat_id = update.effective_chat.id
        session = self.sessions.get(chat_id)

        if not session:
            await update.message.reply_text("No active session. Send a message first!")
            return

        # Get current mode from agent's mode manager
        current_mode = (
            session.agent.mode_manager.current_mode.name
            if hasattr(session.agent, "mode_manager")
            else "NORMAL"
        )

        mode_text = (
            f"🎯 **Current Mode**: {current_mode}\n\n"
            "**Available Modes:**\n"
            "• plan - 📋 PLAN (read-only exploration)\n"
            "• normal - ✋ NORMAL (safe development)\n"
            "• auto - ⚡ AUTO (trusted automation)\n"
            "• yolo - 🚀 YOLO (maximum speed)\n"
            "• architect - 🏛️ ARCHITECT (high-level design)\n\n"
            "Type a mode name to switch (e.g., `auto`)"
        )

        await update.message.reply_text(
            mode_text, parse_mode=constants.ParseMode.MARKDOWN
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

        chat_id = update.effective_chat.id
        session = self.sessions.get(chat_id)

        if not session:
            await update.message.reply_text("No active session. Send a message first!")
            return

        try:
            # Switch mode via agent's mode manager
            if hasattr(session.agent, "mode_manager"):
                from chefchat.modes.types import VibeMode

                mode_enum = VibeMode[mode_name]
                session.agent.mode_manager.switch_mode(mode_enum)

                mode_emojis = {
                    "PLAN": "📋",
                    "NORMAL": "✋",
                    "AUTO": "⚡",
                    "YOLO": "🚀",
                    "ARCHITECT": "🏛️",
                }

                emoji = mode_emojis.get(mode_name, "🎯")
                await update.message.reply_text(
                    f"{emoji} **Switched to {mode_name} mode!**",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            else:
                await update.message.reply_text(
                    "Mode switching not available for this session."
                )
        except Exception as e:
            logger.exception("Failed to switch mode")
            await update.message.reply_text(f"❌ Failed to switch mode: {e}")

    async def term_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Start an interactive terminal session."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id

        # Get command from message
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
        success, message = self.terminal_manager.create_session(chat_id, command)

        await update.message.reply_text(
            message, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def termstatus_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show terminal session status."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id
        status = self.terminal_manager.get_session_status(chat_id)

        await update.message.reply_text(status, parse_mode=constants.ParseMode.MARKDOWN)

    async def termclose_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Close the active terminal session."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id
        message = self.terminal_manager.close_session(chat_id)

        await update.message.reply_text(message)

    async def _term_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, command: str
    ) -> None:
        """Start a terminal with a predefined command."""
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        chat_id = update.effective_chat.id
        success, message = self.terminal_manager.create_session(chat_id, command)

        await update.message.reply_text(
            message, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def _notify_startup(self) -> None:
        """Send startup notification to allowed users."""
        allowed = self.bot_manager.get_allowed_users("telegram")
        for user_id in allowed:
            try:
                if self.application:
                    await self.application.bot.send_message(
                        chat_id=int(user_id),
                        text=(
                            "🚀 **ChefChat Bot Started!**\n\n"
                            f"📁 Working directory: `{TELEGRAM_WORKDIR}`\n"
                            f"🔧 Type /help for commands"
                        ),
                        parse_mode=constants.ParseMode.MARKDOWN,
                    )
            except Exception as e:
                logger.warning(f"Could not notify user {user_id}: {e}")

    def _register_basic_handlers(self) -> None:
        """Register basic command handlers."""
        handlers = [
            ("start", self.start),
            ("stop", self.stop_command),
            ("clear", self.clear_command),
            ("status", self.status_command),
            ("files", self.files_command),
            ("pwd", self.pwd_command),
            ("help", self.help_command),
            ("model", self.model_command),
            ("mode", self.mode_command),
            ("chefchat", self.chefchat_command),
        ]
        for cmd, handler in handlers:
            self.application.add_handler(CommandHandler(cmd, handler))

    def _register_fun_handlers(self) -> None:
        """Register fun/easter egg command handlers."""
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
            self.application.add_handler(
                CommandHandler(cmd, lambda u, c, f=func: f(self, u, c))
            )

    def _register_model_handlers(self) -> None:
        """Register model-related command handlers."""
        self.application.add_handler(
            CommandHandler("modellist", lambda u, c: self._handle_model_list(u, c))
        )
        self.application.add_handler(
            CommandHandler(
                "modelselect", lambda u, c: self._handle_model_select_prompt(u, c)
            )
        )
        self.application.add_handler(CommandHandler("modelstatus", self.model_command))

    def _register_mode_handlers(self) -> None:
        """Register mode switch command handlers."""
        mode_commands = [
            ("plan", "PLAN"),
            ("normal", "NORMAL"),
            ("auto", "AUTO"),
            ("yolo", "YOLO"),
            ("architect", "ARCHITECT"),
        ]
        for cmd, mode in mode_commands:
            self.application.add_handler(
                CommandHandler(
                    cmd, lambda u, c, m=mode: self._handle_mode_switch(u, c, m)
                )
            )

    def _register_terminal_handlers(self) -> None:
        """Register terminal command handlers."""
        self.application.add_handler(CommandHandler("term", self.term_command))
        self.application.add_handler(
            CommandHandler("termstatus", self.termstatus_command)
        )
        self.application.add_handler(
            CommandHandler("termclose", self.termclose_command)
        )

        # Terminal shortcut commands
        shortcuts = [
            ("termbash", "bash"),
            ("termpython3", "python3"),
            ("termvim", "vim"),
            ("termnode", "node"),
            ("termnpm", "npm"),
        ]
        for cmd, shell_cmd in shortcuts:
            self.application.add_handler(
                CommandHandler(
                    cmd, lambda u, c, s=shell_cmd: self._term_shortcut(u, c, s)
                )
            )

    def _register_message_handlers(self) -> None:
        """Register message and callback handlers."""
        # Route unknown slash-commands into the normal chat pipeline
        self.application.add_handler(
            MessageHandler(filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_error_handler(self.error_handler)

    def _register_all_handlers(self) -> None:
        """Register all command, message, and callback handlers."""
        self._register_basic_handlers()
        self._register_fun_handlers()
        self._register_model_handlers()
        self._register_mode_handlers()
        self._register_terminal_handlers()
        self._register_message_handlers()

    async def _shutdown_gracefully(self, started: bool, polling: bool) -> None:
        """Gracefully shutdown the application."""
        try:
            if self.application is not None and polling:
                await self.application.updater.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Telegram updater stop failed: %s", e)

        try:
            if self.application is not None and started:
                await self.application.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Telegram application stop failed: %s", e)

        try:
            if self.application is not None:
                await self.application.shutdown()
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
            await self.application.initialize()
            await self.application.start()
            started = True
            await self.application.updater.start_polling(drop_pending_updates=True)
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

            expired_short_ids = [
                short_id
                for short_id, created in self._approval_created_at.items()
                if (now - created) > self._approval_ttl_s
            ]
            for short_id in expired_short_ids:
                self._approval_created_at.pop(short_id, None)
                self.approval_map.pop(short_id, None)


async def run_telegram_bot(config: VibeConfig) -> None:
    service = TelegramBotService(config)
    await service.run()
