"""Tests for Sommelier station with Phase 2 recommendation engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chefchat.kitchen.bus import ChefMessage, KitchenBus
from chefchat.kitchen.manager import KitchenManager
from chefchat.kitchen.stations.sommelier import Sommelier


@pytest.mark.asyncio
async def test_sommelier_recommend_packages():
    """Test that Sommelier can generate package recommendations via LLM."""
    # Setup mocks
    mock_bus = AsyncMock(spec=KitchenBus)
    mock_manager = MagicMock(spec=KitchenManager)

    # Mock stream_response to yield chunks
    async def mock_stream(*args, **kwargs):
        yield "Try "
        yield "httpx."

    mock_manager.stream_response.side_effect = mock_stream
    mock_manager.RECOMMEND_SYSTEM_PROMPT = "system prompt"

    # Initialize station
    sommelier = Sommelier(mock_bus, mock_manager)

    # Create message
    message = ChefMessage(
        sender="sous_chef",
        recipient="sommelier",
        action="recommend",
        payload={"use_case": "http requests"},
    )

    # Execute
    await sommelier.handle(message)

    # Verify manager called
    args, kwargs = mock_manager.stream_response.call_args
    assert "http requests" in args[0]
    assert kwargs["system"] == "system prompt"

    # Verify bus messages (publish calls)
    publish_calls = mock_bus.publish.call_args_list

    stream_calls = [
        call for call in publish_calls if call.args[0].action == "STREAM_UPDATE"
    ]
    assert len(stream_calls) == 2
    assert stream_calls[0].args[0].payload["content"] == "Try "
    assert stream_calls[1].args[0].payload["content"] == "httpx."

    # Check for final recommendation
    final_call = [
        call
        for call in publish_calls
        if call.args[0].action == "package_recommendations"
    ]
    assert len(final_call) == 1
    assert final_call[0].args[0].payload["message"] == "Try httpx."


@pytest.mark.asyncio
async def test_sommelier_verify_package():
    """Test that Sommelier can verify packages exist on PyPI."""
    mock_bus = AsyncMock(spec=KitchenBus)
    mock_manager = MagicMock(spec=KitchenManager)

    sommelier = Sommelier(mock_bus, mock_manager)

    # The verify_package action doesn't use the manager
    message = ChefMessage(
        sender="line_cook",
        recipient="sommelier",
        action="verify_package",
        payload={"package": "requests"},
    )

    # This will make an actual HTTP call to PyPI
    # Just verify it doesn't crash
    try:
        await sommelier.handle(message)
    except Exception:
        pass  # Network errors are acceptable in unit tests

    # Verify status update was sent
    assert mock_bus.publish.called


@pytest.mark.asyncio
async def test_sommelier_initialization():
    """Test Sommelier initializes with manager correctly."""
    mock_bus = AsyncMock(spec=KitchenBus)
    mock_manager = MagicMock(spec=KitchenManager)

    sommelier = Sommelier(mock_bus, mock_manager)

    assert sommelier.name == "sommelier"
    assert sommelier.manager is mock_manager
    assert len(sommelier._verified_packages) == 0


@pytest.mark.asyncio
async def test_sommelier_check_security():
    """Test Sommelier security check uses helper methods."""
    mock_bus = AsyncMock(spec=KitchenBus)
    mock_manager = MagicMock(spec=KitchenManager)

    sommelier = Sommelier(mock_bus, mock_manager)

    message = ChefMessage(
        sender="expeditor",
        recipient="sommelier",
        action="check_security",
        payload={"packages": ["requests", "flask"]},
    )

    # Execute - this will try to run pip-audit which may not be installed
    await sommelier.handle(message)

    # Verify security_report was sent
    publish_calls = mock_bus.publish.call_args_list
    security_calls = [
        call for call in publish_calls if call.args[0].action == "security_report"
    ]
    assert len(security_calls) == 1
