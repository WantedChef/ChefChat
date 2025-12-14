"""Tests for MCP TUI integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chefchat.interface.tui import ChefChatApp


@pytest.fixture
def app():
    """Create a test app instance."""
    app = ChefChatApp()
    app._bus = AsyncMock()
    app._bus.publish = AsyncMock()
    return app


@pytest.fixture
def mock_config_no_mcp():
    """Config with no MCP servers."""
    config = MagicMock()
    config.mcp_servers = []
    return config


@pytest.fixture
def mock_config_with_mcp():
    """Config with MCP servers configured."""
    stdio_server = MagicMock()
    stdio_server.transport = "stdio"
    stdio_server.name = "test-stdio"
    stdio_server.command = ["npx", "test-server"]

    http_server = MagicMock()
    http_server.transport = "http"
    http_server.name = "test-http"
    http_server.url = "http://localhost:8080"

    config = MagicMock()
    config.mcp_servers = [stdio_server, http_server]
    return config


@pytest.mark.asyncio
async def test_mcp_command_shows_no_servers_message(app, mock_config_no_mcp):
    """Test /mcp command when no servers configured."""
    app._config = mock_config_no_mcp

    # Mock ticket rail
    ticket_rail_mock = MagicMock()
    with patch.object(app, "query_one", return_value=ticket_rail_mock):
        await app._handle_mcp_command()

    ticket_rail_mock.add_system_message.assert_called_once()
    message = ticket_rail_mock.add_system_message.call_args[0][0]
    assert "No MCP servers configured" in message
    assert "config.toml" in message


@pytest.mark.asyncio
async def test_mcp_command_shows_configured_servers(app, mock_config_with_mcp):
    """Test /mcp command shows server list."""
    app._config = mock_config_with_mcp

    ticket_rail_mock = MagicMock()
    with patch.object(app, "query_one", return_value=ticket_rail_mock):
        await app._handle_mcp_command()

    ticket_rail_mock.add_system_message.assert_called_once()
    message = ticket_rail_mock.add_system_message.call_args[0][0]
    assert "MCP Servers" in message
    assert "2" in message  # 2 servers
    assert "test-stdio" in message
    assert "test-http" in message
    assert "stdio" in message
    assert "http" in message


@pytest.mark.asyncio
async def test_mcp_command_loads_config_if_missing(app):
    """Test /mcp loads config if not already loaded."""
    app._config = None

    mock_config = MagicMock()
    mock_config.mcp_servers = []

    ticket_rail_mock = MagicMock()

    with (
        patch.object(app, "query_one", return_value=ticket_rail_mock),
        patch("chefchat.interface.app.VibeConfig.load", return_value=mock_config) as mock_load,
    ):
        await app._handle_mcp_command()

    mock_load.assert_called_once()
