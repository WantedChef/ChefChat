"""CLIProxy Chef Implementation."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chefchat.integrations.cliproxy.client import CLIProxyClient
from chefchat.kitchen.core import ChefBrain

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class CliproxyChef(ChefBrain):
    """Chef implementation using CLIProxyAPI."""

    def __init__(self) -> None:
        """Initialize the CLIProxy Chef."""
        self._client: CLIProxyClient | None = None
        self._model: str = "gpt-3.5-turbo"

    def connect(self, api_key: str | None = None) -> bool:
        """Connect to CLIProxy API."""
        try:
            self._client = CLIProxyClient(api_key=api_key)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to CLIProxy: {e}")
            return False

    async def cook_recipe(
        self, ingredients: dict[str, Any], preferences: dict[str, Any] | None = None
    ) -> str | AsyncIterator[str]:
        """Cook (generate) using CLIProxy."""
        if not self._client:
            if not self.connect():
                raise RuntimeError("CliproxyChef not connected.")

        prefs = preferences or {}
        model = prefs.get("model", self._model)
        temperature = prefs.get("temperature", 0.7)
        stream = prefs.get("stream", False)

        messages = ingredients.get("messages")
        if not messages:
            prompt = ingredients.get("prompt", "")
            system = ingredients.get("system")
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

        result = await self._client.chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=stream,
        )

        if stream:
            # result is AsyncIterator
            return result  # type: ignore
        else:
            # result is dict
            return result["choices"][0]["message"]["content"] or ""  # type: ignore

    async def chat(
        self, user_input: str, history: list[dict[str, str]]
    ) -> str | AsyncIterator[str]:
        """Chat using CLIProxy."""
        ingredients = {"messages": history + [{"role": "user", "content": user_input}]}
        preferences = {"stream": True}
        return await self.cook_recipe(ingredients, preferences)
