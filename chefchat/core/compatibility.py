from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        """Enum where members are also (and must be) strings"""

        def __str__(self) -> str:
            return str(self.value)


__all__ = ["StrEnum"]
