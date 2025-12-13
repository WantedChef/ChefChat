"""ChefChat Kitchen Core - Abstract Interface.

Defines the 'ChefBrain' contract that all specific model implementations
(Strategies) must adhere to.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class ChefBrain(ABC):
    """Abstract base class for AI Chefs (Strategies).

    Enforces the interface for connecting, cooking (generating), and chatting.
    """

    @abstractmethod
    def connect(self, api_key: str | None = None) -> bool:
        """Establish connection to the AI provider.

        Args:
            api_key: Optional API key. If not provided, should load from env.

        Returns:
            True if connected successfully, False otherwise.
        """

    @abstractmethod
    async def cook_recipe(
        self, ingredients: dict[str, Any], preferences: dict[str, Any] | None = None
    ) -> str | AsyncIterator[str]:
        """Execute a generation task (the "recipe").

        Args:
            ingredients: The input data (e.g., prompt, context, instructions).
                         Structure depends on the task (plan, code, etc.).
            preferences: Optional configuration (e.g., model parameters, system prompt).

        Returns:
            Generated text or an async iterator for streaming.
        """

    @abstractmethod
    async def chat(
        self, user_input: str, history: list[dict[str, str]]
    ) -> str | AsyncIterator[str]:
        """Conduct a conversation step.

        Args:
            user_input: The user's latest message.
            history: List of prior messages [{"role": "user", "content": "..."}, ...].

        Returns:
            The assistant's response (string or stream).
        """
