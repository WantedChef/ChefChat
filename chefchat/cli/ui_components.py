"""ChefChat REPL UI Components
=============================

Elegant, Michelin-star UI components for the ChefChat REPL.
Design philosophy: "Mistral Vibe Aesthetics meets Michelin Star Elegance"

Color Palette:
    - Primary (accent): #FF7000 (Mistral Orange)
    - Secondary (borders): #404040 (Dark Grey)
    - Text: #E0E0E0 (Off-white)
    - Muted: #666666 (Dim)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from chefchat.cli.mode_manager import ModeManager
    from chefchat.core.config import VibeConfig


# =============================================================================
# COLOR CONSTANTS
# =============================================================================

COLORS = {
    # Technical names
    "primary": "#FF7000",  # Mistral Orange - accents, active elements
    "secondary": "#404040",  # Dark Grey - borders, inactive
    "text": "#E0E0E0",  # Off-white - readable text
    "muted": "#666666",  # Dim - secondary info
    "success": "#00D26A",  # Green - success states
    "warning": "#FFB800",  # Amber - warnings
    "error": "#FF4444",  # Red - errors
    "bg_dark": "#1A1A1A",  # Dark background
    "bg_subtle": "#252525",  # Slightly lighter bg
    # Kitchen-themed aliases (for repl.py compatibility)
    "fire": "#FF7000",  # Same as primary - the flame of the kitchen
    "charcoal": "#1A1A1A",  # Same as bg_dark - the grill
    "silver": "#E0E0E0",  # Same as text - polished steel
    "smoke": "#666666",  # Same as muted - subtle smoke
    "sage": "#00D26A",  # Same as success - fresh herbs
    "honey": "#FFB800",  # Same as warning - golden honey
    "ember": "#FF4444",  # Hot embers
    "cream": "#F5F5DC",  # Cream color for highlights
    "ash": "#404040",  # Cool ash
    "gold": "#FFD700",  # Gold for highlights
    "lavender": "#E6E6FA",  # Lavender for subtle accents
}


# =============================================================================
# THEME & RENDER CONTEXT
# =============================================================================


@dataclass(frozen=True)
class Theme:
    """Theme definition with palette and feature toggles."""

    palette: dict[str, str]
    emoji_enabled: bool = True
    color_enabled: bool = True


@dataclass(frozen=True)
class RenderContext:
    """Rendering context carrying theme and terminal characteristics."""

    theme: Theme
    width: int = 80


DEFAULT_THEME = Theme(palette=COLORS)


def _palette(ctx: RenderContext | None) -> dict[str, str]:
    """Return an active palette for rendering."""
    if ctx and not ctx.theme.color_enabled:
        return {key: "default" for key in COLORS}
    return ctx.theme.palette if ctx else COLORS


def _icon(emoji: str, fallback: str, ctx: RenderContext | None) -> str:
    """Return emoji or ASCII fallback based on context."""
    if ctx and not ctx.theme.emoji_enabled:
        return fallback
    return emoji


# =============================================================================
# HEADER COMPONENT (The Pass)
# =============================================================================


@dataclass
class HeaderData:
    """Data for the header display."""

    model: str
    mode_indicator: str
    mode_emoji: str
    workdir: str
    version: str = ""
    context_used: int = 0
    context_max: int = 32000


class HeaderDisplay:
    """Elegant header component showing metadata in a clean grid layout.

    Visual output:
    ┌──────────────────────────────────────────────────────────────────┐
    │  👨‍🍳 ChefChat                                    ✋ NORMAL        │
    │  ──────────────────────────────────────────────────────────────  │
    │  mistral-large-latest   │   📂 ~/project   │   0/32k tokens     │
    └──────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, data: HeaderData) -> None:
        self.data = data

    def render(self, ctx: RenderContext | None = None) -> Panel:
        """Render the header as a Rich Panel."""
        palette = _palette(ctx)
        width = ctx.width if ctx else 80
        separator_len = max(30, min(width - 4, 60))

        # Build components
        top_row = self._build_top_row(palette, ctx)
        separator = Text("─" * separator_len, style=palette["secondary"])
        meta_row = self._build_meta_row(palette)

        # Combine all elements
        content = Group(top_row, Text(), separator, Text(), meta_row)
        return Panel(content, border_style=palette["secondary"], padding=(0, 2))

    def _build_top_row(
        self, palette: dict[str, str], ctx: RenderContext | None
    ) -> Table:
        """Build the top row with brand and mode."""
        top_row = Table.grid(expand=True)
        top_row.add_column("brand", justify="left", ratio=1)
        top_row.add_column("mode", justify="right", ratio=1)

        brand = Text()
        brand.append(f"{_icon('👨‍🍳', 'Chef', ctx)} ", style="bold")
        brand.append("ChefChat", style=f"bold {palette['primary']}")
        if self.data.version:
            brand.append(f" v{self.data.version}", style=palette["muted"])

        mode = Text()
        mode.append(f"{self.data.mode_emoji} ", style="bold")
        mode.append(self.data.mode_indicator, style=f"bold {palette['primary']}")

        top_row.add_row(brand, mode)
        return top_row

    def _build_meta_row(self, palette: dict[str, str]) -> Table:
        """Build the meta row with model, path, and context info."""
        meta_row = Table.grid(expand=True)
        meta_row.add_column("model", justify="left", ratio=2)
        meta_row.add_column("path", justify="center", ratio=2)
        meta_row.add_column("context", justify="right", ratio=1)

        # Model text
        model_text = Text(self.data.model, style=palette["text"])

        # Truncate path if needed
        MAX_PATH_LENGTH = 25
        workdir = self.data.workdir
        if len(workdir) > MAX_PATH_LENGTH:
            workdir = "~" + workdir[-(MAX_PATH_LENGTH - 1) :]
        path_text = Text()
        path_text.append("📂 ", style="dim")
        path_text.append(workdir, style=palette["muted"])

        # Context display
        ctx_text = Text()
        ctx_used_k = self.data.context_used / 1000
        ctx_max_k = self.data.context_max / 1000
        ctx_text.append(f"{ctx_used_k:.0f}/{ctx_max_k:.0f}k", style=palette["muted"])

        meta_row.add_row(model_text, path_text, ctx_text)
        return meta_row


# =============================================================================
# PROMPT BUILDER (The Station)
# =============================================================================


class PromptBuilder:
    """Build elegant prompt strings for prompt_toolkit.

    Creates a Powerline-style prompt segment:
        [bg=orange] 👨‍🍳 NORMAL [/] ›
    """

    # Safe Unicode characters for Powerline-style (no special fonts needed)
    SEGMENT_END = ""  # Simple space separator
    ARROW = "›"

    @staticmethod
    def build_prompt(mode_emoji: str, mode_name: str) -> str:
        """Build HTML-formatted prompt for prompt_toolkit.

        Args:
            mode_emoji: Emoji for the mode (✋, ⚡, etc.)
            mode_name: Mode name (NORMAL, AUTO, etc.)

        Returns:
            HTML string for prompt_toolkit
        """
        # Format: [emoji MODE] ›
        return (
            f'<style bg="#FF7000" fg="white"> {mode_emoji} {mode_name} </style>'
            f'<style fg="#FF7000"> </style>'
            f'<style fg="#666666">›</style> '
        )

    @staticmethod
    def build_prompt_simple(mode_emoji: str, mode_name: str) -> str:
        """Build simpler prompt without background colors.

        Fallback for terminals with limited support.
        """
        return f"<mode>{mode_emoji} {mode_name}</mode> <prompt>›</prompt> "


# =============================================================================
# STATUS BAR (The Footer)
# =============================================================================


class StatusBar:
    """Sticky status bar with keyboard shortcuts.

    Visual output:
    ───────────────────────────────────────────────────────────────────────
    [Shift+Tab] Mode  •  [/] Commands  •  [Ctrl+C] Cancel  •  auto-approve: off
    """

    @staticmethod
    def render(auto_approve: bool = False, ctx: RenderContext | None = None) -> Text:
        """Render the status bar."""
        palette = _palette(ctx)
        bar = Text()

        # Separator line
        bar.append("─" * 70, style=palette["secondary"])
        bar.append("\n")

        # Shortcuts
        shortcuts = [("Shift+Tab", "Mode"), ("/help", "Commands"), ("Ctrl+C", "Cancel")]

        for i, (key, action) in enumerate(shortcuts):
            if i > 0:
                bar.append("  •  ", style=palette["muted"])
            bar.append(f"[{key}]", style=f"bold {palette['primary']}")
            bar.append(f" {action}", style=palette["muted"])

        # Auto-approve status
        bar.append("  •  ", style=palette["muted"])
        bar.append("auto-approve: ", style=palette["muted"])
        if auto_approve:
            bar.append("on", style=f"bold {palette['success']}")
        else:
            bar.append("off", style=f"bold {palette['warning']}")

        return bar


# =============================================================================
# MODE TRANSITION DISPLAY
# =============================================================================


class ModeTransitionDisplay:
    """Display elegant mode transition messages.

    Visual output:
    ╭──────────────────────────────────────────────────────────────╮
    │  🔄 NORMAL → AUTO                                            │
    │  ────────────────────────────────────────────────────────    │
    │  ⚡ Auto-approve all tool executions                        │
    │                                                              │
    │  💡 Tools are auto-approved - I'll execute without asking   │
    │  ⚠️ I'll still explain what I'm doing                       │
    │  🛑 Press Ctrl+C to interrupt if needed                     │
    ╰──────────────────────────────────────────────────────────────╯
    """

    @staticmethod
    def render(
        old_mode: str,
        new_mode: str,
        new_emoji: str,
        description: str,
        tips: list[str],
        ctx: RenderContext | None = None,
    ) -> Panel:
        """Render mode transition panel."""
        palette = _palette(ctx)
        content = Text()

        # Transition header
        content.append("🔄 ", style="bold")
        content.append(old_mode, style=palette["muted"])
        content.append(" → ", style=palette["muted"])
        content.append(new_mode, style=f"bold {palette['primary']}")
        content.append("\n")

        # Separator
        content.append("─" * 50, style=palette["secondary"])
        content.append("\n")

        # Mode description
        content.append(f"{new_emoji} ", style="bold")
        content.append(description, style=palette["text"])
        content.append("\n\n")

        # Tips
        for tip in tips[:3]:  # Max 3 tips
            content.append(f"  {tip}\n", style=palette["muted"])

        return Panel(content, border_style=palette["secondary"], padding=(0, 2))


# =============================================================================
# RESPONSE DISPLAY
# =============================================================================


class ResponseDisplay:
    """Display AI responses with elegant styling."""

    @staticmethod
    def render_response(
        content: RenderableType, ctx: RenderContext | None = None
    ) -> Panel:
        """Wrap response content in a styled panel."""
        palette = _palette(ctx)
        return Panel(
            content,
            title=f"[{palette['primary']}]👨‍🍳 Chef[/{palette['primary']}]",
            title_align="left",
            border_style=palette["secondary"],
            padding=(1, 2),
        )

    @staticmethod
    def render_tool_call(tool_name: str, ctx: RenderContext | None = None) -> Text:
        """Render a tool call indicator."""
        palette = _palette(ctx)
        text = Text()
        text.append("  🔧 ", style="dim")
        text.append(tool_name, style=f"bold {palette['primary']}")
        return text

    @staticmethod
    def render_tool_result(
        success: bool = True, message: str = "", ctx: RenderContext | None = None
    ) -> Text:
        """Render a tool result indicator."""
        palette = _palette(ctx)
        text = Text()
        if success:
            text.append("    ✓", style=palette["success"])
        else:
            text.append("    ✗ ", style=palette["error"])
            if message:
                # Truncate long messages
                MAX_ERROR_MSG_LENGTH = 50
                msg = (
                    message[:MAX_ERROR_MSG_LENGTH] + "..."
                    if len(message) > MAX_ERROR_MSG_LENGTH
                    else message
                )
                text.append(msg, style=palette["error"])
        return text


# =============================================================================
# APPROVAL DIALOG
# =============================================================================


class ApprovalDialog:
    """Elegant tool approval dialog.

    Visual output:
    ╭──────────────────────────────────────────────────────────────╮
    │  🍽️ Order Confirmation                                       │
    │  ────────────────────────────────────────────────────────    │
    │  Tool: write_file                                            │
    │                                                              │
    │  {                                                           │
    │    "path": "/tmp/test.txt",                                  │
    │    "content": "Hello World"                                  │
    │  }                                                           │
    │                                                              │
    │  [Y] Execute  •  [n] Skip  •  [always] Auto-approve session │
    ╰──────────────────────────────────────────────────────────────╯
    """

    @staticmethod
    def render(
        tool_name: str, args_syntax: RenderableType, ctx: RenderContext | None = None
    ) -> Panel:
        """Render the approval dialog."""
        palette = _palette(ctx)
        content = Text()
        content.append("Tool: ", style="bold")
        content.append(tool_name, style=f"bold {palette['primary']}")

        # The args_syntax should be a Rich Syntax object passed separately
        combined = Group(content, Text(), args_syntax)

        subtitle = Text()
        subtitle.append("[", style=palette["muted"])
        subtitle.append("Y", style=f"bold {palette['success']}")
        subtitle.append("] Execute  •  [", style=palette["muted"])
        subtitle.append("n", style=f"bold {palette['error']}")
        subtitle.append("] Skip  •  [", style=palette["muted"])
        subtitle.append("always", style=f"bold {palette['warning']}")
        subtitle.append("] Auto-approve", style=palette["muted"])

        return Panel(
            combined,
            title=f"[{palette['primary']}]🍽️ Order Confirmation[/{palette['primary']}]",
            subtitle=subtitle,
            border_style=palette["primary"],
            padding=(1, 2),
        )


# =============================================================================
# HELP DISPLAY
# =============================================================================


class HelpDisplay:
    """Display the help menu with commands and descriptions."""

    @staticmethod
    def render(ctx: RenderContext | None = None) -> Panel:
        """Render the help panel."""
        palette = _palette(ctx)

        # Create a grid for the layout
        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)

        def create_category_table(title: str, items: list[tuple[str, str]]) -> Panel:
            t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
            t.add_column("Key", style=f"bold {palette['primary']}", no_wrap=True)
            t.add_column("Desc", style=palette["text"])

            for key, desc in items:
                t.add_row(key, desc)

            return Panel(
                t,
                title=f"[{palette['muted']}]{title}[/{palette['muted']}]",
                title_align="left",
                border_style=palette["secondary"],
                box=box.ROUNDED if ctx and ctx.theme.emoji_enabled else box.ASCII,
            )

        # 1. Essential Commands
        essentials = [
            ("/help", "Show this help menu"),
            ("/clear", "Clear conversation history"),
            ("/compact", "Compact/summarize history"),
            ("/exit", "Exit ChefChat"),
            ("Ctrl+C", "Cancel / Stop generation"),
        ]

        # 2. Configuration & Status
        config = [
            ("/model", "Switch AI model"),
            ("/mode", "Show current mode info"),
            ("/modes", "List available modes"),
            ("/theme", "Switch UI theme"),
            ("/status", "Show session status"),
            ("/stats", "Show session statistics"),
            ("Shift+Tab", "Cycle modes (Normal/Auto)"),
        ]

        # 3. Integrations (New!)
        integrations = [
            ("/git-setup", "Configure GitHub config"),
            ("/telegram", "Manage Telegram bot"),
            ("/discord", "Manage Discord bot"),
        ]

        # 4. Chef's Specials (Easter Eggs)
        specials = [
            ("/chef", "Kitchen status report"),
            ("/wisdom", "Daily chef wisdom"),
            ("/roast", "Get roasted by Gordon"),
            ("/plate", "Visual plating status"),
            ("/fortune", "Developer fortune cookie"),
        ]

        # Add to grid
        # Left column: Essentials + Integrations
        left_col = Group(
            create_category_table("🚀 Essentials", essentials),
            Text(""),  # Spacer
            create_category_table("🔌 Integrations", integrations),
        )

        # Right column: Config + Specials
        right_col = Group(
            create_category_table("⚙️  Configuration", config),
            Text(""),  # Spacer
            create_category_table("👨‍🍳 Chef's Specials", specials),
        )

        grid.add_row(left_col, right_col)

        return Panel(
            grid,
            title=f"[{palette['primary']}]🍳 ChefChat Command Menu[/{palette['primary']}]",
            border_style=palette["primary"],
            padding=(1, 2),
            subtitle=f"[{palette['muted']}]Type any command to execute[/{palette['muted']}]",
        )


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


def create_header(
    config: VibeConfig, mode_manager: ModeManager, ctx: RenderContext | None = None
) -> Panel:
    """Factory function to create header from config and mode manager."""
    from chefchat.core import __version__

    active_model = config.get_active_model()

    data = HeaderData(
        model=active_model.alias,  # Use .alias to get model name string
        mode_indicator=mode_manager.current_mode.value.upper(),
        mode_emoji=mode_manager.config.emoji,
        workdir=str(config.effective_workdir),
        version=__version__,
    )

    return HeaderDisplay(data).render(ctx)


def create_mode_transition(
    mode_manager: ModeManager,
    old_mode_name: str,
    new_mode_name: str,
    tips: list[str],
    ctx: RenderContext | None = None,
) -> Panel:
    """Factory function to create mode transition display."""
    return ModeTransitionDisplay.render(
        old_mode=old_mode_name,
        new_mode=new_mode_name,
        new_emoji=mode_manager.config.emoji,
        description=mode_manager.config.description,
        tips=tips,
        ctx=ctx,
    )


def get_greeting() -> tuple[str, str]:
    """Get a time-appropriate greeting.

    Returns:
        Tuple of (greeting_text, greeting_emoji)
    """
    from datetime import datetime

    # Time boundaries for greetings
    MORNING_START = 5
    AFTERNOON_START = 12
    EVENING_START = 17
    NIGHT_START = 21

    hour = datetime.now().hour

    if MORNING_START <= hour < AFTERNOON_START:
        return ("Good morning", "☀️")
    elif AFTERNOON_START <= hour < EVENING_START:
        return ("Good afternoon", "🌤️")
    elif EVENING_START <= hour < NIGHT_START:
        return ("Good evening", "🌆")
    else:
        return ("Welcome back", "🌙")
