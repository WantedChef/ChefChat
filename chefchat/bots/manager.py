from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import set_key

from chefchat.core.config import VibeConfig


class BotManager:
    """Manages the lifecycle and configuration of ChefChat bots."""

    def __init__(self, config: VibeConfig) -> None:
        self.config = config
        self.running_tasks: dict[str, asyncio.Task] = {}
        self.bots: dict[str, Any] = {}  # Store bot instances

    def is_running(self, bot_type: str) -> bool:
        """Check if a bot is currently running."""
        return bot_type in self.running_tasks and not self.running_tasks[bot_type].done()

    async def start_bot(self, bot_type: str) -> None:
        """Start a bot (telegram or discord)."""
        if self.is_running(bot_type):
            raise RuntimeError(f"{bot_type} bot is already running.")

        if bot_type == "telegram":
            from chefchat.bots.telegram import run_telegram_bot
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not token:
                raise ValueError("TELEGRAM_BOT_TOKEN not found in environment.")

            # We create a task that runs the bot
            # The bot runner should handle its own loop or be compatible with the current loop
            task = asyncio.create_task(run_telegram_bot(self.config))
            self.running_tasks["telegram"] = task

        elif bot_type == "discord":
            from chefchat.bots.discord_bot import run_discord_bot
            token = os.getenv("DISCORD_BOT_TOKEN")
            if not token:
                raise ValueError("DISCORD_BOT_TOKEN not found in environment.")

            task = asyncio.create_task(run_discord_bot(self.config))
            self.running_tasks["discord"] = task
        else:
            raise ValueError(f"Unknown bot type: {bot_type}")

    async def stop_bot(self, bot_type: str) -> None:
        """Stop a running bot."""
        if not self.is_running(bot_type):
            return

        task = self.running_tasks[bot_type]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            del self.running_tasks[bot_type]
            if bot_type in self.bots:
                # If the bot instance needs explicit closing, do it here
                # (We'll need to expose the bot instance from the runner)
                pass

    def update_env(self, key: str, value: str) -> None:
        """Update a key in the .env file."""
        env_path = Path(".env")
        if not env_path.exists():
            env_path.touch()

        set_key(str(env_path), key, value)
        os.environ[key] = value

    def add_allowed_user(self, bot_type: str, user_id: str) -> None:
        """Add a user ID to the allowlist."""
        key = f"{bot_type.upper()}_ALLOWED_USERS"
        current = os.getenv(key, "")
        users = [u.strip() for u in current.split(",") if u.strip()]

        if user_id not in users:
            users.append(user_id)
            self.update_env(key, ",".join(users))

    def get_allowed_users(self, bot_type: str) -> list[str]:
        """Get list of allowed user IDs."""
        key = f"{bot_type.upper()}_ALLOWED_USERS"
        current = os.getenv(key, "")
        return [u.strip() for u in current.split(",") if u.strip()]
