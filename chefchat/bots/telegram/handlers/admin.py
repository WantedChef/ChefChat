from __future__ import annotations

import os
import shlex
from typing import TYPE_CHECKING

from telegram import Update, constants
from telegram.ext import ContextTypes

from chefchat.kitchen.stations.git_chef import GitCommandValidator

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class AdminHandlers:
    """Admin/systemd/git handlers."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc
        self._override_sessions = False

    async def chefchat_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self.svc._enable_systemd_control:
            if update.message:
                await update.message.reply_text(
                    "This command is disabled on this server."
                )
            return

        user = update.effective_user
        if not user:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            if update.message:
                await update.message.reply_text("Access denied.")
            return

        if not context.args:
            await self._show_chefchat_help(update)
            return

        action = context.args[0].strip().lower()
        await self._dispatch_chefchat_action(update, context, action)

    async def _show_chefchat_help(self, update: Update) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "Usage:\n"
            "/chefchat status\n"
            "/chefchat start\n"
            "/chefchat stop\n"
            "/chefchat restart\n"
            "/chefchat projects\n"
            "/chefchat switch <project>\n"
            "/chefchat miniapp <start|stop|restart|status> [project]\n"
            "/chefchat tunnel <start|stop|restart|status> [project]\n"
            "/chefchat override <on|off>  (bypass session limits)"
        )

    async def _dispatch_chefchat_action(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str
    ) -> None:
        if action in {"miniapp", "tunnel"}:
            await self._handle_service_action(update, context, action)
        elif action == "projects":
            await self._handle_projects_action(update)
        elif action == "switch":
            await self._handle_switch_action(update, context)
        elif action in {"start", "stop", "restart", "status"}:
            await self._handle_systemd_action(update, action)
        elif action == "override":
            await self._handle_override(update, context)
        elif update.message:
            await update.message.reply_text("Unknown action.")

    async def _handle_override(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        MIN_OVERRIDE_ARGS = 2
        args = context.args or []
        if len(args) < MIN_OVERRIDE_ARGS:
            if update.message:
                await update.message.reply_text(
                    f"Override sessions: {'ON' if self.svc.session_limit_override else 'OFF'}\n"
                    "Usage: /chefchat override <on|off>"
                )
            return
        val = args[1].lower()
        if val not in {"on", "off"}:
            if update.message:
                await update.message.reply_text("Use on/off.")
            return
        self.svc.session_limit_override = val == "on"
        if update.message:
            await update.message.reply_text(
                f"Session limit override: {'ON' if self.svc.session_limit_override else 'OFF'}"
            )

    async def _handle_service_action(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str
    ) -> None:
        if not update.message:
            return

        args = context.args or []
        if len(args) < self.svc.MIN_COMMAND_ARGS_MINIAPP:
            await update.message.reply_text(
                f"Usage: /chefchat {action} <start|stop|restart|status> [project]"
            )
            return

        sub_action = args[1].strip().lower()
        if sub_action not in {"start", "stop", "restart", "status"}:
            await update.message.reply_text("Unknown action.")
            return

        project = (
            args[2].strip()
            if len(args) >= self.svc.MIN_COMMAND_ARGS_SWITCH
            else "chefchat"
        )
        if self.svc._allowed_projects and project not in self.svc._allowed_projects:
            await update.message.reply_text("Unknown project.")
            return

        unit_base = "chefchat-miniapp" if action == "miniapp" else "chefchat-tunnel"
        unit = f"{unit_base}@{project}.service"
        ok, out = await self.svc._systemctl_user([sub_action, unit])
        await update.message.reply_text(out if ok else f"Failed: {out}")

    async def _handle_projects_action(self, update: Update) -> None:
        if not update.message:
            return
        projects = (
            ", ".join(self.svc._allowed_projects)
            if self.svc._allowed_projects
            else "(none configured)"
        )
        await update.message.reply_text(f"Projects: {projects}")

    async def _handle_switch_action(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return

        args = context.args or []
        if len(args) < self.svc.MIN_COMMAND_ARGS_MINIAPP:
            await update.message.reply_text("Usage: /chefchat switch <project>")
            return

        project = args[1].strip()
        if self.svc._allowed_projects and project not in self.svc._allowed_projects:
            await update.message.reply_text("Unknown project.")
            return

        unit = f"{self.svc._systemd_unit_base}@{project}.service"
        ok, out = await self.svc._systemctl_user(["restart", unit])
        await update.message.reply_text(out if ok else f"Failed: {out}")

    async def _handle_systemd_action(self, update: Update, action: str) -> None:
        if not update.message:
            return
        unit = f"{self.svc._systemd_unit_base}.service"
        ok, out = await self.svc._systemctl_user([action, unit])
        await update.message.reply_text(out if ok else f"Failed: {out}")

    async def git_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user:
            return

        user_id_str = str(user.id)
        if user_id_str not in self.svc.bot_manager.get_allowed_users("telegram"):
            if update.message:
                await update.message.reply_text("Access denied.")
            return

        if not update.message:
            return

        raw_args = ""
        if context.args:
            raw_args = " ".join(context.args)
        elif update.message and update.message.text:
            text = update.message.text.strip()
            if text.lower().startswith("git "):
                raw_args = text[4:].strip()

        if not raw_args:
            await update.message.reply_text(
                "Usage: /git <command> (e.g., status, log, diff)"
            )
            return

        validated_args = GitCommandValidator.parse_and_validate(raw_args)
        if validated_args is None:
            await update.message.reply_text("❌ Invalid or unsafe git command.")
            return

        await update.message.reply_text(f"🔧 Running git {validated_args[1]}...")

        try:
            safe_command = " ".join(shlex.quote(arg) for arg in validated_args)

            env = {}
            if token := os.environ.get("GITHUB_TOKEN"):
                env["GITHUB_TOKEN"] = token

            stdout, stderr, returncode = await self.svc.executor.execute(
                safe_command, timeout=30, env=env
            )

            output = (stdout if stdout else stderr).strip()
            if not output:
                output = "(No output)"

            icon = "✅" if returncode == 0 else "❌"
            header = f"{icon} Git {validated_args[1]} finished (code {returncode})"

            if len(output) > self.svc.GIT_OUTPUT_MAX_LEN:
                output = output[: self.svc.GIT_OUTPUT_MAX_LEN] + "\n...(truncated)"

            await update.message.reply_text(
                f"**{header}**\n```\n{output}\n```",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error executing git: {e}")
