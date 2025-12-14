from __future__ import annotations

import asyncio
import logging
from unittest.mock import Mock

import pytest

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus


class MockStation(BaseStation):
    async def handle(self, message: ChefMessage) -> None:
        pass

@pytest.mark.asyncio
async def test_queue_overflow_logging(caplog):
    bus = Mock(spec=KitchenBus)
    station = MockStation("test_station", bus)

    # Force the queue to have a small size for testing
    station._inbox = asyncio.Queue(maxsize=1)

    message1 = ChefMessage(sender="sender", recipient="test_station", action="test")
    message2 = ChefMessage(sender="sender", recipient="test_station", action="test")

    station._receive(message1)

    with caplog.at_level(logging.WARNING):
        station._receive(message2)

    assert "Inbox full for station test_station" in caplog.text
    assert "Dropping message" in caplog.text
