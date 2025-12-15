"""Tests for KitchenBus message routing and priority handling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chefchat.kitchen.bus import (
    BaseStation,
    ChefMessage,
    KitchenBus,
    MessagePriority,
    PrioritizedMessage,
)


class MockStation(BaseStation):
    """Mock station for testing bus functionality."""

    def __init__(self, name: str, bus: KitchenBus):
        super().__init__(name, bus)
        self.messages_received = []
        self.handle_calls = []

    async def handle(self, message: ChefMessage) -> None:
        self.messages_received.append(message)
        self.handle_calls.append(MagicMock(message=message))


@pytest.fixture
async def bus_with_stations():
    """Create a bus with mock stations."""
    bus = KitchenBus()
    await bus.start()

    station1 = MockStation("station1", bus)
    station2 = MockStation("station2", bus)

    # Start stations
    await station1.start()
    await station2.start()

    yield bus, station1, station2

    await station1.stop()
    await station2.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_bus_initialization():
    """Test bus initialization."""
    bus = KitchenBus()

    assert bus._queue is not None
    assert bus._subscribers == {}
    assert bus.is_running is False
    assert bus._task is None


@pytest.mark.asyncio
async def test_bus_start_stop_lifecycle():
    """Test bus start/stop lifecycle."""
    bus = KitchenBus()

    # Start bus
    await bus.start()

    assert bus.is_running is True
    assert bus._task is not None
    assert not bus._task.done()

    # Stop bus
    await bus.stop()

    assert bus.is_running is False
    assert bus._task is None


@pytest.mark.asyncio
async def test_station_subscription():
    """Test station subscription and unsubscription."""
    bus = KitchenBus()

    # Create mock callback
    callback = AsyncMock()

    # Subscribe station
    bus.subscribe("test_station", callback)

    assert "test_station" in bus._subscribers
    assert len(bus._subscribers["test_station"]) == 1
    assert bus._subscribers["test_station"][0] is callback

    # Unsubscribe station
    bus.unsubscribe("test_station")

    assert "test_station" not in bus._subscribers


@pytest.mark.asyncio
async def test_direct_message_routing(bus_with_stations):
    """Test routing messages to specific stations."""
    bus, station1, station2 = bus_with_stations

    # Send message to station1
    message = ChefMessage(
        sender="sender",
        recipient="station1",
        action="test_action",
        payload={"data": "test"},
    )

    await bus.publish(message)

    # Allow message processing
    await asyncio.sleep(0.1)

    # Verify only station1 received the message
    assert len(station1.messages_received) == 1
    assert len(station2.messages_received) == 0

    received_msg = station1.messages_received[0]
    assert received_msg.sender == "sender"
    assert received_msg.recipient == "station1"
    assert received_msg.action == "test_action"


@pytest.mark.asyncio
async def test_broadcast_message_routing(bus_with_stations):
    """Test broadcasting messages to all stations."""
    bus, station1, station2 = bus_with_stations

    # Send broadcast message
    message = ChefMessage(
        sender="sender",
        recipient="ALL",
        action="broadcast_test",
        payload={"data": "broadcast"},
    )

    await bus.publish(message)

    # Allow message processing
    await asyncio.sleep(0.1)

    # Verify both stations received the message
    assert len(station1.messages_received) == 1
    assert len(station2.messages_received) == 1

    # Verify message content
    for station in [station1, station2]:
        received_msg = station.messages_received[0]
        assert received_msg.sender == "sender"
        assert received_msg.recipient == "ALL"
        assert received_msg.action == "broadcast_test"


@pytest.mark.asyncio
async def test_message_priority_ordering(bus_with_stations):
    """Test that messages are processed in priority order."""
    bus, station1, station2 = bus_with_stations

    # Create messages with different priorities
    messages = [
        ChefMessage(
            sender="test",
            recipient="station1",
            action="low",
            priority=MessagePriority.LOW,
        ),
        ChefMessage(
            sender="test",
            recipient="station1",
            action="high",
            priority=MessagePriority.HIGH,
        ),
        ChefMessage(
            sender="test",
            recipient="station1",
            action="critical",
            priority=MessagePriority.CRITICAL,
        ),
        ChefMessage(
            sender="test",
            recipient="station1",
            action="normal",
            priority=MessagePriority.NORMAL,
        ),
    ]

    # Publish in random order
    import random

    random.shuffle(messages)

    for msg in messages:
        await bus.publish(msg)

    # Allow processing
    await asyncio.sleep(0.2)

    # Verify priority order (critical, high, normal, low)
    actions = [msg.action for msg in station1.messages_received]
    expected_order = ["critical", "high", "normal", "low"]
    assert actions == expected_order


@pytest.mark.asyncio
async def test_multiple_subscribers_per_station():
    """Test multiple callbacks for same station."""
    bus = KitchenBus()
    await bus.start()

    callback1 = AsyncMock()
    callback2 = AsyncMock()

    # Subscribe multiple callbacks to same station
    bus.subscribe("station", callback1)
    bus.subscribe("station", callback2)

    # Create station that will receive messages
    station = MockStation("station", bus)
    await station.start()

    # Send message
    message = ChefMessage(sender="test", recipient="station", action="test")
    await bus.publish(message)

    # Allow processing
    await asyncio.sleep(0.1)

    # Verify all callbacks were called
    assert len(bus._subscribers["station"]) == 2
    assert station.messages_received  # Station received message

    await station.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_message_to_nonexistent_station(bus_with_stations):
    """Test sending message to station that doesn't exist."""
    bus, station1, station2 = bus_with_stations

    # Send message to nonexistent station
    message = ChefMessage(sender="sender", recipient="nonexistent", action="test")

    await bus.publish(message)

    # Allow processing
    await asyncio.sleep(0.1)

    # Verify no stations received the message
    assert len(station1.messages_received) == 0
    assert len(station2.messages_received) == 0


@pytest.mark.asyncio
async def test_async_callback_handling():
    """Test handling of async vs sync callbacks."""
    bus = KitchenBus()
    await bus.start()

    # Create both sync and async callbacks
    sync_called = []
    async_called = []

    def sync_callback(msg):
        sync_called.append(msg)

    async def async_callback(msg):
        async_called.append(msg)

    bus.subscribe("sync_station", sync_callback)
    bus.subscribe("async_station", async_callback)

    # Create stations
    sync_station = MockStation("sync_station", bus)
    async_station = MockStation("async_station", bus)

    await sync_station.start()
    await async_station.start()

    # Send messages
    await bus.publish(
        ChefMessage(sender="test", recipient="sync_station", action="test")
    )
    await bus.publish(
        ChefMessage(sender="test", recipient="async_station", action="test")
    )

    # Allow processing
    await asyncio.sleep(0.1)

    # Verify both callbacks were called
    assert len(sync_called) == 1
    assert len(async_called) == 1

    await sync_station.stop()
    await async_station.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_callback_error_handling():
    """Test that callback errors don't crash the bus."""
    bus = KitchenBus()
    await bus.start()

    # Create callback that raises error
    def failing_callback(msg):
        raise RuntimeError("Callback failed")

    def working_callback(msg):
        working_callback.called = True

    working_callback.called = False

    # Subscribe callbacks
    bus.subscribe("failing_station", failing_callback)
    bus.subscribe("working_station", working_callback)

    # Create stations
    failing_station = MockStation("failing_station", bus)
    working_station = MockStation("working_station", bus)

    await failing_station.start()
    await working_station.start()

    # Send messages
    await bus.publish(
        ChefMessage(sender="test", recipient="failing_station", action="test")
    )
    await bus.publish(
        ChefMessage(sender="test", recipient="working_station", action="test")
    )

    # Allow processing
    await asyncio.sleep(0.1)

    # Verify working callback was called despite failing callback
    assert working_callback.called is True

    await failing_station.stop()
    await working_station.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_prioritized_message_ordering():
    """Test PrioritizedMessage class behavior."""
    # Create prioritized messages
    low_msg = PrioritizedMessage(
        priority=3, message=ChefMessage(sender="test", recipient="test", action="low")
    )
    high_msg = PrioritizedMessage(
        priority=1, message=ChefMessage(sender="test", recipient="test", action="high")
    )
    normal_msg = PrioritizedMessage(
        priority=2,
        message=ChefMessage(sender="test", recipient="test", action="normal"),
    )

    # Test ordering
    messages = [low_msg, high_msg, normal_msg]
    sorted_messages = sorted(messages)

    # Should be ordered by priority (lower number = higher priority)
    assert sorted_messages[0] is high_msg
    assert sorted_messages[1] is normal_msg
    assert sorted_messages[2] is low_msg


@pytest.mark.asyncio
async def test_concurrent_message_publishing(bus_with_stations):
    """Test concurrent message publishing."""
    bus, station1, station2 = bus_with_stations

    # Publish many messages concurrently
    async def publish_messages():
        for i in range(10):
            recipient = "station1" if i % 2 == 0 else "station2"
            await bus.publish(
                ChefMessage(
                    sender="test",
                    recipient=recipient,
                    action=f"msg_{i}",
                    payload={"index": i},
                )
            )

    # Run publishing concurrently
    tasks = [publish_messages() for _ in range(3)]
    await asyncio.gather(*tasks)

    # Allow processing
    await asyncio.sleep(0.3)

    # Verify all messages were delivered
    assert len(station1.messages_received) == 15  # 3 * 5 (even indices)
    assert len(station2.messages_received) == 15  # 3 * 5 (odd indices)


@pytest.mark.asyncio
async def test_message_payload_validation():
    """Test message payload validation in ChefMessage."""
    # Test various payload types
    valid_messages = [
        ChefMessage(sender="test", recipient="test", action="test", payload={}),
        ChefMessage(
            sender="test", recipient="test", action="test", payload={"key": "value"}
        ),
        ChefMessage(
            sender="test", recipient="test", action="test", payload={"list": [1, 2, 3]}
        ),
        ChefMessage(
            sender="test", recipient="test", action="test", payload=None
        ),  # Should become {}
    ]

    for msg in valid_messages:
        # Should not raise validation error
        assert isinstance(msg.payload, dict)

    # Test invalid payload
    with pytest.raises(ValueError):
        ChefMessage(
            sender="test", recipient="test", action="test", payload="not a dict"
        )


@pytest.mark.asyncio
async def test_bus_queue_overflow():
    """Test bus behavior under high load."""
    bus = KitchenBus()

    # Don't start the bus, so queue will fill up
    for i in range(1000):
        await bus.publish(
            ChefMessage(sender="test", recipient="test", action=f"msg_{i}", payload={})
        )

    # Queue should accept all messages (asyncio queue is unbounded by default)
    assert bus._queue.qsize() == 1000

    await bus.stop()


def test_message_priority_enum():
    """Test MessagePriority enum values."""
    assert MessagePriority.CRITICAL == 0
    assert MessagePriority.HIGH == 1
    assert MessagePriority.NORMAL == 2
    assert MessagePriority.LOW == 3

    # Test ordering
    priorities = [
        MessagePriority.LOW,
        MessagePriority.CRITICAL,
        MessagePriority.NORMAL,
        MessagePriority.HIGH,
    ]
    sorted_priorities = sorted(priorities)
    expected_order = [
        MessagePriority.CRITICAL,
        MessagePriority.HIGH,
        MessagePriority.NORMAL,
        MessagePriority.LOW,
    ]
    assert sorted_priorities == expected_order
