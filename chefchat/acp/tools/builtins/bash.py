from __future__ import annotations

import asyncio
import re
import shlex
import os
from typing import final

from acp import CreateTerminalRequest, TerminalHandle
from acp.schema import (
    EnvVariable,
    TerminalToolCallContent,
    ToolCallProgress,
    ToolCallStart,
    WaitForTerminalExitResponse,
)

from chefchat import CHEFCHAT_ROOT
from chefchat.acp.tools.base import AcpToolState, BaseAcpTool
from chefchat.core.tools.base import ToolError, ToolPermission
from chefchat.core.tools.builtins.bash import BashArgs, BashResult, BashToolConfig
from chefchat.core.types import ToolCallEvent, ToolResultEvent
from chefchat.core.utils import logger


class AcpBashState(AcpToolState):
    pass


class Bash(BaseAcpTool[BashArgs, BashResult, BashToolConfig, AcpBashState]):
    prompt_path = CHEFCHAT_ROOT / "core" / "tools" / "builtins" / "prompts" / "bash.md"
    state: AcpBashState

    @classmethod
    def _get_tool_state_class(cls) -> type[AcpBashState]:
        return AcpBashState

    async def run(self, args: BashArgs) -> BashResult:
        connection, session_id, _ = self._load_state()

        timeout = args.timeout or self.config.default_timeout
        max_bytes = self.config.max_output_bytes
        env, command, cmd_args = self._parse_command(args.command)

        create_request = CreateTerminalRequest(
            sessionId=session_id,
            command=command,
            args=cmd_args,
            env=env,
            cwd=str(self.config.effective_workdir),
            outputByteLimit=max_bytes,
        )

        try:
            terminal_handle = await connection.createTerminal(create_request)
        except Exception as e:
            raise ToolError(f"Failed to create terminal: {e!r}") from e

        await self._send_in_progress_session_update([
            TerminalToolCallContent(type="terminal", terminalId=terminal_handle.id)
        ])

        try:
            exit_response = await self._wait_for_terminal_exit(
                terminal_handle, timeout, args.command
            )

            output_response = await terminal_handle.current_output()

            return self._build_result(
                command=args.command,
                stdout=output_response.output,
                stderr="",
                returncode=exit_response.exitCode or 0,
            )

        finally:
            try:
                await terminal_handle.release()
            except Exception as e:
                logger.error(f"Failed to release terminal: {e!r}")

    def _parse_command(
        self, command_str: str
    ) -> tuple[list[EnvVariable], str, list[str]]:
        parts = shlex.split(command_str)
        env: list[EnvVariable] = []
        command: str = ""
        args: list[str] = []

        for part in parts:
            if "=" in part and not command:
                key, value = part.split("=", 1)
                env.append(EnvVariable(name=key, value=value))
            elif not command:
                command = part
            else:
                args.append(part)

        return env, command, args

    @classmethod
    def get_summary(cls, args: BashArgs) -> str:
        summary = f"{args.command}"
        if args.timeout:
            summary += f" (timeout {args.timeout}s)"

        return summary

    async def _wait_for_terminal_exit(
        self, terminal_handle: TerminalHandle, timeout: int, command: str
    ) -> WaitForTerminalExitResponse:
        try:
            return await asyncio.wait_for(
                terminal_handle.wait_for_exit(), timeout=timeout
            )
        except TimeoutError:
            # Capture output before killing for better error context
            partial_output = ""
            try:
                output_response = await terminal_handle.current_output()
                partial_output = output_response.output[:500] if output_response.output else ""
            except Exception:
                pass
            
            try:
                await terminal_handle.kill()
            except Exception as e:
                logger.error(f"Failed to kill terminal: {e!r}")

            raise self._build_timeout_error(command, timeout, partial_output)

    @classmethod
    def tool_call_session_update(cls, event: ToolCallEvent) -> ToolCallStart:
        if not isinstance(event.args, BashArgs):
            raise ValueError(f"Unexpected tool args: {event.args}")

        return ToolCallStart(
            sessionUpdate="tool_call",
            title=Bash.get_summary(event.args),
            content=None,
            toolCallId=event.tool_call_id,
            kind="execute",
            rawInput=event.args.model_dump_json(),
        )

    def _build_timeout_error(self, command: str, timeout: int, partial_output: str = "") -> ToolError:
        msg = f"Command timed out after {timeout}s: {command!r}"
        if partial_output:
            msg += f"\nPartial output: {partial_output}"
        return ToolError(msg)

    @final
    def _build_result(
        self, *, command: str, stdout: str, stderr: str, returncode: int
    ) -> BashResult:
        if returncode != 0:
            error_msg = f"Command failed: {command!r}\n"
            error_msg += f"Return code: {returncode}"
            if stderr:
                error_msg += f"\nStderr: {stderr}"
            if stdout:
                error_msg += f"\nStdout: {stdout}"
            raise ToolError(error_msg.strip())

        return BashResult(stdout=stdout, stderr=stderr, returncode=returncode)

    def _validate_command_safety(self, command: str) -> bool:
        """
        Validate command safety by checking for dangerous shell operators.
        
        Returns True if command is safe (no shell operators), False otherwise.
        """
        # Dangerous shell operators that allow command chaining or execution
        # && = AND operator
        # || = OR operator
        # ; = Command separator
        # | = Pipe (can be dangerous if used to chain)
        # ` = Backticks for command substitution
        # $() = Command substitution
        dangerous_patterns = [";", "&&", "||", "|", "`", "$("]
        
        return not any(pattern in command for pattern in dangerous_patterns)

    def _is_denylisted(self, command: str) -> bool:
        """Check if command matches denylist patterns."""
        # Check against patterns directly
        if any(command.startswith(pattern) for pattern in self.config.denylist):
            return True
            
        # Check full path commands against base names
        # e.g. /bin/rm should match rm
        parts = command.split()
        if not parts:
            return False
            
        cmd_name = parts[0]
        base_name = os.path.basename(cmd_name)
        
        return any(base_name == pattern or base_name.startswith(pattern + " ") 
                  for pattern in self.config.denylist)

    def _is_standalone_denylisted(self, command: str) -> bool:
        """Check if command is a standalone denylisted command."""
        parts = command.split()
        if not parts:
            return False

        # Check both full command and basename
        cmd_name = parts[0]
        base_name = os.path.basename(cmd_name)
        has_args = len(parts) > 1

        if not has_args:
            if cmd_name in self.config.denylist_standalone:
                return True
            if base_name in self.config.denylist_standalone:
                return True

        return False

    def _is_allowlisted(self, command: str) -> bool:
        """Check if command matches allowlist patterns."""
        return any(command.startswith(pattern) for pattern in self.config.allowlist)

    def check_allowlist_denylist(self, args: BashArgs) -> ToolPermission:
        """Check if the bash command is allowed based on allowlist/denylist."""
        
        # First, check for dangerous shell operators
        if not self._validate_command_safety(args.command):
            # If command contains dangerous operators, we MUST ask unless it's explicitly explicitly 
            # safe. But for now, let's enable strict mode where we ASK or BLOCK.
            # To be safe, if we detect chaining, we treat it as potentially dangerous.
            # We can't easily parse complex chained commands to check each part against allowlist.
            # So if it's complex, we default to stricter checking or just ASK.
            
            # Additional check: if command mimics a known safe command but has operators, 
            # maybe we still want to block?
            # For this remediation, we will BLOCK dangerous operators if they are not 
            # fundamentally required for simple operations.
            logger.warning(f"Blocking command with dangerous operators: {args.command}")
            return ToolPermission.NEVER

        command_parts = re.split(r"(?:&&|\|\||;|\|)", args.command)
        command_parts = [part.strip() for part in command_parts if part.strip()]

        if not command_parts:
            return ToolPermission.ASK

        for command_part in command_parts:
            # Check denylists first (highest priority)
            if self._is_denylisted(command_part) or self._is_standalone_denylisted(
                command_part
            ):
                logger.warning(f"Blocking denylisted command: {command_part}")
                return ToolPermission.NEVER
                
            # If any part is NOT allowlisted, we must ASK
            if not self._is_allowlisted(command_part):
                return ToolPermission.ASK

        # If we got here, all parts passed denylist and are allowlisted. 
        # But wait, if we had multiple parts (chaining), _validate_command_safety would have caught it.
        # So we really only process single commands here.
        return ToolPermission.ALWAYS

    @classmethod
    def tool_result_session_update(
        cls, event: ToolResultEvent
    ) -> ToolCallProgress | None:
        return ToolCallProgress(
            sessionUpdate="tool_call_update",
            toolCallId=event.tool_call_id,
            status="failed" if event.error else "completed",
        )
