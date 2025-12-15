from __future__ import annotations

from types import SimpleNamespace

import pytest

from chefchat.bots.telegram.handlers.models import ModelHandlers
from chefchat.bots.telegram.handlers.policy import PolicyHandlers
from chefchat.bots.telegram.handlers.tasks import TaskHandlers
from chefchat.bots.telegram.task_manager import TaskManager
from chefchat.core.config import VibeConfig


class StubBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, dict]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> SimpleNamespace:
        self.sent.append((chat_id, text, kwargs))
        return SimpleNamespace(chat_id=chat_id, text=text, kwargs=kwargs)


class StubMessage:
    def __init__(self, chat_id: int, text: str) -> None:
        self.chat = SimpleNamespace(id=chat_id)
        self.text = text
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs) -> SimpleNamespace:
        self.replies.append((text, kwargs))
        return SimpleNamespace(text=text, kwargs=kwargs)


class StubCallbackQuery:
    def __init__(self, chat_id: int, data: str) -> None:
        self.data = data
        self.chat_id = chat_id
        self.answered: list[tuple[str | None, bool]] = []
        self.edited: list[tuple[str, dict]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edited.append((text, kwargs))


class StubUpdate:
    def __init__(
        self,
        chat_id: int,
        user_id: int,
        message: StubMessage | None = None,
        callback_query: StubCallbackQuery | None = None,
    ) -> None:
        self.effective_chat = SimpleNamespace(id=chat_id)
        self.effective_user = SimpleNamespace(id=user_id)
        self.message = message
        self.callback_query = callback_query


class DummySession:
    def __init__(self) -> None:
        self.last_policy: str | None = None

    def set_tool_policy(self, policy: str) -> None:
        self.last_policy = policy


class DummySvc:
    def __init__(
        self,
        *,
        allowed_users: list[str],
        task_store,
        config: VibeConfig | None = None,
    ) -> None:
        self.config = config or VibeConfig()
        self.sessions: dict[int, DummySession] = {}
        self.application = SimpleNamespace(bot=StubBot())
        self.tool_policies: dict[int, str] = {}
        self.bot_manager = SimpleNamespace(
            get_allowed_users=lambda _: allowed_users,
        )
        self.task_manager = TaskManager(store_path=task_store)
        self.policy = PolicyHandlers(self)
        self.sent: list[tuple[int, str]] = []

        async def _send_message(chat_id: int, text: str) -> None:
            self.sent.append((chat_id, text))
            await self.application.bot.send_message(chat_id=chat_id, text=text)

        self._send_message = _send_message


@pytest.fixture
def telegram_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CHEFCHAT_HOME", str(tmp_path))
    for key in (
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "MISTRAL_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.setenv(key, "test-key")
    return tmp_path


@pytest.mark.asyncio
async def test_botmode_sets_policy_and_session(telegram_env) -> None:
    svc = DummySvc(allowed_users=["42"], task_store=telegram_env / "tasks.json")
    session = DummySession()
    chat_id = 777
    svc.sessions[chat_id] = session

    update = StubUpdate(
        chat_id=chat_id, user_id=42, message=StubMessage(chat_id, "/botmode chat")
    )
    context = SimpleNamespace(args=["chat"])

    await svc.policy.botmode_command(update, context)

    assert svc.tool_policies[chat_id] == "chat"
    assert session.last_policy == "chat"
    assert any("Bot-modus" in text for _, text in svc.sent)


@pytest.mark.asyncio
async def test_model_callback_switches_model(monkeypatch, telegram_env) -> None:
    monkeypatch.setattr(VibeConfig, "save_updates", staticmethod(lambda data: None))
    svc = DummySvc(allowed_users=["42"], task_store=telegram_env / "tasks.json")
    handler = ModelHandlers(
        svc,
        menu_buttons_per_row=2,
        cheap_model_price_threshold=0.5,
        min_command_args_model_select=2,
    )

    update = StubUpdate(
        chat_id=123, user_id=42, message=StubMessage(123, "/model")
    )
    await handler.model_command(update, SimpleNamespace(args=[]))

    assert update.message.replies, "Model menu should send a reply"
    assert "Model Control Strategy" in update.message.replies[0][0]

    target = svc.config.models[0].alias
    cb_update = StubUpdate(
        chat_id=123,
        user_id=42,
        callback_query=StubCallbackQuery(123, f"mod:{target}"),
    )
    await handler._handle_model_callback(cb_update, SimpleNamespace())

    assert svc.config.active_model == target
    assert cb_update.callback_query.answered, "Callback should be acknowledged"


@pytest.mark.asyncio
async def test_task_command_flow(telegram_env) -> None:
    svc = DummySvc(allowed_users=["42"], task_store=telegram_env / "tasks.json")
    handler = TaskHandlers(svc)
    chat_id = 999

    create_update = StubUpdate(
        chat_id=chat_id,
        user_id=42,
        message=StubMessage(chat_id, "/task write tests"),
    )
    await handler.task_command(create_update, SimpleNamespace(args=[]))
    assert "Taak #1" in svc.sent[-1][1]

    done_update = StubUpdate(
        chat_id=chat_id,
        user_id=42,
        message=StubMessage(chat_id, "/task done 1"),
    )
    await handler.task_command(done_update, SimpleNamespace(args=[]))
    assert "Klaar #1" in svc.sent[-1][1]

    list_update = StubUpdate(
        chat_id=chat_id,
        user_id=42,
        message=StubMessage(chat_id, "/task list"),
    )
    await handler.task_command(list_update, SimpleNamespace(args=[]))
    assert "📋" in svc.sent[-1][1]
