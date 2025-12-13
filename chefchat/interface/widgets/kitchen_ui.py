"""Shared Kitchen UI Components."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, Static
from textual.worker import Worker

from chefchat.interface.constants import WHISK_FRAMES
from chefchat.modes import MODE_CONFIGS, ModeManager

if TYPE_CHECKING:
    pass


class WhiskLoader(Horizontal):
    """Animated loading indicator with kitchen flair."""

    # CSS defined in styles.tcss

    def __init__(self) -> None:
        super().__init__()
        self._frame_index = 0
        self._message = "Cooking..."
        self._worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        yield Static(WHISK_FRAMES[0], classes="whisk-spinner")
        yield Static(self._message, classes="whisk-message")

    async def on_unmount(self) -> None:
        self.stop()

    def start(self, message: str = "Cooking...") -> None:
        self._message = message
        try:
            msg_widget = self.query_one(".whisk-message", Static)
            msg_widget.update(message)
        except Exception:
            pass

        if self._worker and not self._worker.is_finished:
            return

        self.add_class("visible")

        async def _animate_worker() -> None:
            try:
                while True:
                    self._frame_index = (self._frame_index + 1) % len(WHISK_FRAMES)
                    try:
                        spinner = self.query_one(".whisk-spinner", Static)
                        spinner.update(WHISK_FRAMES[self._frame_index])
                    except Exception:
                        break
                    await asyncio.sleep(0.15)
            except asyncio.CancelledError:
                pass
            finally:
                self.remove_class("visible")

        self._worker = self.run_worker(
            _animate_worker(),
            exclusive=True,
            group="whisk_animation",
            exit_on_error=False,
        )

    def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._worker = None
        self.remove_class("visible")
        self._frame_index = 0


class KitchenHeader(Static):
    """Custom header with kitchen branding."""

    #  CSS defined in styles.tcss

    def compose(self) -> ComposeResult:
        yield Static(
            "👨‍🍳 [bold]ChefChat[/] • The Michelin Star AI-Engineer",
            classes="header-title",
        )


class CommandInput(Input):
    """Custom command input with kitchen styling."""

    # CSS defined in styles.tcss


class KitchenFooter(Horizontal):
    """Enhanced footer showing mode, status, and key hints."""

    # CSS defined in styles.tcss

    def __init__(
        self,
        mode_manager: ModeManager,
        active_model: str = "Unknown",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._mode_manager = mode_manager
        self._active_model = active_model

    def compose(self) -> ComposeResult:
        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]
        auto = "ON" if self._mode_manager.auto_approve else "OFF"
        auto_class = "auto-on" if self._mode_manager.auto_approve else "auto-off"

        # Mode Section
        yield Static(f"{config.emoji} {mode.value.upper()}", classes="footer-mode")

        # Model Info (New)
        yield Static(f" 🤖 {self._active_model} ", classes="footer-label footer-model")

        # Status Section
        yield Static("Auto: ", classes="footer-label")
        yield Static(auto, classes=f"footer-value {auto_class}")

        yield Static(" | ", classes="footer-sep")

        # Key Hints
        yield Static("Shift+Tab: Cycle Mode", classes="key-hint")
        yield Static("Ctrl+C: Cancel", classes="key-hint")
        yield Static("Ctrl+Q: Quit", classes="key-hint")

    def refresh_mode(self) -> None:
        """Refresh the footer display after a mode change."""
        mode = self._mode_manager.current_mode
        config = MODE_CONFIGS[mode]
        auto = "ON" if self._mode_manager.auto_approve else "OFF"

        try:
            # Update Mode
            self.query_one(".footer-mode", Static).update(
                f"{config.emoji} {mode.value.upper()}"
            )

            # Update Auto Status
            auto_widget = self.query_one(".footer-value", Static)
            auto_widget.update(auto)

            # Update class for color
            auto_widget.remove_class("auto-on", "auto-off")
            new_class = "auto-on" if self._mode_manager.auto_approve else "auto-off"
            auto_widget.add_class(new_class)

        except Exception:
            pass

    def refresh_model(self, active_model: str) -> None:
        self._active_model = active_model
        try:
             self.query_one(".footer-model", Static).update(f" 🤖 {active_model} ")
        except Exception:
             pass
