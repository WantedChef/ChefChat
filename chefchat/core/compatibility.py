from __future__ import annotations

import enum

try:
    from enum import StrEnum
except ImportError:

    class StrEnum(str, enum.Enum):
        """Enum where members are also (and must be) strings"""

        def __str__(self) -> str:
            return str(self.value)


try:
    from typing import override
except ImportError:
    from typing_extensions import override


__all__ = ["StrEnum", "override"]
