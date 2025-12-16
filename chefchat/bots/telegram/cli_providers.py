"""CLI Providers module for Telegram bot.

This module provides integration with external AI CLI tools:
- Gemini CLI (Google) - One-shot queries
- Codex CLI (OpenAI) - One-shot exec
- OpenCode CLI - One-shot run

Uses non-interactive mode for reliable Telegram integration.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import shlex
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default working directory for CLI commands
CLI_WORKDIR = Path(os.getenv("CHEFCHAT_HOME", Path.home() / ".chefchat")) / "cli_runs"

# Maximum output length for Telegram
MAX_OUTPUT_LENGTH = 3800

# Command timeout in seconds
CLI_TIMEOUT = 120

# Number of historical entries to keep per chat
MAX_HISTORY = 5


@dataclass
class CLIProvider:
    """Configuration for a CLI provider."""

    name: str
    command: str
    description: str
    shortcut: str  # Telegram command shortcut (without /)
    icon: str
    # Command template for one-shot execution
    # Use {prompt} as placeholder for the user's message
    exec_template: str
    # Command to get version (if supported)
    version_args: list[str] | None = field(default_factory=lambda: ["--version"])
    # Environment variables that typically unlock the provider
    env_keys: list[str] = field(default_factory=list)
    # Default args appended before the prompt (e.g., auto-approve flags)
    default_args: list[str] = field(default_factory=list)
    # Optional env var name that provides additional args (space-delimited)
    args_env_var: str | None = None

    def get_full_path(self) -> str | None:
        """Get full path to CLI binary, or None if not found."""
        import shutil

        return shutil.which(self.command)

    def is_available(self) -> bool:
        """Check if this CLI is installed and available."""
        return self.get_full_path() is not None

    def _extra_args(self) -> list[str]:
        """Return default args plus any provided via env var."""
        args: list[str] = list(self.default_args)
        if self.args_env_var:
            env_val = os.getenv(self.args_env_var, "").strip()
            if env_val:
                args.extend(shlex.split(env_val))
        return args

    def build_argv(self, prompt: str) -> list[str]:
        """Build argv list for subprocess execution."""
        # Break template into parts and drop the {prompt} placeholder
        template_parts = shlex.split(
            self.exec_template.replace("{prompt}", "{prompt}")
        )
        base: list[str] = [p for p in template_parts if p != "{prompt}"]
        base.extend(self._extra_args())
        base.append(prompt)
        return base

    def build_command(self, prompt: str) -> str:
        """Build a shell-safe command string (used mainly for logging)."""
        return shlex.join(self.build_argv(prompt))


# Available CLI providers with their one-shot execution commands
CLI_PROVIDERS: dict[str, CLIProvider] = {
    "gemini": CLIProvider(
        name="Gemini CLI",
        command="gemini",
        description="Google Gemini AI",
        shortcut="cligemini",
        icon="✨",
        # Gemini uses positional argument for one-shot
        exec_template="gemini {prompt}",
        # Auto-approve actions to avoid interactive prompts in Telegram
        default_args=["--approval-mode", "yolo"],
        args_env_var="GEMINI_CLI_ARGS",
        env_keys=["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    ),
    "codex": CLIProvider(
        name="Codex CLI",
        command="codex",
        description="OpenAI Codex",
        shortcut="clicodex",
        icon="🧠",
        # Codex uses 'exec' subcommand for non-interactive
        exec_template="codex exec {prompt}",
        env_keys=["OPENAI_API_KEY", "OPENAI_KEY"],
    ),
    "opencode": CLIProvider(
        name="OpenCode CLI",
        command="opencode",
        description="OpenCode AI",
        shortcut="cliopencode",
        icon="⚡",
        # OpenCode uses 'run' subcommand for non-interactive
        exec_template="opencode run {prompt}",
        env_keys=["OPENCODE_API_KEY", "OPENAI_API_KEY"],
    ),
}


class CLIProviderManager:
    """Manages CLI provider one-shot executions for Telegram chats.

    This uses a non-interactive, one-shot model where each message
    is sent to the CLI and the response is returned.
    """

    def __init__(self) -> None:
        # Track active provider per chat (for context)
        self.active_provider: dict[int, str] = {}
        # Track pending executions
        self.pending: dict[int, asyncio.Task] = {}
        # Keep short history per chat
        self.history: dict[int, deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=MAX_HISTORY)
        )

        self.workdir = CLI_WORKDIR
        self.workdir.mkdir(parents=True, exist_ok=True)

    def get_available_providers(self) -> list[CLIProvider]:
        """Get list of available (installed) CLI providers."""
        return [p for p in CLI_PROVIDERS.values() if p.is_available()]

    def _sanitize_output(self, text: str) -> str:
        """Strip ANSI codes and redact obvious secrets."""
        import re

        # Remove ANSI codes
        text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
        text = re.sub(r"\x1b\][^\x07]*\x07", "", text)

        # Redact common API key patterns
        patterns = [
            r"sk-[A-Za-z0-9]{20,}",
            r"AIza[0-9A-Za-z-_]{20,}",
            r"ghp_[A-Za-z0-9]{30,}",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "[redacted]", text)
        return text

    async def _get_version(self, provider: CLIProvider) -> str | None:
        """Attempt to read provider version."""
        if not provider.version_args:
            return None

        full_path = provider.get_full_path()
        if not full_path:
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                full_path,
                *provider.version_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return "(version timeout)"

            out = (stdout or b"").decode("utf-8", errors="replace").strip()
            return out or None
        except Exception:
            return None

    async def get_diagnostics(self) -> str:
        """Return human-readable diagnostics for providers."""
        lines = ["🧪 CLI Diagnostics"]
        for _key, provider in CLI_PROVIDERS.items():
            available = provider.is_available()
            env_hits = [k for k in provider.env_keys if os.getenv(k)]
            version = await self._get_version(provider) if available else None
            arg_parts = provider._extra_args()

            status = "✅" if available else "❌"
            lines.append(
                f"{status} {provider.icon} {provider.name} (`{provider.command}`)"
            )

            if available and version:
                lines.append(f"   • Version: {version}")
            elif available:
                lines.append("   • Version: (not reported)")
            else:
                lines.append("   • Not installed")

            if env_hits:
                hits = ", ".join(env_hits)
                lines.append(f"   • Keys present: {hits}")
            elif provider.env_keys:
                lines.append("   • Keys missing: " + ", ".join(provider.env_keys))
            if arg_parts:
                lines.append("   • Args: " + " ".join(arg_parts))
            if provider.args_env_var:
                env_state = "set" if os.getenv(provider.args_env_var) else "unset"
                lines.append(f"   • {provider.args_env_var}: {env_state}")

        return "\n".join(lines)

    def set_active_provider(self, chat_id: int, provider_name: str) -> tuple[bool, str]:
        """Set the active CLI provider for a chat."""
        if provider_name not in CLI_PROVIDERS:
            available = ", ".join(CLI_PROVIDERS.keys())
            return False, f"❌ Unknown provider. Available: {available}"

        provider = CLI_PROVIDERS[provider_name]
        if not provider.is_available():
            return False, f"❌ {provider.name} is not installed on this system."

        self.active_provider[chat_id] = provider_name

        return (
            True,
            f"{provider.icon} **{provider.name}** selected!\n"
            f"_{provider.description}_\n\n"
            f"Now send your questions. Each message will be processed separately.\n"
            f"Use `/cliclose` to switch back to ChefChat.",
        )

    async def execute_prompt(
        self,
        chat_id: int,
        prompt: str,
        cwd: Path | None = None,
        provider_override: str | None = None,
        persist: bool = False,
    ) -> str:
        """Execute a prompt with the active CLI provider."""
        provider_name = provider_override or self.active_provider.get(chat_id)
        if provider_name is None:
            return "❌ No CLI provider selected. Use `/cli <provider>` first."

        provider = CLI_PROVIDERS[provider_name]

        if cwd is None:
            cwd = self.workdir
        cwd.mkdir(parents=True, exist_ok=True)

        if persist:
            self.active_provider[chat_id] = provider_name

        # Prevent overlapping requests per chat
        existing = self.pending.get(chat_id)
        if existing and not existing.done():
            return "⏳ Previous CLI request still running. Use /clicancel to stop it."

        argv = provider.build_argv(prompt)

        try:
            task = asyncio.create_task(
                self._run_cli_process(
                    chat_id, provider_name, provider, argv, cwd, prompt
                )
            )
            self.pending[chat_id] = task
            return await task
        except Exception as e:
            logger.exception("CLI execution failed")
            return f"❌ Error running {provider.name}: {e}"
        finally:
            task = self.pending.get(chat_id)
            if task and task.done():
                self.pending.pop(chat_id, None)

    async def _run_cli_process(
        self,
        chat_id: int,
        provider_key: str,
        provider: CLIProvider,
        argv: list[str],
        cwd: Path,
        prompt: str,
    ) -> str:
        logger.info(
            "telegram.cli.run",
            extra={
                "chat_id": chat_id,
                "provider": provider_key,
                "cwd": str(cwd),
                "prompt_len": len(prompt),
                "argv": argv,
            },
        )
        start = time.perf_counter()
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(cwd),
            env={**os.environ, "TERM": "dumb", "NO_COLOR": "1", "FORCE_COLOR": "0"},
        )

        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=CLI_TIMEOUT
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return f"❌ {provider.name} timed out after {CLI_TIMEOUT}s"
        finally:
            duration = time.perf_counter() - start

        output = (stdout or b"").decode("utf-8", errors="replace").strip()
        output = self._sanitize_output(output)

        if not output:
            output = "(No output)"

        truncated = False
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + "\n...(truncated)"
            truncated = True

        self._record_history(
            chat_id, provider_key, provider, prompt, output, duration, truncated
        )

        return (
            f"{provider.icon} **{provider.name}** (took {duration:.1f}s):\n\n{output}"
        )

    def _record_history(
        self,
        chat_id: int,
        provider_key: str,
        provider: CLIProvider,
        prompt: str,
        output: str,
        duration: float,
        truncated: bool,
    ) -> None:
        entry = {
            "provider_key": provider_key,
            "provider": provider.name,
            "prompt": prompt,
            "output": output,
            "duration": f"{duration:.1f}s",
            "truncated": "yes" if truncated else "no",
        }
        self.history[chat_id].appendleft(entry)

    def close_session(self, chat_id: int) -> str:
        """Close/deactivate CLI provider for a chat."""
        if chat_id not in self.active_provider:
            return "❌ No CLI provider active."

        provider_name = self.active_provider[chat_id]
        provider = CLI_PROVIDERS[provider_name]
        del self.active_provider[chat_id]

        # Cancel any pending task
        if chat_id in self.pending:
            self.pending[chat_id].cancel()
            del self.pending[chat_id]

        return f"✅ {provider.name} deactivated. Back to ChefChat."

    def cancel(self, chat_id: int) -> str:
        """Cancel an in-flight CLI execution."""
        task = self.pending.get(chat_id)
        if not task or task.done():
            return "❌ No running CLI request to cancel."

        task.cancel()
        return "🛑 Cancelled current CLI request."

    def get_session_status(self, chat_id: int) -> str:
        """Get status of CLI provider for a chat."""
        if chat_id not in self.active_provider:
            return "❌ No CLI provider active."

        provider_name = self.active_provider[chat_id]
        provider = CLI_PROVIDERS[provider_name]

        running = self.pending.get(chat_id)
        running_msg = "Running" if running and not running.done() else "Idle"

        return (
            f"{provider.icon} **{provider.name} Active**\n\n"
            f"Command: `{provider.command}`\n"
            f"Mode: One-shot (each message processed separately)\n"
            f"State: {running_msg}\n\n"
            f"Send a message to ask {provider.name}, or `/cliclose` to deactivate."
        )

    def get_history(self, chat_id: int) -> str:
        """Return a formatted history string for the chat."""
        if not self.history.get(chat_id):
            return "ℹ️ No CLI runs yet for this chat."

        PROMPT_DISPLAY_LIMIT = 120
        lines = ["🗂️ Recent CLI runs (latest first):"]
        for entry in self.history[chat_id]:
            lines.append(
                f"• {entry['provider']} in {entry['duration']} (truncated: {entry['truncated']})\n"
                f"  Prompt: {entry['prompt'][:PROMPT_DISPLAY_LIMIT]}"
                + ("..." if len(entry["prompt"]) > PROMPT_DISPLAY_LIMIT else "")
            )
        return "\n".join(lines)

    def get_last_prompt(self, chat_id: int) -> tuple[str, str, str] | None:
        """Return (provider_key, provider_name, prompt) for the latest run."""
        if not self.history.get(chat_id):
            return None
        entry = self.history[chat_id][0]
        return entry["provider_key"], entry["provider"], entry["prompt"]

    def clear_history(self, chat_id: int) -> str:
        """Clear stored CLI history for this chat."""
        if chat_id in self.history:
            self.history[chat_id].clear()
        return "🧹 Cleared CLI history."

    def get_setup_help(self) -> str:
        """Return quick install/help text."""
        lines = [
            "🛠️ CLI Setup",
            "Install providers on your host:",
            "• gemini: `pip install google-gemini-cli`",
            "• codex: `pip install openai-codex-cli`",
            "• opencode: `pip install opencode-cli`",
            "",
            "Gemini runs with `--approval-mode yolo` to avoid interactive prompts.",
            "Override flags via `GEMINI_CLI_ARGS`, e.g. `GEMINI_CLI_ARGS=\"--approval-mode auto_edit\"`.",
            "",
            "Set API keys:",
            "- Gemini: `GEMINI_API_KEY` or `GOOGLE_API_KEY`",
            "- Codex: `OPENAI_API_KEY`",
            "- OpenCode: `OPENCODE_API_KEY`",
            "",
            "Then use `/cli <provider>` or `gemini: prompt` inline.",
        ]
        return "\n".join(lines)

    def has_active_session(self, chat_id: int) -> bool:
        """Check if chat has an active CLI provider."""
        return chat_id in self.active_provider

    def get_active_provider(self, chat_id: int) -> CLIProvider | None:
        """Get the active provider for a chat, or None."""
        if chat_id in self.active_provider:
            return CLI_PROVIDERS[self.active_provider[chat_id]]
        return None
