from __future__ import annotations

from collections import OrderedDict
from collections.abc import AsyncGenerator, Callable

try:
    from enum import StrEnum, auto
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


import time

# Import ModeManager for type checking only to avoid circular imports
from typing import TYPE_CHECKING
from uuid import uuid4

from vibe.core.config import VibeConfig
from vibe.core.interaction_logger import InteractionLogger
from vibe.core.llm.backend.factory import BACKEND_FACTORY
from vibe.core.llm.format import APIToolFormatHandler, ResolvedMessage
from vibe.core.llm.types import BackendLike
from vibe.core.middleware import (
    AutoCompactMiddleware,
    ContextWarningMiddleware,
    ConversationContext,
    MiddlewareAction,
    MiddlewarePipeline,
    MiddlewareResult,
    PriceLimitMiddleware,
    ResetReason,
    TurnLimitMiddleware,
)
from vibe.core.prompts import UtilityPrompt
from vibe.core.system_prompt import get_universal_system_prompt
from vibe.core.tools.manager import ToolManager
from vibe.core.types import (
    AgentStats,
    ApprovalCallback,
    AssistantEvent,
    BaseEvent,
    CompactEndEvent,
    CompactStartEvent,
    LLMChunk,
    LLMMessage,
    LLMUsage,
    Role,
    ToolCall,
    ToolCallEvent,
    ToolResultEvent,
)
from vibe.core.utils import (
    VIBE_STOP_EVENT_TAG,
    get_user_agent,
    is_user_cancellation_event,
)

if TYPE_CHECKING:
    from vibe.cli.mode_manager import ModeManager


class AgentError(Exception):
    """Base exception for Agent errors."""


class AgentStateError(AgentError):
    """Raised when agent is in an invalid state."""


class LLMResponseError(AgentError):
    """Raised when LLM response is malformed or missing expected data."""


class Agent:
    def __init__(
        self,
        config: VibeConfig,
        auto_approve: bool = False,
        message_observer: Callable[[LLMMessage], None] | None = None,
        max_turns: int | None = None,
        max_price: float | None = None,
        backend: BackendLike | None = None,
        enable_streaming: bool = False,
        mode_manager: ModeManager | None = None,
    ) -> None:
        self.config = config

        self.tool_manager = ToolManager(config)
        self.format_handler = APIToolFormatHandler()

        self.backend_factory = lambda: backend or self._select_backend()
        self.backend = self.backend_factory()

        self.middleware_pipeline = MiddlewarePipeline()
        self.enable_streaming = enable_streaming
        self._setup_middleware(max_turns, max_price)

        # Initialize MessageManager (Refactor B.1)
        from vibe.core.message_manager import MessageManager

        self.message_manager = MessageManager(
            config, self.tool_manager, mode_manager, message_observer
        )

        # Initialize AgentToolExecutor (Refactor B.1 Part 2)
        from vibe.core.agent_tool_executor import AgentToolExecutor

        self.tool_executor = AgentToolExecutor(
            config, self.tool_manager, self.format_handler, mode_manager, auto_approve
        )

        self.stats = AgentStats()
        try:
            active_model = config.get_active_model()
            self.stats.input_price_per_million = active_model.input_price
            self.stats.output_price_per_million = active_model.output_price
        except ValueError:
            pass

        # Store mode_manager for mode-aware tool execution
        self.mode_manager: ModeManager | None = mode_manager

        self.session_id = str(uuid4())

        self.interaction_logger = InteractionLogger(
            config.session_logging,
            self.session_id,
            auto_approve,
            config.effective_workdir,
        )

        self._last_chunk: LLMChunk | None = None

    @property
    def auto_approve(self) -> bool:
        return self.tool_executor.auto_approve

    @auto_approve.setter
    def auto_approve(self, value: bool) -> None:
        self.tool_executor.auto_approve = value

    @property
    def messages(self) -> list[LLMMessage]:
        return self.message_manager.messages

    @messages.setter
    def messages(self, value: list[LLMMessage]) -> None:
        self.message_manager.messages = value

    def _select_backend(self) -> BackendLike:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)
        timeout = self.config.api_timeout
        return BACKEND_FACTORY[provider.backend](provider=provider, timeout=timeout)

    def add_message(self, message: LLMMessage) -> None:
        self.message_manager.add_message(message)

    def _flush_new_messages(self) -> None:
        self.message_manager.flush_new_messages()

    async def act(self, msg: str) -> AsyncGenerator[BaseEvent]:
        self._clean_message_history()
        async for event in self._conversation_loop(msg):
            yield event

    def _setup_middleware(self, max_turns: int | None, max_price: float | None) -> None:
        self.middleware_pipeline.clear()

        if max_turns is not None:
            self.middleware_pipeline.add(TurnLimitMiddleware(max_turns))

        if max_price is not None:
            self.middleware_pipeline.add(PriceLimitMiddleware(max_price))

        if self.config.auto_compact_threshold > 0:
            self.middleware_pipeline.add(
                AutoCompactMiddleware(self.config.auto_compact_threshold)
            )
            if self.config.context_warnings:
                self.middleware_pipeline.add(
                    ContextWarningMiddleware(0.5, self.config.auto_compact_threshold)
                )

    async def _handle_middleware_result(
        self, result: MiddlewareResult
    ) -> AsyncGenerator[BaseEvent]:
        match result.action:
            case MiddlewareAction.STOP:
                yield AssistantEvent(
                    content=f"<{VIBE_STOP_EVENT_TAG}>{result.reason}</{VIBE_STOP_EVENT_TAG}>",
                    prompt_tokens=0,
                    completion_tokens=0,
                    session_total_tokens=self.stats.session_total_llm_tokens,
                    last_turn_duration=0,
                    tokens_per_second=0,
                    stopped_by_middleware=True,
                )
                await self.interaction_logger.save_interaction(
                    self.messages, self.stats, self.config, self.tool_manager
                )

            case MiddlewareAction.INJECT_MESSAGE:
                if result.message and len(self.messages) > 0:
                    last_msg = self.messages[-1]
                    if last_msg.content:
                        last_msg.content += f"\n\n{result.message}"
                    else:
                        last_msg.content = result.message

            case MiddlewareAction.COMPACT:
                old_tokens = result.metadata.get(
                    "old_tokens", self.stats.context_tokens
                )
                threshold = result.metadata.get(
                    "threshold", self.config.auto_compact_threshold
                )

                yield CompactStartEvent(
                    current_context_tokens=old_tokens, threshold=threshold
                )

                summary = await self.compact()

                yield CompactEndEvent(
                    old_context_tokens=old_tokens,
                    new_context_tokens=self.stats.context_tokens,
                    summary_length=len(summary),
                )

            case MiddlewareAction.CONTINUE:
                pass

    def _get_context(self) -> ConversationContext:
        return ConversationContext(
            messages=self.messages, stats=self.stats, config=self.config
        )

    async def _conversation_loop(self, user_msg: str) -> AsyncGenerator[BaseEvent]:
        self.messages.append(LLMMessage(role=Role.user, content=user_msg))
        self.stats.steps += 1

        try:
            should_break_loop = False
            while not should_break_loop:
                result = await self.middleware_pipeline.run_before_turn(
                    self._get_context()
                )

                async for event in self._handle_middleware_result(result):
                    yield event

                if result.action == MiddlewareAction.STOP:
                    self._flush_new_messages()
                    return

                self.stats.steps += 1
                user_cancelled = False
                async for event in self._perform_llm_turn():
                    if is_user_cancellation_event(event):
                        user_cancelled = True
                    yield event

                last_message = self.messages[-1]
                should_break_loop = (
                    last_message.role != Role.tool
                    and self._last_chunk is not None
                    and self._last_chunk.finish_reason is not None
                )

                self._flush_new_messages()
                await self.interaction_logger.save_interaction(
                    self.messages, self.stats, self.config, self.tool_manager
                )

                if user_cancelled:
                    self._flush_new_messages()
                    await self.interaction_logger.save_interaction(
                        self.messages, self.stats, self.config, self.tool_manager
                    )
                    return

                after_result = await self.middleware_pipeline.run_after_turn(
                    self._get_context()
                )

                async for event in self._handle_middleware_result(after_result):
                    yield event

                if after_result.action == MiddlewareAction.STOP:
                    self._flush_new_messages()
                    return

                self._flush_new_messages()
                await self.interaction_logger.save_interaction(
                    self.messages, self.stats, self.config, self.tool_manager
                )

        except Exception:
            self._flush_new_messages()
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )
            raise

    async def _perform_llm_turn(
        self,
    ) -> AsyncGenerator[AssistantEvent | ToolCallEvent | ToolResultEvent]:
        if self.enable_streaming:
            async for event in self._stream_assistant_events():
                yield event
        else:
            assistant_event = await self._get_assistant_event()
            if assistant_event.content:
                yield assistant_event

        last_message = self.messages[-1]
        last_chunk = self._last_chunk
        if last_chunk is None or last_chunk.usage is None:
            raise LLMResponseError("LLM response missing chunk or usage data")

        parsed = self.format_handler.parse_message(last_message)
        resolved = self.format_handler.resolve_tool_calls(
            parsed, self.tool_manager, self.config
        )

        if last_chunk.usage.completion_tokens > 0 and self.stats.last_turn_duration > 0:
            self.stats.tokens_per_second = (
                last_chunk.usage.completion_tokens / self.stats.last_turn_duration
            )

        if not resolved.tool_calls and not resolved.failed_calls:
            return

        async for event in self._handle_tool_calls(resolved):
            yield event

    def _create_assistant_event(
        self, content: str, chunk: LLMChunk | None
    ) -> AssistantEvent:
        return AssistantEvent(
            content=content,
            prompt_tokens=chunk.usage.prompt_tokens if chunk and chunk.usage else 0,
            completion_tokens=chunk.usage.completion_tokens
            if chunk and chunk.usage
            else 0,
            session_total_tokens=self.stats.session_total_llm_tokens,
            last_turn_duration=self.stats.last_turn_duration,
            tokens_per_second=self.stats.tokens_per_second,
        )

    async def _stream_assistant_events(self) -> AsyncGenerator[AssistantEvent]:
        chunks: list[LLMChunk] = []
        content_buffer = ""
        chunks_with_content = 0
        BATCH_SIZE = 5

        async for chunk in self._chat_streaming():
            chunks.append(chunk)

            if chunk.message.tool_calls and chunk.finish_reason is None:
                if chunk.message.content:
                    content_buffer += chunk.message.content
                    chunks_with_content += 1

                if content_buffer:
                    yield self._create_assistant_event(content_buffer, chunk)
                    content_buffer = ""
                    chunks_with_content = 0
                continue

            if chunk.message.content:
                content_buffer += chunk.message.content
                chunks_with_content += 1

                if chunks_with_content >= BATCH_SIZE:
                    yield self._create_assistant_event(content_buffer, chunk)
                    content_buffer = ""
                    chunks_with_content = 0

        if content_buffer:
            last_chunk = chunks[-1] if chunks else None
            yield self._create_assistant_event(content_buffer, last_chunk)

        full_content = ""
        full_tool_calls_map = OrderedDict[int, ToolCall]()
        for chunk in chunks:
            full_content += chunk.message.content or ""
            if not chunk.message.tool_calls:
                continue

            for tc in chunk.message.tool_calls:
                if tc.index is None:
                    raise LLMResponseError("Tool call chunk missing index")
                if tc.index not in full_tool_calls_map:
                    full_tool_calls_map[tc.index] = tc
                else:
                    new_args_str = (
                        full_tool_calls_map[tc.index].function.arguments or ""
                    ) + (tc.function.arguments or "")
                    full_tool_calls_map[tc.index].function.arguments = new_args_str

        full_tool_calls = list(full_tool_calls_map.values()) or None
        last_message = LLMMessage(
            role=Role.assistant, content=full_content, tool_calls=full_tool_calls
        )
        self.messages.append(last_message)
        finish_reason = next(
            (c.finish_reason for c in chunks if c.finish_reason is not None), None
        )
        self._last_chunk = LLMChunk(
            message=last_message, usage=chunks[-1].usage, finish_reason=finish_reason
        )

    def _create_assistant_event(
        self, content: str, chunk: LLMChunk | None
    ) -> AssistantEvent:
        return AssistantEvent(
            content=content,
            prompt_tokens=chunk.usage.prompt_tokens if chunk and chunk.usage else 0,
            completion_tokens=chunk.usage.completion_tokens
            if chunk and chunk.usage
            else 0,
            session_total_tokens=self.stats.session_total_llm_tokens,
            last_turn_duration=self.stats.last_turn_duration,
            tokens_per_second=self.stats.tokens_per_second,
        )

    async def _handle_tool_calls(
        self, resolved: ResolvedMessage
    ) -> AsyncGenerator[ToolCallEvent | ToolResultEvent]:
        async for event in self.tool_executor.handle_tool_calls(
            resolved, self.messages, self.stats, self.interaction_logger
        ):
            yield event

    async def _get_assistant_event(self) -> AssistantEvent:
        result = await self._chat()
        self.add_message(result.message)
        self._last_chunk = result
        return self._create_assistant_event(result.message.content or "", result)

    async def _chat(self, max_tokens: int | None = None) -> LLMChunk:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)

        # Before middleware
        for middleware in self.middleware_pipeline.middlewares:
            before_result = await middleware.before_chat_completion(
                self.messages, self.tool_manager, self.config
            )
            if before_result.action == MiddlewareAction.STOP:
                return LLMChunk(
                    message=LLMMessage(
                        role=Role.assistant, content=before_result.message
                    ),
                    finish_reason="stop",
                    usage=LLMUsage(prompt_tokens=0, completion_tokens=0),
                )

        try:
            start_time = time.perf_counter()
            available_tools = self.format_handler.get_available_tools(
                self.tool_manager, self.config
            )
            tool_choice = self.format_handler.get_tool_choice()

            async with self.backend as backend:
                result = await backend.complete(
                    model=active_model,
                    messages=self.messages,
                    temperature=active_model.temperature,
                    tools=available_tools,
                    tool_choice=tool_choice,
                    extra_headers={
                        "User-Agent": get_user_agent(),
                        "x-affinity": self.session_id,
                    },
                    max_tokens=max_tokens,
                )

            end_time = time.perf_counter()

            self.stats.last_turn_duration = end_time - start_time
            self.stats.last_turn_prompt_tokens = result.usage.prompt_tokens
            self.stats.last_turn_completion_tokens = result.usage.completion_tokens
            self.stats.session_prompt_tokens += result.usage.prompt_tokens
            self.stats.session_completion_tokens += result.usage.completion_tokens
            self.stats.context_tokens = (
                result.usage.prompt_tokens + result.usage.completion_tokens
            )

            return result

        except Exception as e:
            raise RuntimeError(
                f"API error from {provider.name} (model: {active_model.name}): {e}"
            ) from e

    async def _chat_streaming(
        self, max_tokens: int | None = None
    ) -> AsyncGenerator[LLMChunk]:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)

        available_tools = self.format_handler.get_available_tools(
            self.tool_manager, self.config
        )
        tool_choice = self.format_handler.get_tool_choice()
        try:
            start_time = time.perf_counter()
            last_chunk = None
            async with self.backend as backend:
                async for chunk in backend.complete_streaming(
                    model=active_model,
                    messages=self.messages,
                    temperature=active_model.temperature,
                    tools=available_tools,
                    tool_choice=tool_choice,
                    extra_headers={
                        "User-Agent": get_user_agent(),
                        "x-affinity": self.session_id,
                    },
                    max_tokens=max_tokens,
                ):
                    last_chunk = chunk
                    processed_message = (
                        self.format_handler.process_api_response_message(chunk.message)
                    )
                    yield LLMChunk(
                        message=processed_message,
                        usage=chunk.usage,
                        finish_reason=chunk.finish_reason,
                    )

            end_time = time.perf_counter()
            if last_chunk is None:
                raise LLMResponseError("Streamed completion returned no chunks")
            if last_chunk.usage is None:
                raise LLMResponseError(
                    "Usage data missing in final chunk of streamed completion"
                )

            self.stats.last_turn_duration = end_time - start_time
            self.stats.last_turn_prompt_tokens = last_chunk.usage.prompt_tokens
            self.stats.last_turn_completion_tokens = last_chunk.usage.completion_tokens
            self.stats.session_prompt_tokens += last_chunk.usage.prompt_tokens
            self.stats.session_completion_tokens += last_chunk.usage.completion_tokens
            self.stats.context_tokens = (
                last_chunk.usage.prompt_tokens + last_chunk.usage.completion_tokens
            )

        except Exception as e:
            raise RuntimeError(
                f"API error from {provider.name} (model: {active_model.name}): {e}"
            ) from e

    def _clean_message_history(self) -> None:
        self.message_manager.clean_history()

    def _reset_session(self) -> None:
        self.session_id = str(uuid4())
        self.interaction_logger.reset_session(self.session_id)

    def set_approval_callback(self, callback: ApprovalCallback) -> None:
        self.tool_executor.set_approval_callback(callback)

    async def clear_history(self) -> None:
        await self.interaction_logger.save_interaction(
            self.messages, self.stats, self.config, self.tool_manager
        )
        self.messages = self.messages[:1]

        self.stats = AgentStats()

        try:
            active_model = self.config.get_active_model()
            self.stats.update_pricing(
                active_model.input_price, active_model.output_price
            )
        except ValueError:
            pass

        self.middleware_pipeline.reset()
        self.tool_manager.reset_all()
        self._reset_session()

    async def compact(self) -> str:
        try:
            self._clean_message_history()
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )

            last_user_message = None
            for msg in reversed(self.messages):
                if msg.role == Role.user:
                    last_user_message = msg.content
                    break

            summary_request = UtilityPrompt.COMPACT.read()
            self.messages.append(LLMMessage(role=Role.user, content=summary_request))
            self.stats.steps += 1

            summary_result = await self._chat()
            if summary_result.usage is None:
                raise LLMResponseError(
                    "Usage data missing in compaction summary response"
                )
            summary_content = summary_result.message.content or ""

            if last_user_message:
                summary_content += (
                    f"\n\nLast request from user was: {last_user_message}"
                )

            system_message = self.messages[0]
            summary_message = LLMMessage(role=Role.user, content=summary_content)
            self.messages = [system_message, summary_message]

            active_model = self.config.get_active_model()

            async with self.backend as backend:
                actual_context_tokens = await backend.count_tokens(
                    model=active_model,
                    messages=self.messages,
                    tools=self.format_handler.get_available_tools(
                        self.tool_manager, self.config
                    ),
                    extra_headers={"User-Agent": get_user_agent()},
                )

            self.stats.context_tokens = actual_context_tokens

            self._reset_session()
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )

            self.middleware_pipeline.reset(reset_reason=ResetReason.COMPACT)

            return summary_content or ""

        except Exception:
            await self.interaction_logger.save_interaction(
                self.messages, self.stats, self.config, self.tool_manager
            )
            raise

    async def reload_with_initial_messages(
        self,
        config: VibeConfig | None = None,
        max_turns: int | None = None,
        max_price: float | None = None,
    ) -> None:
        await self.interaction_logger.save_interaction(
            self.messages, self.stats, self.config, self.tool_manager
        )

        preserved_messages = self.messages[1:] if len(self.messages) > 1 else []
        old_system_prompt = self.messages[0].content if len(self.messages) > 0 else ""

        if config is not None:
            self.config = config
            self.backend = self.backend_factory()

        self.tool_manager = ToolManager(self.config)

        new_system_prompt = get_universal_system_prompt(self.tool_manager, self.config)
        self.messages = [LLMMessage(role=Role.system, content=new_system_prompt)]
        did_system_prompt_change = old_system_prompt != new_system_prompt

        if preserved_messages:
            self.messages.extend(preserved_messages)

        if len(self.messages) == 1 or did_system_prompt_change:
            self.stats.reset_context_state()

        try:
            active_model = self.config.get_active_model()
            self.stats.update_pricing(
                active_model.input_price, active_model.output_price
            )
        except ValueError:
            pass

        self._last_observed_message_index = 0

        self._setup_middleware(max_turns, max_price)

        if self.message_observer:
            for msg in self.messages:
                self.message_observer(msg)
            self._last_observed_message_index = len(self.messages)

        self.tool_manager.reset_all()

        await self.interaction_logger.save_interaction(
            self.messages, self.stats, self.config, self.tool_manager
        )
