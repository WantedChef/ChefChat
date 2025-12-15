"""Interactive terminal session manager for Telegram bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
import os
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class TerminalSession:
    """Manages an interactive terminal session."""

    session_id: str
    chat_id: int
    process: subprocess.Popen
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    command: str = ""
    cwd: Path = field(
        default_factory=lambda: Path(
            os.getenv("CHEFCHAT_HOME", Path.home() / ".chefchat")
        )
        / "shells"
    )

    def _read_output_unix(self) -> list[str]:
        """Read output from process using Unix select()."""
        import select

        output_lines: list[str] = []
        ready, _, _ = select.select([self.process.stdout], [], [], 0.5)
        if not ready:
            return output_lines

        while True:
            ready, _, _ = select.select([self.process.stdout], [], [], 0.1)
            if not ready:
                break
            line = self.process.stdout.readline()
            if not line:
                break
            output_lines.append(line.strip())
        return output_lines

    def _read_output_windows(self) -> list[str]:
        """Read output from process on Windows (blocking fallback)."""
        import time

        output_lines: list[str] = []
        time.sleep(0.5)
        while True:
            line = self.process.stdout.readline()
            if not line:
                break
            output_lines.append(line.strip())
        return output_lines

    def _read_output(self) -> list[str]:
        """Read available output from the process."""
        import sys

        if sys.platform != "win32":
            return self._read_output_unix()
        return self._read_output_windows()

    def send_input(self, text: str) -> str:
        """Send input to the terminal and return output."""
        try:
            if self.process.poll() is not None:
                return "❌ Terminal session has ended."

            # Support multi-line input
            for line in text.splitlines():
                self.process.stdin.write(f"{line}\n")
            self.process.stdin.flush()
            self.last_activity = datetime.now()

            # Read output (with timeout)
            try:
                output_lines = self._read_output()
            except Exception as e:
                logger.warning(f"Error reading output: {e}")
                output_lines = []

            if not output_lines:
                return (
                    "💻 **Terminal**: (no output)\n"
                    "_(Session active: type `/termclose` to exit)_"
                )

            output = "\n".join(output_lines)
            return f"💻 **Terminal**:\n```\n{output}\n```"

        except Exception as e:
            logger.exception("Failed to send input to terminal")
            return f"❌ Error: {e}"

    def terminate(self) -> None:
        """Terminate the terminal session."""
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        except Exception:
            logger.exception("Failed to terminate terminal session")

    def is_alive(self) -> bool:
        """Check if the terminal session is still running."""
        return self.process.poll() is None


class TerminalManager:
    """Manages multiple terminal sessions for different chats."""

    def __init__(self) -> None:
        self.sessions: dict[int, TerminalSession] = {}

    def create_session(
        self, chat_id: int, command: str, cwd: Path | None = None
    ) -> tuple[bool, str]:
        """Create a new terminal session."""
        # Close existing session if any
        if chat_id in self.sessions:
            self.sessions[chat_id].terminate()
            del self.sessions[chat_id]

        try:
            if cwd is None:
                cwd = Path(
                    os.getenv("CHEFCHAT_HOME", Path.home() / ".chefchat")
                ) / "shells"
            cwd.mkdir(parents=True, exist_ok=True)

            # Start interactive shell
            process = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(cwd),
                bufsize=1,
            )

            session_id = f"term_{chat_id}_{datetime.now().timestamp()}"
            session = TerminalSession(
                session_id=session_id,
                chat_id=chat_id,
                process=process,
                command=command,
                cwd=cwd,
            )

            self.sessions[chat_id] = session

            return (
                True,
                f"✅ Terminal started: `{command}`\nType your commands, or `/termclose` to exit.",
            )

        except Exception as e:
            logger.exception("Failed to create terminal session")
            return False, f"❌ Failed to start terminal: {e}"

    def send_to_session(self, chat_id: int, text: str) -> str:
        """Send input to an active terminal session."""
        if chat_id not in self.sessions:
            return "❌ No active terminal session. Use `/term <command>` to start one."

        session = self.sessions[chat_id]

        if not session.is_alive():
            del self.sessions[chat_id]
            return "❌ Terminal session has ended. Use `/term <command>` to start a new one."

        return session.send_input(text)

    def close_session(self, chat_id: int) -> str:
        """Close a terminal session."""
        if chat_id not in self.sessions:
            return "❌ No active terminal session."

        session = self.sessions[chat_id]
        session.terminate()
        del self.sessions[chat_id]

        return "✅ Terminal session closed."

    def get_session_status(self, chat_id: int) -> str:
        """Get status of a terminal session."""
        if chat_id not in self.sessions:
            return "❌ No active terminal session."

        session = self.sessions[chat_id]

        if not session.is_alive():
            del self.sessions[chat_id]
            return "❌ Terminal session has ended."

        uptime = (datetime.now() - session.created_at).total_seconds()
        last_active = (datetime.now() - session.last_activity).total_seconds()

        return (
            f"✅ **Terminal Active**\n\n"
            f"Command: `{session.command}`\n"
            f"Working Dir: `{session.cwd}`\n"
            f"Uptime: {uptime:.0f}s\n"
            f"Last Activity: {last_active:.0f}s ago"
        )

    def has_active_session(self, chat_id: int) -> bool:
        """Check if chat has an active terminal session."""
        if chat_id not in self.sessions:
            return False

        session = self.sessions[chat_id]
        if not session.is_alive():
            del self.sessions[chat_id]
            return False

        return True

    def cleanup_dead_sessions(self) -> None:
        """Remove all dead terminal sessions."""
        dead_chats = [
            chat_id
            for chat_id, session in self.sessions.items()
            if not session.is_alive()
        ]

        for chat_id in dead_chats:
            del self.sessions[chat_id]
