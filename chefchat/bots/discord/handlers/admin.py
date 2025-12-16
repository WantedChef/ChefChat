from __future__ import annotations

import asyncio
import os
import shlex
from typing import TYPE_CHECKING

import discord

from chefchat.modes import ModeManager
from chefchat.kitchen.stations.git_chef import GitCommandValidator

if TYPE_CHECKING:
    from chefchat.bots.discord.bot import DiscordBotService

DISCORD_MSG_LIMIT = 1900


class AdminHandlers:
    def __init__(self, svc: DiscordBotService) -> None:
        self.svc = svc

    async def handle_message(self, message: discord.Message) -> bool:
        content = message.content.strip()

        if content.startswith("/chefchat"):
            await self._handle_chefchat_command(message)
            return True

        if content.startswith("/status"):
            await self._handle_status(message)
            return True

        if content.startswith("/git"):
            await self._handle_git_command(message)
            return True

        return False

    async def _handle_chefchat_command(self, message: discord.Message) -> None:
        args = message.content.split()[1:]
        if not args:
            await message.channel.send(
                "Usage:\n"
                "/chefchat status\n"
                "/chefchat start\n"
                "/chefchat stop\n"
                "/chefchat restart\n"
            )
            return

        action = args[0].lower()
        if action in {"status", "start", "stop", "restart"}:
            # Basic systemd integration similar to Telegram
            unit = "chefchat-discord.service"  # simplified for now
            ok, out = await self._systemctl_user([action, unit])
            await message.channel.send(f"```{out}```" if ok else f"❌ Failed: {out}")
        else:
            await message.channel.send("Unknown action.")

    async def _handle_status(self, message: discord.Message) -> None:
        """Render a status embed including mode snapshot."""
        session = self.svc._get_session(message.channel.id, str(message.author.id))
        if not session:
            await message.channel.send("No active session yet. Send a message first.")
            return

        embed = discord.Embed(
            title="📊 ChefChat Status",
            color=discord.Color.gold(),
        )

        # Mode snapshot
        mode_manager: ModeManager | None = getattr(session.agent, "mode_manager", None)
        if mode_manager:
            mode_snapshot = mode_manager.get_state_snapshot(include_modes=False)
            current = mode_snapshot.get("current_mode", {})
            embed.add_field(
                name="Mode",
                value=(
                    f"{current.get('emoji', '')} {current.get('name', 'N/A')}\n"
                    f"Auto: {'ON' if current.get('auto_approve') else 'OFF'} • "
                    f"Read-only: {'YES' if current.get('read_only') else 'NO'}"
                ).strip(),
                inline=False,
            )
        else:
            embed.add_field(name="Mode", value="Unavailable", inline=False)

        await message.channel.send(embed=embed)

    async def _handle_git_command(self, message: discord.Message) -> None:
        args = message.content.split()[1:]
        if not args:
            await message.channel.send(
                "Usage: `/git <command>` (e.g., status, log, diff)"
            )
            return

        raw_args = " ".join(args)
        await self._execute_git_command(message, raw_args)

    async def handle_git_direct(self, message: discord.Message) -> None:
        """Handle direct git commands without slash (e.g., 'git status')."""
        # Extract everything after "git "
        raw_args = message.content.strip()[4:].strip()  # Remove "git " prefix
        if not raw_args:
            await message.channel.send(
                "Usage: `git <command>` (e.g., git status, git log)"
            )
            return
        await self._execute_git_command(message, raw_args)

    async def _execute_git_command(
        self, message: discord.Message, raw_args: str
    ) -> None:
        """Execute a git command with validation."""
        validated_args = GitCommandValidator.parse_and_validate(raw_args)

        if validated_args is None:
            await message.channel.send("❌ Invalid or unsafe git command.")
            return

        await message.channel.send(f"🔧 Running git {validated_args[1]}...")

        try:
            safe_command = " ".join(shlex.quote(arg) for arg in validated_args)
            env = {}
            if token := os.environ.get("GITHUB_TOKEN"):
                env["GITHUB_TOKEN"] = token

            stdout, stderr, returncode = await self.svc.executor.execute(
                safe_command, timeout=30, env=env
            )

            output = (stdout if stdout else stderr).strip()
            if not output:
                output = "(No output)"

            icon = "✅" if returncode == 0 else "❌"
            header = f"{icon} Git {validated_args[1]} finished (code {returncode})"

            # Truncate if too long (Discord limit 2000, leave room for wrapper)
            if len(output) > DISCORD_MSG_LIMIT:
                output = output[:DISCORD_MSG_LIMIT] + "\n...(truncated)"

            await message.channel.send(f"**{header}**\n```\n{output}\n```")

        except Exception as e:
            await message.channel.send(f"❌ Error executing git: {e}")

    async def _systemctl_user(self, args: list[str]) -> tuple[bool, str]:
        systemctl = os.getenv("SYSTEMCTL_BIN", "/usr/bin/systemctl")
        if not os.path.exists(systemctl):
            return False, "systemctl not found"

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
