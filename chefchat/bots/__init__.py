"""ChefChat Bots module.

This module contains the implementation for Telegram and Discord bots,
as well as the logic to bridge them with the ChefChat Agent.

Note: Bot functionality requires optional dependencies:
    - python-telegram-bot>=22.5 (for Telegram)
    - discord.py>=2.6.4 (for Discord)

Install with: pip install python-telegram-bot discord.py
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

# Core bot infrastructure (always available)
from chefchat.bots.manager import BotManager
from chefchat.bots.session import BotSession

__all__ = ["BotManager", "BotSession", "run_discord_bot", "run_telegram_bot"]


def run_telegram_bot(*args: Any, **kwargs: Any) -> Coroutine[Any, Any, None]:
    """Run the Telegram bot. Requires python-telegram-bot package."""
    try:
        from chefchat.bots.telegram import run_telegram_bot as _run
    except ImportError as e:
        raise ImportError(
            "Telegram bot requires 'python-telegram-bot' package. "
            "Install with: pip install python-telegram-bot"
        ) from e
    return _run(*args, **kwargs)


def run_discord_bot(*args: Any, **kwargs: Any) -> Coroutine[Any, Any, None]:
    """Run the Discord bot. Requires discord.py package."""
    try:
        from chefchat.bots.discord_bot import run_discord_bot as _run
    except ImportError as e:
        raise ImportError(
            "Discord bot requires 'discord.py' package. "
            "Install with: pip install discord.py"
        ) from e
    return _run(*args, **kwargs)
