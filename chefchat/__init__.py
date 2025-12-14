"""ChefChat - The Michelin Star AI-Engineer TUI."""

from __future__ import annotations

from pathlib import Path

__version__ = "1.0.5-dev"
CHEFCHAT_ROOT = Path(__file__).parent

__all__ = ["CHEFCHAT_ROOT", "__version__"]
