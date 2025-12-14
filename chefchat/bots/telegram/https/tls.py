from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HttpsConfig:
    domain: str
    email: str
    http_port: int = 80
    https_port: int = 443
