"""ChefChat Classic REPL – The Grand Service (Redesigned)
==========================================================

A premium, terminal-native REPL with full ChefChat integration.
Gordon Ramsay energy meets Michelin-star elegance.

Features:
    - Mode cycling with Shift+Tab
    - Easter egg commands (/chef, /wisdom, /roast)
    - Interactive tool approval (Waiter logic)
    - Beautiful Rich-powered dark UI
    - Professional kitchen atmosphere
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import time
from typing import TYPE_CHECKING, Any, NoReturn

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax

# =============================================================================
# CHEFCHAT INTEGRATIONS
# =============================================================================
from chefchat.bots.cli_handler import handle_bot_command
from chefchat.cli.autocompletion.adapter import PromptToolkitCompleterAdapter

# Easter Eggs Integration
from chefchat.cli.easter_eggs import (
    get_dev_fortune,
    get_kitchen_status,
    get_modes_display,
    get_random_roast,
    get_random_wisdom,
)
from chefchat.cli.mode_manager import MODE_TIPS, ModeManager, VibeMode

# Plating Integration (visual formatting)
from chefchat.cli.plating import generate_plating

# UI Components (the new premium dark system)
from chefchat.cli.ui_components import (
    COLORS,
    DEFAULT_THEME,
    ApprovalDialog,
    HelpDisplay,
    ModeTransitionDisplay,
    RenderContext,
    ResponseDisplay,
    StatusBar,
    Theme,
    create_header,
)

# Core imports
from chefchat.core.agent import Agent
from chefchat.core.autocompletion.completers import CommandCompleter, PathCompleter
from chefchat.core.autocompletion.file_indexer import FileIndexer
from chefchat.core.config import VibeConfig
from chefchat.core.error_handler import ChefErrorHandler
from chefchat.core.types import AssistantEvent, ToolCallEvent, ToolResultEvent
from chefchat.core.utils import (
    ApprovalResponse,
    CancellationReason,
    get_user_cancellation_message,
)

if TYPE_CHECKING:
    pass

# Constants
ARGS_JSON_TRUNCATE_LIMIT = 400
SUMMARY_PREVIEW_LIMIT = 200


# =============================================================================
# REPL CLASS
# =============================================================================


class ChefChatREPL:
    """Premium REPL interface for ChefChat – The Full Kitchen Experience."""

    def __init__(
        self, config: VibeConfig, initial_mode: VibeMode = VibeMode.NORMAL
    ) -> None:
        """Initialize the REPL with premium dark UI."""
        self.config = config
        self.mode_manager = ModeManager(initial_mode=initial_mode)

        # Configure Console for better Windows compatibility
        # Force terminal ensures colors are rendered even if detection fails
        self.console = Console(force_terminal=True, force_interactive=True)

        self.agent: Agent | None = None
        self._last_mode = initial_mode
        self._render_context = self._build_render_context()

        # Setup keybindings
        self.kb = KeyBindings()
        self._setup_keybindings()

        # Prompt styling with ChefChat dark colors
        self.style = Style.from_dict({
            "mode": f"bg:{COLORS['fire']} {COLORS['charcoal']} bold",
            "arrow": COLORS["fire"],
            "prompt": COLORS["silver"],
        })

        self.session: PromptSession[str] = PromptSession(
            key_bindings=self.kb, style=self.style
        )

        # Session tracking
        self.session_start_time = time.time()
        self.tools_executed = 0
        self._last_interrupt_time = 0.0

        # Autocompletion setup
        file_indexer = FileIndexer(
            parallel_walk=config.file_indexer_parallel_walk,
            max_workers=config.file_indexer_max_workers,
        )
        commands = [
            ("/help", "Show help menu"),
            ("/model", "Switch AI model"),
            ("/chef", "Kitchen status"),
            ("/wisdom", "Chef wisdom"),
            ("/roast", "Get roasted"),
            ("/fortune", "Dev fortune"),
            ("/plate", "Show plating"),
            ("/mode", "Current mode info"),
            ("/modes", "List modes"),
            ("/theme", "Switch UI theme"),
            ("/compact", "Compact conversation history"),
            ("/summarize", "Compact conversation history"),
            ("/clear", "Clear history"),
            ("/status", "Show status"),
            ("/stats", "Show statistics"),
            ("/git-setup", "Configure Git settings"),
            ("/telegram", "Manage Telegram bot"),
            ("/discord", "Manage Discord bot"),
            ("/exit", "Exit application"),
            ("/quit", "Exit application"),
        ]
        self.completer = PromptToolkitCompleterAdapter([
            CommandCompleter(commands),
            PathCompleter(indexer=file_indexer, target_matches=20),
        ])

        # Re-create session with completer
        self.session: PromptSession[str] = PromptSession(
            key_bindings=self.kb,
            style=self.style,
            completer=self.completer,
            complete_while_typing=True,
        )

    # =========================================================================
    # KEYBINDINGS
    # =========================================================================

    def _setup_keybindings(self) -> None:
        """Setup keyboard bindings with elegant mode transitions."""
        from prompt_toolkit.keys import Keys

        @self.kb.add(Keys.BackTab)
        def cycle_mode_handler(event: Any) -> None:
            old_mode, new_mode = self.mode_manager.cycle_mode()
            self._last_mode = new_mode

            # Update agent's approval state
            if self.agent:
                self.agent.auto_approve = self.mode_manager.auto_approve
                if self.mode_manager.auto_approve:
                    self.agent.approval_callback = None
                else:
                    self.agent.approval_callback = self.ask_user_approval

            # Force the prompt (and toolbar) to refresh with new mode
            event.app.invalidate()

    # =========================================================================
    # STARTUP BANNER - "Welcome to the Kitchen"
    # =========================================================================

    def _show_startup_banner(self) -> None:
        """Display the ChefChat startup banner with warmth."""
        from chefchat.cli.ui_components import get_greeting
        from chefchat.core import __version__

        greeting, greeting_emoji = get_greeting()

        banner_text = f"""
[bold {COLORS["fire"]}]👨‍🍳 ChefChat[/bold {COLORS["fire"]}] [dim]v{__version__}[/dim]

[{COLORS["cream"]}]{greeting_emoji} {greeting}![/{COLORS["cream"]}]
[{COLORS["silver"]}]Ready to cook up something amazing?[/{COLORS["silver"]}]
"""
        panel = Panel(
            Align.center(banner_text.strip()),
            box=box.ROUNDED,
            border_style=COLORS["fire"],
            subtitle=f"[{COLORS['smoke']}]Type /help for the menu[/{COLORS['smoke']}]",
            subtitle_align="center",
            padding=(1, 2),
        )
        self.console.print()
        self.console.print(panel)

    async def _handle_git_setup(self) -> None:
        """Handle /git-setup command."""
        from rich.prompt import Prompt

        self.console.print(f"\n[{COLORS['fire']}]GitHub Setup[/{COLORS['fire']}]")
        self.console.print("This will configure your GitHub token in the .env file.\n")

        token = Prompt.ask("Enter your GitHub Token (hidden)", password=True)

        if not token:
            self.console.print(f"[{COLORS['ember']}]Cancelled.[/{COLORS['ember']}]\n")
            return

        # Update .env
        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = env_path.read_text().splitlines()

        new_lines = []
        found = False
        for line in lines:
            if line.startswith("GITHUB_TOKEN="):
                new_lines.append(f"GITHUB_TOKEN={token}")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"GITHUB_TOKEN={token}")

        env_path.write_text("\n".join(new_lines) + "\n")
        # Update current process env
        os.environ["GITHUB_TOKEN"] = token

        self.console.print(
            f"[{COLORS['sage']}]✓ GITHUB_TOKEN saved to .env[/{COLORS['sage']}]\n"
        )

    async def _handle_model_command(self, arg: str = "") -> None:
        """Handle model commands in the REPL with full subcommand support."""
        if not arg.strip():
            await self._model_select_interactive()
            return
    
        parts = arg.split(maxsplit=1)
        action = parts[0].lower() if parts else ""
        sub_arg = parts[1].strip() if len(parts) > 1 else ""
    
        # Command dispatch table
        command_handlers = {
            "help": self._model_show_help,
            "list": self._model_list,
            "select": lambda: self._model_select(sub_arg),
            "info": lambda: self._model_info(sub_arg),
            "status": self._model_status,
            "speed": self._model_speed,
            "reasoning": self._model_reasoning,
            "multimodal": self._model_multimodal,
            "compare": lambda: self._model_compare(sub_arg),
            "manage": self._model_manage_tui_only,
        }
    
        handler = command_handlers.get(action)
        if handler:
            await handler()
        else:
            # Fallback for backward compatibility - treat as direct model selection
            await self._model_select(arg)

    async def _model_select_interactive(self) -> None:
        """Interactive model selector used by `/model`."""
        from rich.prompt import Prompt
        from rich.table import Table

        # Create a display table for models
        table = Table(
            title=f"[{COLORS['primary']}]Available Models[/{COLORS['primary']}]",
            box=box.ROUNDED,
            border_style=COLORS["ash"],
            show_header=True,
            header_style=f"bold {COLORS['silver']}",
        )
        table.add_column("#", justify="right", style=COLORS["muted"])
        table.add_column("Alias", style=f"bold {COLORS['primary']}")
        table.add_column("Provider", style=COLORS["text"])
        table.add_column("Model ID", style=COLORS["muted"])

        models = self.config.models
        for idx, model in enumerate(models, 1):
            is_active = model.alias == self.config.active_model
            marker = "★" if is_active else str(idx)
            style = f"bold {COLORS['success']}" if is_active else COLORS["text"]

            table.add_row(marker, model.alias, model.provider, model.name, style=style)

        self.console.print()
        self.console.print(table)
        self.console.print()

        # Ask for selection
        try:
            choice = Prompt.ask(
                f"[{COLORS['fire']}]Select model #[/{COLORS['fire']}]",
                default=str(
                    next(
                        (
                            i
                            for i, m in enumerate(models, 1)
                            if m.alias == self.config.active_model
                        ),
                        1,
                    )
                ),
            )

            if choice.strip():
                try:
                    idx = int(choice)
                    if 1 <= idx <= len(models):
                        selected_model = models[idx - 1]
                        self.config.active_model = selected_model.alias

                        # Re-initialize agent
                        await self._initialize_agent()

                        self.console.print(
                            f"\n  [{COLORS['sage']}]✓ Switched to {selected_model.alias} ({selected_model.provider})[/{COLORS['sage']}]\n"
                        )
                    else:
                        self.console.print(
                            f"  [{COLORS['ember']}]Invalid number[/{COLORS['ember']}]"
                        )
                except ValueError:
                    # Check if they typed the alias directly
                    found = False
                    for model in models:
                        if model.alias.lower() == choice.lower():
                            self.config.active_model = model.alias
                            await self._initialize_agent()
                            self.console.print(
                                f"\n  [{COLORS['sage']}]✓ Switched to {model.alias}[/{COLORS['sage']}]\n"
                            )
                            found = True
                            break
                    if not found:
                        self.console.print(
                            f"  [{COLORS['ember']}]Invalid selection[/{COLORS['ember']}]"
                        )

        except KeyboardInterrupt:
            self.console.print(f"\n  [{COLORS['honey']}]Cancelled[/{COLORS['honey']}]")

    # =========================================================================
    # MODEL COMMAND METHODS - Complete Implementation
    # =========================================================================

    async def _model_show_help(self) -> None:
        """Show help for model commands."""
        help_text = f"""[{COLORS['primary']}]## 🤖 Model Management Commands[/{COLORS['primary']}]

[{COLORS['silver']}]### Core Commands[/{COLORS['silver']}]
• `/model` — Show interactive model selector
• `/model list` — List all available models with details
• `/model select <alias>` — Switch to a specific model
• `/model info <alias>` — Show detailed model information
• `/model status` — Show current model and API status

[{COLORS['silver']}]### Feature-Based Commands[/{COLORS['silver']}]
• `/model speed` — List fastest models (Groq 8b, GPT-OSS 20b)
• `/model reasoning` — List reasoning models (Kimi K2, GPT-OSS 120b)
• `/model multimodal` — List multimodal models (Llama Scout/Maverick)
• `/model compare <alias1> <alias2>` — Compare models side-by-side

[{COLORS['silver']}]### Examples[/{COLORS['silver']}]
• `/model select groq-8b` — Switch to Groq 8B model
• `/model info llama-scout` — Show Llama Scout details
• `/model list` — See all available models

[{COLORS['silver']}]### Current Active Model[/{COLORS['silver']}]
Use `/model status` to see which model is currently active.
"""
        self.console.print()
        self.console.print(help_text)
        self.console.print()

    async def _model_list(self) -> None:
        """List all available models with details, checking API availability."""
        from rich.table import Table
        
        self.console.print()
        self.console.print(f"[{COLORS['primary']}]## 🤖 Available Models[/{COLORS['primary']}]")
        self.console.print()

        # Group models by provider
        provider_groups = {}
        for model in self.config.models:
            provider = model.provider
            if provider not in provider_groups:
                provider_groups[provider] = []
            provider_groups[provider].append(model)

        for provider in sorted(provider_groups.keys()):
            self.console.print(f"[{COLORS['fire']}]### {provider.upper()}[/{COLORS['fire']}]")

            # Check if provider has API key configured
            provider_config = None
            for p in self.config.providers:
                if p.name == provider:
                    provider_config = p
                    break
            
            has_api_key = (
                bool(os.getenv(provider_config.api_key_env_var))
                if provider_config and provider_config.api_key_env_var
                else False
            )

            if has_api_key:
                self.console.print(f"[{COLORS['sage']}]✅ API key configured[/{COLORS['sage']}]")
            else:
                self.console.print(f"[{COLORS['ember']}]❌ No API key configured[/{COLORS['ember']}]")

            # Create table for this provider's models
            table = Table(
                box=box.ROUNDED,
                border_style=COLORS["ash"],
                show_header=True,
                header_style=f"bold {COLORS['silver']}",
            )
            table.add_column("Alias", style=f"bold {COLORS['primary']}")
            table.add_column("Status", style=COLORS["text"])
            table.add_column("Model ID", style=COLORS["muted"])
            table.add_column("Temperature", justify="right", style=COLORS["muted"])

            for model in sorted(provider_groups[provider], key=lambda m: m.alias):
                is_active = model.alias == self.config.active_model
                status = f"[{COLORS['success']}]🟢 Active[/{COLORS['success']}]" if is_active else f"[{COLORS['text']}]⚪ Available[/{COLORS['text']}]"
                
                table.add_row(
                    model.alias,
                    status,
                    model.name,
                    str(model.temperature)
                )

            self.console.print(table)
            self.console.print()

    async def _model_select(self, model_alias: str) -> None:
        """Select a model by alias."""
        if not model_alias:
            await self._model_show_help()
            return

        # Find model by alias (case-insensitive)
        model = None
        target = model_alias.lower()
        for m in self.config.models:
            if target in {m.alias.lower(), m.name.lower()}:
                model = m
                break

        if not model:
            self.console.print(
                f"[{COLORS['ember']}]❌ Model `{model_alias}` not found. Use `/model list` to see available models.[/{COLORS['ember']}]"
            )
            return

        try:
            self.config.active_model = model.alias
            await self._initialize_agent()

            self.console.print(
                f"[{COLORS['sage']}]✅ **Model switched to `{model.alias}`**[/{COLORS['sage']}]"
            )
        except Exception as e:
            self.console.print(f"[{COLORS['ember']}]Failed to switch model: {e}[/{COLORS['ember']}]")

    async def _model_info(self, model_alias: str) -> None:
        """Show detailed information about a specific model."""
        if not model_alias:
            await self._model_show_help()
            return

        model = None
        target = model_alias.lower()
        for m in self.config.models:
            if target in {m.alias.lower(), m.name.lower()}:
                model = m
                break

        if not model:
            self.console.print(f"[{COLORS['ember']}]❌ Model `{model_alias}` not found[/{COLORS['ember']}]")
            return

        is_active = model.alias == self.config.active_model
        
        # Get provider info
        provider = None
        for p in self.config.providers:
            if p.name == model.provider:
                provider = p
                break

        api_key_status = "✅ Set"
        if provider and provider.api_key_env_var:
            api_key_status = "✅ Set" if os.getenv(provider.api_key_env_var) else "⚠️ Missing"

        info = f"""[{COLORS['primary']}]## 🤖 Model Details: {model.alias}[/{COLORS['primary']}]

[{COLORS['silver']}]**Status**:[/{COLORS['silver']}] {"🟢 Active" if is_active else "⚪ Available"}
[{COLORS['silver']}]**Name**:[/{COLORS['silver']}] `{model.name}`
[{COLORS['silver']}]**Provider**:[/{COLORS['silver']}] {model.provider}

[{COLORS['silver']}]### Configuration[/{COLORS['silver']}]
• **Temperature**: {model.temperature}
• **Max Tokens**: {model.max_tokens or "Default"}

[{COLORS['silver']}]### Pricing[/{COLORS['silver']}]
• **Input**: ${model.input_price}/M tokens
• **Output**: ${model.output_price}/M tokens

[{COLORS['silver']}]### API Key[/{COLORS['silver']}]
• **Environment Variable**: `{provider.api_key_env_var or "None"}` if provider else "None"
• **Status**: {api_key_status}
"""

        if model.features:
            features_str = ", ".join(sorted(model.features))
            info += f"\n[{COLORS['silver']}]### 🚀 Features[/{COLORS['silver']}]\n{features_str}"

        if model.multimodal:
            info += f"\n[{COLORS['silver']}]### 🖼️ Multimodal Capabilities[/{COLORS['silver']}]\n**Vision Support**: ✅\n**Max File Size**: {model.max_file_size} MB"

        self.console.print()
        self.console.print(info)
        self.console.print()

    async def _model_status(self) -> None:
        """Show current model status and configuration."""
        try:
            active_model = self.config.get_active_model()
            
            # Get provider info
            provider = None
            for p in self.config.providers:
                if p.name == active_model.provider:
                    provider = p
                    break

            api_key_status = "✅ Set"
            if provider and provider.api_key_env_var:
                api_key_status = "✅ Set" if os.getenv(provider.api_key_env_var) else "❌ Missing"

            status = f"""[{COLORS['primary']}]## 🤖 Current Model Status[/{COLORS['primary']}]

[{COLORS['silver']}]**Active Model**:[/{COLORS['silver']}] `{active_model.alias}`
[{COLORS['silver']}]**Provider**:[/{COLORS['silver']}] {active_model.provider}
[{COLORS['silver']}]**API Key**:[/{COLORS['silver']}] {api_key_status} (`{provider.api_key_env_var if provider else "None"}`)

[{COLORS['silver']}]### Quick Actions[/{COLORS['silver']}]
• `/model list` — Show all models
• `/model select <alias>` — Switch models
• `/model info {active_model.alias}` — Model details
"""
        except Exception as e:
            status = f"[{COLORS['ember']}]## 🤖 Model Status Error[/{COLORS['ember']}]\n\n❌ {e}"

        self.console.print()
        self.console.print(status)
        self.console.print()

    async def _model_speed(self) -> None:
        """Show fastest models sorted by tokens/sec."""
        self.console.print()
        self.console.print(f"[{COLORS['primary']}]## ⚡ Fastest Models[/{COLORS['primary']}]")
        self.console.print()

        speed_models = [
            ("gpt-oss-20b", "1000 TPS", "$0.075/$0.30"),
            ("llama-scout", "750 TPS", "$0.11/$0.34"),
            ("groq-8b", "560 TPS", "$0.05/$0.08"),
            ("qwen-32b", "400 TPS", "$0.29/$0.59"),
            ("groq-70b", "280 TPS", "$0.59/$0.79"),
        ]

        for alias, speed, pricing in speed_models:
            self.console.print(f"• **{alias}** — {speed} — {pricing}")

        self.console.print(f"\n[{COLORS['muted']}]*Use `/model select <alias>` to switch*[/{COLORS['muted']}]")
        self.console.print()

    async def _model_reasoning(self) -> None:
        """Show models with reasoning capabilities."""
        self.console.print()
        self.console.print(f"[{COLORS['primary']}]## 🧠 Reasoning Models[/{COLORS['primary']}]")
        self.console.print()

        reasoning_models = [
            ("kimi-k2", "Deep Reasoning", "$1.00/$3.00", "262K context"),
            ("gpt-oss-120b", "Browser + Code", "$0.15/$0.60", "131K context"),
            ("gpt-oss-20b", "Fast Reasoning", "$0.075/$0.30", "131K context"),
        ]

        for alias, capability, pricing, context in reasoning_models:
            self.console.print(f"• **{alias}** — {capability} — {pricing} — {context}")

        self.console.print(f"\n[{COLORS['muted']}]*Use `/model select <alias>` to switch*[/{COLORS['muted']}]")
        self.console.print()

    async def _model_multimodal(self) -> None:
        """Show multimodal (vision) models."""
        self.console.print()
        self.console.print(f"[{COLORS['primary']}]## 🖼️ Multimodal Models[/{COLORS['primary']}]")
        self.console.print()

        multimodal_models = [
            ("llama-scout", "Vision + Tools", "$0.11/$0.34", "20MB files"),
            ("llama-maverick", "Advanced Vision", "$0.20/$0.60", "20MB files"),
        ]

        for alias, capability, pricing, file_size in multimodal_models:
            self.console.print(f"• **{alias}** — {capability} — {pricing} — {file_size}")

        self.console.print(f"\n[{COLORS['muted']}]*Upload images with `@path/to/image.jpg`*[/{COLORS['muted']}]")
        self.console.print(f"[{COLORS['muted']}]*Use `/model select <alias>` to switch*[/{COLORS['muted']}]")
        self.console.print()

    async def _model_compare(self, models_arg: str) -> None:
        """Compare multiple models side-by-side."""
        if not models_arg:
            await self._model_show_help()
            return

        model_aliases = models_arg.split()
        if len(model_aliases) < 2:
            self.console.print(
                f"[{COLORS['ember']}]❌ Please provide at least 2 models to compare. Example: `/model compare groq-8b llama-scout`[/{COLORS['ember']}]"
            )
            return

        self.console.print()
        self.console.print(f"[{COLORS['primary']}]## 📊 Model Comparison[/{COLORS['primary']}]")
        self.console.print()

        # Find models
        models_to_compare = []
        for alias in model_aliases[:3]:  # Limit to 3 models
            model = None
            for m in self.config.models:
                if alias.lower() in {m.alias.lower(), m.name.lower()}:
                    model = m
                    break
            if model:
                models_to_compare.append(model)
            else:
                self.console.print(f"[{COLORS['ember']}]❌ Model `{alias}` not found[/{COLORS['ember']}]")

        if not models_to_compare:
            return

        # Create comparison table
        from rich.table import Table
        
        table = Table(
            title="Model Comparison",
            box=box.ROUNDED,
            border_style=COLORS["ash"],
            show_header=True,
            header_style=f"bold {COLORS['silver']}",
        )
        table.add_column("Model", style=f"bold {COLORS['primary']}")
        table.add_column("Provider", style=COLORS["text"])
        table.add_column("Price (In/Out)", style=COLORS["muted"])
        table.add_column("Features", style=COLORS["text"])

        for model in models_to_compare:
            features = ", ".join(sorted(model.features)[:3])  # Limit to 3 features
            if len(model.features) > 3:
                features += "..."
            
            price_str = f"${model.input_price}/${model.output_price}"
            table.add_row(
                model.alias,
                model.provider,
                price_str,
                features
            )

        self.console.print(table)
        self.console.print()

    async def _model_manage_tui_only(self) -> None:
        """Show that model manage is TUI-only."""
        self.console.print()
        self.console.print(
            f"[{COLORS['honey']}]`/model manage` is only available in the TUI.[/{COLORS['honey']}]"
        )
        self.console.print(
            f"[{COLORS['smoke']}]Run without `--repl` and use `/model manage` there.[/{COLORS['smoke']}]"
        )
        self.console.print()

    def _show_stats(self) -> None:
        """Display session statistics - Today's Service."""
        from rich.table import Table

        uptime_seconds = int(time.time() - self.session_start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"{minutes}m {seconds}s"
        else:
            uptime_str = f"{seconds}s"

        # Get token count from agent if available
        token_count = 0
        if self.agent and hasattr(self.agent, "stats"):
            token_count = getattr(self.agent.stats, "total_tokens", 0)

        table = Table(
            title="📊 Today's Service", box=box.ROUNDED, border_style=COLORS["ash"]
        )
        table.add_column("Metric", style=f"bold {COLORS['silver']}", width=20)
        table.add_column("Value", style=COLORS["cream"])

        table.add_row("⏱️  Service Time", uptime_str)
        table.add_row("🔤 Tokens Used", f"{token_count:,}")
        table.add_row("🔧 Tools Executed", str(self.tools_executed))
        table.add_row("🎯 Current Mode", self.mode_manager.current_mode.value.upper())
        table.add_row(
            "⚡ Auto-Approve", "ON" if self.mode_manager.auto_approve else "OFF"
        )

        self.console.print()
        self.console.print(table)
        self.console.print()

    # =========================================================================
    # UI HELPERS
    # =========================================================================

    def _build_render_context(self) -> RenderContext:
        """Build a render context based on config and console width."""
        width = max(40, self.console.width or 80)
        is_mono = self.config.ui_theme.lower() == "mono"
        theme = Theme(
            palette=DEFAULT_THEME.palette,
            emoji_enabled=False if is_mono else self.config.emoji_enabled,
            color_enabled=False if is_mono else self.config.color_enabled,
        )
        return RenderContext(theme=theme, width=width)

    def _get_bottom_toolbar(self) -> Any:
        """Render the bottom status toolbar."""
        from html import escape

        from prompt_toolkit.formatted_text import HTML

        # Status
        mode_name = escape(self.mode_manager.current_mode.value.upper())
        mode_desc = escape(self.mode_manager.config.description)
        approval_status = "ON" if self.mode_manager.auto_approve else "OFF"
        approval_color = (
            COLORS["sage"] if self.mode_manager.auto_approve else COLORS["honey"]
        )

        return HTML(
            f' <b><style fg="{COLORS["fire"]}">[Shift+Tab]</style></b> Switch Mode '
            f'<style fg="{COLORS["smoke"]}">•</style> '
            f'<b><style fg="{COLORS["silver"]}">{mode_name}</style></b> '
            f'<style fg="{COLORS["smoke"]}">•</style> '
            f'<style fg="{COLORS["smoke"]}">{mode_desc}</style> '
            f'<style fg="{COLORS["smoke"]}">•</style> '
            f'<b>Auto:</b> <style fg="{approval_color}">{approval_status}</style> '
            f'<style fg="{COLORS["smoke"]}">•</style> '
            f'<b><style fg="{COLORS["fire"]}">[Ctrl+C]</style></b> Stop'
        )

    # =========================================================================
    # AGENT INITIALIZATION
    # =========================================================================

    async def _initialize_agent(self) -> None:
        """Initialize the Agent with approval callback."""
        self.agent = Agent(
            self.config,
            auto_approve=self.mode_manager.auto_approve,
            enable_streaming=True,
            mode_manager=self.mode_manager,
        )

        if not self.mode_manager.auto_approve:
            self.agent.approval_callback = self.ask_user_approval

    # =========================================================================
    # WAITER LOGIC - Tool Approval
    # =========================================================================

    async def ask_user_approval(
        self, tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> tuple[str, str | None]:
        """Display Order Confirmation dialog – the Waiter logic."""
        # Format arguments
        args_json = json.dumps(args, indent=2, default=str)
        if len(args_json) > ARGS_JSON_TRUNCATE_LIMIT:
            args_json = args_json[:ARGS_JSON_TRUNCATE_LIMIT] + "\n  ... (truncated)"

        syntax = Syntax(args_json, "json", theme="monokai", line_numbers=False)

        # Display elegant approval dialog
        self.console.print()
        self.console.print(ApprovalDialog.render(tool_name, syntax))

        # Get user decision
        from rich.prompt import Prompt

        try:
            choice = Prompt.ask(
                f"[{COLORS['fire']}]▶[/{COLORS['fire']}] [bold]Your call, Chef[/bold]",
                choices=["y", "n", "always", "Y", "N", "a"],
                default="y",
                show_choices=False,
            )
        except (KeyboardInterrupt, EOFError):
            return (ApprovalResponse.NO, "Interrupted")

        match choice.lower().strip():
            case "y" | "yes" | "":
                self.console.print(
                    f"  [{COLORS['sage']}]✓ Oui, Chef![/{COLORS['sage']}]"
                )
                return (ApprovalResponse.YES, None)
            case "always" | "a":
                self.console.print(
                    f"  [{COLORS['honey']}]⚡ Trusting you for this session[/{COLORS['honey']}]"
                )
                return (ApprovalResponse.ALWAYS, None)
            case _:
                self.console.print(
                    f"  [{COLORS['ember']}]✗ Not today[/{COLORS['ember']}]"
                )
                return (
                    ApprovalResponse.NO,
                    str(
                        get_user_cancellation_message(
                            CancellationReason.OPERATION_CANCELLED
                        )
                    ),
                )

    def _handle_mode_change(self) -> None:
        """Update agent when mode changes."""
        if self.agent:
            self.agent.auto_approve = self.mode_manager.auto_approve
            if self.mode_manager.auto_approve:
                self.agent.approval_callback = None
            else:
                self.agent.approval_callback = self.ask_user_approval

    # =========================================================================
    # AGENT RESPONSE HANDLING
    # =========================================================================

    async def _handle_agent_response(self, user_input: str) -> None:
        """Process user input through the Agent."""
        if not self.agent:
            self.console.print(
                f"[{COLORS['ember']}]Agent not initialized[/{COLORS['ember']}]"
            )
            return

        self._handle_mode_change()
        response_text = ""

        with Live(
            Spinner("dots", text=f"[{COLORS['fire']}] Cooking...[/{COLORS['fire']}]"),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        ):
            try:
                async for event in self.agent.act(user_input):
                    response_text = self._process_agent_event(event, response_text)
            except KeyboardInterrupt:
                self.console.print(
                    f"\n  [{COLORS['honey']}]⚠ Stopped by Chef[/{COLORS['honey']}]"
                )
                return
            except Exception as e:
                self.console.print(
                    f"\n  [{COLORS['ember']}]Error: {e}[/{COLORS['ember']}]"
                )
                return

        # Display response with elegant styling
        if response_text.strip():
            self.console.print()
            self.console.print(
                ResponseDisplay.render_response(
                    Markdown(response_text), ctx=self._render_context
                )
            )
        self.console.print()

    def _process_agent_event(
        self,
        event: AssistantEvent | ToolCallEvent | ToolResultEvent,
        response_text: str,
    ) -> str:
        """Process a single agent event and return updated response text."""
        if isinstance(event, AssistantEvent):
            return response_text + event.content

        if isinstance(event, ToolCallEvent):
            self.console.print(
                ResponseDisplay.render_tool_call(
                    event.tool_name, ctx=self._render_context
                )
            )
            return response_text

        if isinstance(event, ToolResultEvent):
            self._display_tool_result(event)

        return response_text

    def _display_tool_result(self, event: ToolResultEvent) -> None:
        """Display the result of a tool execution."""
        if event.error:
            self.console.print(
                ResponseDisplay.render_tool_result(
                    False, str(event.error)[:50], ctx=self._render_context
                )
            )
        elif event.skipped:
            self.console.print(
                ResponseDisplay.render_tool_result(
                    False, event.skip_reason or "Skipped", ctx=self._render_context
                )
            )
        else:
            self.tools_executed += 1
            self.console.print(
                ResponseDisplay.render_tool_result(True, ctx=self._render_context)
            )

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    async def run_async(self) -> NoReturn:
        """Run the main REPL loop."""
        await self._initialize_agent()

        # Show startup banner
        self._show_startup_banner()

        # Print elegant header
        self.console.print()
        self._render_context = self._build_render_context()
        self.console.print(
            create_header(self.config, self.mode_manager, ctx=self._render_context)
        )
        self.console.print()

        while True:
            try:
                # Dynamic prompt that updates with mode changes
                def get_prompt() -> list[tuple[str, str]]:
                    emoji = self.mode_manager.config.emoji
                    mode_name = self.mode_manager.current_mode.value.upper()
                    return [
                        ("class:mode", f" {emoji} {mode_name} "),
                        ("class:arrow", " "),
                        ("class:prompt", "› "),
                    ]

                with patch_stdout():
                    user_input = await self.session.prompt_async(
                        get_prompt,
                        bottom_toolbar=self._get_bottom_toolbar,
                        refresh_interval=0.5,
                    )

                # Handle exit
                if user_input.strip().lower() in {"exit", "quit", "/exit", "/quit"}:
                    self.console.print(
                        f"\n[{COLORS['silver']}]👋 Service complete. À bientôt, Chef![/{COLORS['silver']}]\n"
                    )
                    sys.exit(0)

                if not user_input.strip():
                    continue

                # Handle commands (including easter eggs!)
                if user_input.strip().startswith("/"):
                    await self._handle_command(user_input.strip())
                    continue

                # Process with agent
                await self._handle_agent_response(user_input)

            except KeyboardInterrupt:
                current_time = time.time()
                if current_time - self._last_interrupt_time < 1.0:
                    self.console.print(
                        f"\n[{COLORS['silver']}]👋 Kitchen closed. Service finished.[/{COLORS['silver']}]\n"
                    )
                    sys.exit(0)
                else:
                    self._last_interrupt_time = current_time
                    self.console.print(
                        f"\n  [{COLORS['honey']}]⚠ Press Ctrl+C again to exit[/{COLORS['honey']}]"
                    )
                continue
            except EOFError:
                self.console.print(
                    f"\n[{COLORS['silver']}]👋 Service complete. À bientôt, Chef![/{COLORS['silver']}]\n"
                )
                sys.exit(0)
            except Exception as e:
                ChefErrorHandler.display_error(e, context="REPL", show_traceback=False)

    # =========================================================================
    # COMMAND HANDLING - Using Registry Pattern
    # =========================================================================

    async def _handle_command(self, command: str) -> None:
        """Handle slash commands including easter eggs."""
        cmd = command.lower().strip()

        # Check for bot commands first (special case with prefix matching)
        if cmd.startswith(("/telegram", "/discord")):
            await handle_bot_command(self, cmd)
            return

        # Handle commands with sub-arguments (e.g. /model manage)
        cmd_name, _, cmd_arg = cmd.partition(" ")

        # Look up command in registry
        handler = self._get_command_handler(cmd_name)
        if handler:
            await handler(cmd_arg.strip())
        else:
            self.console.print(
                f"  [{COLORS['honey']}]Unknown command: {command}[/{COLORS['honey']}]"
            )
            self.console.print(
                f"  [{COLORS['smoke']}]Type /help for the menu[/{COLORS['smoke']}]\n"
            )

    def _get_command_handler(self, cmd: str) -> Any | None:
        """Get the handler for a command from the registry."""
        command_registry: dict[str, Any] = {
            # Easter egg commands
            "/chef": self._cmd_chef,
            "/wisdom": self._cmd_wisdom,
            "/roast": self._cmd_roast,
            "/fortune": self._cmd_fortune,
            "/plate": self._cmd_plate,
            # Standard commands
            "/help": self._cmd_help,
            "/h": self._cmd_help,
            "/?": self._cmd_help,
            "/mode": self._cmd_mode,
            "/model": self._handle_model_command,
            "/modes": self._cmd_modes,
            "/theme": self._cmd_theme,
            "/clear": self._cmd_clear,
            "/compact": self._cmd_compact,
            "/summarize": self._cmd_compact,
            "/status": self._cmd_status,
            "/stats": self._cmd_stats,
            "/git-setup": self._handle_git_setup,
        }
        return command_registry.get(cmd)

    async def _cmd_chef(self) -> None:
        """Kitchen status with mode info."""
        self.console.print()
        self.console.print(get_kitchen_status(self.mode_manager))
        self.console.print()

    async def _cmd_wisdom(self) -> None:
        """Random chef wisdom."""
        self.console.print()
        self.console.print(get_random_wisdom())
        self.console.print()

    async def _cmd_roast(self) -> None:
        """Gordon Ramsay style roast."""
        self.console.print()
        self.console.print(get_random_roast())
        self.console.print()

    async def _cmd_fortune(self) -> None:
        """Developer fortune cookie."""
        self.console.print()
        self.console.print(get_dev_fortune())
        self.console.print()

    async def _cmd_plate(self) -> None:
        """Show the current session plating."""
        self.console.print()
        stats = self.agent.stats if self.agent else None
        self.console.print(generate_plating(self.mode_manager, stats))
        self.console.print()

    async def _cmd_help(self) -> None:
        """Show help menu."""
        self.console.print()
        self.console.print(HelpDisplay.render())
        self.console.print()

    async def _cmd_mode(self) -> None:
        """Show current mode info."""
        tips = MODE_TIPS.get(self.mode_manager.current_mode, [])
        self.console.print()
        self.console.print(
            ModeTransitionDisplay.render(
                old_mode="",
                new_mode=self.mode_manager.current_mode.value.upper(),
                new_emoji=self.mode_manager.config.emoji,
                description=self.mode_manager.config.description,
                tips=tips,
                ctx=self._render_context,
            )
        )
        self.console.print()

    async def _cmd_modes(self) -> None:
        """List all modes."""
        self.console.print()
        self.console.print(get_modes_display(self.mode_manager))
        self.console.print()

    async def _cmd_theme(self) -> None:
        """Switch UI theme."""
        from rich.prompt import Prompt

        themes = ["chef-dark", "mono"]
        default_theme = (
            self.config.ui_theme if self.config.ui_theme in themes else "chef-dark"
        )
        choice = Prompt.ask(
            f"[{COLORS['fire']}]Select theme[/{COLORS['fire']}]",
            choices=themes,
            default=default_theme,
            show_choices=True,
        )

        self.config.ui_theme = choice
        if choice == "mono":
            self.config.color_enabled = False
            self.config.emoji_enabled = False
        else:
            self.config.color_enabled = True
            self.config.emoji_enabled = True

        self._render_context = self._build_render_context()
        self.console.print()
        self.console.print(
            f"[{COLORS['sage']}]✓ Theme switched to {choice}[/{COLORS['sage']}]"
        )
        self.console.print(
            create_header(self.config, self.mode_manager, ctx=self._render_context)
        )
        self.console.print()

    async def _cmd_clear(self) -> None:
        """Clear conversation history."""
        if self.agent:
            self.agent.clear_history()
            self.console.print(
                f"  [{COLORS['sage']}]✓ Conversation cleared - Fresh start![/{COLORS['sage']}]\n"
            )
        else:
            self.console.print(
                f"  [{COLORS['honey']}]No active session to clear[/{COLORS['honey']}]\n"
            )

    async def _cmd_compact(self) -> None:
        """Compact conversation history."""
        if not self.agent:
            self.console.print(
                f"  [{COLORS['honey']}]No active session to compact[/{COLORS['honey']}]\n"
            )
            return

        with Live(
            Spinner(
                "dots",
                text=f"[{COLORS['fire']}] Compacting history...[/{COLORS['fire']}]",
            ),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        ):
            try:
                summary = await self.agent.compact()
                self.console.print(
                    f"  [{COLORS['sage']}]✓ Conversation compacted![/{COLORS['sage']}]"
                )
                preview = (
                    summary[:SUMMARY_PREVIEW_LIMIT] + "..."
                    if len(summary) > SUMMARY_PREVIEW_LIMIT
                    else summary
                )
                self.console.print(
                    f"  [{COLORS['silver']}]Summary preview: {preview}[/{COLORS['silver']}]\n"
                )
            except Exception as e:
                self.console.print(
                    f"  [{COLORS['ember']}]Failed to compact history: {e}[/{COLORS['ember']}]\n"
                )

    async def _cmd_status(self) -> None:
        """Show status bar."""
        self.console.print()
        self.console.print(
            StatusBar.render(self.mode_manager.auto_approve, ctx=self._render_context)
        )
        self.console.print()

    async def _cmd_stats(self) -> None:
        """Show session statistics."""
        self._show_stats()

    def run(self) -> NoReturn:
        """Run the REPL."""
        asyncio.run(self.run_async())


# =============================================================================
# ENTRY POINT
# =============================================================================


def run_repl(config: VibeConfig, initial_mode: VibeMode = VibeMode.NORMAL) -> None:
    """Entry point for the REPL."""
    repl = ChefChatREPL(config, initial_mode)
    repl.run()
