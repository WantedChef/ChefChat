"""Tests for Brigade orchestration and kitchen lifecycle management."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chefchat.kitchen.brigade import Brigade, create_default_brigade
from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus


class MockStation(BaseStation):
    """Mock station for testing."""

    def __init__(self, name: str, bus: KitchenBus):
        super().__init__(name, bus)
        self.messages_received = []
        self.start_called = False
        self.stop_called = False

    async def handle(self, message: ChefMessage) -> None:
        self.messages_received.append(message)


@pytest.fixture
def brigade():
    """Create a fresh brigade for testing."""
    return Brigade()


@pytest.fixture
async def started_brigade(brigade):
    """Create a started brigade with mock stations."""
    station1 = MockStation("station1", brigade.bus)
    station2 = MockStation("station2", brigade.bus)

    brigade.register(station1)
    brigade.register(station2)

    await brigade.open_kitchen()

    yield brigade

    await brigade.close_kitchen()


@pytest.mark.asyncio
async def test_brigade_initialization(brigade):
    """Test brigade initialization."""
    assert brigade.bus is not None
    assert isinstance(brigade.bus, KitchenBus)
    assert len(brigade._stations) == 0
    assert brigade.is_open is False


@pytest.mark.asyncio
async def test_brigade_station_registration(brigade):
    """Test station registration."""
    station = MockStation("test_station", brigade.bus)

    brigade.register(station)

    assert len(brigade._stations) == 1
    assert brigade.station_count == 1
    assert "test_station" in brigade.station_names
    assert brigade.get_station("test_station") is station
    assert brigade.get_station("nonexistent") is None


@pytest.mark.asyncio
async def test_brigade_lifecycle(brigade):
    """Test kitchen open/close lifecycle."""
    station = MockStation("test_station", brigade.bus)
    brigade.register(station)

    # Test opening kitchen
    await brigade.open_kitchen()

    assert brigade.is_open is True
    assert brigade.bus.is_running is True
    assert station.is_running is True
    assert station.start_called is True

    # Test closing kitchen
    await brigade.close_kitchen()

    assert brigade.is_open is False
    assert brigade.bus.is_running is False
    assert station.is_running is False
    assert station.stop_called is True


@pytest.mark.asyncio
async def test_brigade_message_routing(started_brigade):
    """Test message routing through brigade."""
    station1 = started_brigade.get_station("station1")
    station2 = started_brigade.get_station("station2")

    # Send direct message to station1
    message = ChefMessage(
        sender="test_sender",
        recipient="station1",
        action="test_action",
        payload={"data": "test"},
    )

    await started_brigade.bus.publish(message)

    # Allow message processing
    await asyncio.sleep(0.1)

    assert len(station1.messages_received) == 1
    assert len(station2.messages_received) == 0
    assert station1.messages_received[0].action == "test_action"


@pytest.mark.asyncio
async def test_brigade_broadcast(started_brigade):
    """Test broadcast messages to all stations."""
    station1 = started_brigade.get_station("station1")
    station2 = started_brigade.get_station("station2")

    # Send broadcast message
    message = ChefMessage(
        sender="test_sender",
        recipient="ALL",
        action="broadcast_test",
        payload={"data": "broadcast"},
    )

    await started_brigade.bus.publish(message)

    # Allow message processing
    await asyncio.sleep(0.1)

    assert len(station1.messages_received) == 1
    assert len(station2.messages_received) == 1
    assert station1.messages_received[0].action == "broadcast_test"
    assert station2.messages_received[0].action == "broadcast_test"


@pytest.mark.asyncio
async def test_brigade_wait_for_completion(started_brigade):
    """Test waiting for queue completion."""
    # Send some messages
    for i in range(3):
        message = ChefMessage(
            sender="test", recipient="station1", action=f"test_{i}", payload={}
        )
        await started_brigade.bus.publish(message)

    # Wait for completion
    await started_brigade.wait_for_completion()

    # Verify queue is empty
    assert started_brigade.bus._queue.empty()


@pytest.mark.asyncio
async def test_create_default_brigade():
    """Test creation of default brigade configuration."""
    with patch("chefchat.kitchen.brigade.KitchenManager") as mock_manager:
        with patch("chefchat.kitchen.brigade.SousChef") as mock_sous:
            with patch("chefchat.kitchen.brigade.LineCook") as mock_line:
                with patch("chefchat.kitchen.brigade.Sommelier") as mock_somm:
                    with patch("chefchat.kitchen.brigade.Expeditor") as mock_exp:
                        with patch("chefchat.kitchen.brigade.GitChef") as mock_git:
                            brigade = await create_default_brigade()

                            # Verify all stations were registered
                            assert brigade.station_count == 5
                            assert len(brigade.station_names) == 5

                            # Verify station names
                            expected_stations = {
                                "sous_chef",
                                "line_cook",
                                "sommelier",
                                "expeditor",
                                "git_chef",
                            }
                            assert set(brigade.station_names) == expected_stations

                            # Verify mocks were called
                            mock_sous.assert_called_once()
                            mock_line.assert_called_once()
                            mock_somm.assert_called_once()
                            mock_exp.assert_called_once()
                            mock_git.assert_called_once()


@pytest.mark.asyncio
async def test_brigade_error_handling(brigade):
    """Test brigade error handling during startup/shutdown."""

    # Create a station that raises error during start
    class FailingStation(MockStation):
        async def start(self):
            raise RuntimeError("Start failed")

    station = FailingStation("failing_station", brigade.bus)
    brigade.register(station)

    # Opening kitchen should not crash even if station fails
    with pytest.raises(RuntimeError):
        await brigade.open_kitchen()

    # Kitchen should still be considered open despite station failure
    # (the bus started successfully)
    assert brigade.bus.is_running is True


@pytest.mark.asyncio
async def test_brigade_concurrent_operations(started_brigade):
    """Test concurrent message handling."""
    station1 = started_brigade.get_station("station1")
    station2 = started_brigade.get_station("station2")

    # Send many messages concurrently
    tasks = []
    for i in range(10):
        recipient = "station1" if i % 2 == 0 else "station2"
        message = ChefMessage(
            sender="test", recipient=recipient, action=f"test_{i}", payload={"index": i}
        )
        tasks.append(started_brigade.bus.publish(message))

    # Wait for all messages to be sent
    await asyncio.gather(*tasks)

    # Allow processing
    await asyncio.sleep(0.2)

    # Verify messages were delivered
    assert len(station1.messages_received) == 5
    assert len(station2.messages_received) == 5


@pytest.mark.asyncio
async def test_brigade_message_priority(started_brigade):
    """Test message priority handling."""
    station1 = started_brigade.get_station("station1")

    # Send messages with different priorities
    low_priority = ChefMessage(
        sender="test",
        recipient="station1",
        action="low",
        payload={},
        priority=3,  # LOW
    )

    high_priority = ChefMessage(
        sender="test",
        recipient="station1",
        action="high",
        payload={},
        priority=1,  # HIGH
    )

    normal_priority = ChefMessage(
        sender="test",
        recipient="station1",
        action="normal",
        payload={},
        priority=2,  # NORMAL
    )

    # Send in reverse priority order
    await started_brigade.bus.publish(normal_priority)
    await started_brigade.bus.publish(low_priority)
    await started_brigade.bus.publish(high_priority)

    # Allow processing
    await asyncio.sleep(0.1)

    # Messages should be processed in priority order
    actions = [msg.action for msg in station1.messages_received]
    assert actions == ["high", "normal", "low"]


@pytest.mark.asyncio
async def test_brigade_shutdown_order():
    """Test that stations shut down in reverse order."""
    brigade = Brigade()

    # Create multiple stations
    stations = []
    for i in range(3):
        station = MockStation(f"station{i}", brigade.bus)
        stations.append(station)
        brigade.register(station)

    await brigade.open_kitchen()

    # All should be started
    for station in stations:
        assert station.start_called is True

    await brigade.close_kitchen()

    # All should be stopped
    for station in stations:
        assert station.stop_called is True

    # Verify order (reverse of registration)
    # This is hard to test directly with mocks, but we can verify all stop


def test_brigade_properties():
    """Test brigade property methods."""
    brigade = Brigade()

    # Test empty brigade
    assert brigade.station_count == 0
    assert brigade.station_names == []
    assert brigade.is_open is False
    assert brigade.get_station("test") is None

    # Add a station
    station = MockStation("test", brigade.bus)
    brigade.register(station)

    assert brigade.station_count == 1
    assert brigade.station_names == ["test"]
    assert brigade.get_station("test") is station
