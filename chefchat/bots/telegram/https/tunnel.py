from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TunnelConfig:
    name: str
    local_port: int
