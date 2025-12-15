"""ModelService - Business logic for model management.

This service encapsulates all model-related business logic, extracted from
ModelCommandsMixin to enable testing and reuse without UI dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chefchat.core.config import ModelConfig, VibeConfig


@dataclass
class ModelInfo:
    """DTO representing model information for display."""

    alias: str
    name: str
    provider: str
    is_active: bool
    api_key_status: str  # "set" | "missing"
    temperature: float
    input_price: float
    output_price: float
    features: list[str]
    context_size: int | None = None
    multimodal: bool = False
    max_file_size: int | None = None


@dataclass
class ProviderInfo:
    """DTO representing provider information."""

    name: str
    api_base: str
    has_api_key: bool
    model_count: int


class ModelService:
    """Service for model management business logic.

    This class handles all model-related operations that don't require
    direct UI interaction, making the logic testable and reusable.
    """

    def __init__(self, config: VibeConfig) -> None:
        """Initialize with a VibeConfig instance.

        Args:
            config: The application configuration containing models.
        """
        self._config = config

    def get_active_model_alias(self) -> str:
        """Get the alias of the currently active model."""
        return self._config.active_model

    def get_active_model_info(self) -> ModelInfo | None:
        """Get detailed info about the active model."""
        try:
            model = self._config.get_active_model()
            return self._model_to_info(model)
        except Exception:
            return None

    def find_model_by_alias(self, alias: str) -> ModelInfo | None:
        """Find a model by alias (case-insensitive).

        Args:
            alias: Model alias to search for.

        Returns:
            ModelInfo if found, None otherwise.
        """
        target = alias.lower()
        for model in self._config.models.values():
            if target in {model.alias.lower(), model.name.lower()}:
                return self._model_to_info(model)
        return None

    def list_all_models(self) -> list[ModelInfo]:
        """Get all configured models as ModelInfo objects."""
        return [self._model_to_info(model) for model in self._config.models.values()]

    def get_models_by_provider(self) -> dict[str, list[ModelInfo]]:
        """Group models by provider."""
        groups: dict[str, list[ModelInfo]] = {}
        for model in self._config.models.values():
            provider = model.provider
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(self._model_to_info(model))
        return groups

    def get_speed_models(self) -> list[tuple[str, str, str]]:
        """Get fastest models (hardcoded for now).

        Returns:
            List of (alias, speed, pricing) tuples.
        """
        return [
            ("gpt-oss-20b", "1000 TPS", "$0.075/$0.30"),
            ("llama-scout", "750 TPS", "$0.11/$0.34"),
            ("groq-8b", "560 TPS", "$0.05/$0.08"),
            ("qwen-32b", "400 TPS", "$0.29/$0.59"),
            ("groq-70b", "280 TPS", "$0.59/$0.79"),
        ]

    def get_reasoning_models(self) -> list[tuple[str, str, str, str]]:
        """Get reasoning-capable models.

        Returns:
            List of (alias, capability, pricing, context) tuples.
        """
        return [
            ("kimi-k2", "Deep Reasoning", "$1.00/$3.00", "262K context"),
            ("gpt-oss-120b", "Browser + Code", "$0.15/$0.60", "131K context"),
            ("gpt-oss-20b", "Fast Reasoning", "$0.075/$0.30", "131K context"),
        ]

    def get_multimodal_models(self) -> list[tuple[str, str, str, str]]:
        """Get multimodal (vision) models.

        Returns:
            List of (alias, capability, pricing, file_size) tuples.
        """
        return [
            ("llama-scout", "Vision + Tools", "$0.11/$0.34", "20MB files"),
            ("llama-maverick", "Advanced Vision", "$0.20/$0.60", "20MB files"),
        ]

    def compare_models(
        self, aliases: list[str], max_features: int = 3
    ) -> list[dict[str, Any]]:
        """Compare multiple models.

        Args:
            aliases: List of model aliases to compare.
            max_features: Maximum number of features to include.

        Returns:
            List of comparison dicts with model info.
        """
        results = []
        for alias in aliases[:3]:  # Limit to 3 models
            model_info = self.find_model_by_alias(alias)
            if model_info:
                features = model_info.features[:max_features]
                if len(model_info.features) > max_features:
                    features.append("...")
                results.append({
                    "alias": model_info.alias,
                    "provider": model_info.provider,
                    "price": f"${model_info.input_price}/${model_info.output_price}",
                    "features": ", ".join(features),
                })
        return results

    def switch_model(self, alias: str) -> tuple[bool, str]:
        """Switch to a new model.

        Args:
            alias: Model alias to switch to.

        Returns:
            Tuple of (success, message).
        """
        from chefchat.core.config import VibeConfig

        model_info = self.find_model_by_alias(alias)
        if not model_info:
            return (
                False,
                f"Model `{alias}` not found. Use `/model list` to see available models.",
            )

        try:
            self._config.active_model = model_info.alias
            VibeConfig.save_updates({"active_model": model_info.alias})
            return True, f"Switched to model: {model_info.alias}"
        except Exception as e:
            return False, f"Failed to switch model: {e}"

    def check_provider_api_key(self, model: ModelConfig) -> bool:
        """Check if the provider has an API key configured.

        Args:
            model: Model to check provider for.

        Returns:
            True if API key is set, False otherwise.
        """
        try:
            provider = self._config.get_provider_for_model(model)
            return bool(
                provider.api_key_env_var and os.getenv(provider.api_key_env_var)
            )
        except Exception:
            return False

    def _model_to_info(self, model: ModelConfig) -> ModelInfo:
        """Convert a ModelConfig to a ModelInfo DTO."""
        try:
            provider = self._config.get_provider_for_model(model)
            has_key = bool(
                provider.api_key_env_var and os.getenv(provider.api_key_env_var)
            )
        except Exception:
            has_key = False

        return ModelInfo(
            alias=model.alias,
            name=model.name,
            provider=model.provider,
            is_active=model.alias == self._config.active_model,
            api_key_status="set" if has_key else "missing",
            temperature=model.temperature,
            input_price=model.input_price,
            output_price=model.output_price,
            features=list(model.features) if model.features else [],
            multimodal=model.multimodal,
            max_file_size=model.max_file_size,
        )
