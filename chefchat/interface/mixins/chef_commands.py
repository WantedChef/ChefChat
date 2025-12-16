"""Chef Commands Mixin for ChefChat TUI.

Provides chef-style informational commands: modes, status, wisdom, roast, fortune, etc.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from chefchat.interface.protocols import ChefAppProtocol


class ChefCommandsMixin:
    """Mixin providing chef-style fun and status commands for ChefChatApp.

    Requires the following attributes on self:
    - _mode_manager: ModeManager
    - _session_start_time: float
    - _tools_executed: int
    - _agent: Agent | None
    - _bus: KitchenBus | None
    - _brigade: Brigade | None
    """

    # Type hint for self when used as mixin
    self: ChefAppProtocol

    async def _show_modes(self) -> None:
        """Show available modes with current mode highlighted."""
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.modes import ModeManager

        manager: ModeManager = self._mode_manager
        descriptors = manager.list_modes()
        current = manager.current_mode
        lines = [
            "## 🔄 Available Modes",
            "",
            "Press **Shift+Tab** to cycle through modes:",
            "",
        ]

        for descriptor in descriptors:
            mode = descriptor.id
            marker = "▶" if mode == current else " "
            perms = []
            if descriptor.read_only:
                perms.append("🔒 Read-only")
            if descriptor.auto_approve:
                perms.append("🤖 Auto-approve")
            if not perms:
                perms.append("✋ Confirm each")
            perm_str = " • ".join(perms)
            lines.append(
                f"{marker} {descriptor.emoji} **{descriptor.name}**: {descriptor.description} ({perm_str})"
            )

        lines.extend(["", "---", f"Current: **{current.value.upper()}**"])
        self.query_one("#ticket-rail", TicketRail).add_system_message("\n".join(lines))

    async def _show_status(self) -> None:
        """Show session status with full statistics."""
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.modes import MODE_CONFIGS

        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]
        auto = "ON" if self._mode_manager.auto_approve else "OFF"

        # Calculate uptime
        uptime_seconds = int(time.time() - self._session_start_time)
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
        if self._agent and hasattr(self._agent, "stats"):
            token_count = getattr(self._agent.stats, "total_tokens", 0)

        status = f"""## 📊 Today's Service

**⏱️  Service Time**: {uptime_str}
**🔤 Tokens Used**: {token_count:,}
**🔧 Tools Executed**: {self._tools_executed}
**🎯 Current Mode**: {config.emoji} {mode.value.upper()}
**⚡ Auto-Approve**: {auto}
**🍳 Kitchen**: {"🟢 Ready" if self._bus else "🔴 Initializing..."}
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(status)

    async def _show_wisdom(self) -> None:
        """Show chef wisdom."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        wisdoms = [
            '🧑‍🍳 "Mise en place is not just for cooking—it\'s for coding too."',
            '🔪 "Sharp tools, sharp code. Keep your dependencies updated."',
            '🍳 "Low and slow wins the race. Don\'t rush your tests."',
            '🧂 "Season to taste. Iterate based on feedback."',
            '🍲 "A watched pot never boils. A watched CI never finishes."',
            '👨‍🍳 "Every chef was once a dishwasher. Keep refactoring."',
        ]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            random.choice(wisdoms)
        )

    async def _show_roast(self) -> None:
        """Get roasted by Gordon."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        roasts = [
            '🔥 "This code is so raw, it\'s still mooing!"',
            '🔥 "I\'ve seen better architecture in a sandcastle!"',
            '🔥 "WHERE IS THE ERROR HANDLING?!"',
            '🔥 "This function is so long, it needs a GPS!"',
            '🔥 "You call that a commit message? Pathetic!"',
            '🔥 "My grandmother writes cleaner Python, and she\'s a COBOL developer!"',
        ]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            random.choice(roasts)
        )

    async def _show_fortune(self) -> None:
        """Developer fortune cookie."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        fortunes = [
            "🥠 Your next merge conflict will resolve itself peacefully.",
            "🥠 The bug you've been hunting is in the file you refuse to check.",
            "🥠 A refactor is in your future. Embrace it.",
            "🥠 Your deployment will succeed on the first try (just kidding).",
            "🥠 The documentation you need has not been written yet.",
            "🥠 Someone will appreciate your comment today.",
        ]
        self.query_one("#ticket-rail", TicketRail).add_system_message(
            random.choice(fortunes)
        )

    async def _show_chef_status(self) -> None:
        """Show chef/kitchen status."""
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.modes import MODE_CONFIGS

        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]
        auto = "ON" if self._mode_manager.auto_approve else "OFF"
        bus_status = (
            "🟢 Running" if self._bus and self._bus.is_running else "🔴 Not Ready"
        )

        status = f"""## 👨‍🍳 Kitchen Status

**Current Mode**: {config.emoji} {mode.value.upper()}
**Description**: {config.description}
**Auto-Approve**: {auto}
**Kitchen Bus**: {bus_status}

---
*Press Shift+Tab to cycle modes*
"""
        self.query_one("#ticket-rail", TicketRail).add_system_message(status)

    async def _chef_taste(self) -> None:
        """Trigger the Expeditor to run taste tests."""
        from chefchat.interface.widgets.ticket_rail import TicketRail
        from chefchat.kitchen.bus import ChefMessage, MessagePriority

        if not self._brigade:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                "⚠️ **Expeditor not available**\n\n"
                "The kitchen brigade is not fully assembled. Run with `uv run vibe` for full kitchen experience."
            )
            return

        ticket_id = str(uuid4())[:8]
        message = ChefMessage(
            sender="tui",
            recipient="expeditor",
            action="TASTE_TEST",
            payload={"ticket_id": ticket_id, "tests": ["pytest", "ruff"], "path": "."},
            priority=MessagePriority.HIGH,
        )

        await self._bus.publish(message)
        try:
            self.query_one("#ticket-rail", TicketRail).add_system_message(
                f"🥄 **Taste Test Ordered** (Ticket #{ticket_id})\n\n"
                "Expeditor is checking the dish (running tests & linting)..."
            )
        except Exception:
            pass

    async def _chef_timer(self, arg: str) -> None:
        """Show timer info."""
        from chefchat.interface.widgets.ticket_rail import TicketRail

        self.query_one("#ticket-rail", TicketRail).add_system_message(
            "## ⏱️ Kitchen Timer\n\n"
            "Kitchen timer is coming soon to the TUI!\n"
            "Use it to track long-running tasks or just to boil an egg perfectly."
        )
