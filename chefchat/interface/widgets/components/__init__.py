"""Reusable Widget Components.

This module exports smaller, focused widgets extracted from larger
widgets like ThePlate for better reusability and testability.
"""

from __future__ import annotations

from chefchat.interface.widgets.components.activity_panel import (
    ActivityPanel,
    ToolPanel,
)
from chefchat.interface.widgets.components.code_block import CodeBlock

__all__ = ["ActivityPanel", "CodeBlock", "ToolPanel"]
