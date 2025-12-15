"""Unit tests for ModelService."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from chefchat.core.config import ModelConfig, ProviderConfig
from chefchat.interface.services.model_service import ModelService


@dataclass
class DummyConfig:
    models: list[ModelConfig]
    providers: list[ProviderConfig]
    active_model: str

    def ensure_config(self) -> DummyConfig:
        return self

    def get_active_model(self) -> ModelConfig:
        target = self.active_model.lower()
        for model in self.models:
            if target in {model.alias.lower(), model.name.lower()}:
                return model
        raise ValueError("Active model not found")

    def get_provider_for_model(self, model: ModelConfig) -> ProviderConfig:
        for provider in self.providers:
            if provider.name == model.provider:
                return provider
        raise ValueError("Provider not found")


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> ProviderConfig:
    monkeypatch.setenv("TEST_API_KEY", "secret")
    return ProviderConfig(
        name="test-provider",
        api_base="https://api.test.com",
        api_key_env_var="TEST_API_KEY",
    )


@pytest.fixture
def other_provider() -> ProviderConfig:
    return ProviderConfig(name="other", api_base="https://api.other.com")


@pytest.fixture
def config(provider: ProviderConfig, other_provider: ProviderConfig) -> DummyConfig:
    models = [
        ModelConfig(
            name="fast-model",
            provider="test-provider",
            alias="fast",
            input_price=0.1,
            output_price=0.2,
            max_tokens=2048,
            features={"speed", "tool_use"},
            multimodal=True,
        ),
        ModelConfig(
            name="thinker",
            provider="test-provider",
            alias="think",
            input_price=0.2,
            output_price=0.4,
            max_tokens=4096,
            features={"reasoning"},
        ),
        ModelConfig(
            name="general",
            provider="other",
            alias="general",
            input_price=0.0,
            output_price=0.0,
            features=set(),
        ),
    ]
    return DummyConfig(models=models, providers=[provider, other_provider], active_model="think")


def test_get_active_model_alias(config: DummyConfig) -> None:
    service = ModelService(config)
    assert service.get_active_model_alias() == "think"


def test_get_model_info_defaults_to_active(config: DummyConfig) -> None:
    service = ModelService(config)
    info = service.get_model_info("")
    assert info is not None
    assert info.alias == "think"
    assert info.is_active is True


def test_find_model_by_alias_case_insensitive(config: DummyConfig) -> None:
    service = ModelService(config)
    info = service.find_model_by_alias("FAST")
    assert info is not None
    assert info.alias == "fast"
    assert info.supports_function_calling is True
    assert info.supports_vision is True


def test_list_all_models_includes_all(config: DummyConfig) -> None:
    service = ModelService(config)
    aliases = {m.alias for m in service.list_all_models()}
    assert aliases == {"fast", "think", "general"}


def test_speed_and_reasoning_filters(config: DummyConfig) -> None:
    service = ModelService(config)
    speed_aliases = {m.alias for m in service.get_speed_models()}
    reasoning_aliases = {m.alias for m in service.get_reasoning_models()}

    assert speed_aliases == {"fast"}
    assert reasoning_aliases == {"think"}


def test_compare_models_limits_and_order(config: DummyConfig) -> None:
    service = ModelService(config)
    compared = service.compare_models(["fast", "unknown", "think", "fast", "general"])

    assert [m.alias for m in compared] == ["fast", "think", "general"]
    # Max three entries enforced
    assert len(compared) == 3


def test_list_provider_info_reports_keys(
    config: DummyConfig, provider: ProviderConfig
) -> None:
    service = ModelService(config)
    providers = {p.name: p for p in service.list_provider_info()}

    assert "test-provider" in providers
    assert providers["test-provider"].has_api_key is True
    assert providers["test-provider"].model_count == 2
    assert providers["other"].has_api_key is False
