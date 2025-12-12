"""ChefChat TUI - Entry Point.

This module re-exports the main application and run function.
The implementation has been moved to `chefchat/interface/app.py`.
"""

from __future__ import annotations

from chefchat.interface.app import ChefChatApp, run

__all__ = ["ChefChatApp", "run"]
