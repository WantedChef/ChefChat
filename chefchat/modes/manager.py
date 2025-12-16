"""ChefChat Mode Manager
=======================

Refactored mode manager that orchestrates the mode system.
Previously a 1000+ line "God Class", now a clean coordinator.

This is the main entry point for mode management, delegating to:
- chefchat.modes.types: Core type definitions
- chefchat.modes.constants: All constants and configurations
- chefchat.modes.security: Write operation detection
- chefchat.modes.prompts: System prompt injection
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from chefchat.modes.constants import (
    MODE_CONFIGS,
    MODE_CYCLE_ORDER,
    MODE_PERSONALITIES,
    MODE_TIPS,
    READONLY_TOOLS,
)
from chefchat.modes.prompts import get_system_prompt_modifier
from chefchat.modes.security import is_write_operation
from chefchat.modes.types import ModeDescriptor, ModeState, VibeMode

if TYPE_CHECKING:
    from chefchat.modes.types import ModeConfig


class ModeManager:
    """Central manager for the ChefChat mode system.

    Handles mode cycling, transitions, tool permission checks,
    and system prompt injection.

    Example:
        >>> manager = ModeManager(initial_mode=VibeMode.NORMAL)
        >>> print(manager.get_mode_indicator())
        ✋ NORMAL
        >>> old, new = manager.cycle_mode()
        >>> print(f"{old} -> {new}")
        normal -> auto
    """

    # Class-level constants
    CYCLE_ORDER: ClassVar[tuple[VibeMode, ...]] = MODE_CYCLE_ORDER

    def __init__(
        self, initial_mode: VibeMode = VibeMode.NORMAL, snapshots_enabled: bool = True
    ) -> None:
        """Initialize the mode manager.

        Args:
            initial_mode: Starting mode (default: NORMAL for safety)
            snapshots_enabled: Whether get_state_snapshot returns data (can be toggled)
        """
        self.state = ModeState(current_mode=initial_mode)
        self._snapshots_enabled = snapshots_enabled

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def current_mode(self) -> VibeMode:
        """Get the current mode."""
        return self.state.current_mode

    @property
    def auto_approve(self) -> bool:
        """Whether tools should be auto-approved."""
        return self.state.auto_approve

    @property
    def read_only_tools(self) -> bool:
        """Whether write operations are blocked."""
        return self.state.read_only_tools

    @property
    def config(self) -> ModeConfig:
        """Get the configuration for the current mode."""
        return MODE_CONFIGS[self.state.current_mode]

    @property
    def snapshots_enabled(self) -> bool:
        """Whether state snapshots are enabled."""
        return self._snapshots_enabled

    # -------------------------------------------------------------------------
    # Mode Transitions
    # -------------------------------------------------------------------------

    def cycle_mode(self) -> tuple[VibeMode, VibeMode]:
        """Cycle to the next mode (Shift+Tab behavior).

        Returns:
            Tuple of (old_mode, new_mode)
        """
        old_mode = self.state.current_mode
        try:
            current_idx = self.CYCLE_ORDER.index(old_mode)
            next_idx = (current_idx + 1) % len(self.CYCLE_ORDER)
        except ValueError:
            # Mode not in cycle order, start from beginning
            next_idx = 0

        new_mode = self.CYCLE_ORDER[next_idx]
        self.set_mode(new_mode)
        return old_mode, new_mode

    def _coerce_mode(self, mode: VibeMode | str) -> VibeMode:
        """Convert a string or enum into a VibeMode, with validation."""
        if isinstance(mode, VibeMode):
            return mode

        normalized = mode.strip().lower()
        for candidate in VibeMode:
            if candidate.value == normalized:
                return candidate

        valid = ", ".join(m.value for m in VibeMode)
        raise ValueError(f"Unknown mode '{mode}'. Valid modes: {valid}.")

    def set_mode(self, mode: VibeMode) -> None:
        """Set a specific mode.

        Args:
            mode: The mode to switch to
        """
        config = MODE_CONFIGS[mode]
        now = datetime.now()

        self.state.current_mode = mode
        self.state.auto_approve = config.auto_approve
        self.state.read_only_tools = config.read_only
        self.state.started_at = now
        self.state.mode_history.append((mode, now))

    def set_mode_from_name(self, mode: VibeMode | str) -> VibeMode:
        """Set mode using either a VibeMode or a string name."""
        target = self._coerce_mode(mode)
        self.set_mode(target)
        return target

    def set_snapshots_enabled(self, enabled: bool) -> None:
        """Toggle whether get_state_snapshot should return data."""
        self._snapshots_enabled = bool(enabled)

    def describe_mode(self, mode: VibeMode | str | None = None) -> ModeDescriptor:
        """Return a structured descriptor for the requested mode."""
        target = self._coerce_mode(mode) if mode is not None else self.state.current_mode
        config = MODE_CONFIGS[target]

        return ModeDescriptor(
            id=target,
            name=target.value.upper(),
            emoji=config.emoji,
            description=config.description,
            auto_approve=config.auto_approve,
            read_only=config.read_only,
            personality=MODE_PERSONALITIES.get(target, ""),
            tips=list(MODE_TIPS.get(target, [])),
        )

    def list_modes(self) -> list[ModeDescriptor]:
        """Return descriptors for all modes in cycle order."""
        return [self.describe_mode(mode) for mode in self.CYCLE_ORDER]

    def get_state_snapshot(
        self, *, enabled: bool | None = None, include_modes: bool = True
    ) -> dict[str, Any]:
        """Structured snapshot of current mode state.

        Args:
            enabled: Override snapshots_enabled flag for this call.
            include_modes: Whether to include the list of available modes.
        """
        is_enabled = self._snapshots_enabled if enabled is None else bool(enabled)
        if not is_enabled:
            return {}

        current = self.describe_mode()
        snapshot: dict[str, Any] = {
            "current_mode": current.to_dict(),
            "state": self.state.to_dict(),
        }
        if include_modes:
            snapshot["available_modes"] = [mode.to_dict() for mode in self.list_modes()]
        return snapshot

    # -------------------------------------------------------------------------
    # Tool Permission Checks
    # -------------------------------------------------------------------------

    def should_approve_tool(self, tool_name: str) -> bool:
        """Determine if a tool should be automatically approved.

        Args:
            tool_name: Name of the tool being called

        Returns:
            True if tool should be auto-approved, False if confirmation needed
        """
        # Auto-approve mode approves everything
        if self.state.auto_approve:
            return True

        # In read-only mode, only approve read-only tools
        if self.state.read_only_tools:
            return tool_name in READONLY_TOOLS

        # In normal mode (not auto, not read-only), nothing is auto-approved
        return False

    def is_write_operation(
        self, tool_name: str, args: dict[str, Any] | None = None
    ) -> bool:
        """Detect if an operation would write to files.

        Delegates to chefchat.modes.security module.

        Args:
            tool_name: Name of the tool
            args: Tool arguments (for bash command analysis)

        Returns:
            True if this is a write operation
        """
        return is_write_operation(tool_name, args)

    def should_block_tool(
        self, tool_name: str, args: dict[str, Any] | None = None
    ) -> tuple[bool, str | None]:
        """Check if a tool should be blocked in the current mode.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments

        Returns:
            Tuple of (blocked: bool, reason: str | None)
        """
        # If not in read-only mode, nothing is blocked
        if not self.state.read_only_tools:
            return False, None

        # Check if this is a write operation
        if not self.is_write_operation(tool_name, args):
            return False, None

        # Block and provide helpful message
        mode_name = self.state.current_mode.value.upper()
        emoji = self.config.emoji

        reason = f"""⛔ Tool '{tool_name}' blocked in {emoji} {mode_name} mode

This operation would modify files. Current mode is read-only for safety.

**Options:**
1. Press Shift+Tab to switch to NORMAL or AUTO mode
2. Let me add this to the implementation plan instead

What would you like to do?"""

        return True, reason

    # -------------------------------------------------------------------------
    # Display Methods
    # -------------------------------------------------------------------------

    def get_mode_indicator(self) -> str:
        """Get a display string for the current mode.

        Returns:
            String like "📋 PLAN" or "🚀 YOLO"
        """
        emoji = self.config.emoji
        name = self.state.current_mode.value.upper()
        return f"{emoji} {name}"

    def get_mode_description(self) -> str:
        """Get the short description of current mode.

        Returns:
            One-line description of mode behavior
        """
        return self.config.description

    def get_transition_message(self, old_mode: VibeMode, new_mode: VibeMode) -> str:
        """Get the message to display when transitioning modes.

        Args:
            old_mode: The mode being left
            new_mode: The mode being entered

        Returns:
            Formatted transition message
        """
        new_config = MODE_CONFIGS[new_mode]
        return (
            f"🔄 Mode: {old_mode.value.upper()} → {new_mode.value.upper()}\n"
            f"{new_config.emoji} {new_mode.value.upper()}: "
            f"{new_config.description}"
        )

    # -------------------------------------------------------------------------
    # System Prompt Injection
    # -------------------------------------------------------------------------

    def get_system_prompt_modifier(self) -> str:
        """Get mode-specific system prompt injection.

        Delegates to chefchat.modes.prompts module.

        Returns:
            XML-formatted mode instruction block
        """
        return get_system_prompt_modifier(self.state.current_mode)
