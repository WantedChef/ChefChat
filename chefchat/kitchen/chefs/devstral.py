"""Devstral Chef Implementation (Mistral AI).

Specific implementation of ChefBrain for Mistral AI models (Devstral).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from chefchat.kitchen.core import ChefBrain
from chefchat.core.tools.utils_mistral import tool_to_mistral_format

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class DevstralChef(ChefBrain):
    """Chef implementation using Mistral AI (Devstral)."""

    def __init__(self) -> None:
        """Initialize the Devstral Chef."""
        self._client: Any = None
        self._model: str = "mistral-large-latest"
        self._api_key: str | None = None

    def connect(self, api_key: str | None = None) -> bool:
        """Connect to Mistral API."""
        self._api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self._api_key:
            return False

        try:
            from mistralai import Mistral

            self._client = Mistral(api_key=self._api_key)
            return True
        except ImportError:
            # gracefully handle missing package
            return False
        except Exception:
            return False

    async def cook_recipe(
        self, ingredients: dict[str, Any], preferences: dict[str, Any] | None = None
    ) -> str | AsyncIterator[str] | Any:
        """Cook (generate) using Mistral."""
        if not self._client:
            if not self.connect():
                raise RuntimeError(
                    "DevstralChef not connected (missing API key or package)."
                )

        prefs = preferences or {}
        model = prefs.get("model", self._model)
        temperature = prefs.get("temperature", 0.7)
        stream = prefs.get("stream", False)

        tools = ingredients.get("tools")
        mistral_tools = None
        if tools:
            mistral_tools = [tool_to_mistral_format(t) for t in tools]
            # Disable streaming when using tools to simplify handling
            stream = False

        messages = ingredients.get("messages")
        if not messages:
            prompt = ingredients.get("prompt", "")
            system = ingredients.get("system")
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

        if stream:
            return self._stream_response(model, messages, temperature)
        else:
            return await self._generate_response(model, messages, temperature, mistral_tools)

    async def chat(
        self, user_input: str, history: list[dict[str, str]]
    ) -> str | AsyncIterator[str] | Any:
        """Chat using Mistral."""
        # Chat is just a specific recipe
        ingredients = {"messages": history + [{"role": "user", "content": user_input}]}
        # Default chat preferences
        preferences = {"stream": True}
        return await self.cook_recipe(ingredients, preferences)

    async def _generate_response(
        self, model: str, messages: list[dict], temperature: float, tools: list[dict] | None = None
    ) -> Any:
        """Internal generation helper."""
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.complete_async(**kwargs)

        # If tools were used and tool calls exist, return the full message
        if tools and response.choices[0].message.tool_calls:
            return response.choices[0].message

        return response.choices[0].message.content or ""

    async def _stream_response(
        self, model: str, messages: list[dict], temperature: float
    ) -> AsyncIterator[str]:
        """Internal streaming helper."""
        stream = await self._client.chat.stream_async(
            model=model, messages=messages, temperature=temperature
        )
        async for chunk in stream:
            if chunk.data.choices[0].delta.content:
                yield chunk.data.choices[0].delta.content
