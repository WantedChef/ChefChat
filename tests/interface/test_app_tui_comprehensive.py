"""Comprehensive tests for app TUI integration - 100% coverage."""

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
def mock_ticket_rail():
    """Mock ticket rail."""
    rail = MagicMock()
    rail.add_system_message = MagicMock()
    rail.add_user_message = MagicMock()
    return rail


@pytest.fixture
def mock_loader():
    """Mock WhiskLoader."""
    loader = MagicMock()
    loader.start = MagicMock()
    loader.stop = MagicMock()
    return loader


class TestHandleBashCommandEdgeCases:
    """Comprehensive tests for _handle_bash_command."""

    @pytest.mark.asyncio
    async def test_handles_empty_command_after_exclamation(self, app, mock_ticket_rail):
        """Test handling of just '!' with no command."""
        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_bash_command("!")

        # Should show usage message
        mock_ticket_rail.add_system_message.assert_called_once()
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Usage" in message
        assert "!<command>" in message

    @pytest.mark.asyncio
    async def test_handles_whitespace_only_command(self, app, mock_ticket_rail):
        """Test handling of '!   ' with only whitespace."""
        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_bash_command("!   ")

        # Should show usage message
        mock_ticket_rail.add_system_message.assert_called_once()
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Usage" in message

    @pytest.mark.asyncio
    async def test_returns_early_for_non_bash_command(self, app):
        """Test that non-! commands return early."""
        with patch.object(app, "query_one") as mock_query:
            await app._handle_bash_command("/help")

        # Should not call query_one
        mock_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_shows_user_message_with_command(self, app, mock_ticket_rail):
        """Test that user message is shown with the command."""
        with (
            patch.object(app, "query_one", side_effect=[mock_ticket_rail, MagicMock()]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("output", "", 0))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!ls -la")

        # Should show user message with command
        mock_ticket_rail.add_user_message.assert_called_once()
        assert "!ls -la" in mock_ticket_rail.add_user_message.call_args[0][0]

    @pytest.mark.asyncio
    async def test_starts_loader_with_truncated_command(self, app, mock_loader):
        """Test that loader shows truncated command if too long."""
        long_command = "!" + "a" * 50

        with (
            patch.object(app, "query_one", side_effect=[MagicMock(), mock_loader]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("", "", 0))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command(long_command)

        # Loader should be started with truncated command
        mock_loader.start.assert_called_once()
        loader_msg = mock_loader.start.call_args[0][0]
        assert len(loader_msg) < len(long_command)

    @pytest.mark.asyncio
    async def test_handles_command_with_stdout_only(self, app, mock_ticket_rail):
        """Test handling command that produces only stdout."""
        with (
            patch.object(app, "query_one", side_effect=[mock_ticket_rail, MagicMock()]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("stdout output", "", 0))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!echo test")

        # Should show success with stdout
        assert mock_ticket_rail.add_system_message.call_count >= 1
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "succeeded" in message.lower()
        assert "stdout output" in message

    @pytest.mark.asyncio
    async def test_handles_command_with_stderr_only(self, app, mock_ticket_rail):
        """Test handling command that produces only stderr."""
        with (
            patch.object(app, "query_one", side_effect=[mock_ticket_rail, MagicMock()]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("", "error output", 0))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!test")

        # Should show success with stderr
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "stderr" in message.lower()
        assert "error output" in message

    @pytest.mark.asyncio
    async def test_handles_command_with_both_stdout_and_stderr(
        self, app, mock_ticket_rail
    ):
        """Test handling command with both stdout and stderr."""
        with (
            patch.object(app, "query_one", side_effect=[mock_ticket_rail, MagicMock()]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("stdout", "stderr", 0))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!test")

        # Should show both
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "stdout" in message
        assert "stderr" in message

    @pytest.mark.asyncio
    async def test_handles_command_with_no_output(self, app, mock_ticket_rail):
        """Test handling command with no output."""
        with (
            patch.object(app, "query_one", side_effect=[mock_ticket_rail, MagicMock()]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("", "", 0))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!true")

        # Should show no output message
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "no output" in message.lower()

    @pytest.mark.asyncio
    async def test_handles_command_with_nonzero_exit_code(self, app, mock_ticket_rail):
        """Test handling command that fails with nonzero exit code."""
        with (
            patch.object(app, "query_one", side_effect=[mock_ticket_rail, MagicMock()]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("", "error", 1))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!false")

        # Should show exit code
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "Exit code 1" in message or "exit code 1" in message.lower()

    @pytest.mark.asyncio
    async def test_handles_command_exception(self, app, mock_ticket_rail):
        """Test handling exception during command execution."""
        with (
            patch.object(app, "query_one", side_effect=[mock_ticket_rail, MagicMock()]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(side_effect=Exception("Command failed"))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!test")

        # Should show error message
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "failed" in message.lower()
        assert "Command failed" in message

    @pytest.mark.asyncio
    async def test_loader_stopped_on_success(self, app, mock_loader):
        """Test that loader is stopped after successful execution."""
        with (
            patch.object(app, "query_one", side_effect=[MagicMock(), mock_loader]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=("", "", 0))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!test")

        mock_loader.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_loader_stopped_on_exception(self, app, mock_loader):
        """Test that loader is stopped even when exception occurs."""
        with (
            patch.object(app, "query_one", side_effect=[MagicMock(), mock_loader]),
            patch(
                "chefchat.core.tools.executor.SecureCommandExecutor"
            ) as mock_executor_class,
        ):
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(side_effect=Exception("Error"))
            mock_executor_class.return_value = mock_executor

            await app._handle_bash_command("!test")

        # Loader should still be stopped
        mock_loader.stop.assert_called_once()


class TestHandleMcpCommandEdgeCases:
    """Comprehensive tests for _handle_mcp_command."""

    @pytest.mark.asyncio
    async def test_loads_config_if_not_present(self, app, mock_ticket_rail):
        """Test that config is loaded if not already present."""
        app._config = None

        mock_config = MagicMock()
        mock_config.mcp_servers = []

        with (
            patch.object(app, "query_one", return_value=mock_ticket_rail),
            patch(
                "chefchat.interface.app.VibeConfig.load", return_value=mock_config
            ) as mock_load,
        ):
            await app._handle_mcp_command()

        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_shows_help_when_no_servers(self, app, mock_ticket_rail):
        """Test help message shown when no MCP servers configured."""
        mock_config = MagicMock()
        mock_config.mcp_servers = []
        app._config = mock_config

        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_mcp_command()

        mock_ticket_rail.add_system_message.assert_called_once()
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "No MCP servers" in message
        assert "config.toml" in message

    @pytest.mark.asyncio
    async def test_displays_stdio_server_info(self, app, mock_ticket_rail):
        """Test display of stdio MCP server."""
        stdio_server = MagicMock()
        stdio_server.transport = "stdio"
        stdio_server.name = "test-stdio"
        stdio_server.command = ["npx", "test-server", "--arg"]

        mock_config = MagicMock()
        mock_config.mcp_servers = [stdio_server]
        app._config = mock_config

        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_mcp_command()

        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "test-stdio" in message
        assert "stdio" in message
        assert "npx test-server" in message

    @pytest.mark.asyncio
    async def test_displays_http_server_info(self, app, mock_ticket_rail):
        """Test display of HTTP MCP server."""
        http_server = MagicMock()
        http_server.transport = "http"
        http_server.name = "test-http"
        http_server.url = "http://localhost:8080"

        mock_config = MagicMock()
        mock_config.mcp_servers = [http_server]
        app._config = mock_config

        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_mcp_command()

        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "test-http" in message
        assert "http" in message
        assert "http://localhost:8080" in message

    @pytest.mark.asyncio
    async def test_displays_streamable_http_server_info(self, app, mock_ticket_rail):
        """Test display of streamable-http MCP server."""
        streamable_server = MagicMock()
        streamable_server.transport = "streamable-http"
        streamable_server.name = "test-streamable"
        streamable_server.url = "http://localhost:9000"

        mock_config = MagicMock()
        mock_config.mcp_servers = [streamable_server]
        app._config = mock_config

        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_mcp_command()

        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "test-streamable" in message
        assert "streamable-http" in message

    @pytest.mark.asyncio
    async def test_displays_unknown_transport_type(self, app, mock_ticket_rail):
        """Test display of unknown transport type."""
        unknown_server = MagicMock()
        unknown_server.transport = "unknown-type"
        unknown_server.name = "test-unknown"

        mock_config = MagicMock()
        mock_config.mcp_servers = [unknown_server]
        app._config = mock_config

        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_mcp_command()

        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "test-unknown" in message
        assert "unknown-type" in message

    @pytest.mark.asyncio
    async def test_displays_multiple_servers(self, app, mock_ticket_rail):
        """Test display of multiple MCP servers."""
        stdio_server = MagicMock()
        stdio_server.transport = "stdio"
        stdio_server.name = "server1"
        stdio_server.command = ["cmd1"]

        http_server = MagicMock()
        http_server.transport = "http"
        http_server.name = "server2"
        http_server.url = "http://localhost:8080"

        mock_config = MagicMock()
        mock_config.mcp_servers = [stdio_server, http_server]
        app._config = mock_config

        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_mcp_command()

        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "2" in message  # 2 servers
        assert "server1" in message
        assert "server2" in message

    @pytest.mark.asyncio
    async def test_handles_stdio_command_as_string(self, app, mock_ticket_rail):
        """Test handling stdio command when it's a string instead of list."""
        stdio_server = MagicMock()
        stdio_server.transport = "stdio"
        stdio_server.name = "test"
        stdio_server.command = "npx test-server"  # String instead of list

        mock_config = MagicMock()
        mock_config.mcp_servers = [stdio_server]
        app._config = mock_config

        with patch.object(app, "query_one", return_value=mock_ticket_rail):
            await app._handle_mcp_command()

        # Should handle string command gracefully
        message = mock_ticket_rail.add_system_message.call_args[0][0]
        assert "test" in message
