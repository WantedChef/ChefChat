"""System Commands Mixin for ChefChat TUI.

Provides system-level commands: layout, config, clear, quit, MCP, OpenRouter, etc.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol


class SystemCommandsMixin:
    """Mixin providing system-level commands for ChefChatApp.

    Requires the following attributes on self:
    - _layout: TUILayout
    - _config: VibeConfig | None
    - _mode_manager: ModeManager
    - _agent: Agent | None
    - _bus: KitchenBus | None
    """

    # Type hint for self when used as mixin
    self: ChefAppProtocol

    async def _handle_api_command(self) -> None:
        """Show API key onboarding screen."""
        from chefchat.interface.screens.onboarding import OnboardingScreen

        await self.push_screen(OnboardingScreen(), self._on_onboarding_complete)

    async def _handle_git_setup(self) -> None:
        """Handle /git-setup command - configure GitHub token."""
        from chefchat.interface.screens.git_setup import GitSetupScreen
        from chefchat.interface.widgets.ticket_rail import TicketRail

        ticket_rail = self.query_one("#ticket-rail", TicketRail)

        def on_complete(success: bool) -> None:
            if success:
                self.notify("GitHub token saved!", title="Git Setup")
                ticket_rail.add_system_message(
                    "✅ **Git Setup Complete!**\n\nYour GitHub token was saved to `.env`."
                )
            else:
                ticket_rail.add_system_message("❌ Git setup cancelled.")

        await self.push_screen(GitSetupScreen(), on_complete)

    async def _handle_layout_command(self, arg: str) -> None:
        """Handle layout switching command."""
        from chefchat.interface.constants import TUILayout
        from chefchat.interface.widgets.ticket_rail import TicketRail

        arg = arg.lower().strip()

        if arg == "chat":
            if self._layout == TUILayout.CHAT_ONLY:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    "Already in **chat** layout mode."
                )
            else:
                await self._confirm_layout_switch("chat")
        elif arg == "kitchen":
            if self._layout == TUILayout.FULL_KITCHEN:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    "Already in **kitchen** layout mode."
                )
            else:
                await self._confirm_layout_switch("kitchen")
        else:
            current = self._layout.value
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"## 🖼️ Layout Options\n\n"
                f"Current layout: **{current}**\n\n"
                f"• `/layout chat` — Clean chat-only view\n"
                f"• `/layout kitchen` — Full 3-panel kitchen view"
            )

    async def _confirm_layout_switch(self, new_layout: str) -> None:
        """Show confirmation dialog for layout switch."""
        from chefchat.interface.screens.confirm_restart import (
            ConfirmRestartScreen,
            save_tui_preference,
        )
        from chefchat.interface.widgets.ticket_rail import TicketRail

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                save_tui_preference("layout", new_layout)
                self.notify(f"Restarting with {new_layout} layout...", timeout=1)
                self.set_timer(0.5, lambda: self.exit(result="RESTART"))
            else:
                self.query_one("#ticket-rail", TicketRail).add_system_message(
                    "Layout switch cancelled."
                )

        self.push_screen(ConfirmRestartScreen(new_layout), on_confirm)

    async def _handle_quit(self) -> None:
        """Handle quit command."""
        await self._shutdown()
        self.exit()

    async def _handle_plate(self) -> None:
        """Handle plate command wrapper."""
        from chefchat.interface.constants import TUILayout
        from chefchat.interface.widgets.the_plate import ThePlate
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if self._layout == TUILayout.FULL_KITCHEN:
            self.query_one("#the-plate", ThePlate).show_current_plate()
        else:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "📋 `/plate` is only available in **kitchen** layout mode.\n\n"
                "Use `/layout kitchen` to switch to full kitchen view."
            )

    async def _handle_clear(self) -> None:
        """Clear chat history."""
        from chefchat.interface.constants import TUILayout
        from chefchat.interface.widgets.the_pass import ThePass
        from chefchat.interface.widgets.the_plate import ThePlate
        from chefchat.interface.widgets.ticket_rail import TicketRail

        await self.query_one("#ticket-rail", TicketRail).clear_tickets()
        if self._active_mode and self._agent:
            await self._agent.clear_history()
            self.notify("Context cleared")

        if self._layout == TUILayout.FULL_KITCHEN:
            try:
                self.query_one("#the-plate", ThePlate).clear_plate()
                self.query_one("#the-pass", ThePass).reset_all()
            except Exception:
                pass

    async def _show_config(self) -> None:
        """Show configuration info."""
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.modes import MODE_CONFIGS

        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]

        info = f"""## ⚙️ Configuration

**Mode**: {config.emoji} {mode.value.upper()}
**Auto-Approve**: {"ON" if self._mode_manager.auto_approve else "OFF"}

---
*Use the REPL for full configuration options*
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(info)

    async def _show_log_path(self) -> None:
        """Show the current log path."""
        from chefchat.interface.screens.confirm_restart import TUI_PREFS_FILE
        from chefchat.interface.widgets.ticket_rail import TicketRail

        log_dir = TUI_PREFS_FILE.parent / "logs"
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            f"## 📝 Kitchen Logs\n\n"
            f"Logs are stored in:\n`{log_dir}`\n\n"
            f"*Check these for details if the soufflé collapses.*"
        )

    async def _reload_config(self) -> None:
        """Reload configuration."""
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.modes import ModeManager

        self.notify("Reloading configuration...", title="System")
        self._mode_manager = ModeManager(initial_mode=self._mode_manager.current_mode)
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            "🔄 **Configuration Reloaded**"
        )

    async def _compact_history(self) -> None:
        """Compact conversation history."""
        from chefchat.interface.constants import SUMMARY_PREVIEW_LENGTH
        from chefchat.interface.widgets.ticket_rail import TicketRail

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        ticket_rail.add_system_message(
            "🗜️ **Compacting History**\n\nCompressing the conversation context..."
        )

        try:
            if self._agent:
                summary = await self._agent.compact()
                ticket_rail.add_system_message(
                    f"✅ **History compacted successfully**\n\n"
                    f"*Summary: {summary[:SUMMARY_PREVIEW_LENGTH]}{'...' if len(summary) > SUMMARY_PREVIEW_LENGTH else ''}*"
                )
            else:
                await asyncio.sleep(1)
                ticket_rail.add_system_message(
                    "✅ **History compacted**\n\n"
                    "*Note: Full compaction requires active agent mode*"
                )
        except Exception as e:
            ticket_rail.add_system_message(
                f"❌ **Compaction failed**: {e}\n\n"
                "*The conversation history remains unchanged*"
            )

    async def _handle_mcp_command(self) -> None:
        """Show MCP server status and available tools."""
        from chefchat.core.config import VibeConfig
        from chefchat.interface.widgets.ticket_rail import TicketRail

        if not self._config:
            self._config = VibeConfig.load()

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        mcp_servers = self._config.mcp_servers

        if not mcp_servers:
            ticket_rail.add_system_message(
                "## 🔌 MCP Servers\n\n"
                "No MCP servers configured.\n\n"
                "To add an MCP server, edit your `config.toml`:\n\n"
                "```toml\n"
                "[[mcp_servers]]\n"
                'name = "my-server"\n'
                'transport = "stdio"\n'
                'command = ["npx", "my-mcp-server"]\n'
                "```\n\n"
                "*See docs for HTTP and Streamable HTTP transports.*"
            )
            return

        lines = [
            "## 🔌 MCP Servers",
            "",
            f"**{len(mcp_servers)}** server(s) configured:",
            "",
        ]

        for server in mcp_servers:
            transport = getattr(server, "transport", "unknown")
            name = getattr(server, "name", "unnamed")

            match transport:
                case "stdio":
                    cmd = getattr(server, "command", "")
                    if isinstance(cmd, list):
                        cmd = " ".join(cmd[:2])
                    lines.append(f"• **{name}** — `stdio` (`{cmd}`)")
                case "http" | "streamable-http":
                    url = getattr(server, "url", "")
                    lines.append(f"• **{name}** — `{transport}` (`{url}`)")
                case _:
                    lines.append(f"• **{name}** — `{transport}`")

        lines.extend(["", "---", "*MCP tools are loaded when the agent starts.*"])
        ticket_rail.add_system_message("\n".join(lines))

    async def _handle_openrouter_command(self, arg: str = "") -> None:
        """Handle OpenRouter-specific commands."""
        from chefchat.core.config import VibeConfig
        from chefchat.interface.widgets.ticket_rail import TicketRail

        ticket_rail = self.query_one("#ticket-rail", TicketRail)
        action = arg.lower().strip() if arg else "help"

        if action == "help":
            help_text = """## 🌐 OpenRouter Commands

OpenRouter gives you access to 100+ AI models with a single API key!

### Commands
• `/openrouter` — Show this help
• `/openrouter setup` — Configure your OpenRouter API key
• `/openrouter status` — Check API key status and credit
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
            await self._handle_api_command()

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
            if not self._config:
                self._config = VibeConfig.model_construct()

            lines = ["## 🌐 OpenRouter Models\n"]
            for m in self._config.models:
                if m.provider == "openrouter":
                    is_active = m.alias == self._config.active_model
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
            await self._model_select(target)

    async def _show_command_palette(self) -> None:
        """Show help directly in chat instead of separate palette."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        layout_info = f"Current: **{self._layout.value}**"
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

**Kitchen Tools**
• `/taste` — Run taste tests (QA)
• `/timer` — Kitchen timer info
• `/log` — Show log file path

**Fun Commands**
• `/chef` — Kitchen status
• `/wisdom` — Random chef wisdom
• `/roast` — Get roasted by Gordon Ramsay
• `/fortune` — Developer fortune cookie
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(help_text)
