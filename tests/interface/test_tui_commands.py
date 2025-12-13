from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from chefchat.interface.tui import ChefChatApp, ConfirmRestartScreen


@pytest.fixture
def app():
    app = ChefChatApp()
    app._bus = AsyncMock()
    app._bus.publish = AsyncMock()
    return app


@pytest.mark.asyncio
async def test_handle_command_registry_dispatch(app):
    """Test that _handle_command correctly dispatches to handlers using Registry."""
    # Test a mapped command: /clear -> _handle_clear
    app._handle_clear = AsyncMock()
    await app._handle_command("/clear")
    app._handle_clear.assert_called_once()

    # Test a direct command: /timer -> _chef_timer
    app._chef_timer = AsyncMock()
    await app._handle_command("/timer 10m")
    app._chef_timer.assert_called_once_with("10m")


@pytest.mark.asyncio
async def test_handle_command_layout(app):
    """Test legacy layout command dispatch."""
    app._handle_layout_command = AsyncMock()
    await app._handle_command("/layout kitchen")
    app._handle_layout_command.assert_called_once_with("kitchen")


@pytest.mark.asyncio
async def test_handle_command_unknown(app):
    """Test unknown command handling."""
    with patch.object(app, "query_one") as mock_query:
        msg_mock = MagicMock()
        mock_query.return_value = msg_mock
        await app._handle_command("/unknowncmd")
        mock_query.assert_called_with("#ticket-rail", ANY)
        # Note: actual class is imported inside method, so we check string ID


@pytest.mark.asyncio
async def test_confirm_layout_switch_restart(app):
    """Test that confirming layout switch triggers exit with RESTART."""
    # Mocking the confirmation workflow
    # We can't easily test the screen interaction without running the app,
    # but we can test the logic if we could isolate on_confirm.
    # Instead, let's verify _handle_layout_command calls push_screen

    app.push_screen = MagicMock()
    await app._handle_layout_command("kitchen")
    app.push_screen.assert_called_once()
    args, _ = app.push_screen.call_args
    assert isinstance(args[0], ConfirmRestartScreen)
    assert args[0].new_layout == "kitchen"


@pytest.mark.asyncio
async def test_chef_taste_command(app):
    """Test /taste command publishes to bus."""
    # Setup bus
    app._bus = AsyncMock()
    app._brigade = MagicMock()  # Needs brigade to be present

    await app._chef_taste()

    app._bus.publish.assert_called_once()
    call_args = app._bus.publish.call_args[0][0]
    assert call_args.action == "TASTE_TEST"
    assert call_args.recipient == "expeditor"
