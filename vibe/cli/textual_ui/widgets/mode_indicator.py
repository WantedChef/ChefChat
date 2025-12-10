"""Mode Indicator Widget for ChefChat
==================================

Visual indicator showing the current operational mode.
Supports all 5 ChefChat modes with distinct styling.
"""

from __future__ import annotations

from typing import ClassVar

from textual.widgets import Static

from vibe.cli.mode_manager import MODE_CONFIGS, ModeManager, VibeMode


class ModeIndicator(Static):
    """A widget that displays the current operational mode.

    Modes:
        📋 PLAN     - Research & Planning (read-only)
        ✋ NORMAL   - Ask before each tool
        ⚡ AUTO     - Auto-approve all tools
        🚀 YOLO     - Maximum speed, minimal output
        🏛️ ARCHITECT - High-level design (read-only)

    Attributes:
        _mode: The current VibeMode
        _mode_manager: Optional reference to the ModeManager
    """

    # CSS class names for each mode (for styling)
    MODE_CLASSES: ClassVar[dict[VibeMode, str]] = {
        VibeMode.PLAN: "mode-plan",
        VibeMode.NORMAL: "mode-normal",
        VibeMode.AUTO: "mode-auto",
        VibeMode.YOLO: "mode-yolo",
        VibeMode.ARCHITECT: "mode-architect",
    }

    def __init__(
        self, auto_approve: bool = False, mode_manager: ModeManager | None = None
    ) -> None:
        """Initialize the mode indicator.

        Args:
            auto_approve: Legacy flag for backwards compatibility
            mode_manager: Optional ModeManager to sync with
        """
        super().__init__()
        self.can_focus = False

        if mode_manager:
            self._mode = mode_manager.current_mode
            self._mode_manager = mode_manager
        else:
            # Legacy compatibility: auto_approve -> AUTO, else NORMAL
            self._mode = VibeMode.AUTO if auto_approve else VibeMode.NORMAL
            self._mode_manager = None

        self._update_display()

    def _update_display(self) -> None:
        """Update the widget display for the current mode."""
        config = MODE_CONFIGS[self._mode]
        mode_name = self._mode.value.upper()

        # Format: "📋 PLAN (shift+tab to cycle)"
        text = f"{config.emoji} {mode_name} (shift+tab to cycle)"
        self.update(text)

        # Update CSS classes
        for mode, css_class in self.MODE_CLASSES.items():
            if mode == self._mode:
                self.add_class(css_class)
            else:
                self.remove_class(css_class)

    def set_mode(self, mode: VibeMode) -> None:
        """Set the displayed mode.

        Args:
            mode: The new mode to display
        """
        self._mode = mode
        self._update_display()

    def set_auto_approve(self, enabled: bool) -> None:
        """Legacy method for backwards compatibility.

        Maps auto_approve to AUTO/NORMAL mode.

        Args:
            enabled: Whether auto-approve is enabled
        """
        self._mode = VibeMode.AUTO if enabled else VibeMode.NORMAL
        self._update_display()

    def cycle_mode(self) -> tuple[VibeMode, VibeMode]:
        """Cycle to the next mode.

        Returns:
            Tuple of (old_mode, new_mode)
        """
        if self._mode_manager:
            old, new = self._mode_manager.cycle_mode()
            self._mode = new
            self._update_display()
            return old, new

        # Manual cycling without manager
        cycle_order = [
            VibeMode.NORMAL,
            VibeMode.AUTO,
            VibeMode.PLAN,
            VibeMode.YOLO,
            VibeMode.ARCHITECT,
        ]
        old_mode = self._mode
        current_idx = cycle_order.index(self._mode)
        next_idx = (current_idx + 1) % len(cycle_order)
        self._mode = cycle_order[next_idx]
        self._update_display()
        return old_mode, self._mode

    @property
    def current_mode(self) -> VibeMode:
        """Get the current mode."""
        return self._mode

    @property
    def is_auto_approve(self) -> bool:
        """Whether auto-approve is enabled (for backwards compat)."""
        return MODE_CONFIGS[self._mode].auto_approve

    @property
    def is_read_only(self) -> bool:
        """Whether the current mode is read-only."""
        return MODE_CONFIGS[self._mode].read_only
