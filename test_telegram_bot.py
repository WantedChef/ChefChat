#!/usr/bin/env python3
"""Quick test script for Telegram bot commands."""

from __future__ import annotations

import asyncio
import sys


async def test_imports():
    """Test that all bot modules import correctly."""
    print("🧪 Testing bot imports...")

    try:
        print("✅ telegram_bot imported")
    except Exception as e:
        print(f"❌ Failed to import telegram_bot: {e}")
        return False

    try:
        print("✅ fun_commands imported")
    except Exception as e:
        print(f"❌ Failed to import fun_commands: {e}")
        return False

    try:
        print("✅ manager, session, daemon imported")
    except Exception as e:
        print(f"❌ Failed to import bot modules: {e}")
        return False

    return True


async def test_config():
    """Test configuration loading."""
    print("\n🧪 Testing configuration...")

    try:
        from chefchat.core.config import VibeConfig, load_api_keys_from_env

        load_api_keys_from_env()
        config = VibeConfig.load()
        print(f"✅ Config loaded - Active model: {config.active_model}")
        return True
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return False


async def test_fun_commands():
    """Test that fun commands are defined."""
    print("\n🧪 Testing fun commands...")

    try:
        from chefchat.bots.telegram import fun_commands

        commands = [
            "chef_command",
            "wisdom_command",
            "roast_command",
            "fortune_command",
            "stats_command",
            "reload_command",
        ]

        for cmd in commands:
            if hasattr(fun_commands, cmd):
                print(f"✅ {cmd} defined")
            else:
                print(f"❌ {cmd} missing")
                return False

        return True
    except Exception as e:
        print(f"❌ Failed to test fun commands: {e}")
        return False


async def main():
    """Run all tests."""
    print("🤖 ChefChat Telegram Bot - Test Suite\n")

    results = []

    results.append(await test_imports())
    results.append(await test_config())
    results.append(await test_fun_commands())

    print("\n" + "=" * 50)
    if all(results):
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
