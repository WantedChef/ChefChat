from __future__ import annotations

from collections import OrderedDict
from collections.abc import AsyncGenerator
import json
import logging
import os
import time
from typing import TYPE_CHECKING

from chefchat.core.agent import LLMResponseError
from chefchat.core.config import DEFAULT_MAX_TOKENS, VibeConfig
from chefchat.core.llm.backend.factory import get_backend_cls
from chefchat.core.llm.format import (
    APIToolFormatHandler,
    guard_tool_schema_size,
    normalize_tool_choice,
    sanitize_message,
)
from chefchat.core.llm.types import BackendLike
from chefchat.core.middleware import MiddlewarePipeline
from chefchat.core.types import (
    AgentStats,
    AssistantEvent,
    LLMChunk,
    LLMMessage,
    Role,
    ToolCall,
)
from chefchat.core.utils import get_user_agent

if TYPE_CHECKING:
    from chefchat.core.tools.manager import ToolManager


logger = logging.getLogger(__name__)


class LLMClient:
    """Handles direct interactions with the LLM backend."""

    def __init__(
        self,
        config: VibeConfig,
        stats: AgentStats,
        session_id: str,
        tool_manager: ToolManager,
        format_handler: APIToolFormatHandler,
        middleware_pipeline: MiddlewarePipeline,
        backend: BackendLike | None = None,
    ) -> None:
        self.config = config
        self.stats = stats
        self.session_id = session_id
        self.tool_manager = tool_manager
        self.format_handler = format_handler
        self.middleware_pipeline = middleware_pipeline

        self.backend_factory = lambda: backend or self._select_backend()
        self.backend = self.backend_factory()

        # Last chunk stored for internal state tracking if needed by Agent (Agent seemingly accesses it)
        # But Agent accesses it via `self._last_chunk`. We should probably expose it or return it.
        self.last_chunk: LLMChunk | None = None

    def _select_backend(self) -> BackendLike:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)
        backend_cls = get_backend_cls(provider.backend)
        return backend_cls(provider=provider, timeout=self.config.api_timeout)

    def reload(self, config: VibeConfig) -> None:
        """Reload client with new configuration."""
        self.config = config
        self.backend = self.backend_factory()

    def create_assistant_event(
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

    def _load_mock_chunks_from_env(self) -> list[LLMChunk] | None:
        """Load mock LLM chunks from the test harness.

        Tests can set VIBE_MOCK_LLM_DATA to a JSON list of LLMChunk-like dicts.
        When present, we bypass network calls entirely.
        """
        if (raw := os.environ.get("VIBE_MOCK_LLM_DATA")) is None:
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, list):
            return None

        chunks: list[LLMChunk] = []
        for item in data:
            if isinstance(item, dict):
                try:
                    chunks.append(LLMChunk.model_validate(item))
                except Exception:
                    continue
        return chunks or None

    @staticmethod
    def _validate_message_sequence(messages: list[LLMMessage]) -> None:
        """Ensure the final message is a valid role for starting a turn."""
        if not messages:
            msg = "Conversation history is empty; cannot query the model."
            raise RuntimeError(msg)

        if messages[-1].role not in {Role.user, Role.tool}:
            role_name = messages[-1].role.value if messages[-1].role else "unknown"
            msg = (
                "Conversation desynchronised (last message role is "
                f"'{role_name}'). Run /clear and try again."
            )
            raise RuntimeError(msg)

    def _apply_usage_from_chunk(self, chunk: LLMChunk) -> None:
        usage = chunk.usage
        if usage is None:
            return

        self.stats.last_turn_prompt_tokens = usage.prompt_tokens
        self.stats.last_turn_completion_tokens = usage.completion_tokens
        self.stats.session_prompt_tokens += usage.prompt_tokens
        self.stats.session_completion_tokens += usage.completion_tokens
        self.stats.context_tokens = usage.prompt_tokens + usage.completion_tokens

    def _extra_headers_for_provider(self) -> dict[str, str]:
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)
        headers: dict[str, str] = {}
        match provider.name:
            case "groq":
                headers["X-Request-Source"] = "chefchat"
            case _:
                pass
        return headers

    async def chat(
        self, messages: list[LLMMessage], max_tokens: int | None = None
    ) -> LLMChunk:
        self._validate_message_sequence(messages)
        messages = [sanitize_message(m) for m in messages]
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)

        if provider.api_key_env_var and not os.getenv(provider.api_key_env_var):
            raise RuntimeError(
                f"Missing API key for provider '{provider.name}'. "
                f"Set {provider.api_key_env_var} or configure via /api."
            )
        if not provider.api_base:
            raise RuntimeError(f"Provider '{provider.name}' has no api_base configured.")

        if (mock_chunks := self._load_mock_chunks_from_env()) is not None:
            # Deterministic test harness: return the last chunk as the final answer.
            self.stats.last_turn_duration = 0.0
            self.last_chunk = mock_chunks[-1]
            self._apply_usage_from_chunk(self.last_chunk)
            return self.last_chunk

        try:
            start_time = time.perf_counter()
            available_tools = self.format_handler.get_available_tools(
                self.tool_manager, self.config
            )
            guard_tool_schema_size(available_tools)
            tool_choice = normalize_tool_choice(self.format_handler.get_tool_choice())

            target_max_tokens = min(
                max_tokens or active_model.max_tokens or DEFAULT_MAX_TOKENS,
                active_model.max_tokens or DEFAULT_MAX_TOKENS,
            )

            async with self.backend as backend:
                result = await backend.complete(
                    model=active_model,
                    messages=messages,
                    temperature=active_model.temperature,
                    tools=available_tools,
                    tool_choice=tool_choice,
                    extra_headers={
                        "User-Agent": get_user_agent(),
                        "x-affinity": self.session_id,
                        **self._extra_headers_for_provider(),
                    },
                    max_tokens=target_max_tokens,
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

            self.last_chunk = result
            return result

        except Exception as e:
            from chefchat.core.llm.exceptions import BackendError

            if isinstance(e, BackendError):
                logger.error(
                    "LLM backend error (%s): %s\n%s",
                    provider.name,
                    e.parsed_error or e.reason or "N/A",
                    e.body_text[:2000] if e.body_text else "",
                )

                if e.is_context_too_long():
                    error_msg = f"""**Prompt Too Long Error**

The system prompt exceeded the model's token limit.

**Details:**
- Model: {e.model}
- Approximate size: {e.payload_summary.approx_chars:,} characters
- Provider message: {e.parsed_error or "N/A"}

**Recovery Options:**
1. **Switch to YOLO mode** (🚀) - Uses minimal prompts
2. **Clear conversation** with `/clear`
3. **Reduce project context** in configuration
4. **Use a model with larger context window**

Press `Shift+Tab` to cycle modes or type `/modes` for options.
"""
                    raise RuntimeError(error_msg) from e

                # For other BackendError cases, surface the provider's message.
                detail = e.parsed_error or e.reason or "N/A"
                raise RuntimeError(
                    f"API error from {provider.name} (model: {active_model.name}): {detail}"
                ) from e

            # Non-backend streaming issues: fall back to non-streaming completion.
            raise RuntimeError(
                f"API error from {provider.name} (model: {active_model.name}): {e}"
            ) from e

    async def list_models(self) -> list[str]:
        """List available models from the current backend's provider."""
        try:
            async with self.backend as backend:
                return await backend.list_models(
                    extra_headers=self._extra_headers_for_provider()
                )
        except Exception:
            # If listing fails, return empty list
            return []

    async def _chat_streaming(
        self, messages: list[LLMMessage], max_tokens: int | None = None
    ) -> AsyncGenerator[LLMChunk]:
        self._validate_message_sequence(messages)
        messages = [sanitize_message(m) for m in messages]
        active_model = self.config.get_active_model()
        provider = self.config.get_provider_for_model(active_model)

        if (mock_chunks := self._load_mock_chunks_from_env()) is not None:
            # Deterministic test harness: yield provided chunks and update stats.
            self.stats.last_turn_duration = 0.0
            for chunk in mock_chunks:
                yield chunk
                self.last_chunk = chunk
            if self.last_chunk is not None:
                self._apply_usage_from_chunk(self.last_chunk)
            return

        available_tools = self.format_handler.get_available_tools(
            self.tool_manager, self.config
        )
        guard_tool_schema_size(available_tools)
        tool_choice = normalize_tool_choice(self.format_handler.get_tool_choice())
        try:
            start_time = time.perf_counter()
            last_chunk = None
            async with self.backend as backend:
                async for chunk in backend.complete_streaming(
                    model=active_model,
                    messages=messages,
                    temperature=active_model.temperature,
                    tools=available_tools,
                    tool_choice=tool_choice,
                    extra_headers={
                        "User-Agent": get_user_agent(),
                        "x-affinity": self.session_id,
                        **self._extra_headers_for_provider(),
                    },
                    max_tokens=min(
                        max_tokens or active_model.max_tokens or DEFAULT_MAX_TOKENS,
                        active_model.max_tokens or DEFAULT_MAX_TOKENS,
                    ),
                ):
                    yield chunk
                    last_chunk = chunk

            end_time = time.perf_counter()
            self.stats.last_turn_duration = end_time - start_time
            if last_chunk is None or last_chunk.usage is None:
                # Should probably warn, but for now rely on backend
                pass
            else:
                self.stats.last_turn_prompt_tokens = last_chunk.usage.prompt_tokens
                self.stats.last_turn_completion_tokens = (
                    last_chunk.usage.completion_tokens
                )
                self.stats.session_prompt_tokens += last_chunk.usage.prompt_tokens
                self.stats.session_completion_tokens += (
                    last_chunk.usage.completion_tokens
                )
                self.stats.context_tokens = (
                    last_chunk.usage.prompt_tokens + last_chunk.usage.completion_tokens
                )

        except Exception as e:
            # Check if this is a BackendError with context-too-long
            from chefchat.core.llm.exceptions import BackendError

            if isinstance(e, BackendError):
                logger.error(
                    "LLM backend streaming error (%s): %s\n%s",
                    provider.name,
                    e.parsed_error or e.reason or "N/A",
                    e.body_text[:2000] if e.body_text else "",
                )

            if isinstance(e, BackendError) and e.is_context_too_long():
                # Convert to user-friendly error with recovery hints
                error_msg = f"""**Prompt Too Long Error**

The system prompt exceeded the model's token limit.

**Details:**
- Model: {e.model}
- Approximate size: {e.payload_summary.approx_chars:,} characters
- Provider message: {e.parsed_error or "N/A"}

**Recovery Options:**
1. **Switch to YOLO mode** (🚀) - Uses minimal prompts
2. **Clear conversation** with `/clear`
3. **Reduce project context** in configuration
4. **Use a model with larger context window**

Press `Shift+Tab` to cycle modes or type `/modes` for options.
"""
                raise RuntimeError(error_msg) from e

            # For other errors, use the original error message
            if isinstance(e, BackendError):
                detail = e.parsed_error or e.reason or "N/A"
                raise RuntimeError(
                    f"API error from {provider.name} (model: {active_model.name}): {detail}"
                ) from e

            raise RuntimeError(
                f"API error from {provider.name} (model: {active_model.name}): {e}"
            ) from e

    def _process_chunk_content(
        self,
        chunk: LLMChunk,
        content_buffer: str,
        chunks_with_content: int,
        batch_size: int,
    ) -> tuple[str, int, AssistantEvent | None]:
        """Process a chunk's content and determine if an event should be yielded.

        Args:
            chunk: Current LLM chunk.
            content_buffer: Accumulated content buffer.
            chunks_with_content: Number of chunks with content.
            batch_size: Batch size for yielding events.

        Returns:
            Tuple of (new_buffer, new_count, event_or_none).
        """
        # Handle tool calls with content
        if chunk.message.tool_calls and chunk.finish_reason is None:
            if chunk.message.content:
                content_buffer += chunk.message.content
                chunks_with_content += 1

            if content_buffer:
                event = self.create_assistant_event(content_buffer, chunk)
                return "", 0, event
            return content_buffer, chunks_with_content, None

        # Handle regular content
        if chunk.message.content:
            content_buffer += chunk.message.content
            chunks_with_content += 1

            if chunks_with_content >= batch_size:
                event = self.create_assistant_event(content_buffer, chunk)
                return "", 0, event

        return content_buffer, chunks_with_content, None

    def _merge_tool_calls(
        self, chunks: list[LLMChunk]
    ) -> tuple[str, list[ToolCall] | None]:
        """Merge tool calls from all chunks into a complete set.

        Args:
            chunks: List of LLM chunks.

        Returns:
            Tuple of (full_content, merged_tool_calls).
        """
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
        return full_content, full_tool_calls

    async def stream_assistant_events(
        self, messages: list[LLMMessage]
    ) -> AsyncGenerator[AssistantEvent]:
        chunks: list[LLMChunk] = []
        content_buffer = ""
        chunks_with_content = 0
        BATCH_SIZE = 1 if self._load_mock_chunks_from_env() is not None else 5

        async for chunk in self._chat_streaming(messages):
            chunks.append(chunk)

            content_buffer, chunks_with_content, event = self._process_chunk_content(
                chunk, content_buffer, chunks_with_content, BATCH_SIZE
            )
            if event:
                yield event

        if content_buffer:
            last_chunk = chunks[-1] if chunks else None
            yield self.create_assistant_event(content_buffer, last_chunk)

        full_content, full_tool_calls = self._merge_tool_calls(chunks)
        last_message = LLMMessage(
            role=Role.assistant, content=full_content, tool_calls=full_tool_calls
        )
        # We don't append to self.messages here because this is LLMClient
        # The caller (Agent) is responsible for appending the final message to history

        finish_reason = next(
            (c.finish_reason for c in chunks if c.finish_reason is not None), None
        )
        self.last_chunk = LLMChunk(
            message=last_message, usage=chunks[-1].usage, finish_reason=finish_reason
        )
