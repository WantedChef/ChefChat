"""Fun easter egg commands for Telegram bot."""

from __future__ import annotations

import logging
from pathlib import Path
import random
import subprocess
from typing import TYPE_CHECKING

from telegram import Update, constants
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService

logger = logging.getLogger(__name__)

# Telegram bot working directory
TELEGRAM_WORKDIR = Path.home() / "chefchat_output_"


async def chef_command(
    bot_service: TelegramBotService, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show kitchen status report with session stats."""
    user = update.effective_user
    if not user:
        return

    user_id_str = str(user.id)
    allowed = bot_service.bot_manager.get_allowed_users("telegram")
    if user_id_str not in allowed:
        await update.message.reply_text("Access denied.")
        return

    chat_id = update.effective_chat.id
    session = bot_service.sessions.get(chat_id)

    uptime = "Unknown"
    try:
        result = subprocess.run(
            ["uptime", "-p"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            uptime = result.stdout.strip()
    except Exception:
        pass

    if session:
        # Get session stats
        msg_count = len(session.agent.messages)
        status_text = (
            f"👨‍🍳 **Chef's Kitchen Report**\\n\\n"
            f"🔥 Station: Active\\n"
            f"⏱️ Uptime: {uptime}\\n"
            f"💬 Messages: {msg_count}\\n"
            f"📁 Workdir: `{TELEGRAM_WORKDIR}`\\n\\n"
            f"*'Mise en place, chef!'* 🍽️"
        )
    else:
        status_text = (
            f"👨‍🍳 **Chef's Kitchen Report**\\n\\n"
            f"🔥 Station: Ready\\n"
            f"⏱️ Uptime: {uptime}\\n"
            f"💬 No active session\\n"
            f"📁 Workdir: `{TELEGRAM_WORKDIR}`\\n\\n"
            f"*Send a message to start cooking!* 🍳"
        )

    await update.message.reply_text(
        status_text, parse_mode=constants.ParseMode.MARKDOWN
    )


async def wisdom_command(
    bot_service: TelegramBotService, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Share culinary-inspired programming wisdom."""
    wisdoms = [
        "🔪 *Sharp tools make clean cuts.* Keep your dependencies updated.",
        "🍲 *Low and slow wins the race.* Take time for quality refactoring.",
        "📋 *Mise en place before you code.* Plan before you implement.",
        "🧂 *Season to taste.* Configuration should be flexible.",
        "🔥 *Control your heat.* Manage your compute resources wisely.",
        "👨‍🍳 *A chef is only as good as their ingredients.* Quality input = quality output.",
        "🍽️ *Presentation matters.* Write code that others enjoy reading.",
        "⏰ *Timing is everything.* Async when needed, sync when simple.",
        "🥘 *Layer your flavors.* Build abstractions thoughtfully.",
        "🧹 *Clean as you go.* Refactor continuously, not just at the end.",
    ]

    wisdom = random.choice(wisdoms)
    await update.message.reply_text(wisdom, parse_mode=constants.ParseMode.MARKDOWN)


async def roast_command(
    bot_service: TelegramBotService, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Gordon Ramsay style motivational burns."""
    roasts = [
        "🔥 *This code is so raw, it's still importing dependencies!*",
        "😤 *You call that a function? My grandmother writes better code, and she's been dead for 20 years!*",
        "💀 *This spaghetti code is an insult to Italian cuisine!*",
        "🤬 *What are you? An idiot sandwich? Use proper error handling!*",
        "😡 *This code is drier than the Sahara! Add some comments!*",
        "🎭 *You're cooking up bugs faster than a Michelin star restaurant serves courses!*",
        "⚡ *This performance is slower than a snail on vacation! Optimize it!*",
        "🗑️ *This code belongs in the bin, not in production!*",
        "😱 *You've got more technical debt than a bankrupt restaurant!*",
        "🔪 *Sharp code, sharp mind. Yours is duller than a butter knife!*",
    ]

    roast = random.choice(roasts)
    await update.message.reply_text(roast, parse_mode=constants.ParseMode.MARKDOWN)


async def fortune_command(
    bot_service: TelegramBotService, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Developer fortune cookies."""
    fortunes = [
        "🥠 *A bug fixed today is a feature tomorrow.*",
        "🥠 *Your next commit will bring great joy to code reviewers.*",
        "🥠 *The best code is code not written. But you still have to write some.*",
        "🥠 *In the kitchen of development, you are the head chef.*",
        "🥠 *Your tests will pass on the first try... eventually.*",
        "🥠 *Refactoring brings clarity, like a well-organized spice rack.*",
        "🥠 *The merge conflict you fear will resolve itself gracefully.*",
        "🥠 *Your documentation will be read and appreciated by future you.*",
        "🥠 *The production deploy will go smoothly. Trust the process.*",
        "🥠 *Your code review comments will be constructive and well-received.*",
    ]

    fortune = random.choice(fortunes)
    await update.message.reply_text(fortune, parse_mode=constants.ParseMode.MARKDOWN)


async def stats_command(
    bot_service: TelegramBotService, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show detailed session statistics."""
    user = update.effective_user
    if not user:
        return

    user_id_str = str(user.id)
    allowed = bot_service.bot_manager.get_allowed_users("telegram")
    if user_id_str not in allowed:
        await update.message.reply_text("Access denied.")
        return

    chat_id = update.effective_chat.id
    session = bot_service.sessions.get(chat_id)

    if not session:
        await update.message.reply_text(
            "📊 No active session. Send a message to start!"
        )
        return

    # Get detailed stats
    msg_count = len(session.agent.messages)

    # Count tool calls
    tool_calls = 0
    for msg in session.agent.messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls += len(msg.tool_calls)

    stats_text = (
        f"📊 **Session Statistics**\\n\\n"
        f"💬 Total messages: {msg_count}\\n"
        f"🔧 Tool calls: {tool_calls}\\n"
        f"🤖 Model: {session.config.active_model}\\n"
        f"📁 Working dir: `{TELEGRAM_WORKDIR}`\\n"
    )

    await update.message.reply_text(stats_text, parse_mode=constants.ParseMode.MARKDOWN)


async def reload_command(
    bot_service: TelegramBotService, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Reload bot configuration (hot-reload)."""
    user = update.effective_user
    if not user:
        return

    user_id_str = str(user.id)
    allowed = bot_service.bot_manager.get_allowed_users("telegram")
    if user_id_str not in allowed:
        await update.message.reply_text("Access denied.")
        return

    try:
        # Reload config
        from chefchat.core.config import VibeConfig, load_api_keys_from_env

        load_api_keys_from_env()
        new_config = VibeConfig.load()
        bot_service.config = new_config

        # Update bot manager config
        bot_service.bot_manager.config = new_config

        # Update all active sessions with new config
        for session in bot_service.sessions.values():
            session.config = new_config
            session.agent.config = new_config

        await update.message.reply_text(
            "🔄 **Configuration reloaded!**\\n\\n"
            f"Active model: {new_config.active_model}\\n"
            f"Active sessions updated: {len(bot_service.sessions)}",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.exception("Failed to reload config")
        await update.message.reply_text(f"❌ Reload failed: {e}")
