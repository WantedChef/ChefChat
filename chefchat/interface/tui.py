"""ChefChat TUI - Entry Point.

This module re-exports the main application and run function.
The implementation has been moved to `chefchat/interface/app.py`.
"""

from __future__ import annotations

from chefchat.interface.app import ChefChatApp, run
from chefchat.interface.screens.confirm_restart import ConfirmRestartScreen
from chefchat.interface.widgets.kitchen_ui import KitchenFooter

__all__ = ["ChefChatApp", "ConfirmRestartScreen", "KitchenFooter", "run"]
