"""System Command Handlers.

Handlers for system-level commands like /config, /layout, /mcp, /api, /git-setup, etc.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from rich.table import Table

from chefchat.interface.widgets.ticket_rail import TicketRail

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol


async def show_config(app: ChefAppProtocol) -> None:
    """Show current configuration."""
    info = app.config_service.get_config_info()
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    table = Table(title="🔧 Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Active Model", info.active_model)
    table.add_row("Providers", str(info.provider_count))
    table.add_row("Total Models", str(info.model_count))
    table.add_row("MCP Servers", str(len(info.mcp_servers)))
    table.add_row(
        "Config Path", info.config_path.replace(str(app._config.home_path), "~")
    )
    table.add_row("Log Path", info.log_path.replace(str(app._config.home_path), "~"))

    keys = ", ".join(info.api_keys_configured) if info.api_keys_configured else "None"
    table.add_row("API Keys", keys)

    ticket_rail.add_rich_content(table)


async def show_mcp_status(app: ChefAppProtocol) -> None:
    """Show MCP server status."""
    servers = app.config_service.list_mcp_servers()
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    if not servers:
        ticket_rail.add_system_message("🔌 No MCP servers configured.")
        return

    table = Table(title="🔌 MCP Servers", show_header=True)
    table.add_column("Name", style="bold cyan")
    table.add_column("Command", style="green")
    table.add_column("Enabled", justify="center")

    for name, info in servers.items():
        enabled = "✅" if info.enabled else "❌"
        cmd = f"{info.command} {' '.join(info.args)}"
        table.add_row(name, cmd, enabled)

    ticket_rail.add_rich_content(table)


async def reload_config(app: ChefAppProtocol) -> None:
    """Reload configuration from disk."""
    success, message = app.config_service.reload_config()
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    if success:
        app.notify(message)
        ticket_rail.add_system_message(f"✅ **{message}**")
        # Could satisfy a 'refresh' event here
    else:
        app.notify(message, severity="error")
        ticket_rail.add_system_message(f"❌ **{message}**")


async def handle_layout_command(app: ChefAppProtocol, layout_name: str) -> None:
    """Handle layout switching."""
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    valid_layouts = app.config_service.get_available_layouts()

    if not layout_name:
        layouts_str = ", ".join(f"`{l}`" for l in valid_layouts)
        ticket_rail.add_system_message(
            f"🖼️ **Current Layout**: `{app._layout}`\n\n"
            f"Available: {layouts_str}\n"
            "Use `/layout <name>` to switch (requires restart)."
        )
        return

    layout_name = layout_name.lower()
    if layout_name not in valid_layouts:
        ticket_rail.add_system_message(
            f"❌ Invalid layout `{layout_name}`. Available: {', '.join(valid_layouts)}"
        )
        return

    # For now, simplistic layout switch logic (could be improved with events)
    # We trigger the same confirmation logic as the mixin did
    # But here we implement it cleanly

    from chefchat.interface.screens.confirm_restart import ConfirmDialog

    async def confirm_callback(result: bool) -> None:
        if result:
            from chefchat.interface.screens.confirm_restart import save_tui_preference

            save_tui_preference("layout", layout_name)
            app.exit("RESTART")

    await app.push_screen(
        ConfirmDialog(
            title="Confirm Layout Switch",
            message=f"Switch to '{layout_name}' layout? (App will restart)",
            callback=confirm_callback,
        )
    )


async def handle_api_command(app: ChefAppProtocol) -> None:
    """Show API key onboarding screen."""
    from chefchat.interface.screens.onboarding import OnboardingScreen

    async def on_complete(success: bool) -> None:
        if success:
            app.notify("API keys configured!", title="Setup Complete")

    await app.push_screen(OnboardingScreen(), on_complete)


async def handle_git_setup(app: ChefAppProtocol) -> None:
    """Handle /git-setup command - configure GitHub token."""
    from chefchat.interface.screens.git_setup import GitSetupScreen

    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    async def on_complete(success: bool) -> None:
        if success:
            app.notify("GitHub token saved!", title="Git Setup")
            ticket_rail.add_system_message(
                "✅ **Git Setup Complete!**\n\nYour GitHub token was saved to `.env`."
            )
        else:
            ticket_rail.add_system_message("❌ Git setup cancelled.")

    await app.push_screen(GitSetupScreen(), on_complete)


async def handle_openrouter_command(app: ChefAppProtocol, arg: str) -> None:
    """Handle OpenRouter-specific commands."""
    from chefchat.interface.handlers import model_handlers

    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))
    action = arg.lower().strip() if arg else "help"

    if action == "help":
        help_text = """## 🌐 OpenRouter Commands

OpenRouter gives you access to 100+ AI models with a single API key!

### Commands
• `/openrouter` — Show this help
• `/openrouter setup` — Configure your OpenRouter API key
• `/openrouter status` — Check API key status
• `/openrouter models` — List all available OpenRouter models
• `/openrouter <model>` — Quick switch to OpenRouter model

### Available Models (preconfigured)
• `or-claude-sonnet` — Claude 3.5 Sonnet (best reasoning)
• `or-claude-haiku` — Claude 3.5 Haiku (fast & cheap)
• `or-gpt4o` — GPT-4o via OpenRouter
• `or-gpt4o-mini` — GPT-4o Mini (fast)
• `or-gemini-flash` — Gemini 2.0 Flash (FREE!)
• `or-deepseek` — DeepSeek Chat (cheap + good)
• `or-deepseek-coder` — DeepSeek Coder
• `or-qwen-coder` — Qwen 2.5 Coder 32B
• `or-llama-70b` — Llama 3.3 70B
• `or-mistral-large` — Mistral Large 2411

### Quick Start
1. Get API key: https://openrouter.ai/keys
2. Run `/openrouter setup`
3. Run `/model select or-claude-sonnet`
"""
        ticket_rail.add_system_message(help_text)

    elif action == "setup":
        await handle_api_command(app)

    elif action == "status":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if api_key:
            key_preview = (
                f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
            )
            ticket_rail.add_system_message(
                f"## 🌐 OpenRouter Status\n\n"
                f"**API Key**: ✅ Configured ({key_preview})\n"
                f"**Endpoint**: https://openrouter.ai/api/v1\n\n"
                f"Use `/model select or-<model>` to switch to an OpenRouter model."
            )
        else:
            ticket_rail.add_system_message(
                "## 🌐 OpenRouter Status\n\n"
                "**API Key**: ❌ Not configured\n\n"
                "Run `/openrouter setup` or `/api` to configure your key.\n"
                "Get your key at: https://openrouter.ai/keys"
            )

    elif action == "models":
        # List OpenRouter models using model_service
        models = app.model_service.list_all_models()
        or_models = [m for m in models if m.provider == "openrouter"]

        if not or_models:
            ticket_rail.add_system_message("No OpenRouter models configured.")
            return

        lines = ["## 🌐 OpenRouter Models\n"]
        active_alias = app.model_service.get_active_model_alias()

        for m in or_models:
            is_active = m.alias == active_alias
            status = "🟢 Active" if is_active else ""
            price = (
                f"${m.input_price:.2f}/${m.output_price:.2f}"
                if m.input_price
                else "FREE"
            )
            features = ", ".join(sorted(m.features)[:3]) if m.features else ""
            lines.append(
                f"**{m.alias}** {status}\n  `{m.name}` | {price}/M | {features}"
            )
        ticket_rail.add_system_message("\n".join(lines))

    else:
        # Try to interpret as model switch
        target = f"or-{action}" if not action.startswith("or-") else action
        await model_handlers._select_model(app, target)


async def handle_quit(app: ChefAppProtocol) -> None:
    """Handle quit command."""
    # Call shutdown if it exists
    if hasattr(app, "_shutdown"):
        await app._shutdown()  # type: ignore
    app.exit()


async def handle_clear(app: ChefAppProtocol) -> None:
    """Clear chat history."""
    from chefchat.interface.constants import TUILayout
    from chefchat.interface.widgets.the_pass import ThePass
    from chefchat.interface.widgets.the_plate import ThePlate

    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))
    await ticket_rail.clear_tickets()

    if app._active_mode and app._agent:
        await app._agent.clear_history()
        app.notify("Context cleared")

    if app._layout == TUILayout.FULL_KITCHEN:
        try:
            app.query_one("#the-plate", ThePlate).clear_plate()
            app.query_one("#the-pass", ThePass).reset_all()
        except Exception:
            pass


async def show_help(app: ChefAppProtocol) -> None:
    """Show help directly in chat."""
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    layout_info = f"Current: **{app._layout.value}**"
    help_text = f"""## 📋 ChefChat Commands

**Navigation**
• `/help` — Show this menu
• `/clear` — Clear the chat
• `/quit` — Exit ChefChat

**Modes** *(Shift+Tab to cycle)*
• `/modes` — Show all available modes
• `/status` — Show current session status

**Layout** ({layout_info})
• `/layout chat` — Clean chat-only view
• `/layout kitchen` — Full 3-panel kitchen view

**Models**
• `/model` — Model management commands
• `/openrouter` — OpenRouter-specific commands

**Kitchen Tools**
• `/config` — Show configuration
• `/mcp` — MCP server status
• `/api` — Configure API keys
• `/git-setup` — Configure GitHub token

**Fun Commands**
• `/wisdom` — Random chef wisdom
• `/roast` — Get roasted by Gordon Ramsay
• `/fortune` — Developer fortune cookie
"""
    ticket_rail.add_system_message(help_text)
