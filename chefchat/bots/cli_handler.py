import asyncio
from typing import Any

from rich.console import Console
from rich.panel import Panel

from chefchat.bots.manager import BotManager

async def handle_bot_command(repl: Any, command: str) -> None:
    """
    Handles /telegram and /discord commands from the REPL.
    """
    parts = command.strip().split()
    if not parts:
        return

    bot_type = parts[0][1:]  # telegram or discord
    action = parts[1] if len(parts) > 1 else "help"

    # Persist manager on the REPL instance
    if not hasattr(repl, "bot_manager"):
        repl.bot_manager = BotManager(repl.config)
    manager = repl.bot_manager

    console: Console = repl.console

    if action == "help":
        console.print(Panel(f"""
[bold]🤖 {bot_type.title()} Bot Integration[/bold]

Commands:
  /{bot_type} setup         - Walkthrough to set up the bot
  /{bot_type} start         - Start the bot (background)
  /{bot_type} stop          - Stop the bot
  /{bot_type} status        - Check status
  /{bot_type} allow <id>    - Allow a user ID
  /{bot_type} token <tok>   - Manually set token
        """, title="Help", expand=False))
        return

    if action == "setup":
        console.print(f"[bold]🛠️  {bot_type.title()} Setup[/bold]")
        console.print("I will guide you through setting up the bot.")

        # Ask for token
        console.print(f"\n1. Please enter your {bot_type.title()} Bot Token:")
        try:
            token = await repl.session.prompt_async("> ", is_password=True)
        except (EOFError, KeyboardInterrupt):
            console.print("[red]Cancelled.[/]")
            return

        if token.strip():
            manager.update_env(f"{bot_type.upper()}_BOT_TOKEN", token.strip())
            console.print("[green]Token saved![/]")
        else:
            console.print("[yellow]Skipped token update.[/]")

        # Ask for allowed user
        console.print(f"\n2. (Optional) Enter your User ID to allow access immediately:")
        try:
            user_id = await repl.session.prompt_async("> ")
        except (EOFError, KeyboardInterrupt):
            return

        if user_id.strip():
            manager.add_allowed_user(bot_type, user_id.strip())
            console.print(f"[green]User {user_id} allowed![/]")

        console.print(f"\n[bold]Setup complete![/bold] Run `/{bot_type} start` to launch.")

    elif action == "token":
        if len(parts) < 3:
            console.print("[red]Usage: token <token_value>[/]")
            return
        token = parts[2]
        manager.update_env(f"{bot_type.upper()}_BOT_TOKEN", token)
        console.print(f"[green]{bot_type.title()} token updated.[/]")

    elif action == "allow":
        if len(parts) < 3:
            console.print("[red]Usage: allow <user_id>[/]")
            return
        user_id = parts[2]
        manager.add_allowed_user(bot_type, user_id)
        console.print(f"[green]User {user_id} added to allowlist.[/]")

    elif action == "start":
        if manager.is_running(bot_type):
            console.print(f"[yellow]{bot_type.title()} bot is already running.[/]")
            return

        try:
            await manager.start_bot(bot_type)
            console.print(f"[green]🚀 {bot_type.title()} bot started in background![/]")
            console.print("[dim]Use the bot to chat. Check logs for debug info.[/]")
        except Exception as e:
            console.print(f"[red]Failed to start bot: {e}[/]")

    elif action == "stop":
        if not manager.is_running(bot_type):
            console.print(f"[yellow]{bot_type.title()} bot is not running.[/]")
            return

        await manager.stop_bot(bot_type)
        console.print(f"[green]🛑 {bot_type.title()} bot stopped.[/]")

    elif action == "status":
        running = manager.is_running(bot_type)
        status = "[green]RUNNING[/]" if running else "[red]STOPPED[/]"
        allowed = manager.get_allowed_users(bot_type)

        console.print(f"Status: {status}")
        console.print(f"Allowed Users: {', '.join(allowed) if allowed else 'None'}")

    else:
        console.print(f"[red]Unknown command: {action}[/]")
