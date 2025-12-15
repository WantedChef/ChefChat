"""ChefChat Bot Daemon - Lightweight Entry Point."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import signal
import sys
from typing import NoReturn

from chefchat.bots.manager import BotManager
from chefchat.core.config import VibeConfig, load_api_keys_from_env

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("chefchat.bots.daemon")


def _setup_working_directory() -> None:
    """Change to designated output directory if it exists."""
    output_dir = Path("/home/chef/chefchat_output_")
    if output_dir.exists() and output_dir.is_dir():
        try:
            os.chdir(output_dir)
            logger.info(f"Working directory: {output_dir}")
        except OSError as e:
            logger.warning(f"Could not change to {output_dir}: {e}")


def _load_config() -> VibeConfig:
    """Load configuration or exit on failure."""
    try:
        load_api_keys_from_env()
        return VibeConfig.load()
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)


async def _start_enabled_bots(manager: BotManager) -> bool:
    """Start all enabled bots based on available tokens.

    Returns True if at least one bot was started.
    """
    bots_to_start = [
        ("telegram", "TELEGRAM_BOT_TOKEN"),
        ("discord", "DISCORD_BOT_TOKEN"),
    ]

    started_any = False
    for bot_name, token_env in bots_to_start:
        if os.getenv(token_env):
            started_any |= await _start_single_bot(manager, bot_name)

    return started_any


async def _start_single_bot(manager: BotManager, bot_name: str) -> bool:
    """Start a single bot, return True on success."""
    try:
        logger.info(f"Starting {bot_name.title()} Bot...")
        await manager.start_bot(bot_name)
        return True
    except Exception as e:
        logger.error(f"Failed to start {bot_name.title()} bot: %s", e)
        return False


async def _stop_running_bots(manager: BotManager) -> None:
    """Stop all running bots."""
    for bot_name in ["telegram", "discord"]:
        if manager.is_running(bot_name):
            await manager.stop_bot(bot_name)


def _setup_signal_handlers(stop_event: asyncio.Event) -> None:
    """Setup graceful shutdown signal handlers."""

    def _handle_stop(sig: int, _frame: object) -> None:
        logger.info("Received signal %s. Stopping...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)


async def run_daemon() -> None:
    """Run the ChefChat bots in daemon mode."""
    logger.info("Starting ChefChat Bot Daemon...")

    _setup_working_directory()
    config = _load_config()
    manager = BotManager(config)

    started_any = await _start_enabled_bots(manager)

    if not started_any:
        logger.warning(
            "No bots started. Please set TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN."
        )
        sys.exit(1)

    logger.info("ChefChat Bot Daemon is running. Press Ctrl+C to stop.")

    stop_event = asyncio.Event()
    _setup_signal_handlers(stop_event)

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down bots...")
        await _stop_running_bots(manager)
        logger.info("Daemon stopped.")


def main() -> NoReturn:
    """Entry point."""
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical("Daemon crash: %s", e)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
