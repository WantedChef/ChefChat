from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
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
    return [
        p.strip()
        for p in os.getenv("CHEFCHAT_PROJECTS", "chefchat").split(",")
        if p.strip()
    ]


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
        self._auto_approve = os.getenv(
            "CHEFCHAT_BOT_AUTO_APPROVE", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        # Build route table for API dispatch
        self._routes: dict[
            tuple[str, str], Callable[[SimpleHTTPRequestHandler], None]
        ] = {
            ("/api/meta", "GET"): self._api_meta,
            ("/api/status", "GET"): self._api_status,
            ("/api/restart", "POST"): self._api_restart,
            ("/api/switch", "POST"): self._api_switch,
            ("/api/mode/toggle-auto", "POST"): self._api_toggle_auto,
        }

    def _check_auth(self, handler: SimpleHTTPRequestHandler) -> bool:
        init_data = handler.headers.get("X-Telegram-Init-Data", "")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        return verify_init_data(init_data=init_data, bot_token=token)

    def _json(
        self, handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _require_auth(self, handler: SimpleHTTPRequestHandler) -> bool:
        """Check auth and send 401 if unauthorized. Returns True if authorized."""
        if not self._check_auth(handler):
            self._json(
                handler,
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "output": "unauthorized"},
            )
            return False
        return True

    def _read_json_body(self, handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
        """Read and parse JSON body from request."""
        length = int(handler.headers.get("Content-Length", "0") or "0")
        raw = handler.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_api(self, handler: SimpleHTTPRequestHandler) -> bool:
        """Dispatch API requests to route handlers."""
        path = handler.path.split("?", 1)[0]
        route_key = (path, handler.command)

        route_handler = self._routes.get(route_key)
        if route_handler:
            route_handler(handler)
            return True
        return False

    def _api_meta(self, handler: SimpleHTTPRequestHandler) -> None:
        """GET /api/meta - Return project metadata."""
        if not self._require_auth(handler):
            return
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

    def _api_status(self, handler: SimpleHTTPRequestHandler) -> None:
        """GET /api/status - Return project status."""
        if not self._require_auth(handler):
            return
        data = asyncio.run(get_status(project=self._project))
        self._json(handler, HTTPStatus.OK, data)

    def _api_restart(self, handler: SimpleHTTPRequestHandler) -> None:
        """POST /api/restart - Restart the current project."""
        if not self._require_auth(handler):
            return
        ok, out = asyncio.run(restart_project(project=self._project))
        self._json(
            handler,
            HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            {"ok": ok, "output": out},
        )

    def _api_switch(self, handler: SimpleHTTPRequestHandler) -> None:
        """POST /api/switch - Switch to a different project."""
        if not self._require_auth(handler):
            return

        payload = self._read_json_body(handler)
        project = str(payload.get("project", "")).strip()

        if not project:
            self._json(
                handler,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "output": "missing project"},
            )
            return

        if project not in _projects():
            self._json(
                handler,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "output": "unknown project"},
            )
            return

        # Switch = restart target project service; also update what this UI displays
        ok, out = asyncio.run(restart_project(project=project))
        if ok:
            self._project = project
        self._json(
            handler,
            HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
            {"ok": ok, "output": out},
        )

    def _api_toggle_auto(self, handler: SimpleHTTPRequestHandler) -> None:
        """POST /api/mode/toggle-auto - Toggle auto-approve mode."""
        if not self._require_auth(handler):
            return

        self._auto_approve = not self._auto_approve
        ok, out = set_bot_auto_approve_persist(
            project=self._project, enable=self._auto_approve
        )
        if not ok:
            self._json(handler, HTTPStatus.BAD_REQUEST, {"ok": False, "output": out})
            return

        ok2, out2 = asyncio.run(restart_project(project=self._project))
        if not ok2:
            self._json(handler, HTTPStatus.BAD_REQUEST, {"ok": False, "output": out2})
            return

        self._json(
            handler, HTTPStatus.OK, {"ok": True, "auto_approve": self._auto_approve}
        )

    def serve(self) -> None:
        static_dir = Path(__file__).parent / "static"

        server = self

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(static_dir), **kwargs)

            def do_GET(self) -> None:
                if self.path.startswith("/api/"):
                    if server._handle_api(self):
                        return
                return super().do_GET()

            def do_POST(self) -> None:
                if self.path.startswith("/api/"):
                    if server._handle_api(self):
                        return
                self.send_error(HTTPStatus.NOT_FOUND)

        httpd = ThreadingHTTPServer((self._config.host, self._config.port), Handler)
        httpd.serve_forever()


def run_mini_app(config: MiniAppConfig | None = None) -> None:
    MiniAppServer(config or MiniAppConfig()).serve()
