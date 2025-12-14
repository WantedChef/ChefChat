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


async def run_daemon() -> None:
    """Run the ChefChat bots in daemon mode."""
    logger.info("Starting ChefChat Bot Daemon...")

    # Change to designated output directory if it exists
    output_dir = Path("/home/chef/chefchat_output_")
    if output_dir.exists() and output_dir.is_dir():
        try:
            os.chdir(output_dir)
            logger.info(f"Working directory: {output_dir}")
        except OSError as e:
            logger.warning(f"Could not change to {output_dir}: {e}")

    try:
        load_api_keys_from_env()
        config = VibeConfig.load()
    except Exception as e:
        logger.error("Failed to load configuration: %s", e)
        sys.exit(1)

    manager = BotManager(config)

    # Detect enabled bots
    # We check if tokens are present in env
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    discord_token = os.getenv("DISCORD_BOT_TOKEN")

    started_any = False

    if telegram_token:
        try:
            logger.info("Starting Telegram Bot...")
            await manager.start_bot("telegram")
            started_any = True
        except Exception as e:
            logger.error("Failed to start Telegram bot: %s", e)

    if discord_token:
        try:
            logger.info("Starting Discord Bot...")
            await manager.start_bot("discord")
            started_any = True
        except Exception as e:
            logger.error("Failed to start Discord bot: %s", e)

    if not started_any:
        logger.warning(
            "No bots started. Please set TELEGRAM_BOT_TOKEN or DISCORD_BOT_TOKEN."
        )
        sys.exit(1)

    logger.info("ChefChat Bot Daemon is running. Press Ctrl+C to stop.")

    # Graceful shutdown handler
    stop_event = asyncio.Event()

    def _handle_stop(sig: int, frame: object) -> None:
        logger.info("Received signal %s. Stopping...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    # Wait until stopped
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down bots...")
        if manager.is_running("telegram"):
            await manager.stop_bot("telegram")
        if manager.is_running("discord"):
            await manager.stop_bot("discord")
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
