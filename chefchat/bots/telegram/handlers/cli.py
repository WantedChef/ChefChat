from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from chefchat.bots.telegram.cli_providers import CLI_PROVIDERS

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService


class CLIHandlers:
    """CLI provider command handlers."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc

    async def cli_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id

        if not context.args:
            available = self.svc.cli_manager.get_available_providers()
            if not available:
                await self.svc._send_message(chat_id, "❌ No CLI providers available.")
                return

            text = "**Available CLI Providers:**\n\n"
            for p in available:
                text += f"{p.icon} `{p.command}` - {p.description}\n"
            text += "\nUsage: `/cli <provider>`"
            await self.svc._send_message(chat_id, text)
            return

        provider_name = context.args[0].lower()
        success, message = self.svc.cli_manager.set_active_provider(
            chat_id, provider_name
        )
        await self.svc._send_message(chat_id, message)

    async def cli_close_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        message = self.svc.cli_manager.close_session(chat_id)
        await self.svc._send_message(chat_id, message)

    async def cli_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        message = self.svc.cli_manager.get_session_status(chat_id)
        await self.svc._send_message(chat_id, message)

    async def cli_providers_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id

        text = "**CLI Providers:**\n\n"
        for provider in CLI_PROVIDERS.values():
            status = "✅ Installed" if provider.is_available() else "❌ Not found"
            text += f"{provider.icon} **{provider.name}**\n"
            text += f"   Command: `{provider.command}`\n"
            text += f"   Status: {status}\n\n"

        await self.svc._send_message(chat_id, text)

    async def cli_run_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        if not context.args:
            await self.svc._send_message(
                chat_id,
                "Usage: `/clirun <provider?> <prompt>`\n"
                "Example: `/clirun gemini summarize README.md`",
            )
            return

        provider_key = None
        args = context.args
        if args and args[0].lower() in CLI_PROVIDERS:
            provider_key = args[0].lower()
            args = args[1:]

        prompt = " ".join(args).strip()
        if not prompt:
            await self.svc._send_message(chat_id, "❌ No prompt provided.")
            return

        await self.svc._send_message(chat_id, "⏳ Running CLI request...")
        output = await self.svc.cli_manager.execute_prompt(
            chat_id, prompt, provider_override=provider_key, persist=bool(provider_key)
        )
        await self.svc._send_message(chat_id, output)

    async def cli_cancel_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        message = self.svc.cli_manager.cancel(chat_id)
        await self.svc._send_message(chat_id, message)

    async def cli_history_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        if context.args and context.args[0].lower() == "clear":
            await self.svc._send_message(
                chat_id, self.svc.cli_manager.clear_history(chat_id)
            )
            return
        await self.svc._send_message(chat_id, self.svc.cli_manager.get_history(chat_id))

    async def cli_diag_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        diag = await self.svc.cli_manager.get_diagnostics()
        await self.svc._send_message(chat_id, diag)

    async def cli_setup_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        await self.svc._send_message(chat_id, self.svc.cli_manager.get_setup_help())

    async def cli_retry_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        last = self.svc.cli_manager.get_last_prompt(chat_id)
        if not last:
            await self.svc._send_message(chat_id, "ℹ️ No previous CLI prompt to retry.")
            return

        provider_key, provider_name, prompt = last
        await self.svc._send_message(
            chat_id, f"⏳ Retrying with {provider_name}...\nPrompt: {prompt[:200]}"
        )
        override = provider_key.lower() if provider_key else None
        output = await self.svc.cli_manager.execute_prompt(
            chat_id, prompt, provider_override=override, persist=bool(override)
        )
        await self.svc._send_message(chat_id, output)

    async def cli_shortcut(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, provider_name: str
    ) -> None:
        chat = update.effective_chat
        if not chat:
            return
        chat_id = chat.id
        success, message = self.svc.cli_manager.set_active_provider(
            chat_id, provider_name
        )
        await self.svc._send_message(chat_id, message)
