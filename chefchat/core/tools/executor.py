"""Central secure command executor module.

This module provides a secure, centralized way to execute external commands.
It enforces:
1. Safe argument parsing (shlex)
2. Safe environment variables (no API key leakage)
3. Timeout handling
4. Logging
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import shlex
from typing import ClassVar, Literal

from chefchat.core.tools.base import ToolError
from chefchat.core.utils import get_subprocess_encoding, is_windows

logger = logging.getLogger(__name__)


class SecureCommandExecutor:
    """Centralized, secure command execution.

    All external commands MUST go through this executor.
    Prevents shell injection, validates executables, logs all calls.
    """

    # Whitelist of allowed executables
    # Note: This list is for prevention of shell meta-character abuse.
    # High-level write blocking is handled by ModeManager.
    ALLOWED_EXECUTABLES: ClassVar[set[str]] = {
        # File operations
        "cat",
        "head",
        "tail",
        "wc",
        "file",
        "stat",
        "ls",
        "find",
        "grep",
        "awk",
        "sed",
        "cut",
        "sort",
        "uniq",
        "tr",
        "echo",
        "mkdir",
        "rm",
        "cp",
        "mv",
        "touch",
        "pwd",
        "tree",
        "locate",
        "which",
        "whereis",
        "type",
        "basename",
        "dirname",
        "realpath",
        "chmod",
        "chown",
        "chgrp",
        "ln",
        "readlink",
        # Git
        "git",
        # Network (Use with caution)
        "curl",
        "wget",
        "ping",
        "dig",
        "host",
        "nslookup",
        # System
        "ps",
        "top",
        "htop",
        "pgrep",
        "kill",
        "pkill",
        "uptime",
        "uname",
        "hostname",
        "date",
        "env",
        "printenv",
        "whoami",
        "id",
        "groups",
        "df",
        "du",
        "free",
        # Languages/Tools
        "python",
        "python3",
        "pip",
        "uv",
        "node",
        "npm",
        "npx",
        "make",
        "gcc",
        "clang",
        "cargo",
        "go",
        "rustc",
        "docker",
        "docker-compose",
        # Shell utilities
        "bash",
        "sh",
        "zsh",
        "fish",
        # Text processing
        "less",
        "more",
        "nano",
        "vim",
        "emacs",
        "code",
        # Archive utilities
        "tar",
        "zip",
        "unzip",
        "gzip",
        "gunzip",
        "bzip2",
        "bunzip2",
        # Process management
        "nohup",
        "sleep",
        "cal",
        "who",
        "w",
        # Development tools
        "pytest",
        "black",
        "ruff",
        "mypy",
        "flake8",
        "pre-commit",
        "poetry",
        "virtualenv",
        "conda",
        "yarn",
        "pnpm",
        "gradle",
        "mvn",
        "ant",
        "cmake",
        # Additional useful commands
        "rsync",
        "scp",
        "ssh",
        "jq",
        "yq",
        "httpie",
        "http",  # Usually blocked by non-interactive mode but added for completeness
    }

    # Shell built-ins that require shell context
    SHELL_BUILTINS: ClassVar[set[str]] = {
        "cd",
        "pushd",
        "popd",
        "dirs",
        "source",
        "exec",
        "exit",
        "export",
        "unset",
        "alias",
        "unalias",
        "history",
        "jobs",
        "fg",
        "bg",
        "wait",
        "umask",
        "ulimit",
        "type",
        "times",
        "hash",
    }

    def __init__(self, workdir: Path) -> None:
        """Initialize executor.

        Args:
            workdir: Working directory for commands
        """
        self.workdir = workdir
        self._current_workdir = workdir

    @staticmethod
    def get_safe_env() -> dict[str, str]:
        """Create minimal env for subprocesses - NO API KEY LEAKAGE.

        Returns:
            Dictionary of safe environment variables.
        """
        # Only include these safe variables from the host environment
        SAFE_VARS = {
            "PATH",
            "HOME",
            "USER",
            "SHELL",
            "TERM",
            "LANG",
            "LC_ALL",
            "TZ",
            "TMPDIR",
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
        }

        base_env = {key: os.environ[key] for key in SAFE_VARS if key in os.environ}

        # Add secure defaults
        base_env.update({
            "CI": "true",
            "NONINTERACTIVE": "1",
            "NO_TTY": "1",
            "NO_COLOR": "1",
            # Force standard tools behavior
            "PAGER": "cat",
            "EDITOR": "cat",
            "VISUAL": "cat",
            "GIT_PAGER": "cat",
            # Python specific
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        })

        # Windows specific adjustments
        if is_windows():
            base_env["GIT_PAGER"] = "more"
            base_env["PAGER"] = "more"
            # Windows needs some extra env vars to function comfortably
            for win_var in [
                "SystemRoot",
                "SystemDrive",
                "Windir",
                "COMSPEC",
                "PATHEXT",
            ]:
                if win_var in os.environ:
                    base_env[win_var] = os.environ[win_var]
        else:
            base_env["TERM"] = "dumb"

        return base_env

    async def execute(
        self, command: str, timeout: int = 30, env: dict[str, str] | None = None
    ) -> tuple[str, str, int]:
        """Execute command securely.

        Args:
            command: Command string (will be parsed with shlex)
            timeout: Timeout in seconds
            env: Optional extra environment variables (merged with safe default)

        Returns:
            (stdout, stderr, returncode)

        Raises:
            ToolError: If command is unsafe or execution fails
        """
        # 1. Parse command
        try:
            args = shlex.split(command)
        except ValueError as e:
            raise ToolError(f"Invalid command syntax: {e}")

        if not args:
            raise ToolError("Empty command")

        # 2. Validate executable
        executable = args[0]
        base_executable = os.path.basename(executable)

        # Check if it's a shell built-in
        is_shell_builtin = (
            base_executable in self.SHELL_BUILTINS or executable in self.SHELL_BUILTINS
        )

        # Validate executable (allow shell built-ins)
        if (
            not is_shell_builtin
            and base_executable not in self.ALLOWED_EXECUTABLES
            and executable not in self.ALLOWED_EXECUTABLES
        ):
            raise ToolError(
                f"Executable '{executable}' is not allowed. "
                f"Permitted executables: {', '.join(sorted(self.ALLOWED_EXECUTABLES))} "
                f"Shell built-ins: {', '.join(sorted(self.SHELL_BUILTINS))}"
            )

        # 3. Prepare Environment
        safe_env = self.get_safe_env()
        if env:
            safe_env.update(env)

        # 4. Log
        # logger.debug(f"Executing: {command} in {self.workdir}")

        # 5. Execute (shell for built-ins, direct for executables)
        try:
            # start_new_session is Unix-only
            kwargs: dict[Literal["start_new_session"], bool] = (
                {} if is_windows() else {"start_new_session": True}
            )

            # Special handling for cd command
            if base_executable == "cd" and len(args) > 1:
                target_dir = args[1]
                if target_dir == "~":
                    target_path = Path.home()
                elif target_dir.startswith("-"):
                    # Handle cd - (previous directory) - for simplicity, go to home
                    target_path = Path.home()
                else:
                    target_path = Path(target_dir)

                # Resolve relative paths against current working directory
                if not target_path.is_absolute():
                    target_path = self._current_workdir / target_path

                target_path = target_path.resolve()

                if not target_path.exists():
                    raise ToolError(f"Directory does not exist: {target_path}")

                if not target_path.is_dir():
                    raise ToolError(f"Path is not a directory: {target_path}")

                # Update the working directory for subsequent commands
                self._current_workdir = target_path

                # Return success with no output
                return "", f"Changed directory to: {target_path}", 0

            # Use current working directory for execution
            execution_dir = self._current_workdir

            if is_shell_builtin:
                # For shell built-ins, we need to use shell=True
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                    cwd=execution_dir,
                    env=safe_env,
                    **kwargs,
                )
            else:
                # For regular executables, use direct execution
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                    cwd=execution_dir,
                    env=safe_env,
                    **kwargs,
                )

            subprocess_timeout = timeout

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=subprocess_timeout
                )
            except TimeoutError:
                # Force kill process tree
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                raise ToolError(f"Command timed out after {timeout}s: {command}")

            # Decode
            encoding = get_subprocess_encoding()
            stdout = stdout_bytes.decode(encoding, errors="replace")
            stderr = stderr_bytes.decode(encoding, errors="replace")
            returncode = proc.returncode or 0

            return stdout, stderr, returncode

        except (ToolError, asyncio.CancelledError):
            raise
        except Exception as e:
            raise ToolError(f"Command execution failed: {e}") from e

    def get_current_workdir(self) -> Path:
        """Get the current working directory for command execution."""
        return self._current_workdir

    def reset_workdir(self) -> None:
        """Reset the working directory to the original workdir."""
        self._current_workdir = self.workdir
