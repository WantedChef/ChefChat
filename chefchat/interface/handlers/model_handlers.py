"""Model Command Handlers.

This module contains the handler functions for the `/model` command and its subcommands.
It acts as the Presentation Layer, formatting data from ModelService for the TUI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from rich.table import Table

from chefchat.interface.widgets.ticket_rail import TicketRail

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol
    from chefchat.interface.services.model_service import ModelInfo

logger = logging.getLogger(__name__)


async def handle_model_command(app: ChefAppProtocol, arg: str) -> None:
    """Handle /model command and dispatch subcommands.

    Args:
        app: The application instance
        arg: Command argument (subcommand + args)
    """
    parts = arg.strip().split(maxsplit=1)
    if not parts:
        await _show_help(app)
        return

    subcommand = parts[0].lower()
    sub_arg = parts[1] if len(parts) > 1 else ""

    handlers = {
        "help": lambda: _show_help(app),
        "list": lambda: _list_models(app),
        "select": lambda: _select_model(app, sub_arg),
        "info": lambda: _show_info(app, sub_arg),
        "status": lambda: _show_status(app),
        "speed": lambda: _list_filtered_models(app, "speed"),
        "reasoning": lambda: _list_filtered_models(app, "reasoning"),
        "multimodal": lambda: _list_filtered_models(app, "multimodal"),
        "compare": lambda: _compare_models(app, sub_arg),
    }

    handler = handlers.get(subcommand)
    if handler:
        await handler()
    # If argument matches a model alias, treat as select
    elif app.model_service.find_model_by_alias(subcommand):
        await _select_model(app, subcommand)
    else:
        ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))
        ticket_rail.add_system_message(
            f"❓ Unknown model subcommand: `{subcommand}`\n\n"
            "Type `/model help` for usage."
        )


async def _show_help(app: ChefAppProtocol) -> None:
    """Show help for /model command."""
    help_text = """
### 🤖 Model Management

**Commands:**
• `/model list` — Show all available models
• `/model select <alias>` — Switch active model
• `/model info [alias]` — Show model details
• `/model status` — Show current model status
• `/model speed` — Show fast models
• `/model reasoning` — Show reasoning models
• `/model compare <m1> <m2>` — Compare models
"""
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))
    ticket_rail.add_system_message(help_text)


async def _list_models(app: ChefAppProtocol) -> None:
    """List all available models."""
    models = app.model_service.list_all_models()
    _display_model_table(app, models, "Available Models")


async def _list_filtered_models(app: ChefAppProtocol, category: str) -> None:
    """List models filtered by category."""
    if category == "speed":
        models = app.model_service.get_speed_models()
        title = "🚀 Speed Models"
    elif category == "reasoning":
        models = app.model_service.get_reasoning_models()
        title = "🧠 Reasoning Models"
    elif category == "multimodal":
        models = app.model_service.get_multimodal_models()
        title = "👁️ Multimodal Models"
    else:
        models = []
        title = "Unknown Category"

    _display_model_table(app, models, title)


def _display_model_table(
    app: ChefAppProtocol, models: list[ModelInfo], title: str
) -> None:
    """Display a list of models in a table."""
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    if not models:
        ticket_rail.add_system_message(f"**{title}**\n\nNo models found.")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Alias", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Name")
    table.add_column("Context", justify="right")
    table.add_column("Input/Output ($)", justify="right")

    active_alias = app.model_service.get_active_model_alias()

    for model in models:
        is_active = model.alias == active_alias

        # Mark active model
        alias_display = f"[bold yellow]★ {model.alias}[/]" if is_active else model.alias

        # Format pricing
        if model.input_price or model.output_price:
            price = f"{model.input_price:.2f}/{model.output_price:.2f}"
        else:
            price = "free"

        context = (
            f"{model.context_window // 1000}k" if model.context_window else "n/a"
        )

        table.add_row(
            alias_display,
            model.provider,
            model.name,
            context,
            price,
        )

    ticket_rail.add_rich_content(table)
    ticket_rail.add_system_message("💡 Use `/model select <alias>` to switch models.")


async def _select_model(app: ChefAppProtocol, alias: str) -> None:
    """Switch active model."""
    if not alias:
        ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))
        ticket_rail.add_system_message("⚠️ Please specify a model alias.")
        return

    success, message = app.model_service.switch_model(alias)

    if success:
        app.notify(message, title="Model Switched")
        # Trigger model refresh in UI
        # Note: In a real event-driven system, we'd emit an event here.
        # For now, we rely on the service updating config, which app observes?
        # Actually app.py doesn't observe config yet.
        # But we can update the Footer manually via app.
        try:
            from chefchat.interface.widgets.kitchen_ui import KitchenFooter

            footer = app.query_one("#kitchen-footer", KitchenFooter)
            footer.refresh_mode()  # This refreshes model display too usually
        except Exception:
            pass

        ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))
        ticket_rail.add_system_message(f"✅ **{message}**")

    else:
        app.notify(message, severity="error")
        ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))
        ticket_rail.add_system_message(f"❌ **Error**: {message}")


async def _show_info(app: ChefAppProtocol, alias: str) -> None:
    """Show detailed info for a model."""
    info = app.model_service.get_model_info(alias)
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    if not info:
        if alias:
            ticket_rail.add_system_message(f"❌ Model `{alias}` not found.")
        else:
            ticket_rail.add_system_message("❌ No active model found.")
        return

    context = f"{info.context_window:,}" if info.context_window else "n/a"
    max_out = f"{info.max_output_tokens:,}" if info.max_output_tokens else "n/a"
    pricing = (
        f"${info.input_price:.2f} / ${info.output_price:.2f}"
        if info.input_price or info.output_price
        else "FREE"
    )
    capabilities = [
        f"Vision: {'✅' if info.supports_vision else '❌'}",
        f"Function Calling: {'✅' if info.supports_function_calling else '❌'}",
    ]
    if info.max_file_size:
        capabilities.append(f"File Size: {info.max_file_size}MB")

    feature_line = ", ".join(sorted(info.features)) if info.features else "n/a"

    # Use Markdown for details
    details = f"""
### ℹ️ Model Details: {info.alias}

- **Name**: `{info.name}`
- **Provider**: {info.provider}
- **Context Window**: {context} tokens
- **Max Output**: {max_out} tokens
- **Pricing**: {pricing} (per 1M tokens)
- **Capabilities**: {'; '.join(capabilities)}
- **Features**: {feature_line}
"""
    ticket_rail.add_system_message(details)


async def _show_status(app: ChefAppProtocol) -> None:
    """Show current active model status."""
    info = app.model_service.get_active_model_info()
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    if not info:
        ticket_rail.add_system_message("⚠️ No active model configured.")
        return

    msg = (
        f"🟢 **Active Model**: `{info.alias}` ({info.provider})\n"
        f"ID: {info.name}"
    )
    ticket_rail.add_system_message(msg)


async def _compare_models(app: ChefAppProtocol, arg: str) -> None:
    """Compare two or more models."""
    aliases = arg.strip().split()
    ticket_rail = cast(TicketRail, app.query_one("#ticket-rail"))

    if len(aliases) < 2:
        ticket_rail.add_system_message(
            "⚠️ Please specify at least two models to compare."
        )
        return

    comparison = app.model_service.compare_models(aliases)

    if not comparison:
        ticket_rail.add_system_message("❌ Could not find specified models.")
        return

    # Create comparison table
    table = Table(title="Model Comparison", show_header=True)
    table.add_column("Feature")

    for model in comparison:
        table.add_column(model.alias, justify="center")

    # Rows
    table.add_row(
        "Context", *[f"{(m.context_window or 0) // 1000}k" for m in comparison]
    )
    table.add_row(
        "Cost (In/Out)",
        *[
            "free"
            if not (m.input_price or m.output_price)
            else f"${m.input_price:.2f}/${m.output_price:.2f}"
            for m in comparison
        ],
    )
    table.add_row(
        "Vision", *[("✅" if m.supports_vision else "❌") for m in comparison]
    )

    ticket_rail.add_rich_content(table)
