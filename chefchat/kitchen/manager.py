"""Kitchen Manager - The Context for AI Operations.

Manages the active Chef (Strategy) and provides high-level methods
for kitchen stations to get work done.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from chefchat.kitchen.core import ChefBrain

logger = logging.getLogger(__name__)


class KitchenManager:
    """The Factory and Context for the Kitchen's AI operations.

    Responsibilities:
    - Lazy load the appropriate Chef (Strategy)
    - Provide high-level methods (plan, cook, roast) that delegate to the Chef
    - Handle fallbacks and errors
    """

    PLAN_SYSTEM_PROMPT = """You are the Sous Chef, a senior software architect.
Your job is to analyze user requests and create detailed implementation plans.

Output format:
1. Brief analysis of the request
2. Step-by-step implementation plan
3. Files to create/modify
4. Potential challenges

Be concise but thorough. Think like a Michelin-star chef planning a complex dish."""

    CODE_SYSTEM_PROMPT = """You are the Line Cook, an expert programmer.
Your job is to write clean, production-ready code based on the plan.

Rules:
- Write complete, working code
- Include docstrings and type hints
- Follow PEP 8 style
- Handle edge cases

Output only the code, no explanations unless in comments."""

    ROAST_SYSTEM_PROMPT = """You are The Critic, a sarcastic Gordon Ramsay-style code reviewer.
Your job is to roast the code while providing genuinely useful feedback.

Style:
- Be brutally honest but educational
- Use kitchen/cooking metaphors
- Point out real issues in a memorable way
- End with one genuine compliment if warranted

Keep it under 300 words. Make it sting, but make it useful."""

    def __init__(self, chef_name: str = "devstral") -> None:
        """Initialize the Kitchen Manager.

        Args:
            chef_name: Name of the chef module to load (default: "devstral")
        """
        self.chef_name = chef_name
        self._chef: ChefBrain | None = None

    @property
    def chef(self) -> ChefBrain:
        """Get the active chef, lazy-loading if necessary."""
        if self._chef is None:
            self._chef = self._load_chef(self.chef_name)
        return self._chef

    def _load_chef(self, name: str) -> ChefBrain:
        """Load the specific chef module and instantiate the chef.

        Args:
            name: Name of the chef (e.g. "devstral")

        Returns:
            Instantiated ChefBrain
        """
        try:
            module = importlib.import_module(f"chefchat.kitchen.chefs.{name}")
            # Assume class name is Capitalized + Chef (e.g. DevstralChef)
            class_name = f"{name.capitalize()}Chef"
            chef_class = getattr(module, class_name)
            chef = chef_class()

            # Attempt connection
            if not chef.connect():
                logger.warning(
                    f"Chef {name} failed to connect. Falling back to simulation."
                )
                return self._get_simulated_chef()

            return chef

        except ImportError as e:
            logger.error(f"Could not load chef module '{name}': {e}")
            return self._get_simulated_chef()
        except Exception as e:
            logger.exception(f"Error initializing chef '{name}': {e}")
            return self._get_simulated_chef()

    def _get_simulated_chef(self) -> ChefBrain:
        """Return a simulated chef for fallbacks."""
        # Simple inline simulation to avoid crashing
        from chefchat.kitchen.core import ChefBrain

        class SimulatedChef(ChefBrain):
            def connect(self, api_key: str | None = None) -> bool:
                return True

            async def cook_recipe(
                self, ingredients: dict[str, Any], preferences: dict[str, Any] | None = None
            ) -> str:
                return "# Simulated Response\n\nAI is not available. Please check your API keys."

            async def chat(
                self, user_input: str, history: list[dict[str, str]]
            ) -> AsyncIterator[str]:
                yield "Simulated response: AI unavailable."

        return SimulatedChef()

    async def generate_plan(self, context: str) -> str:
        """Generate an implementation plan.

        Args:
            context: User's request and context

        Returns:
            The generated plan
        """
        ingredients = {"prompt": context, "system": self.PLAN_SYSTEM_PROMPT}
        result = await self.chef.cook_recipe(ingredients)
        # Handle case where cook_recipe returns iterator (though for this we expect str)
        if hasattr(result, "__aiter__"):
            text = ""
            async for chunk in result:
                text += chunk
            return text
        return str(result)

    async def write_code(self, plan: str, context: str = "") -> str:
        """Generate code based on a plan.

        Args:
            plan: The plan to implement
            context: Additional context

        Returns:
            Generated code
        """
        prompt = f"Plan:\n{plan}\n\nContext:\n{context}\n\nGenerate the code."
        ingredients = {"prompt": prompt, "system": self.CODE_SYSTEM_PROMPT}
        result = await self.chef.cook_recipe(ingredients)
        if hasattr(result, "__aiter__"):
            text = ""
            async for chunk in result:
                text += chunk
            return text
        return str(result)

    async def fix_code(self, code: str, errors: list[str]) -> str:
        """Fix code based on errors.

        Args:
            code: The broken code
            errors: List of error messages

        Returns:
            Fixed code
        """
        error_msg = "\n- ".join(errors)
        prompt = f"The following code has errors:\n\n```python\n{code}\n```\n\nErrors:\n{error_msg}\n\nFix all errors."
        ingredients = {"prompt": prompt, "system": self.CODE_SYSTEM_PROMPT}
        result = await self.chef.cook_recipe(ingredients)
        if hasattr(result, "__aiter__"):
            text = ""
            async for chunk in result:
                text += chunk
            return text
        return str(result)

    async def roast_code(self, code: str, file_path: str = "unknown") -> str:
        """Generate a code review.

        Args:
            code: Code to review
            file_path: File path

        Returns:
            The review
        """
        prompt = f"Review this code from `{file_path}`:\n\n```python\n{code}\n```"
        ingredients = {"prompt": prompt, "system": self.ROAST_SYSTEM_PROMPT}
        result = await self.chef.cook_recipe(ingredients)
        if hasattr(result, "__aiter__"):
            text = ""
            async for chunk in result:
                text += chunk
            return text
        return str(result)

    async def stream_response(
        self, prompt: str, system: str | None = None
    ) -> AsyncIterator[str]:
        """Stream a response (compatibility method).

        Args:
            prompt: User prompt
            system: Optional system prompt

        Yields:
            Response chunks
        """
        ingredients = {"prompt": prompt, "system": system}
        preferences = {"stream": True}

        result = await self.chef.cook_recipe(ingredients, preferences)

        if hasattr(result, "__aiter__"):
            async for chunk in result:
                yield chunk
        else:
            yield str(result)
