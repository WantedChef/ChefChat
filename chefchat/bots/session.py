"""Bot session management for ChefChat."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import time
from typing import Any

from chefchat.bots.memory import ConversationMemory
from chefchat.core.agent import Agent
from chefchat.core.config import VibeConfig
from chefchat.core.types import AssistantEvent, ToolCallEvent, ToolResultEvent
from chefchat.core.utils import ApprovalResponse
from chefchat.modes import ModeManager, VibeMode

logger = logging.getLogger(__name__)


class BotSession:
    """Manages a ChefChat session for a specific user/chat on a bot platform.

    Bridges the Agent's event stream to the bot's messaging interface.
    Now with persistent conversation memory.
    """

    def __init__(
        self,
        config: VibeConfig,
        send_message: Callable[[str], Awaitable[Any]],
        update_message: Callable[[Any, str], Awaitable[None]],
        request_approval: Callable[[str, dict[str, Any], str], Awaitable[Any]],
        user_id: str,
        chat_id: int | str | None = None,
        tool_policy: str = "dev",
    ) -> None:
        self.config = config
        self.send_message = send_message
        self.update_message = update_message
        self.request_approval = request_approval
        self.user_id = user_id
        self.chat_id = str(chat_id) if chat_id else user_id
        self.tool_policy = tool_policy  # dev | chat | combo
        self.safe_auto_tools = {"read_file", "grep"}

        # Initialize persistent memory
        self.memory = ConversationMemory(chat_id=self.chat_id)

        # Mode manager for this session (bots stay in NORMAL unless switched)
        self.mode_manager = ModeManager(
            initial_mode=VibeMode.NORMAL, snapshots_enabled=False
        )

        # Ensure we always have a valid active model configured for the Agent.
        self._ensure_active_model()

        # Initialize agent
        # We might want to pass a modified config or mode_manager if needed
        self.agent = Agent(
            config,
            auto_approve=False,  # We want control
            enable_streaming=True,
            mode_manager=self.mode_manager,
        )
        self.agent.set_approval_callback(self._approval_callback)

        # Sync memory with agent if we have previous messages
        self._restore_context_from_memory()

        # Approval management
        self._pending_approvals: dict[str, asyncio.Future[tuple[str, str | None]]] = {}

    def _ensure_active_model(self) -> None:
        """Fallback to the first configured model if the active one is missing."""
        try:
            self.config.get_active_model()
        except ValueError:
            if self.config.models:
                fallback = self.config.models[0].alias
                logger.warning(
                    "BotSession: active_model '%s' missing; falling back to '%s'",
                    self.config.active_model,
                    fallback,
                )
                self.config.active_model = fallback
            else:
                logger.error("BotSession: no models configured; agent may fail to start")

    def _restore_context_from_memory(self) -> None:
        """Restore agent context from persistent memory."""
        if not self.memory.entries:
            return

        # Get context injection for system prompt enhancement
        context_injection = self.memory.get_context_injection()
        if context_injection:
            # Log context restoration
            logger.info(
                "session.restore: chat=%s entries=%d context=%s",
                self.chat_id,
                len(self.memory.entries),
                context_injection[:100],
            )

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

        # Sync user message to persistent memory
        self.memory.add_message("user", text)

        # Debug: log message count before processing
        msg_count_before = len(self.agent.messages)
        logger.debug(
            "session.act: chat=%s before=%d memory=%d text=%r",
            self.chat_id,
            msg_count_before,
            len(self.memory.entries),
            text[:50] if text else "",
        )

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

            # Sync assistant response to persistent memory
            if response_buffer:
                self.memory.add_message("assistant", response_buffer)
                self.memory.save_to_disk()

            # Debug: log message count after successful processing
            msg_count_after = len(self.agent.messages)
            logger.debug(
                "session.act: chat=%s after=%d memory=%d (added %d)",
                self.chat_id,
                msg_count_after,
                len(self.memory.entries),
                msg_count_after - msg_count_before,
            )

        except Exception as e:
            logger.exception("Error in agent loop")
            await self.send_message(f"💥 Error: {e}")

    async def clear_history(self) -> None:
        """Clear agent history and persistent memory."""
        await self.agent.clear_history()
        self.memory.clear()
        logger.info("session.clear: chat=%s", self.chat_id)

    def get_memory_stats(self) -> dict:
        """Get memory statistics for this session."""
        return self.memory.get_stats()

    def get_memory_context(self) -> str | None:
        """Get context injection from memory."""
        return self.memory.get_context_injection()
