from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from chefchat.acp.tools.builtins.bash import (
    AcpBashState,
    Bash,
    BashArgs,
    BashToolConfig,
)
from chefchat.core.tools.base import ToolPermission


class TestBashSecurity:
    @pytest.fixture
    def bash_tool(self):
        config = BashToolConfig(
            allowlist=["ls", "echo", "cat"],
            denylist=["rm", "sudo"],
            denylist_standalone=["rm", "sudo"],
            workdir=Path("/tmp"),
            tool_paths=[],
        )
        state = MagicMock(spec=AcpBashState)
        tool = Bash(config, state)
        return tool

    def test_blocks_command_chaining(self, bash_tool):
        # Semicolon
        args = BashArgs(command="ls; rm -rf /")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.NEVER

        # AND operator
        args = BashArgs(command="ls && cat /etc/passwd")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.NEVER

        # OR operator
        args = BashArgs(command="ls || echo 'fail'")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.NEVER

        # Pipe
        args = BashArgs(command="ls | grep secret")
        # NOTE: Pipes might be allowed if individual commands are allowed?
        # Current implementation plan says block operators unless explicitly allowed.
        # Let's assume strict blocking for now.
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.NEVER

    def test_blocks_command_substitution(self, bash_tool):
        # Backticks
        args = BashArgs(command="echo `whoami`")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.NEVER

        # $() syntax
        args = BashArgs(command="echo $(whoami)")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.NEVER

    def test_allows_safe_commands(self, bash_tool):
        args = BashArgs(command="ls -la")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.ALWAYS

        args = BashArgs(command="echo 'hello world'")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.ALWAYS

    def test_denylist_bypass_attempt(self, bash_tool):
        # Current logic might allow this if generic "rm" is blocked but "/bin/rm" isn't
        # This test verifies the fix for full path checking
        args = BashArgs(command="/bin/rm -rf /")
        assert bash_tool.check_allowlist_denylist(args) == ToolPermission.NEVER
