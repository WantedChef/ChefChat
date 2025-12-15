from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
import json
import os
import types
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol, TypeVar

import httpx

from chefchat.core.llm.exceptions import BackendErrorBuilder
from chefchat.core.types import (
    AvailableTool,
    LLMChunk,
    LLMMessage,
    LLMUsage,
    Role,
    StrToolChoice,
)
from chefchat.core.utils import async_generator_retry, async_retry
from chefchat.utils.tokenizer import count_tokens

if TYPE_CHECKING:
    from chefchat.core.config import ModelConfig, ProviderConfig


class PreparedRequest(NamedTuple):
    endpoint: str
    headers: dict[str, str]
    body: bytes


class APIAdapter(Protocol):
    endpoint: ClassVar[str]

    def prepare_request(
        self,
        *,
        model_name: str,
        messages: list[LLMMessage],
        temperature: float,
        tools: list[AvailableTool] | None,
        max_tokens: int | None,
        tool_choice: StrToolChoice | AvailableTool | None,
        enable_streaming: bool,
        provider: ProviderConfig,
        api_key: str | None = None,
    ) -> PreparedRequest: ...

    def parse_response(self, data: dict[str, Any]) -> LLMChunk: ...


BACKEND_ADAPTERS: dict[str, APIAdapter] = {}

T = TypeVar("T", bound=APIAdapter)


def register_adapter(
    adapters: dict[str, APIAdapter], name: str
) -> Callable[[type[T]], type[T]]:
    def decorator(cls: type[T]) -> type[T]:
        adapters[name] = cls()
        return cls

    return decorator


@register_adapter(BACKEND_ADAPTERS, "openai")
class OpenAIAdapter(APIAdapter):
    endpoint: ClassVar[str] = "/chat/completions"

    def _map_role(self, role: str) -> str:
        # OpenAI uses the same role strings as our internal enum
        return role

    def _map_role_reverse(self, role: str | None) -> str:
        # OpenAI uses the same role strings as our internal enum
        if not role:
            return "assistant"
        return role

    def build_payload(
        self,
        model_name: str,
        converted_messages: list[dict[str, Any]],
        temperature: float,
        tools: list[AvailableTool] | None,
        max_tokens: int | None,
        tool_choice: StrToolChoice | AvailableTool | None,
    ) -> dict[str, Any]:
        payload = {
            "model": model_name,
            "messages": [
                {**msg, "role": self._map_role(msg["role"])}
                for msg in converted_messages
            ],
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = [tool.model_dump(exclude_none=True) for tool in tools]
        if tool_choice:
            payload["tool_choice"] = (
                tool_choice
                if isinstance(tool_choice, str)
                else tool_choice.model_dump()
            )
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        return payload

    def build_headers(self, api_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Groq-specific optimizations
        if self._provider.name == "groq":
            headers["User-Agent"] = "ChefChat/1.0"
            headers["X-Request-Source"] = "chefchat"

        return headers

    def prepare_request(
        self,
        *,
        model_name: str,
        messages: list[LLMMessage],
        temperature: float,
        tools: list[AvailableTool] | None,
        max_tokens: int | None,
        tool_choice: StrToolChoice | AvailableTool | None,
        enable_streaming: bool,
        provider: ProviderConfig,
        api_key: str | None = None,
    ) -> PreparedRequest:
        converted_messages = [msg.model_dump(exclude_none=True) for msg in messages]

        payload = self.build_payload(
            model_name, converted_messages, temperature, tools, max_tokens, tool_choice
        )

        if enable_streaming:
            payload["stream"] = True
            if provider.name == "mistral":
                payload["stream_options"] = {"stream_tool_calls": True}

        # Groq-specific model adjustments
        if provider.name == "groq":
            payload = self._adjust_for_groq_model(payload, model_name)

        headers = self.build_headers(api_key)

        body = json.dumps(payload).encode("utf-8")

        return PreparedRequest(self.endpoint, headers, body)

    def parse_response(self, data: dict[str, Any]) -> LLMChunk:
        if data.get("choices"):
            choice = data["choices"][0]
            if "message" in choice:
                role = self._map_role_reverse(choice["message"].get("role"))
                message = LLMMessage.model_validate({**choice["message"], "role": role})
            elif "delta" in choice:
                role = self._map_role_reverse(choice["delta"].get("role"))
                message = LLMMessage.model_validate({**choice["delta"], "role": role})
            else:
                raise ValueError("Invalid response data")
            finish_reason = choice.get("finish_reason")

        elif "message" in data:
            role = self._map_role_reverse(data["message"].get("role"))
            message = LLMMessage.model_validate({**data["message"], "role": role})
            finish_reason = data.get("finish_reason")
        elif "delta" in data:
            role = self._map_role_reverse(data["delta"].get("role"))
            message = LLMMessage.model_validate({**data["delta"], "role": role})
            finish_reason = None
        else:
            message = LLMMessage(role=Role.assistant, content="")
            finish_reason = None

        usage_data = data.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
        )

        return LLMChunk(message=message, usage=usage, finish_reason=finish_reason)


class GenericBackend:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        provider: ProviderConfig,
        timeout: float = 720.0,
    ) -> None:
        """Initialize the backend.

        Args:
            client: Optional httpx client to use. If not provided, one will be created.
        """
        self._client = client
        self._owns_client = client is None
        self._provider = provider
        self._timeout = timeout

    async def __aenter__(self) -> GenericBackend:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
            self._owns_client = True
        return self._client

    async def complete(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        tools: list[AvailableTool] | None = None,
        max_tokens: int | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LLMChunk:
        api_key = (
            os.getenv(self._provider.api_key_env_var)
            if self._provider.api_key_env_var
            else None
        )

        api_style = getattr(self._provider, "api_style", "openai")
        adapter = BACKEND_ADAPTERS[api_style]

        endpoint, headers, body = adapter.prepare_request(
            model_name=model.name,
            messages=messages,
            temperature=temperature,
            tools=tools,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            enable_streaming=False,
            provider=self._provider,
            api_key=api_key,
        )

        if extra_headers:
            headers.update(extra_headers)

        url = f"{self._provider.api_base}{endpoint}"

        try:
            res_data, _ = await self._make_request(url, body, headers)
            return adapter.parse_response(res_data)

        except httpx.HTTPStatusError as e:
            raise BackendErrorBuilder.build_http_error(
                provider=self._provider.name,
                endpoint=url,
                response=e.response,
                headers=dict(e.response.headers.items()),
                model=model.name,
                messages=messages,
                temperature=temperature,
                has_tools=bool(tools),
                tool_choice=tool_choice,
            ) from e
        except httpx.RequestError as e:
            raise BackendErrorBuilder.build_request_error(
                provider=self._provider.name,
                endpoint=url,
                error=e,
                model=model.name,
                messages=messages,
                temperature=temperature,
                has_tools=bool(tools),
                tool_choice=tool_choice,
            ) from e

    async def complete_streaming(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        tools: list[AvailableTool] | None = None,
        max_tokens: int | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        api_key = (
            os.getenv(self._provider.api_key_env_var)
            if self._provider.api_key_env_var
            else None
        )

        api_style = getattr(self._provider, "api_style", "openai")
        adapter = BACKEND_ADAPTERS[api_style]

        endpoint, headers, body = adapter.prepare_request(
            model_name=model.name,
            messages=messages,
            temperature=temperature,
            tools=tools,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            enable_streaming=True,
            provider=self._provider,
            api_key=api_key,
        )

        if extra_headers:
            headers.update(extra_headers)

        url = f"{self._provider.api_base}{endpoint}"

        try:
            async for res_data in self._make_streaming_request(url, body, headers):
                yield adapter.parse_response(res_data)

        except httpx.HTTPStatusError as e:
            raise BackendErrorBuilder.build_http_error(
                provider=self._provider.name,
                endpoint=url,
                response=e.response,
                headers=dict(e.response.headers.items()),
                model=model.name,
                messages=messages,
                temperature=temperature,
                has_tools=bool(tools),
                tool_choice=tool_choice,
            ) from e
        except httpx.RequestError as e:
            raise BackendErrorBuilder.build_request_error(
                provider=self._provider.name,
                endpoint=url,
                error=e,
                model=model.name,
                messages=messages,
                temperature=temperature,
                has_tools=bool(tools),
                tool_choice=tool_choice,
            ) from e

    class HTTPResponse(NamedTuple):
        data: dict[str, Any]
        headers: dict[str, str]

    @async_retry(tries=3)
    async def _make_request(
        self, url: str, data: bytes, headers: dict[str, str]
    ) -> HTTPResponse:
        client = self._get_client()
        response = await client.post(url, content=data, headers=headers)
        response.raise_for_status()

        response_headers = dict(response.headers.items())
        response_body = response.json()
        return self.HTTPResponse(response_body, response_headers)

    @async_generator_retry(tries=3)
    async def _make_streaming_request(
        self, url: str, data: bytes, headers: dict[str, str]
    ) -> AsyncGenerator[dict[str, Any]]:
        client = self._get_client()
        async with client.stream(
            method="POST", url=url, content=data, headers=headers
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip() == "":
                    continue

                DELIM_CHAR = ":"
                DELIM_CHAR = ":"
                delim_index = line.find(DELIM_CHAR)

                if delim_index == -1:
                    # Malformed line, skip it
                    continue

                key = line[0:delim_index]

                # Robustly extract value, handling optional space after colon
                remainder = line[delim_index + 1 :]
                if remainder.startswith(" "):
                    value = remainder[1:]
                else:
                    value = remainder

                if key != "data":
                    # This might be the case with openrouter, so we just ignore it
                    continue
                if value == "[DONE]":
                    return
                try:
                    yield json.loads(value.strip())
                except json.JSONDecodeError:
                    # Skip malformed JSON lines
                    continue

    async def count_tokens(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        tools: list[AvailableTool] | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> int:
        # Use local tokenizer to estimate tokens
        # This is much faster and cheaper than an API call
        # It handles both tiktoken (precise for OpenAI) and heuristic (fallback)

        # Simple approximation of chat formatting:
        # Sum of content tokens + constant overhead per message
        total = 0
        for msg in messages:
            total += count_tokens(msg.content or "", model.name)
            total += 4  # Approximate overhead per message (role, structure)

        if tools:
            # Rough estimate for tools definition
            for tool in tools:
                # Estimate based on function definition
                # Very rough: 1 token per 4 chars of json dump
                total += count_tokens(json.dumps(tool.model_dump()), model.name)

        return total

    async def list_models(self, *, extra_headers: dict[str, str] | None = None) -> list[str]:
        """Fetch available models from the provider's API."""
        api_key = (
            os.getenv(self._provider.api_key_env_var)
            if self._provider.api_key_env_var
            else None
        )

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Groq-specific headers
        if self._provider.name == "groq":
            headers["User-Agent"] = "ChefChat/1.0"
            headers["X-Request-Source"] = "chefchat"

        if extra_headers:
            headers.update(extra_headers)

        url = f"{self._provider.api_base}/models"

        try:
            client = self._get_client()
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Extract model IDs from response
            models = []
            if "data" in data:
                # OpenAI-style response
                for model in data["data"]:
                    if "id" in model:
                        models.append(model["id"])
            elif isinstance(data, list):
                # Some APIs return list directly
                models = data

            return models

        except httpx.HTTPStatusError as e:
            # If models endpoint not supported, return empty list
            if e.response.status_code == 404:
                return []
            raise BackendErrorBuilder.build_http_error(
                provider=self._provider.name,
                endpoint=url,
                response=e.response,
                headers=dict(e.response.headers.items()),
                model="N/A",
                messages=[],
                temperature=0.0,
                has_tools=False,
                tool_choice=None,
            ) from e
        except httpx.RequestError as e:
            raise BackendErrorBuilder.build_request_error(
                provider=self._provider.name,
                endpoint=url,
                error=e,
                model="N/A",
                messages=[],
                temperature=0.0,
                has_tools=False,
                tool_choice=None,
            ) from e

    def _adjust_for_groq_model(
        self, payload: dict[str, Any], model_name: str
    ) -> dict[str, Any]:
        """Adjust request parameters for specific Groq models."""
        if "llama-4-scout" in model_name or "llama-4-maverick" in model_name:
            # Enable multimodal for Llama 4 models
            if any("image" in str(msg) for msg in payload.get("messages", [])):
                payload["modalities"] = ["text", "image"]

        elif "kimi-k2" in model_name:
            # Kimi K2 specific optimizations
            payload["max_tokens"] = min(payload.get("max_tokens", 8192), 16384)

        elif "gpt-oss" in model_name:
            # Enable browser tools for GPT-OSS models
            if not payload.get("tools"):
                payload["tools"] = self._get_groq_browser_tools()

        return payload

    def _get_groq_browser_tools(self) -> list[dict[str, Any]]:
        """Get Groq browser tools for compatible models."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "code_execution",
                    "description": "Execute Python code",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python code to execute",
                            }
                        },
                        "required": ["code"],
                    },
                },
            },
        ]

    async def close(self) -> None:
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None
