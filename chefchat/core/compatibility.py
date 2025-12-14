from __future__ import annotations

import enum

try:
    from enum import StrEnum
except ImportError:

    class StrEnum(enum.StrEnum):
        """Enum where members are also (and must be) strings"""

        def __str__(self) -> str:
            return str(self.value)


__all__ = ["StrEnum"]
