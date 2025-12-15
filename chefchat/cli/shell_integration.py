"""Shell integration module for Zsh and Bash.

Provides shell detection, history reading, and alias generation
for integrating ChefChat with the user's shell environment.
"""

from __future__ import annotations

import os
from pathlib import Path
import re


class ShellIntegration:
    """Manage shell (Zsh/Bash) integration.

    Detects the user's shell, reads command history,
    and generates aliases for ChefChat commands.
    """

    @staticmethod
    def detect_shell() -> str:
        """Detect the current shell from environment.

        Returns:
            Shell name (zsh, bash, fish, or unknown).
        """
        shell = os.environ.get("SHELL", "")
        shell_lower = shell.lower()

        if "zsh" in shell_lower:
            return "zsh"
        elif "bash" in shell_lower:
            return "bash"
        elif "fish" in shell_lower:
            return "fish"
        else:
            # Try to detect from running process
            shell_basename = os.path.basename(shell)
            if shell_basename in {"zsh", "bash", "fish", "sh", "dash"}:
                return shell_basename
            return "unknown"

    @staticmethod
    def get_history_file() -> Path | None:
        """Get the shell history file path.

        Returns:
            Path to history file or None if not found.
        """
        shell = ShellIntegration.detect_shell()
        home = Path.home()

        # Check for HISTFILE environment variable first
        histfile = os.environ.get("HISTFILE")
        if histfile:
            return Path(histfile)

        # Default locations by shell
        match shell:
            case "zsh":
                return home / ".zsh_history"
            case "bash":
                return home / ".bash_history"
            case "fish":
                return home / ".local" / "share" / "fish" / "fish_history"
            case _:
                # Fallback to bash history
                return home / ".bash_history"

    @staticmethod
    def _parse_shell_line(line: str, shell: str) -> str | None:
        """Parse a shell history line based on shell type.

        Args:
            line: Raw history line.
            shell: Shell type (zsh, bash, fish).

        Returns:
            Parsed command or None if line should be skipped.
        """
        line = line.strip()
        if not line:
            return None

        # Parse shell-specific formats
        if shell == "zsh":
            # Zsh extended history format: : timestamp:0;command
            if line.startswith(":") and ";" in line:
                line = line.split(";", 1)[1]

        elif shell == "fish":
            # Fish history format: - cmd: command
            if line.startswith("- cmd:"):
                line = line[6:].strip()

        # Skip comments and empty after parsing
        if line.startswith("#") or not line:
            return None

        return line

    @staticmethod
    def _deduplicate_commands(commands: list[str], limit: int) -> list[str]:
        """Deduplicate commands while preserving order (most recent first).

        Args:
            commands: List of commands.
            limit: Maximum number of commands to return.

        Returns:
            Deduplicated list of commands.
        """
        seen: set[str] = set()
        unique_commands: list[str] = []
        for cmd in reversed(commands):
            if cmd not in seen:
                seen.add(cmd)
                unique_commands.append(cmd)
            if len(unique_commands) >= limit:
                break
        return unique_commands

    @staticmethod
    def read_history(limit: int = 100) -> list[str]:
        """Read recent commands from shell history.

        Args:
            limit: Maximum number of commands to return.

        Returns:
            List of recent commands, most recent first.
        """
        history_file = ShellIntegration.get_history_file()

        if not history_file or not history_file.exists():
            return []

        try:
            content = history_file.read_text(errors="ignore")
            lines = content.splitlines()
        except OSError:
            return []

        shell = ShellIntegration.detect_shell()
        commands: list[str] = []

        for line in lines:
            parsed = ShellIntegration._parse_shell_line(line, shell)
            if parsed:
                commands.append(parsed)

        return ShellIntegration._deduplicate_commands(commands, limit)

    @staticmethod
    def generate_aliases() -> str:
        """Generate shell aliases for ChefChat.

        Returns:
            Shell code for aliases.
        """
        shell = ShellIntegration.detect_shell()

        # Common aliases for all shells
        aliases = """
# ChefChat Aliases
alias chef='uv run vibe'
alias cheftui='uv run vibe --tui'
alias chefactive='uv run vibe --tui --active'
alias chefchat='uv run vibe'

# Chef quick commands
alias cfq='uv run vibe -q'
alias cfh='uv run vibe --help'
"""

        if shell == "fish":
            # Fish uses different syntax
            aliases = """
# ChefChat Aliases (Fish)
alias chef 'uv run vibe'
alias cheftui 'uv run vibe --tui'
alias chefactive 'uv run vibe --tui --active'
alias chefchat 'uv run vibe'

# Chef quick commands
alias cfq 'uv run vibe -q'
alias cfh 'uv run vibe --help'
"""

        return aliases.strip()

    @staticmethod
    def get_rc_file() -> Path | None:
        """Get the shell rc file path.

        Returns:
            Path to rc file or None.
        """
        shell = ShellIntegration.detect_shell()
        home = Path.home()

        match shell:
            case "zsh":
                return home / ".zshrc"
            case "bash":
                # Check if .bash_profile exists (macOS preference)
                bash_profile = home / ".bash_profile"
                bashrc = home / ".bashrc"
                return bash_profile if bash_profile.exists() else bashrc
            case "fish":
                return home / ".config" / "fish" / "config.fish"
            case _:
                return home / ".bashrc"

    @staticmethod
    def install_aliases(rc_file: Path | None = None) -> bool:
        """Install aliases to shell rc file.

        Args:
            rc_file: Path to rc file, or None to auto-detect.

        Returns:
            True if installation succeeded.
        """
        if rc_file is None:
            rc_file = ShellIntegration.get_rc_file()

        if rc_file is None:
            return False

        aliases = ShellIntegration.generate_aliases()
        marker_start = "# >>> ChefChat Integration >>>"
        marker_end = "# <<< ChefChat Integration <<<"

        try:
            # Read existing content
            if rc_file.exists():
                content = rc_file.read_text()
            else:
                content = ""

            # Check if already installed
            if marker_start in content:
                # Update existing block
                pattern = re.compile(
                    rf"{re.escape(marker_start)}.*?{re.escape(marker_end)}", re.DOTALL
                )
                new_block = f"{marker_start}\n{aliases}\n{marker_end}"
                content = pattern.sub(new_block, content)
            else:
                # Append new block
                if content and not content.endswith("\n"):
                    content += "\n"
                content += f"\n{marker_start}\n{aliases}\n{marker_end}\n"

            # Write back
            rc_file.write_text(content)
            return True

        except OSError:
            return False

    @staticmethod
    def uninstall_aliases(rc_file: Path | None = None) -> bool:
        """Remove aliases from shell rc file.

        Args:
            rc_file: Path to rc file, or None to auto-detect.

        Returns:
            True if removal succeeded.
        """
        if rc_file is None:
            rc_file = ShellIntegration.get_rc_file()

        if rc_file is None or not rc_file.exists():
            return False

        marker_start = "# >>> ChefChat Integration >>>"
        marker_end = "# <<< ChefChat Integration <<<"

        try:
            content = rc_file.read_text()

            if marker_start not in content:
                return True  # Nothing to remove

            # Remove the block
            pattern = re.compile(
                rf"\n?{re.escape(marker_start)}.*?{re.escape(marker_end)}\n?", re.DOTALL
            )
            content = pattern.sub("\n", content)

            rc_file.write_text(content)
            return True

        except OSError:
            return False

    @staticmethod
    def is_installed(rc_file: Path | None = None) -> bool:
        """Check if ChefChat aliases are installed.

        Args:
            rc_file: Path to rc file, or None to auto-detect.

        Returns:
            True if aliases are installed.
        """
        if rc_file is None:
            rc_file = ShellIntegration.get_rc_file()

        if rc_file is None or not rc_file.exists():
            return False

        try:
            content = rc_file.read_text()
            return "# >>> ChefChat Integration >>>" in content
        except OSError:
            return False
