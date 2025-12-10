"""ChefChat Classic REPL
=====================

A lightweight, terminal-native REPL alternative to the Textual UI.
Michelin-star elegance with Mistral Vibe aesthetics.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any, NoReturn

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.syntax import Syntax

from vibe.cli.mode_manager import MODE_TIPS, ModeManager, VibeMode
from vibe.cli.ui_components import (
    COLORS,
    ApprovalDialog,
    HelpDisplay,
    ModeTransitionDisplay,
    ResponseDisplay,
    StatusBar,
    create_header,
)
from vibe.core.agent import Agent
from vibe.core.config import VibeConfig
from vibe.core.types import AssistantEvent, ToolCallEvent, ToolResultEvent
from vibe.core.utils import (
    ApprovalResponse,
    CancellationReason,
    get_user_cancellation_message,
)

if TYPE_CHECKING:
    pass


class ChefChatREPL:
    """Classic REPL interface for ChefChat with elegant UI."""

    def __init__(
        self, config: VibeConfig, initial_mode: VibeMode = VibeMode.NORMAL
    ) -> None:
        """Initialize the REPL."""
        self.config = config
        self.mode_manager = ModeManager(initial_mode=initial_mode)
        self.console = Console()
        self.agent: Agent | None = None
        self._last_mode = initial_mode

        # Setup keybindings
        self.kb = KeyBindings()
        self._setup_keybindings()

        # Prompt styling matching our color palette
        self.style = Style.from_dict({
            "mode": f"bg:{COLORS['primary']} fg:white bold",
            "arrow": COLORS["primary"],
            "prompt": COLORS["muted"],
        })

        self.session: PromptSession[str] = PromptSession(
            key_bindings=self.kb, style=self.style
        )

    def _setup_keybindings(self) -> None:
        """Setup keyboard bindings with elegant mode transition display."""
        from prompt_toolkit.keys import Keys

        @self.kb.add(Keys.BackTab)
        def cycle_mode_handler(event: Any) -> None:
            old_mode, new_mode = self.mode_manager.cycle_mode()
            self._last_mode = new_mode

            # Update agent
            if self.agent:
                self.agent.auto_approve = self.mode_manager.auto_approve
                if self.mode_manager.auto_approve:
                    self.agent.approval_callback = None
                else:
                    self.agent.approval_callback = self.ask_user_approval

            # Get tips for the new mode
            tips = MODE_TIPS.get(new_mode, [])

            # Print elegant transition panel
            output = event.app.output
            output.write("\n\n")

            # Create transition display using Rich via console
            # Note: We print directly since we're in prompt_toolkit context
            console = Console(file=sys.stdout, force_terminal=True)
            panel = ModeTransitionDisplay.render(
                old_mode=old_mode.value.upper(),
                new_mode=new_mode.value.upper(),
                new_emoji=self.mode_manager.config.emoji,
                description=self.mode_manager.config.description,
                tips=tips,
            )
            console.print(panel)
            output.write("\n")
            output.flush()

    async def _initialize_agent(self) -> None:
        """Initialize the Agent."""
        self.agent = Agent(
            self.config,
            auto_approve=self.mode_manager.auto_approve,
            enable_streaming=True,
            mode_manager=self.mode_manager,
        )

        if not self.mode_manager.auto_approve:
            self.agent.approval_callback = self.ask_user_approval

    async def ask_user_approval(
        self, tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> tuple[str, str | None]:
        """Elegant Order Confirmation dialog."""
        # Format arguments
        args_json = json.dumps(args, indent=2, default=str)
        if len(args_json) > 400:
            args_json = args_json[:400] + "\n  ... (truncated)"

        syntax = Syntax(args_json, "json", theme="monokai", line_numbers=False)

        # Display elegant approval dialog
        self.console.print()
        self.console.print(ApprovalDialog.render(tool_name, syntax))

        # Get user decision
        from rich.prompt import Prompt

        try:
            choice = Prompt.ask(
                f"[{COLORS['primary']}]▶[/{COLORS['primary']}] [bold]Allow?[/bold]",
                choices=["y", "n", "always", "Y", "N"],
                default="y",
                show_choices=False,
            )
        except (KeyboardInterrupt, EOFError):
            return (ApprovalResponse.NO, "Interrupted")

        match choice.lower().strip():
            case "y" | "yes" | "":
                self.console.print(
                    f"  [{COLORS['success']}]✓ Approved[/{COLORS['success']}]"
                )
                return (ApprovalResponse.YES, None)
            case "always" | "a":
                self.console.print(
                    f"  [{COLORS['warning']}]⚡ Auto-approved for session[/{COLORS['warning']}]"
                )
                return (ApprovalResponse.ALWAYS, None)
            case _:
                self.console.print(f"  [{COLORS['error']}]✗ Denied[/{COLORS['error']}]")
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

    async def _handle_agent_response(self, user_input: str) -> None:
        """Process user input through the Agent."""
        if not self.agent:
            self.console.print(
                f"[{COLORS['error']}]Agent not initialized[/{COLORS['error']}]"
            )
            return

        self._handle_mode_change()
        response_text = ""

        with Live(
            Spinner(
                "dots", text=f"[{COLORS['primary']}] Cooking...[/{COLORS['primary']}]"
            ),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        ):
            try:
                async for event in self.agent.act(user_input):
                    if isinstance(event, AssistantEvent):
                        response_text += event.content

                    elif isinstance(event, ToolCallEvent):
                        self.console.print(
                            ResponseDisplay.render_tool_call(event.tool_name)
                        )

                    elif isinstance(event, ToolResultEvent):
                        if event.error:
                            self.console.print(
                                ResponseDisplay.render_tool_result(
                                    False, str(event.error)[:50]
                                )
                            )
                        elif event.skipped:
                            self.console.print(
                                ResponseDisplay.render_tool_result(
                                    False, event.skip_reason or "Skipped"
                                )
                            )
                        else:
                            self.console.print(ResponseDisplay.render_tool_result(True))

            except KeyboardInterrupt:
                self.console.print(
                    f"\n  [{COLORS['warning']}]⚠ Interrupted[/{COLORS['warning']}]"
                )
                return
            except Exception as e:
                self.console.print(
                    f"\n  [{COLORS['error']}]Error: {e}[/{COLORS['error']}]"
                )
                return

        # Display response
        if response_text.strip():
            self.console.print()
            self.console.print(ResponseDisplay.render_response(Markdown(response_text)))
        self.console.print()

    async def run_async(self) -> NoReturn:
        """Run the main REPL loop."""
        await self._initialize_agent()

        # Print elegant header
        self.console.print()
        self.console.print(create_header(self.config, self.mode_manager))

        # Print status bar
        self.console.print(StatusBar.render(self.mode_manager.auto_approve))
        self.console.print()

        while True:
            try:
                # Build elegant prompt
                indicator = self.mode_manager.get_mode_indicator()
                emoji = self.mode_manager.config.emoji
                mode_name = self.mode_manager.current_mode.value.upper()

                prompt_html = HTML(
                    f"<mode> {emoji} {mode_name} </mode>"
                    f"<arrow> </arrow>"
                    f"<prompt>›</prompt> "
                )

                with patch_stdout():
                    user_input = await self.session.prompt_async(prompt_html)

                # Handle exit
                if user_input.strip().lower() in {"exit", "quit", "/exit", "/quit"}:
                    self.console.print(
                        f"\n[{COLORS['muted']}]👋 Goodbye from the Kitchen![/{COLORS['muted']}]\n"
                    )
                    sys.exit(0)

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.strip().startswith("/"):
                    await self._handle_command(user_input.strip())
                    continue

                # Process with agent
                await self._handle_agent_response(user_input)

            except KeyboardInterrupt:
                self.console.print()
                continue
            except EOFError:
                self.console.print(
                    f"\n[{COLORS['muted']}]👋 Goodbye from the Kitchen![/{COLORS['muted']}]\n"
                )
                sys.exit(0)
            except Exception as e:
                self.console.print(f"[{COLORS['error']}]Error: {e}[/{COLORS['error']}]")

    async def _handle_command(self, command: str) -> None:
        """Handle slash commands."""
        cmd = command.lower().strip()

        if cmd in {"/help", "/h", "/?"}:
            self.console.print()
            self.console.print(HelpDisplay.render())
            self.console.print()

        elif cmd == "/mode":
            tips = MODE_TIPS.get(self.mode_manager.current_mode, [])
            panel = ModeTransitionDisplay.render(
                old_mode="",
                new_mode=self.mode_manager.current_mode.value.upper(),
                new_emoji=self.mode_manager.config.emoji,
                description=self.mode_manager.config.description,
                tips=tips,
            )
            self.console.print()
            self.console.print(panel)
            self.console.print()

        elif cmd == "/modes":
            from rich.table import Table

            from vibe.cli.mode_manager import MODE_CONFIGS

            table = Table(
                show_header=True, header_style=f"bold {COLORS['primary']}", box=None
            )
            table.add_column("Mode", style="bold")
            table.add_column("Description")
            table.add_column("", justify="right", width=3)

            for mode in VibeMode:
                cfg = MODE_CONFIGS[mode]
                current = "◀" if mode == self.mode_manager.current_mode else ""
                table.add_row(
                    f"{cfg.emoji} {mode.name}",
                    cfg.description,
                    f"[{COLORS['success']}]{current}[/{COLORS['success']}]",
                )

            from rich.panel import Panel

            self.console.print()
            self.console.print(
                Panel(
                    table,
                    title=f"[{COLORS['primary']}]Available Modes[/{COLORS['primary']}]",
                    border_style=COLORS["secondary"],
                )
            )
            self.console.print()

        elif cmd == "/clear":
            if self.agent:
                self.agent.clear_history()
                self.console.print(
                    f"  [{COLORS['success']}]✓ Conversation cleared[/{COLORS['success']}]\n"
                )
            else:
                self.console.print(
                    f"  [{COLORS['warning']}]No active session[/{COLORS['warning']}]\n"
                )

        elif cmd == "/status":
            self.console.print()
            self.console.print(StatusBar.render(self.mode_manager.auto_approve))
            self.console.print()

        else:
            self.console.print(
                f"  [{COLORS['warning']}]Unknown: {command}[/{COLORS['warning']}]"
            )
            self.console.print(
                f"  [{COLORS['muted']}]Type /help for commands[/{COLORS['muted']}]\n"
            )

    def run(self) -> NoReturn:
        """Run the REPL."""
        asyncio.run(self.run_async())


def run_repl(config: VibeConfig, initial_mode: VibeMode = VibeMode.NORMAL) -> None:
    """Entry point for the REPL."""
    repl = ChefChatREPL(config, initial_mode)
    repl.run()
