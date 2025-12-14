from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from chefchat.bots.telegram.mini_app.auth import verify_init_data
from chefchat.bots.telegram.mini_app.control import (
    get_status,
    restart_project,
    set_bot_auto_approve_persist,
)


@dataclass(frozen=True, slots=True)
class MiniAppConfig:
    host: str = "127.0.0.1"
    port: int = 8088


def _projects() -> list[str]:
    return [p.strip() for p in os.getenv("CHEFCHAT_PROJECTS", "chefchat").split(",") if p.strip()]


def _current_project() -> str:
    # Prefer explicit env var set by systemd unit: Environment=CHEFCHAT_PROJECT_NAME=%i
    if project := os.getenv("CHEFCHAT_PROJECT_NAME"):
        return project.strip()

    # Fallback: assume /home/chef/<project>/ChefChat as working dir
    try:
        cwd = Path.cwd()
        if cwd.name.lower() == "chefchat":
            return cwd.parent.name
    except Exception:
        pass

    return "chefchat"


class MiniAppServer:
    def __init__(self, config: MiniAppConfig) -> None:
        self._config = config
        self._project = _current_project()
        self._auto_approve = os.getenv("CHEFCHAT_BOT_AUTO_APPROVE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _check_auth(self, handler: SimpleHTTPRequestHandler) -> bool:
        init_data = handler.headers.get("X-Telegram-Init-Data", "")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        return verify_init_data(init_data=init_data, bot_token=token)

    def _json(self, handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_api(self, handler: SimpleHTTPRequestHandler) -> bool:
        path = handler.path.split("?", 1)[0]

        if path == "/api/meta" and handler.command == "GET":
            if not self._check_auth(handler):
                self._json(handler, HTTPStatus.UNAUTHORIZED, {"ok": False, "output": "unauthorized"})
                return True

            self._json(
                handler,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "project": self._project,
                    "projects": _projects(),
                    "auto_approve": self._auto_approve,
                },
            )
            return True

        if path == "/api/status" and handler.command == "GET":
            if not self._check_auth(handler):
                self._json(handler, HTTPStatus.UNAUTHORIZED, {"ok": False, "output": "unauthorized"})
                return True

            data = asyncio.run(get_status(project=self._project))
            self._json(handler, HTTPStatus.OK, data)
            return True

        if path == "/api/restart" and handler.command == "POST":
            if not self._check_auth(handler):
                self._json(handler, HTTPStatus.UNAUTHORIZED, {"ok": False, "output": "unauthorized"})
                return True

            ok, out = asyncio.run(restart_project(project=self._project))
            self._json(handler, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST, {"ok": ok, "output": out})
            return True

        if path == "/api/switch" and handler.command == "POST":
            if not self._check_auth(handler):
                self._json(handler, HTTPStatus.UNAUTHORIZED, {"ok": False, "output": "unauthorized"})
                return True

            length = int(handler.headers.get("Content-Length", "0") or "0")
            raw = handler.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                payload = {}

            project = str(payload.get("project", "")).strip()
            if not project:
                self._json(handler, HTTPStatus.BAD_REQUEST, {"ok": False, "output": "missing project"})
                return True

            if project not in _projects():
                self._json(handler, HTTPStatus.BAD_REQUEST, {"ok": False, "output": "unknown project"})
                return True

            # Switch = restart target project service; also update what this UI displays
            ok, out = asyncio.run(restart_project(project=project))
            if ok:
                self._project = project
            self._json(handler, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST, {"ok": ok, "output": out})
            return True

        if path == "/api/mode/toggle-auto" and handler.command == "POST":
            if not self._check_auth(handler):
                self._json(handler, HTTPStatus.UNAUTHORIZED, {"ok": False, "output": "unauthorized"})
                return True

            self._auto_approve = not self._auto_approve
            ok, out = set_bot_auto_approve_persist(project=self._project, enable=self._auto_approve)
            if not ok:
                self._json(handler, HTTPStatus.BAD_REQUEST, {"ok": False, "output": out})
                return True

            ok2, out2 = asyncio.run(restart_project(project=self._project))
            if not ok2:
                self._json(handler, HTTPStatus.BAD_REQUEST, {"ok": False, "output": out2})
                return True

            self._json(handler, HTTPStatus.OK, {"ok": True, "auto_approve": self._auto_approve})
            return True

        return False

    def serve(self) -> None:
        static_dir = Path(__file__).parent / "static"

        server = self

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(static_dir), **kwargs)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/api/"):
                    if server._handle_api(self):
                        return
                return super().do_GET()

            def do_POST(self) -> None:  # noqa: N802
                if self.path.startswith("/api/"):
                    if server._handle_api(self):
                        return
                self.send_error(HTTPStatus.NOT_FOUND)

        httpd = ThreadingHTTPServer((self._config.host, self._config.port), Handler)
        httpd.serve_forever()


def run_mini_app(config: MiniAppConfig | None = None) -> None:
    MiniAppServer(config or MiniAppConfig()).serve()
