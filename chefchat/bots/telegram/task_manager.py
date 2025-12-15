"""Simple task manager for Telegram bot."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(os.getenv("CHEFCHAT_HOME", Path.home() / ".chefchat"))
DEFAULT_STORE = BASE_DIR / "telegram_tasks.json"


@dataclass
class Task:
    task_id: int
    chat_id: int
    text: str
    status: str = "todo"  # todo | doing | done
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskManager:
    """Persist small task lists for Telegram chats."""

    def __init__(self, store_path: Path | None = None) -> None:
        self.store_path = store_path or DEFAULT_STORE
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[int, dict[int, Task]] = {}
        self.changelog: list[dict[str, Any]] = []
        self._load()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text())
        except Exception:
            return

        for raw in data.get("tasks", []):
            try:
                task = Task(**raw)
                self.tasks.setdefault(task.chat_id, {})[task.task_id] = task
            except TypeError:
                continue

        self.changelog = data.get("changelog", [])

    def _save(self) -> None:
        payload = {
            "tasks": [
                t.to_dict()
                for t in sorted(
                    (task for tasks in self.tasks.values() for task in tasks.values()),
                    key=lambda x: (x.chat_id, x.task_id),
                )
            ],
            "changelog": self.changelog[-50:],  # keep latest 50
        }
        self.store_path.write_text(json.dumps(payload, indent=2))

    def _next_id(self, chat_id: int) -> int:
        chat_tasks = self.tasks.get(chat_id, {})
        return (max(chat_tasks.keys()) + 1) if chat_tasks else 1

    def _record(self, action: str, task: Task) -> None:
        self.changelog.append(
            {
                "ts": self._now(),
                "chat_id": task.chat_id,
                "action": action,
                "id": task.task_id,
                "text": task.text,
                "status": task.status,
            }
        )

    def add(self, chat_id: int, text: str) -> Task:
        task = Task(
            task_id=self._next_id(chat_id),
            chat_id=chat_id,
            text=text,
            status="todo",
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.tasks.setdefault(chat_id, {})[task.task_id] = task
        self._record("add", task)
        self._save()
        return task

    def edit(self, chat_id: int, task_id: int, text: str) -> Task | None:
        task = self.tasks.get(chat_id, {}).get(task_id)
        if not task:
            return None
        task.text = text
        task.updated_at = self._now()
        self._record("edit", task)
        self._save()
        return task

    def set_status(self, chat_id: int, task_id: int, status: str) -> Task | None:
        task = self.tasks.get(chat_id, {}).get(task_id)
        if not task:
            return None
        task.status = status
        task.updated_at = self._now()
        self._record(status, task)
        self._save()
        return task

    def delete(self, chat_id: int, task_id: int) -> Task | None:
        task = self.tasks.get(chat_id, {}).pop(task_id, None)
        if not task:
            return None
        self._record("delete", task)
        self._save()
        return task

    def list_text(self, chat_id: int) -> str:
        chat_tasks = self.tasks.get(chat_id, {})
        if not chat_tasks:
            return "ℹ️ Geen taken."
        lines = ["📋 **Taken**"]
        for task in sorted(chat_tasks.values(), key=lambda t: t.task_id):
            status_icon = {
                "todo": "🟡",
                "doing": "🟠",
                "done": "✅",
            }.get(task.status, "•")
            lines.append(
                f"{status_icon} [{task.task_id}] {task.text} (laatst: {task.updated_at})"
            )
        return "\n".join(lines)

    def changelog_text(self, chat_id: int, limit: int = 10) -> str:
        entries = [e for e in self.changelog if e.get("chat_id") == chat_id]
        if not entries:
            return "ℹ️ Nog geen wijzigingen."
        lines = ["🕑 Laatste wijzigingen:"]
        for entry in entries[-limit:][::-1]:
            lines.append(
                f"{entry['ts']} | #{entry['id']} | {entry['action']} → {entry['status']} | {entry['text']}"
            )
        return "\n".join(lines)
