"""TUI Command Registry - Functional command registration for the TUI.

This module provides a clean, testable command registry specifically for the TUI.
Commands are registered with decorators and can be dispatched without knowing
the implementation details.

The design allows gradual migration from mixin-based command handling.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol

# Type aliases for handler functions
CommandHandler: TypeAlias = Callable[["ChefAppProtocol", str], Awaitable[None]]
SimpleHandler: TypeAlias = Callable[["ChefAppProtocol"], Awaitable[None]]


@dataclass
class TUICommand:
    """A registered TUI command."""

    name: str  # Primary name (e.g., "/help")
    handler: CommandHandler | SimpleHandler
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    category: str = "general"
    takes_argument: bool = False
    hidden: bool = False  # Don't show in help

    @property
    def all_names(self) -> list[str]:
        """Get all names including aliases."""
        return [self.name, *self.aliases]


class TUICommandRegistry:
    """Registry for TUI commands.

    Provides a clean way to register and dispatch commands without
    the complexity of mixin-based dispatch.

    Usage:
        ```python
        registry = TUICommandRegistry()

        @registry.command("/help", description="Show help")
        async def show_help(app: ChefAppProtocol) -> None:
            pass

        @registry.command("/model", takes_argument=True)
        async def model_command(app: ChefAppProtocol, arg: str) -> None:
            pass

        # Dispatch
        await registry.dispatch(app, "/help")
        await registry.dispatch(app, "/model list")
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._commands: dict[str, TUICommand] = {}
        self._aliases: dict[str, str] = {}  # Maps alias -> primary name

    def command(
        self,
        name: str,
        *,
        description: str = "",
        aliases: list[str] | None = None,
        category: str = "general",
        takes_argument: bool = False,
        hidden: bool = False,
    ) -> Callable[[CommandHandler | SimpleHandler], CommandHandler | SimpleHandler]:
        """Decorator to register a command handler.

        Args:
            name: Command name (e.g., "/help")
            description: Help text for the command
            aliases: Alternative names for the command
            category: Category for grouping in help
            takes_argument: Whether command accepts an argument
            hidden: Whether to hide from help output

        Returns:
            Decorator function
        """

        def decorator(
            handler: CommandHandler | SimpleHandler,
        ) -> CommandHandler | SimpleHandler:
            cmd = TUICommand(
                name=name,
                handler=handler,
                description=description,
                aliases=aliases or [],
                category=category,
                takes_argument=takes_argument,
                hidden=hidden,
            )
            self.register(cmd)
            return handler

        return decorator

    def register(self, cmd: TUICommand) -> None:
        """Register a command.

        Args:
            cmd: The command to register
        """
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = cmd.name

    def find(self, name: str) -> TUICommand | None:
        """Find a command by name or alias.

        Args:
            name: Command name or alias

        Returns:
            The command if found, None otherwise
        """
        # Normalize name
        if not name.startswith("/"):
            name = f"/{name}"
        name = name.lower()

        # Direct lookup
        if name in self._commands:
            return self._commands[name]

        # Alias lookup
        if name in self._aliases:
            primary = self._aliases[name]
            return self._commands.get(primary)

        return None

    async def dispatch(self, app: ChefAppProtocol, command_line: str) -> bool:
        """Dispatch a command to its handler.

        Args:
            app: The TUI app instance
            command_line: Full command line (e.g., "/model list")

        Returns:
            True if command was handled, False otherwise
        """
        if not command_line.startswith("/"):
            return False

        parts = command_line.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        cmd = self.find(name)
        if not cmd:
            return False

        # Call handler with appropriate arguments
        if cmd.takes_argument:
            await cmd.handler(app, arg)  # type: ignore
        else:
            await cmd.handler(app)  # type: ignore

        return True

    def get_commands_by_category(self) -> dict[str, list[TUICommand]]:
        """Get commands grouped by category.

        Returns:
            Dict mapping category name to list of commands
        """
        result: dict[str, list[TUICommand]] = {}
        for cmd in self._commands.values():
            if cmd.hidden:
                continue
            if cmd.category not in result:
                result[cmd.category] = []
            result[cmd.category].append(cmd)
        return result

    def format_help(self) -> str:
        """Generate help text for all commands.

        Returns:
            Formatted help string in markdown
        """
        lines = ["## 📋 Available Commands\n"]

        for category, commands in sorted(self.get_commands_by_category().items()):
            lines.append(f"### {category.title()}\n")
            for cmd in sorted(commands, key=lambda c: c.name):
                alias_str = f" (also: {', '.join(cmd.aliases)})" if cmd.aliases else ""
                arg_hint = " <arg>" if cmd.takes_argument else ""
                lines.append(f"• `{cmd.name}{arg_hint}` — {cmd.description}{alias_str}")
            lines.append("")

        return "\n".join(lines)

    @property
    def command_names(self) -> list[str]:
        """Get all command names (for autocompletion)."""
        return list(self._commands.keys())


# ============================================================================
# Default TUI Commands (can be extended or overridden)
# ============================================================================


def create_default_registry() -> TUICommandRegistry:
    """Create a registry with default TUI commands.

    Returns:
        Configured registry with standard commands
    """
    registry = TUICommandRegistry()

    # Note: These are placeholder handlers.
    # The actual implementation will call methods on ChefChatApp.

    from chefchat.interface.handlers import model_handlers, system_handlers

    @registry.command(
        "/help",
        description="Show available commands",
        aliases=["/h", "/?"],
        category="general",
    )
    async def cmd_help(app: ChefAppProtocol) -> None:
        await system_handlers.show_help(app)

    @registry.command(
        "/status",
        description="Show current status",
        aliases=["/stats"],
        category="general",
    )
    async def cmd_status(app: ChefAppProtocol) -> None:
        await app._show_status()

    @registry.command(
        "/clear", description="Clear chat history", aliases=["/cls"], category="general"
    )
    async def cmd_clear(app: ChefAppProtocol) -> None:
        await system_handlers.handle_clear(app)

    @registry.command(
        "/quit",
        description="Exit the application",
        aliases=["/exit", "/q"],
        category="general",
    )
    async def cmd_quit(app: ChefAppProtocol) -> None:
        await system_handlers.handle_quit(app)

    @registry.command(
        "/model", description="Model management", category="models", takes_argument=True
    )
    async def cmd_model(app: ChefAppProtocol, arg: str) -> None:
        await model_handlers.handle_model_command(app, arg)

    @registry.command(
        "/layout",
        description="Switch TUI layout",
        category="system",
        takes_argument=True,
    )
    async def cmd_layout(app: ChefAppProtocol, arg: str) -> None:
        await system_handlers.handle_layout_command(app, arg)

    @registry.command("/config", description="Show configuration", category="system")
    async def cmd_config(app: ChefAppProtocol) -> None:
        await system_handlers.show_config(app)

    @registry.command("/reload", description="Reload configuration", category="system")
    async def cmd_reload(app: ChefAppProtocol) -> None:
        await system_handlers.reload_config(app)

    @registry.command("/mcp", description="Show MCP server status", category="system")
    async def cmd_mcp(app: ChefAppProtocol) -> None:
        await system_handlers.show_mcp_status(app)

    @registry.command("/wisdom", description="Get chef wisdom", category="fun")
    async def cmd_wisdom(app: ChefAppProtocol) -> None:
        await app._show_wisdom()

    @registry.command("/fortune", description="Get a chef fortune", category="fun")
    async def cmd_fortune(app: ChefAppProtocol) -> None:
        await app._show_fortune()

    @registry.command("/roast", description="Get roasted by the chef", category="fun")
    async def cmd_roast(app: ChefAppProtocol) -> None:
        await app._show_roast()

    @registry.command("/api", description="Manage API keys", category="system")
    async def cmd_api(app: ChefAppProtocol) -> None:
        await system_handlers.handle_api_command(app)

    @registry.command(
        "/git-setup",
        description="Configure GitHub token",
        category="system",
    )
    async def cmd_git_setup(app: ChefAppProtocol) -> None:
        await system_handlers.handle_git_setup(app)

    @registry.command(
        "/openrouter",
        description="OpenRouter management",
        category="models",
        takes_argument=True,
    )
    async def cmd_openrouter(app: ChefAppProtocol, arg: str) -> None:
        await system_handlers.handle_openrouter_command(app, arg)

    @registry.command(
        "/telegram",
        description="Telegram bot control",
        category="bots",
        takes_argument=True,
    )
    async def cmd_telegram(app: ChefAppProtocol, arg: str) -> None:
        await app._handle_telegram_command(arg)

    @registry.command(
        "/discord",
        description="Discord bot control",
        category="bots",
        takes_argument=True,
    )
    async def cmd_discord(app: ChefAppProtocol, arg: str) -> None:
        await app._handle_discord_command(arg)

    return registry


# Global registry instance
_tui_registry: TUICommandRegistry | None = None


def get_tui_command_registry() -> TUICommandRegistry:
    """Get or create the global TUI command registry."""
    global _tui_registry
    if _tui_registry is None:
        _tui_registry = create_default_registry()
    return _tui_registry
