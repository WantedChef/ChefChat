from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import set_key


def _unit_for_project(*, project: str) -> str:
    base = os.getenv("CHEFCHAT_TELEGRAM_UNIT_BASE", "chefchat-telegram").strip() or "chefchat-telegram"
    return f"{base}@{project}.service"


async def systemctl_user(args: list[str]) -> tuple[bool, str]:
    systemctl = os.getenv("SYSTEMCTL_BIN", "/usr/bin/systemctl")
    if not Path(systemctl).exists():
        return False, f"systemctl not found: {systemctl}"

    proc = await asyncio.create_subprocess_exec(
        systemctl,
        "--user",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await proc.communicate()
    out = (out_b or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode == 0, out or "OK"


async def get_status(*, project: str) -> dict[str, str | bool]:
    unit = _unit_for_project(project=project)
    ok, out = await systemctl_user([
        "show",
        unit,
        "-p",
        "ActiveState",
        "-p",
        "SubState",
        "-p",
        "ExecMainStatus",
        "-p",
        "MainPID",
    ])
    if not ok:
        return {"ok": False, "unit": unit, "output": out}

    parsed: dict[str, str] = {}
    for line in out.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        parsed[k.strip()] = v.strip()

    return {
        "ok": True,
        "unit": unit,
        "active": parsed.get("ActiveState", ""),
        "sub": parsed.get("SubState", ""),
        "pid": parsed.get("MainPID", ""),
        "exit": parsed.get("ExecMainStatus", ""),
    }


async def restart_project(*, project: str) -> tuple[bool, str]:
    return await systemctl_user(["restart", _unit_for_project(project=project)])


def set_bot_auto_approve(*, enable: bool) -> None:
    # This sets the env var for the *current process* only.
    # Persisting per-project should be handled by editing the project's .vibe/.env.
    os.environ["CHEFCHAT_BOT_AUTO_APPROVE"] = "1" if enable else "0"


def set_bot_auto_approve_persist(*, project: str, enable: bool) -> tuple[bool, str]:
    env_path = Path(f"/home/chef/{project}/ChefChat/.vibe/.env")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.touch()

    try:
        set_key(str(env_path), "CHEFCHAT_BOT_AUTO_APPROVE", "1" if enable else "0")
    except Exception as e:
        return False, f"Failed to update {env_path}: {e}"

    os.environ["CHEFCHAT_BOT_AUTO_APPROVE"] = "1" if enable else "0"
    return True, f"Updated {env_path}"
