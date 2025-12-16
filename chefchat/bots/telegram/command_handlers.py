from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from chefchat.bots.telegram import fun_commands

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class CommandHandlers:  # noqa: PLR0904
    """Command handlers extracted from TelegramBotService."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc

    async def clear_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat or not update.message:
            return

        session = self.svc._get_session(chat.id, str(user.id))
        if not session:
            await self.svc.start(update, context)
            return

        await session.clear_history()
        await update.message.reply_text("🧹 History cleared.")

    async def context_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.context_handlers.context_command(update, context)

    async def chefchat_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.admin.chefchat_command(update, context)

    async def git_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.admin.git_command(update, context)

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.core.status_command(update, context)

    async def api_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.core.api_command(update, context)

    async def stop_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.core.stop_command(update, context)

    async def files_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.core.files_command(update, context)

    async def pwd_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.core.pwd_command(update, context)

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.core.help_command(update, context)

    async def model_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.models.model_command(update, context)

    async def handle_model_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.models._handle_model_callback(update, context)

    async def model_refresh_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.models.model_refresh_command(update, context)

    async def mode_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc._render_mode_status(update, context)

    async def handle_mode_switch(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, mode_name: str
    ) -> None:
        await self.svc._handle_mode_switch(update, context, mode_name)

    async def botmode_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.policy.botmode_command(update, context)

    async def handle_botmode_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, policy: str
    ) -> None:
        await self.svc._handle_botmode_shortcut(update, context, policy)

    async def handle_botmode_callback(
        self, update: Update, data: str
    ) -> None:
        await self.svc.policy.handle_callback(update, data)

    async def term_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.term_handlers.term_command(update, context)

    async def termstatus_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.term_handlers.termstatus_command(update, context)

    async def termclose_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.term_handlers.termclose_command(update, context)

    async def term_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, cmd: str
    ) -> None:
        await self.svc.term_handlers.term_shortcut(update, context, cmd)

    async def term_switch_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.term_handlers.term_switch_command(update, context)

    async def term_upload_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.term_handlers.term_upload_command(update, context)

    async def cli_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_command(update, context)

    async def cli_close_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_close_command(update, context)

    async def cli_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_status_command(update, context)

    async def cli_providers_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_providers_command(update, context)

    async def cli_run_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_run_command(update, context)

    async def cli_cancel_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_cancel_command(update, context)

    async def cli_history_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_history_command(update, context)

    async def cli_diag_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_diag_command(update, context)

    async def cli_setup_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_setup_command(update, context)

    async def cli_retry_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.cli_handlers.cli_retry_command(update, context)

    async def task_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.svc.task_handlers.task_command(update, context)

    async def cli_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, provider_name: str
    ) -> None:
        await self.svc.cli_handlers.cli_shortcut(update, context, provider_name)

    # Fun commands proxied to existing module
    async def chef_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await fun_commands.chef_command(self.svc, update, context)

    async def wisdom_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await fun_commands.wisdom_command(self.svc, update, context)

    async def roast_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await fun_commands.roast_command(self.svc, update, context)

    async def fortune_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await fun_commands.fortune_command(self.svc, update, context)

    async def reload_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await fun_commands.reload_command(self.svc, update, context)

    async def stats_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await fun_commands.stats_command(self.svc, update, context)

    async def mode_status_inline(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.mode_command(update, context)
