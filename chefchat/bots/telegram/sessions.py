from __future__ import annotations

from collections.abc import Callable, ItemsView, Iterable, KeysView, ValuesView
import time

from chefchat.bots.manager import BotManager
from chefchat.bots.session import BotSession
from chefchat.core.config import VibeConfig


class SessionStore:
    """Manages Telegram chat sessions and per-user limits."""

    def __init__(
        self,
        config: VibeConfig,
        bot_manager: BotManager,
        *,
        max_sessions_per_user: int | None,
        session_limit_override: bool,
    ) -> None:
        self.config = config
        self.bot_manager = bot_manager
        self.max_sessions_per_user = max_sessions_per_user
        self.session_limit_override = session_limit_override

        self.sessions: dict[int, BotSession] = {}
        self._user_session_counts: dict[str, int] = {}
        self._last_activity: dict[int, float] = {}
        self._warned_idle: set[int] = set()

    def get_or_create(
        self,
        chat_id: int,
        user_id: str,
        *,
        factory: Callable[[], BotSession],
    ) -> BotSession | None:
        """Return existing session or create a new one if allowed."""
        if chat_id not in self.sessions:
            allowed = self.bot_manager.get_allowed_users("telegram")
            if user_id not in allowed:
                return None

            if (
                self.max_sessions_per_user is not None
                and not self.session_limit_override
                and self._user_session_counts.get(user_id, 0)
                >= self.max_sessions_per_user
            ):
                return None

            session = factory()
            self.sessions[chat_id] = session
            self._user_session_counts[user_id] = self._user_session_counts.get(
                user_id, 0
            ) + 1

        self._last_activity[chat_id] = time.monotonic()
        return self.sessions[chat_id]

    def forget(self, chat_id: int) -> None:
        session = self.sessions.pop(chat_id, None)
        if session:
            user_id = getattr(session, "user_id", None)
            if user_id and user_id in self._user_session_counts:
                self._user_session_counts[user_id] = max(
                    0, self._user_session_counts[user_id] - 1
                )
        self._last_activity.pop(chat_id, None)
        self._warned_idle.discard(chat_id)

    def touch(self, chat_id: int) -> None:
        self._last_activity[chat_id] = time.monotonic()

    def warnable(self, chat_id: int, threshold_s: float) -> bool:
        last = self._last_activity.get(chat_id)
        if last is None:
            return False
        return (time.monotonic() - last) > threshold_s and chat_id not in self._warned_idle

    def mark_warned(self, chat_id: int) -> None:
        self._warned_idle.add(chat_id)

    def idle_sessions(self, ttl_s: float) -> list[int]:
        now = time.monotonic()
        return [chat_id for chat_id, ts in self._last_activity.items() if (now - ts) > ttl_s]

    def get(self, chat_id: int) -> BotSession | None:
        return self.sessions.get(chat_id)

    def values(self) -> ValuesView[BotSession]:
        return self.sessions.values()

    def items(self) -> ItemsView[int, BotSession]:
        return self.sessions.items()

    def keys(self) -> KeysView[int]:
        return self.sessions.keys()

    def __len__(self) -> int:
        return len(self.sessions)

    def __iter__(self) -> Iterable[int]:
        return iter(self.sessions)

    def __contains__(self, chat_id: object) -> bool:
        return chat_id in self.sessions
