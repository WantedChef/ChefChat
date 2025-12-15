"""Bot session management for ChefChat."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import time
from typing import Any

from chefchat.core.agent import Agent
from chefchat.core.config import VibeConfig
from chefchat.core.types import AssistantEvent, ToolCallEvent, ToolResultEvent
from chefchat.core.utils import ApprovalResponse

logger = logging.getLogger(__name__)


class BotSession:
    """Manages a ChefChat session for a specific user/chat on a bot platform.

    Bridges the Agent's event stream to the bot's messaging interface.
    """

    def __init__(
        self,
        config: VibeConfig,
        send_message: Callable[[str], Awaitable[Any]],
        update_message: Callable[[Any, str], Awaitable[None]],
        request_approval: Callable[[str, dict[str, Any], str], Awaitable[Any]],
        user_id: str,
        tool_policy: str = "dev",
    ) -> None:
        self.config = config
        self.send_message = send_message
        self.update_message = update_message
        self.request_approval = request_approval
        self.user_id = user_id
        self.tool_policy = tool_policy  # dev | chat | combo
        self.safe_auto_tools = {"read_file", "grep"}

        # Initialize agent
        # We might want to pass a modified config or mode_manager if needed
        self.agent = Agent(
            config,
            auto_approve=False,  # We want control
            enable_streaming=True,
        )
        self.agent.set_approval_callback(self._approval_callback)

        # Approval management
        self._pending_approvals: dict[str, asyncio.Future[tuple[str, str | None]]] = {}

    async def _approval_callback(
        self, tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> tuple[str, str | None]:
        """Called by Agent when a tool needs approval."""
        # Enforce tool policy before surfacing the approval UI
        if self.tool_policy == "chat":
            return (
                ApprovalResponse.NO,
                f"Tools zijn uitgeschakeld (bot-mode: chat). Tool: {tool_name}",
            )

        if self.tool_policy == "combo" and tool_name in self.safe_auto_tools:
            return (ApprovalResponse.ALWAYS, "Auto-goedgekeurd in Combo-modus.")

        approval_id = tool_call_id  # Use tool_call_id as correlation ID

        future = asyncio.get_running_loop().create_future()
        self._pending_approvals[approval_id] = future

        # Ask the bot implementation to show the UI
        try:
            await self.request_approval(tool_name, args, approval_id)
        except Exception as e:
            logger.error("Failed to request approval: %s", e)
            del self._pending_approvals[approval_id]
            return (ApprovalResponse.NO, "Failed to display approval request")

        try:
            # Wait for the user's decision
            result = await future
            return result
        finally:
            self._pending_approvals.pop(approval_id, None)

    def set_tool_policy(self, policy: str) -> None:
        """Update tool policy for this session."""
        self.tool_policy = policy

    def resolve_approval(
        self, approval_id: str, response: str, message: str | None = None
    ) -> None:
        """Called by the bot implementation when user clicks a button."""
        if approval_id in self._pending_approvals:
            future = self._pending_approvals[approval_id]
            if not future.done():
                future.set_result((response, message))

    async def handle_user_message(self, text: str) -> None:
        """Process an incoming message from the user."""
        # Initial status message
        current_msg_handle = await self.send_message("👨‍🍳 Cooking...")

        response_buffer = ""
        last_update_time = 0.0
        update_interval = 1.0  # seconds

        try:
            async for event in self.agent.act(text):
                if isinstance(event, AssistantEvent):
                    response_buffer += event.content

                    # Throttled update
                    now = time.time()
                    if now - last_update_time > update_interval:
                        await self.update_message(
                            current_msg_handle, response_buffer + " ▌"
                        )
                        last_update_time = now

                elif isinstance(event, ToolCallEvent):
                    # Notify about tool use
                    await self.send_message(f"🔧 Using tool: `{event.tool_name}`")

                elif isinstance(event, ToolResultEvent):
                    # Maybe show result status?
                    if event.error:
                        await self.send_message(
                            f"❌ Tool error: {str(event.error)[:100]}"
                        )
                    else:
                        pass  # Success is silent-ish or implied

            # Final update
            await self.update_message(current_msg_handle, response_buffer)

        except Exception as e:
            logger.exception("Error in agent loop")
            await self.send_message(f"💥 Error: {e}")

    async def clear_history(self) -> None:
        await self.agent.clear_history()
