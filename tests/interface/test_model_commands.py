"""Tests for TUI model command functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chefchat.interface.app import ChefChatApp


@pytest.fixture
def app():
    """Create a test app instance."""
    app = ChefChatApp()
    app._bus = AsyncMock()
    app._bus.publish = AsyncMock()
    return app


@pytest.fixture
def mock_config():
    """Create a mock config with test models."""
    mock_config = MagicMock()
    mock_config.models = [
        MagicMock(
            alias="test-model-1",
            name="test-model-1-full",
            provider="test-provider",
            temperature=0.7,
            input_price=0.1,
            output_price=0.2,
            features=["speed", "reasoning"],
        ),
        MagicMock(
            alias="test-model-2",
            name="test-model-2-full",
            provider="another-provider",
            temperature=0.5,
            input_price=0.3,
            output_price=0.4,
            features=["multimodal"],
        ),
    ]
    mock_config.active_model = "test-model-1"
    mock_config.get_active_model.return_value = mock_config.models[0]
    mock_config.get_provider_for_model.return_value = MagicMock(
        api_base="https://api.example.com",
        api_key_env_var="TEST_API_KEY",
        backend=MagicMock(value="openai"),
    )
    return mock_config


@pytest.mark.asyncio
async def test_handle_model_command_with_subcommand(app):
    """Test that model command properly passes arguments."""
    with patch.object(app, "_handle_model_command") as mock_handler:
        await app._dispatch_tui_command("/model", "list")
        mock_handler.assert_called_once_with("list")


@pytest.mark.asyncio
async def test_handle_model_command_no_args(app):
    """Test model command with no arguments."""
    with patch.object(app, "_handle_model_command") as mock_handler:
        await app._dispatch_tui_command("/model", "")
        mock_handler.assert_called_once_with("")


@pytest.mark.asyncio
async def test_handle_model_command_with_complex_args(app):
    """Test model command with complex arguments."""
    with patch.object(app, "_handle_model_command") as mock_handler:
        await app._dispatch_tui_command("/model", "select test-model-1")
        mock_handler.assert_called_once_with("select test-model-1")


@pytest.mark.asyncio
async def test_model_show_help(app, mock_config):
    """Test showing model help."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        await app._model_show_help()

        mock_ticket_rail.add_system_message.assert_called_once()
        call_args = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Model Management Commands" in call_args
        assert "/model list" in call_args
        assert "/model select" in call_args


@pytest.mark.asyncio
async def test_model_list_with_config(app, mock_config):
    """Test listing models with valid config."""
    app._config = mock_config
    app._get_llm_client = MagicMock()
    app._get_llm_client.return_value.list_models = AsyncMock(
        return_value=["test-model-1-full"]
    )

    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        with patch("os.getenv", return_value="fake-key"):
            await app._model_list()

            mock_ticket_rail.add_system_message.assert_called_once()
            call_args = mock_ticket_rail.add_system_message.call_args[0][0]
            assert "Available Models" in call_args
            assert "test-model-1" in call_args


@pytest.mark.asyncio
async def test_model_select_valid(app, mock_config):
    """Test selecting a valid model."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        with patch("chefchat.core.config.VibeConfig.save_updates") as mock_save:
            with patch.object(app, "notify") as mock_notify:
                await app._model_select("test-model-1")

                mock_save.assert_called_once_with({"active_model": "test-model-1"})
                mock_notify.assert_called_once_with("Switched to model: test-model-1")


@pytest.mark.asyncio
async def test_model_select_invalid(app, mock_config):
    """Test selecting an invalid model."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        await app._model_select("non-existent-model")

        mock_ticket_rail.add_system_message.assert_called_once()
        call_args = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "not found" in call_args


@pytest.mark.asyncio
async def test_model_info_valid(app, mock_config):
    """Test showing model info for valid model."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        with patch("os.getenv", return_value="fake-key"):
            await app._model_info("test-model-1")

            mock_ticket_rail.add_system_message.assert_called_once()
            call_args = mock_ticket_rail.add_system_message.call_args[0][0]
            assert "Model Details" in call_args
            assert "test-model-1" in call_args


@pytest.mark.asyncio
async def test_model_status(app, mock_config):
    """Test showing model status."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        with patch("os.getenv", return_value="fake-key"):
            await app._model_status()

            mock_ticket_rail.add_system_message.assert_called_once()
            call_args = mock_ticket_rail.add_system_message.call_args[0][0]
            assert "Current Model Status" in call_args
            assert "test-model-1" in call_args


@pytest.mark.asyncio
async def test_model_manage_screen(app, mock_config):
    """Test opening model management screen."""
    app._config = mock_config

    with patch(
        "chefchat.interface.screens.model_manager.ModelManagerScreen"
    ):
        mock_push_screen = AsyncMock()
        app.push_screen = mock_push_screen

        await app._model_manage()

        mock_push_screen.assert_called_once()


@pytest.mark.asyncio
async def test_model_speed_list(app, mock_config):
    """Test listing speed models."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        await app._model_speed()

        mock_ticket_rail.add_system_message.assert_called_once()
        call_args = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Fastest Models" in call_args


@pytest.mark.asyncio
async def test_model_reasoning_list(app, mock_config):
    """Test listing reasoning models."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        await app._model_reasoning()

        mock_ticket_rail.add_system_message.assert_called_once()
        call_args = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Reasoning Models" in call_args


@pytest.mark.asyncio
async def test_model_multimodal_list(app, mock_config):
    """Test listing multimodal models."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        await app._model_multimodal()

        mock_ticket_rail.add_system_message.assert_called_once()
        call_args = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Multimodal Models" in call_args


@pytest.mark.asyncio
async def test_model_compare_valid(app, mock_config):
    """Test comparing valid models."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        await app._model_compare("test-model-1 test-model-2")

        mock_ticket_rail.add_system_message.assert_called_once()
        call_args = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Model Comparison" in call_args


@pytest.mark.asyncio
async def test_model_compare_insufficient_models(app, mock_config):
    """Test comparing insufficient number of models."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        await app._model_compare("test-model-1")

        mock_ticket_rail.add_system_message.assert_called_once()
        call_args = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Please provide at least 2 models" in call_args


@pytest.mark.asyncio
async def test_handle_model_command_dispatch(app, mock_config):
    """Test that model command dispatch works correctly for all subcommands."""
    app._config = mock_config
    mock_ticket_rail = MagicMock()

    with patch.object(app, "query_one", return_value=mock_ticket_rail):
        # Test each subcommand gets dispatched correctly
        subcommands = [
            ("list", "_model_list"),
            ("select test-model", "_model_select"),
            ("info test-model", "_model_info"),
            ("status", "_model_status"),
            ("speed", "_model_speed"),
            ("reasoning", "_model_reasoning"),
            ("multimodal", "_model_multimodal"),
            ("compare model1 model2", "_model_compare"),
            ("manage", "_model_manage"),
            ("help", "_model_show_help"),
        ]

        for subcommand, expected_method in subcommands:
            with patch.object(app, expected_method) as mock_method:
                await app._handle_model_command(subcommand)
                mock_method.assert_called_once()
