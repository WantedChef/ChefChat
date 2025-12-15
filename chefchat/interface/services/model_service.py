"""ModelService - Business logic for model management.

This service encapsulates all model-related business logic, extracted from
ModelCommandsMixin to enable testing and reuse without UI dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import os
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from chefchat.core.config import ModelConfig, VibeConfig
    from chefchat.interface.services.config_service import ConfigService


@dataclass
class ModelInfo:
    """DTO representing model information for display."""

    alias: str
    name: str
    provider: str
    model_id: str
    is_active: bool
    api_key_status: str  # "set" | "missing"
    temperature: float
    input_price: float
    output_price: float
    features: list[str]
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_vision: bool = False
    supports_function_calling: bool = False
    multimodal: bool = False
    max_file_size: int | None = None
    rate_limits: dict[str, int] | None = None


@dataclass
class ProviderInfo:
    """DTO representing provider information."""

    name: str
    api_base: str
    has_api_key: bool
    model_count: int
    api_key_env_var: str | None = None


class ModelService:
    """Service for model management business logic.

    This class handles all model-related operations that don't require
    direct UI interaction, making the logic testable and reusable.
    """

    def __init__(self, config_service: ConfigService | VibeConfig) -> None:
        """Initialize with a ConfigService instance.

        Args:
            config_service: The ConfigService instance or VibeConfig for accessing configuration.
        """
        self._config_service = config_service

    @property
    def _config(self) -> VibeConfig:
        """Get the current config, ensuring it's up-to-date."""
        if hasattr(self._config_service, "ensure_config"):
            return self._config_service.ensure_config()
        return self._config_service

    @property
    def _models(self) -> Iterable[ModelConfig]:
        """Return configured models as a simple iterable."""
        # VibeConfig stores models as a list; keep compatibility if a dict sneaks in.
        models = getattr(self._config, "models", [])
        if isinstance(models, dict):
            return models.values()
        return list(models)

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

    def get_model_info(self, alias: str | None = None) -> ModelInfo | None:
        """Get a model by alias (case-insensitive). Defaults to active model."""
        target = (alias or self._config.active_model or "").strip()
        if not target:
            return None
        return self.find_model_by_alias(target)

    def find_model_by_alias(self, alias: str) -> ModelInfo | None:
        """Find a model by alias or model name (case-insensitive).

        Args:
            alias: Model alias to search for.

        Returns:
            ModelInfo if found, None otherwise.
        """
        target = alias.lower()
        for model in self._models:
            if target in {model.alias.lower(), model.name.lower()}:
                return self._model_to_info(model)
        return None

    def list_all_models(self) -> list[ModelInfo]:
        """Get all configured models as ModelInfo objects."""
        return [self._model_to_info(model) for model in self._models]

    def get_models_by_provider(self) -> dict[str, list[ModelInfo]]:
        """Group models by provider."""
        groups: dict[str, list[ModelInfo]] = {}
        for model in self._models:
            provider = model.provider
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(self._model_to_info(model))
        return groups

    def get_speed_models(self) -> list[ModelInfo]:
        """Return models tagged for speed/latency."""
        return self._filter_models(
            lambda m: "speed" in m.features or "fast" in m.features
        )

    def get_reasoning_models(self) -> list[ModelInfo]:
        """Return models tagged for reasoning."""
        return self._filter_models(lambda m: "reasoning" in m.features)

    def get_multimodal_models(self) -> list[ModelInfo]:
        """Return models that support multimodal/vision."""
        return self._filter_models(lambda m: m.multimodal or "vision" in m.features)

    def compare_models(self, aliases: list[str]) -> list[ModelInfo]:
        """Compare up to three models by alias."""
        seen: set[str] = set()
        results: list[ModelInfo] = []
        for alias in aliases:
            if len(results) >= 3:
                break
            normalized = alias.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            model_info = self.find_model_by_alias(alias)
            if model_info:
                results.append(model_info)
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

    def list_provider_info(self) -> list[ProviderInfo]:
        """Return provider key status with model counts."""
        providers = getattr(self._config, "providers", [])
        counts: dict[str, int] = {}
        for model in self._models:
            counts[model.provider] = counts.get(model.provider, 0) + 1

        result: list[ProviderInfo] = []
        for provider in providers:
            has_key = bool(
                provider.api_key_env_var and os.getenv(provider.api_key_env_var)
            )
            result.append(
                ProviderInfo(
                    name=provider.name,
                    api_base=provider.api_base,
                    has_api_key=has_key,
                    model_count=counts.get(provider.name, 0),
                    api_key_env_var=provider.api_key_env_var or None,
                )
            )
        return result

    async def fetch_provider_models(self, timeout: float = 8.0) -> dict[str, list[str]]:
        """Fetch live model listings from each configured provider's /models endpoint."""
        results: dict[str, list[str]] = {}

        async with httpx.AsyncClient(timeout=timeout) as client:
            for provider in getattr(self._config, "providers", []):
                if not provider.api_base:
                    continue

                url = provider.api_base.rstrip("/") + "/models"
                headers = {"Content-Type": "application/json"}
                if provider.api_key_env_var:
                    key = os.getenv(provider.api_key_env_var, "")
                    if key:
                        headers["Authorization"] = f"Bearer {key}"  # OpenAI-style header

                try:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()

                    names: list[str] = []
                    if isinstance(data, dict) and "data" in data:
                        for item in data["data"]:
                            if isinstance(item, dict):
                                ident = item.get("id") or item.get("name")
                                if ident:
                                    names.append(str(ident))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                ident = item.get("id") or item.get("name")
                                if ident:
                                    names.append(str(ident))
                            elif isinstance(item, str):
                                names.append(item)

                    results[provider.name] = sorted(set(names))
                except Exception:
                    # Track provider with empty list when fetch fails (auth missing or unsupported)
                    results.setdefault(provider.name, [])

        return results

    def _filter_models(self, predicate: Any) -> list[ModelInfo]:
        """Filter models using a predicate against ModelConfig."""
        return [self._model_to_info(m) for m in self._models if predicate(m)]

    def _model_to_info(self, model: ModelConfig) -> ModelInfo:
        """Convert a ModelConfig to a ModelInfo DTO."""
        try:
            provider = self._config.get_provider_for_model(model)
            has_key = bool(
                provider.api_key_env_var and os.getenv(provider.api_key_env_var)
            )
        except Exception:
            has_key = False

        features = list(model.features) if model.features else []
        supports_vision = model.multimodal or "vision" in features
        supports_function_calling = "tool_use" in features
        context_window = model.max_tokens if model.max_tokens else None

        return ModelInfo(
            alias=model.alias,
            name=model.name,
            provider=model.provider,
            model_id=model.name,
            is_active=model.alias == self._config.active_model,
            api_key_status="set" if has_key else "missing",
            temperature=model.temperature,
            input_price=model.input_price,
            output_price=model.output_price,
            features=features,
            context_window=context_window,
            max_output_tokens=model.max_tokens,
            supports_vision=supports_vision,
            supports_function_calling=supports_function_calling,
            multimodal=model.multimodal,
            max_file_size=model.max_file_size,
            rate_limits=model.rate_limits or {},
        )
