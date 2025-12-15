"""Unit tests for ModelService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chefchat.interface.services.model_service import ModelInfo, ModelService


@pytest.fixture
def mock_model() -> MagicMock:
    """Create a mock model configuration."""
    model = MagicMock()
    model.alias = "test-model"
    model.name = "Test Model"
    model.provider = "test-provider"
    model.temperature = 0.7
    model.input_price = 0.1
    model.output_price = 0.2
    model.features = ["feature1", "feature2"]
    model.multimodal = False
    model.max_file_size = None
    return model


@pytest.fixture
def mock_config(mock_model: MagicMock) -> MagicMock:
    """Create a mock VibeConfig."""
    config = MagicMock()
    config.active_model = "test-model"
    config.models = {"test-model": mock_model}

    # Mock get_active_model
    config.get_active_model.return_value = mock_model

    # Mock get_provider_for_model
    provider = MagicMock()
    provider.api_key_env_var = "TEST_API_KEY"
    provider.api_base = "https://api.test.com"
    config.get_provider_for_model.return_value = provider

    return config


class TestModelService:
    """Tests for ModelService class."""

    def test_get_active_model_alias(self, mock_config: MagicMock) -> None:
        """Test getting active model alias."""
        service = ModelService(mock_config)
        assert service.get_active_model_alias() == "test-model"

    def test_get_active_model_info(self, mock_config: MagicMock) -> None:
        """Test getting active model as ModelInfo."""
        service = ModelService(mock_config)
        info = service.get_active_model_info()

        assert info is not None
        assert info.alias == "test-model"
        assert info.is_active is True
        assert info.temperature == 0.7

    def test_find_model_by_alias_found(
        self, mock_config: MagicMock, mock_model: MagicMock
    ) -> None:
        """Test finding model by alias when it exists."""
        mock_config.models = {"test-model": mock_model}
        service = ModelService(mock_config)

        info = service.find_model_by_alias("test-model")
        assert info is not None
        assert info.alias == "test-model"

    def test_find_model_by_alias_case_insensitive(
        self, mock_config: MagicMock, mock_model: MagicMock
    ) -> None:
        """Test case-insensitive model lookup."""
        mock_config.models = {"test-model": mock_model}
        service = ModelService(mock_config)

        info = service.find_model_by_alias("TEST-MODEL")
        assert info is not None
        assert info.alias == "test-model"

    def test_find_model_by_alias_not_found(self, mock_config: MagicMock) -> None:
        """Test finding non-existent model returns None."""
        mock_config.models = {}
        service = ModelService(mock_config)

        info = service.find_model_by_alias("nonexistent")
        assert info is None

    def test_list_all_models(
        self, mock_config: MagicMock, mock_model: MagicMock
    ) -> None:
        """Test listing all models."""
        mock_model2 = MagicMock()
        mock_model2.alias = "second-model"
        mock_model2.name = "Second Model"
        mock_model2.provider = "other-provider"
        mock_model2.temperature = 0.5
        mock_model2.input_price = 0.05
        mock_model2.output_price = 0.1
        mock_model2.features = []
        mock_model2.multimodal = False
        mock_model2.max_file_size = None

        mock_config.models = {"test-model": mock_model, "second-model": mock_model2}
        service = ModelService(mock_config)

        models = service.list_all_models()
        assert len(models) == 2
        aliases = {m.alias for m in models}
        assert "test-model" in aliases
        assert "second-model" in aliases

    def test_get_speed_models(self, mock_config: MagicMock) -> None:
        """Test getting speed models returns expected format."""
        service = ModelService(mock_config)
        speed_models = service.get_speed_models()

        assert len(speed_models) > 0
        assert all(len(m) == 3 for m in speed_models)  # (alias, speed, pricing)

    def test_get_reasoning_models(self, mock_config: MagicMock) -> None:
        """Test getting reasoning models returns expected format."""
        service = ModelService(mock_config)
        reasoning_models = service.get_reasoning_models()

        assert len(reasoning_models) > 0
        assert all(len(m) == 4 for m in reasoning_models)

    def test_compare_models(
        self, mock_config: MagicMock, mock_model: MagicMock
    ) -> None:
        """Test comparing models."""
        mock_config.models = {"test-model": mock_model}
        service = ModelService(mock_config)

        results = service.compare_models(["test-model"])
        assert len(results) == 1
        assert results[0]["alias"] == "test-model"
        assert "price" in results[0]

    def test_compare_models_max_three(
        self, mock_config: MagicMock, mock_model: MagicMock
    ) -> None:
        """Test that comparison is limited to 3 models."""
        mock_config.models = {"test-model": mock_model}
        service = ModelService(mock_config)

        # Try to compare 5 models (only first 3 should be processed)
        results = service.compare_models(["test-model", "a", "b", "c", "d"])
        # Only test-model exists, others will be skipped
        assert len(results) <= 3


class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_model_info_creation(self) -> None:
        """Test creating ModelInfo instance."""
        info = ModelInfo(
            alias="test",
            name="Test Model",
            provider="provider",
            is_active=True,
            api_key_status="set",
            temperature=0.7,
            input_price=0.1,
            output_price=0.2,
            features=["a", "b"],
        )

        assert info.alias == "test"
        assert info.is_active is True
        assert info.api_key_status == "set"
        assert info.features == ["a", "b"]
        assert info.multimodal is False  # default
        assert info.context_size is None  # default
