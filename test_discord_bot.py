#!/usr/bin/env python3
"""Test Discord bot imports and basic functionality."""

from __future__ import annotations

from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def test_imports() -> bool:
    """Test all Discord bot imports."""
    print("🧪 Testing Discord bot imports...")

    try:
        from chefchat.bots.discord.bot import (  # noqa: F401
            DiscordBotService,
            run_discord_bot,
        )

        print("✅ Main bot module imported")
    except ImportError as e:
        print(f"❌ Failed to import main bot: {e}")
        return False

    try:
        from chefchat.bots.discord.handlers.admin import AdminHandlers  # noqa: F401

        print("✅ Admin handlers imported")
    except ImportError as e:
        print(f"❌ Failed to import admin handlers: {e}")
        return False

    try:
        from chefchat.bots.discord.handlers.model import ModelHandlers  # noqa: F401

        print("✅ Model handlers imported")
    except ImportError as e:
        print(f"❌ Failed to import model handlers: {e}")
        return False

    try:
        from chefchat.bots.discord.handlers.terminal import (
            TerminalHandlers,  # noqa: F401
        )

        print("✅ Terminal handlers imported")
    except ImportError as e:
        print(f"❌ Failed to import terminal handlers: {e}")
        return False

    try:
        from chefchat.bots.terminal import TerminalManager  # noqa: F401

        print("✅ Shared TerminalManager imported")
    except ImportError as e:
        print(f"❌ Failed to import TerminalManager: {e}")
        return False

    print("\n🎉 All imports successful!")
    return True


def test_telegram_still_works() -> bool:
    """Verify Telegram bot still works after refactoring."""
    print("\n🧪 Testing Telegram bot compatibility...")

    try:
        from chefchat.bots.telegram.telegram_bot import TelegramBotService  # noqa: F401

        print("✅ Telegram bot still imports correctly")
        return True
    except ImportError as e:
        print(f"❌ Telegram bot broken: {e}")
        return False


if __name__ == "__main__":
    success = test_imports() and test_telegram_still_works()

    if success:
        print("\n✨ Discord bot is ready to use!")
        print("\n📝 Next steps:")
        print("1. Set DISCORD_BOT_TOKEN in your .env file")
        print("2. Add your Discord user ID to DISCORD_ALLOWED_USERS")
        print("3. Run: python -m chefchat.cli bot discord")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        sys.exit(1)
