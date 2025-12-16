from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class ApprovalInfo:
    short_id: str
    tool_call_id: str
    chat_id: int
    tool_name: str | None
    created_at: float


class ApprovalStore:
    """Tracks tool approval requests and handles expiration."""

    def __init__(self, ttl_s: float) -> None:
        self._ttl_s = ttl_s
        self._by_short_id: dict[str, ApprovalInfo] = {}

    def register(self, short_id: str, tool_call_id: str, chat_id: int, tool_name: str | None) -> None:
        self._by_short_id[short_id] = ApprovalInfo(
            short_id=short_id,
            tool_call_id=tool_call_id,
            chat_id=chat_id,
            tool_name=tool_name,
            created_at=time.monotonic(),
        )

    def pop(self, short_id: str) -> ApprovalInfo | None:
        return self._by_short_id.pop(short_id, None)

    def get_tool_call(self, short_id: str) -> str | None:
        info = self._by_short_id.get(short_id)
        return info.tool_call_id if info else None

    def expire(self, now: float) -> list[ApprovalInfo]:
        expired: list[ApprovalInfo] = []
        for short_id, info in list(self._by_short_id.items()):
            if (now - info.created_at) > self._ttl_s:
                expired.append(self._by_short_id.pop(short_id))
        return expired
