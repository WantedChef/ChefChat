"""ChefChat Line Cook Station - The Code Generation Agent.

The Line Cook is where the actual cooking happens. They:
- Receive PLAN messages from the Sous Chef
- Execute tasks autonomously using available tools
- Generate code, write files, run commands
- Send progress updates to the bus
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus
from chefchat.core.tools.manager import ToolManager
from chefchat.core.config import get_config
from chefchat.modes.manager import ModeManager, VibeMode

if TYPE_CHECKING:
    from chefchat.kitchen.manager import KitchenManager


class LineCook(BaseStation):
    """The autonomous code execution station.

    Handles:
    - Task execution via LLM loop
    - Tool usage (write_file, bash, etc.)
    - Progress reporting
    - Strict adherence to operational modes (Plan vs. Execute)
    """

    def __init__(self, bus: KitchenBus, manager: KitchenManager) -> None:
        """Initialize the Line Cook station.

        Args:
            bus: The kitchen bus to connect to
            manager: The kitchen manager for AI operations
        """
        super().__init__("line_cook", bus)
        self.manager = manager
        self._current_task: str | None = None

        # Initialize ToolManager
        config = get_config()
        self.tool_manager = ToolManager(config)

        # Initialize ModeManager (defaults to NORMAL)
        # It will be updated via MODE_UPDATE messages
        self.mode_manager = ModeManager(initial_mode=VibeMode.NORMAL)

    async def handle(self, message: ChefMessage) -> None:
        """Process incoming messages.

        Args:
            message: The message to process
        """
        action = str(message.action).upper()

        if action == "PLAN":
            # Implementation request from Sous Chef
            await self._execute_plan(message.payload)

        elif action == "FIX_ERRORS":
            # Fix errors from Expeditor (self-healing loop)
            # Re-route to autonomous execution with context
            await self._fix_errors_autonomous(message.payload)

        elif action == "MODE_UPDATE":
            await self._handle_mode_update(message.payload)

    async def _handle_mode_update(self, payload: dict) -> None:
        """Handle mode update broadcast."""
        mode_val = payload.get("mode", "normal")
        try:
            mode = VibeMode(mode_val)
            self.mode_manager.set_mode(mode)

            # Log for debugging/confirmation
            emoji = self.mode_manager.config.emoji
            await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={
                    "type": "system",
                    "content": f"🍳 **Line Cook**: Mode updated to {emoji} {mode.value.upper()}",
                },
            )
        except ValueError:
            pass

    async def _execute_plan(self, plan: dict) -> None:
        """Execute the implementation plan autonomously.

        Args:
            plan: The implementation plan from Sous Chef
        """
        task = plan.get("task", "Unknown Task")
        ticket_id = plan.get("ticket_id", "unknown")

        self._current_task = ticket_id

        # Notify we're starting
        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "cooking",
                "progress": 0,
                "message": "🍳 Firing up the grill (Autonomous Mode)...",
            },
        )

        try:
            # Run the autonomous loop
            await self._autonomous_loop(task, ticket_id)

            # Complete!
            await self.send(
                recipient="tui",
                action="STATUS_UPDATE",
                payload={
                    "station": self.name,
                    "status": "complete",
                    "progress": 100,
                    "message": "✅ Order Up!",
                },
            )

            # Report completion to Sous Chef
            await self.send(
                recipient="sous_chef",
                action="TASK_COMPLETE",
                payload={
                    "ticket_id": ticket_id,
                    "result": "Task completed autonomously",
                },
            )

        except Exception as e:
            await self._send_error(str(e))

    async def _autonomous_loop(self, task: str, ticket_id: str) -> None:
        """Run the main agent loop.

        Args:
            task: The task description
            ticket_id: Ticket ID for context
        """
        # Load available tools
        tools = list(self.tool_manager.available_tools().values())
        tool_instances = {t_cls.get_name(): self.tool_manager.get(t_cls.get_name()) for t_cls in tools}

        # System prompt for autonomous agent
        mode_instruction = self.mode_manager.get_system_prompt_modifier()

        system_prompt = self.manager.CODE_SYSTEM_PROMPT + f"""

You are an autonomous coding agent. You have access to tools to interact with the file system and run commands.
Use these tools to complete the user's task.

MODE INSTRUCTIONS:
{mode_instruction}

GUIDELINES:
1. Break down the task into steps.
2. Use `write_file` to create or modify code (ONLY if allowed by current mode).
3. Use `bash` to run commands if needed.
4. If a tool call fails or is blocked, explain why and try a different approach or stop.
5. When you have completed the task, output a final message starting with "Task Complete:".
"""

        history = [
            {"role": "user", "content": f"Please implement this task:\n{task}"}
        ]

        max_turns = 20
        turn = 0

        while turn < max_turns:
            turn += 1
            await self.send(
                recipient="tui",
                action="STATUS_UPDATE",
                payload={
                    "station": self.name,
                    "status": "cooking",
                    "progress": int((turn / max_turns) * 100),
                    "message": f"🍳 Step {turn}...",
                },
            )

            # Call Chef with tools
            response = await self.manager.chef.cook_recipe(
                ingredients={
                    "messages": history,
                    "tools": list(tool_instances.values()),
                    "system": system_prompt
                },
                preferences={"stream": False} # Tool use requires non-streaming for now
            )

            # Check if response is a tool call or text
            if hasattr(response, "tool_calls") and response.tool_calls:
                # Append assistant message with tool calls to history
                history.append(response)

                # Execute tool calls
                for tool_call in response.tool_calls:
                    function_name = tool_call.function.name
                    arguments_str = tool_call.function.arguments
                    tool_call_id = tool_call.id

                    await self.send(
                        recipient="tui",
                        action="LOG_MESSAGE",
                        payload={
                            "type": "system",
                            "content": f"🛠️ **Tool Call**: `{function_name}`",
                        },
                    )

                    try:
                        arguments = json.loads(arguments_str)
                        tool_instance = tool_instances.get(function_name)

                        if not tool_instance:
                            result_content = f"Error: Tool {function_name} not found"
                        else:
                            # MODE CHECK: Gatekeeper
                            blocked, reason = self.mode_manager.should_block_tool(function_name, arguments)

                            if blocked:
                                result_content = f"TOOL BLOCKED: {reason}"
                                await self.send(
                                    recipient="tui",
                                    action="LOG_MESSAGE",
                                    payload={
                                        "type": "system",
                                        "content": f"🛑 **Blocked**: {function_name} is not allowed in {self.mode_manager.current_mode.value} mode.",
                                    },
                                )
                            else:
                                # Invoke tool
                                result = await tool_instance.invoke(**arguments)

                                # Handle different result types
                                if hasattr(result, "model_dump_json"):
                                    result_content = result.model_dump_json()
                                else:
                                    result_content = str(result)

                    except Exception as e:
                        result_content = f"Error executing tool: {e}"

                    # Add tool result to history
                    history.append({
                        "role": "tool",
                        "name": function_name,
                        "content": result_content,
                        "tool_call_id": tool_call_id
                    })

            else:
                # Text response
                content = str(response)
                history.append({"role": "assistant", "content": content})

                await self.send(
                    recipient="tui",
                    action="LOG_MESSAGE",
                    payload={
                        "type": "assistant",
                        "content": content,
                    },
                )

                if "Task Complete" in content or "Task complete" in content:
                    return

    async def _fix_errors_autonomous(self, payload: dict) -> None:
        """Fix errors using autonomous loop."""
        ticket_id = payload.get("ticket_id", "unknown")
        errors = payload.get("errors", [])
        path = payload.get("path", ".")

        task = (
            f"Fix the following errors in file {path}:\n"
            f"{json.dumps(errors, indent=2)}\n"
            f"Use tools to read the file, analyze it, and write the fix."
        )

        await self._execute_plan({"task": task, "ticket_id": ticket_id})

    async def _send_error(self, error: str) -> None:
        """Send an error message to the TUI and Sous Chef.

        Args:
            error: Error message to send
        """
        # Update status to error
        await self.send(
            recipient="tui",
            action="STATUS_UPDATE",
            payload={
                "station": self.name,
                "status": "error",
                "progress": 0,
                "message": f"❌ Error: {error[:50]}...",
            },
        )

        # Log error message
        await self.send(
            recipient="tui",
            action="LOG_MESSAGE",
            payload={"type": "system", "content": f"❌ **Line Cook Error**: {error}"},
        )

        # Notify Sous Chef of the error
        await self.send(
            recipient="sous_chef",
            action="TASK_ERROR",
            payload={"ticket_id": self._current_task, "error": error},
        )

        self._current_task = None
