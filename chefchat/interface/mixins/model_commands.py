"""Model Commands Mixin for ChefChat TUI.

Provides all /model command functionality: list, select, info, status, compare, etc.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol


class ModelCommandsMixin:
    """Mixin providing model management commands for ChefChatApp.

    Requires the following attributes on self:
    - _config: VibeConfig | None
    - _agent: Agent | None
    - _active_mode: bool
    """

    # Type hint for self when used as mixin
    self: ChefAppProtocol

    async def _handle_model_command(self, arg: str = "") -> None:
        """Handle model management commands with subcommands."""
        from chefchat.core.config import MissingAPIKeyError, VibeConfig

        if not self._config:
            try:
                self._config = VibeConfig.load()
            except MissingAPIKeyError:
                self.notify(
                    "API key missing. Run /api to configure keys.", severity="warning"
                )
                return
            except Exception as e:
                self.notify(f"Config Error: {e}", severity="error")
                return

        arg = arg.strip()
        parts = arg.split(maxsplit=1)
        action = parts[0].lower() if parts else ""
        sub_arg = parts[1].strip() if len(parts) > 1 else ""

        # Command dispatch table
        command_handlers = {
            "help": lambda: self._model_show_help(),
            "list": lambda: self._model_list(),
            "select": lambda: self._model_select(sub_arg),
            "info": lambda: self._model_info(sub_arg),
            "status": lambda: self._model_status(),
            "speed": lambda: self._model_speed(),
            "reasoning": lambda: self._model_reasoning(),
            "multimodal": lambda: self._model_multimodal(),
            "compare": lambda: self._model_compare(sub_arg),
            "manage": lambda: self._model_manage(),
        }

        handler = command_handlers.get(action)
        if handler:
            await handler()
        elif not action:
            # Default: Open Interactive Manager
            await self._open_model_manager()
        else:
            # Fallback for backward compatibility - treat as direct model selection
            await self._model_select(arg)

    def _get_llm_client(self) -> Any:
        """Get the LLM client from the agent."""
        if not self._agent:
            raise RuntimeError("Agent not initialized")
        return self._agent.llm_client

    async def _model_show_help(self) -> None:
        """Show help for model commands."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        help_text = """## 🤖 Model Management Commands

### Core Commands
• `/model` — Show model selection screen (default)
• `/model list` — List all available models with details
• `/model select <alias>` — Switch to a specific model
• `/model info <alias>` — Show detailed model information
• `/model status` — Show current model and API status
• `/model manage` — Open comprehensive model management UI

### Feature-Based Commands
• `/model speed` — List fastest models (Groq 8b, GPT-OSS 20b)
• `/model reasoning` — List reasoning models (Kimi K2, GPT-OSS 120b)
• `/model multimodal` — List multimodal models (Llama Scout/Maverick)
• `/model compare <alias1> <alias2>` — Compare models side-by-side

### Examples
• `/model select groq-8b` — Switch to Groq 8B model
• `/model info llama-scout` — Show Llama Scout details
• `/model list` — See all available models
• `/model manage` — Open enhanced model management interface

### Current Active Model
Use `/model status` to see which model is currently active.
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(help_text)

    async def _model_list(self) -> None:
        """List all available models with details, checking API availability."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        lines = ["## 🤖 Available Models", ""]

        llm_client = None
        try:
            llm_client = self._get_llm_client()
        except Exception:
            llm_client = None

        # Group models by provider
        provider_groups: dict[str, list] = {}
        for model in self._config.models:
            provider = model.provider
            if provider not in provider_groups:
                provider_groups[provider] = []
            provider_groups[provider].append(model)

        for provider in sorted(provider_groups.keys()):
            lines.append(f"### {provider.upper()}")

            # Check if provider has API key configured
            provider_config = self._config.get_provider_for_model(
                provider_groups[provider][0]
            )
            has_api_key = (
                bool(os.getenv(provider_config.api_key_env_var))
                if provider_config.api_key_env_var
                else False
            )

            if has_api_key:
                try:
                    if llm_client is None:
                        raise RuntimeError("LLM client not available")
                    available_models = await llm_client.list_models()
                    available_set = set(available_models)
                    lines.append(
                        f"✅ API key configured - {len(available_models)} models available"
                    )
                except Exception:
                    available_set = set()
                    lines.append("⚠️ API key configured but unable to fetch models")
            else:
                available_set = set()
                lines.append(
                    "❌ No API key configured - showing configured models only"
                )

            for model in sorted(provider_groups[provider], key=lambda m: m.alias):
                is_active = model.alias == self._config.active_model
                status = "🟢 Active" if is_active else "⚪ Configured"

                if has_api_key and available_set:
                    if model.name in available_set:
                        status += " ✅ Available"
                    else:
                        status += " ❌ Not available"

                lines.append(f"**{model.alias}** {status}")
                lines.append(f"• Name: `{model.name}`")
                lines.append(f"• Temperature: {model.temperature}")

                if model.input_price or model.output_price:
                    lines.append(
                        f"• Pricing: ${model.input_price}/M in, ${model.output_price}/M out"
                    )

                if model.features:
                    features_str = ", ".join(sorted(model.features))
                    lines.append(f"• Features: {features_str}")

                lines.append("")

        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_select(self, model_alias: str) -> None:
        """Select a model by alias."""
        from chefchat.core.config import VibeConfig
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if not model_alias:
            await self._model_show_help()
            return

        if not self._config:
            self.notify("Config unavailable; cannot switch model.", severity="error")
            return

        # Find model by alias (case-insensitive)
        model = None
        target = model_alias.lower()
        for m in self._config.models:
            if target in {m.alias.lower(), m.name.lower()}:
                model = m
                break

        if not model:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❌ Model `{model_alias}` not found. Use `/model list` to see available models."
            )
            return

        try:
            self._config.active_model = model.alias
            VibeConfig.save_updates({"active_model": model.alias})

            if self._active_mode:
                asyncio.create_task(self._initialize_agent())

            self.notify(f"Switched to model: {model.alias}")
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"✅ **Model switched to `{model.alias}`**"
            )
        except Exception as e:
            self.notify(f"Failed to switch model: {e}", severity="error")

    async def _model_info(self, model_alias: str) -> None:
        """Show detailed information about a specific model."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if not model_alias:
            await self._model_show_help()
            return

        model = None
        target = model_alias.lower()
        for m in self._config.models:
            if target in {m.alias.lower(), m.name.lower()}:
                model = m
                break

        if not model:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"❌ Model `{model_alias}` not found"
            )
            return

        is_active = model.alias == self._config.active_model
        provider = self._config.get_provider_for_model(model)
        api_key_note = (
            "✅ Set"
            if (provider.api_key_env_var and os.getenv(provider.api_key_env_var))
            else "⚠️ Missing"
        )

        info = f"""## 🤖 Model Details: {model.alias}

**Status**: {"🟢 Active" if is_active else "⚪ Available"}
**Name**: `{model.name}`
**Provider**: {model.provider}
**API Base**: {provider.api_base}

### Configuration
• **Temperature**: {model.temperature}
• **Max Tokens**: {model.max_tokens or "Default"}
• **Backend**: {provider.backend.value}

### Pricing
• **Input**: ${model.input_price}/M tokens
• **Output**: ${model.output_price}/M tokens

### API Key
• **Environment Variable**: `{provider.api_key_env_var or "None"}`
• **Status**: {api_key_note}
"""

        if model.features:
            features_str = ", ".join(sorted(model.features))
            info += f"\n### 🚀 Features\n{features_str}"

        if model.multimodal:
            info += f"\n### 🖼️ Multimodal Capabilities\n**Vision Support**: ✅\n**Max File Size**: {model.max_file_size} MB"

        if model.rate_limits:
            rate_info = []
            for limit_type, value in model.rate_limits.items():
                rate_info.append(f"{limit_type.upper()}: {value:,}")
            info += f"\n### ⚡ Rate Limits\n{', '.join(rate_info)}"

        self.query_one("#ticket-rail", TicketRail).add_system_message(info)

    async def _model_status(self) -> None:
        """Show current model status and configuration."""
        from chefchat.core.config import VibeConfig
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if not self._config:
            self._config = VibeConfig.load()

        try:
            active_model = self._config.get_active_model()
            provider = self._config.get_provider_for_model(active_model)

            api_key_status = (
                "✅ Set"
                if provider.api_key_env_var and os.getenv(provider.api_key_env_var)
                else "❌ Missing"
            )

            status = f"""## 🤖 Current Model Status

**Active Model**: `{active_model.alias}`
**Provider**: {active_model.provider}
**API Key**: {api_key_status} (`{provider.api_key_env_var}`)
**Temperature**: {active_model.temperature}
**Cost**: ${active_model.input_price}/M in, ${active_model.output_price}/M out

### Quick Actions
• `/model list` — Show all models
• `/model select <alias>` — Switch models
• `/model info {active_model.alias}` — Model details
"""
        except Exception as e:
            status = f"## 🤖 Model Status Error\n\n❌ {e}"

        self.query_one("#ticket-rail", TicketRail).add_system_message(status)

    async def _model_speed(self) -> None:
        """Show fastest models sorted by tokens/sec."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        lines = ["## ⚡ Fastest Models", ""]

        speed_models = [
            ("gpt-oss-20b", "1000 TPS", "$0.075/$0.30"),
            ("llama-scout", "750 TPS", "$0.11/$0.34"),
            ("groq-8b", "560 TPS", "$0.05/$0.08"),
            ("qwen-32b", "400 TPS", "$0.29/$0.59"),
            ("groq-70b", "280 TPS", "$0.59/$0.79"),
        ]

        for alias, speed, pricing in speed_models:
            lines.append(f"• **{alias}** — {speed} — {pricing}")

        lines.append("\n*Use `/model select <alias>` to switch*")
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_reasoning(self) -> None:
        """Show models with reasoning capabilities."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        lines = ["## 🧠 Reasoning Models", ""]

        reasoning_models = [
            ("kimi-k2", "Deep Reasoning", "$1.00/$3.00", "262K context"),
            ("gpt-oss-120b", "Browser + Code", "$0.15/$0.60", "131K context"),
            ("gpt-oss-20b", "Fast Reasoning", "$0.075/$0.30", "131K context"),
        ]

        for alias, capability, pricing, context in reasoning_models:
            lines.append(f"• **{alias}** — {capability} — {pricing} — {context}")

        lines.append("\n*Use `/model select <alias>` to switch*")
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_multimodal(self) -> None:
        """Show multimodal (vision) models."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        lines = ["## 🖼️ Multimodal Models", ""]

        multimodal_models = [
            ("llama-scout", "Vision + Tools", "$0.11/$0.34", "20MB files"),
            ("llama-maverick", "Advanced Vision", "$0.20/$0.60", "20MB files"),
        ]

        for alias, capability, pricing, file_size in multimodal_models:
            lines.append(f"• **{alias}** — {capability} — {pricing} — {file_size}")

        lines.append("\n*Upload images with `@path/to/image.jpg`*")
        lines.append("*Use `/model select <alias>` to switch*")
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_compare(self, models_arg: str) -> None:
        """Compare multiple models side-by-side."""
        from chefchat.interface.constants import (
            MAX_FEATURES_DISPLAY,
            MIN_MODELS_TO_COMPARE,
        )
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if not models_arg:
            await self._model_show_help()
            return

        model_aliases = models_arg.split()
        if len(model_aliases) < MIN_MODELS_TO_COMPARE:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "❌ Please provide at least 2 models to compare. Example: `/model compare groq-8b llama-scout`"
            )
            return

        lines = ["## 📊 Model Comparison", ""]

        # Find models
        models_to_compare = []
        for alias in model_aliases[:3]:  # Limit to 3 models
            model = None
            for m in self._config.models:
                if alias in {m.alias, m.name}:
                    model = m
                    break
            if model:
                models_to_compare.append(model)
            else:
                lines.append(f"❌ Model `{alias}` not found")

        if not models_to_compare:
            return

        # Create comparison table
        lines.append("| Model | Provider | Speed | Price | Features |")
        lines.append("|-------|----------|-------|--------|----------|")

        for model in models_to_compare:
            features = ", ".join(sorted(model.features)[:MAX_FEATURES_DISPLAY])
            if len(model.features) > MAX_FEATURES_DISPLAY:
                features += "..."

            price_str = f"${model.input_price}/${model.output_price}"
            lines.append(
                f"| {model.alias} | {model.provider} | N/A | {price_str} | {features} |"
            )

        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _model_manage(self) -> None:
        """Open comprehensive model management screen."""
        await self._open_model_manager()

    async def _open_model_manager(self) -> None:
        """Open the interactive model manager screen."""
        from chefchat.core.config import VibeConfig
        from chefchat.interface.screens.model_manager import ModelManagerScreen

        if not self._config:
            self._config = VibeConfig.load()

        def on_model_selected(model_alias: str | None) -> None:
            if model_alias and self._config:
                try:
                    self._config.active_model = model_alias
                    VibeConfig.save_updates({"active_model": model_alias})

                    if self._active_mode:
                        asyncio.create_task(self._initialize_agent())

                    self.notify(f"Switched to model: {model_alias}")
                except Exception as e:
                    self.notify(f"Failed to switch model: {e}", severity="error")

        await self.push_screen(ModelManagerScreen(self._config), on_model_selected)

    # Alias methods for backward compatibility with different command handlers
    async def _show_model_status(self) -> None:
        """Alias for _model_status (used by alternate command dispatch)."""
        await self._model_status()

    async def _list_available_models(self) -> None:
        """Alias for _model_list (used by alternate command dispatch)."""
        await self._model_list()

    async def _switch_model(self, alias: str) -> None:
        """Alias for _model_select (used by alternate command dispatch)."""
        await self._model_select(alias)
