"""ChefChat Kitchen Brigade - The Actor Manager.

The Brigade Manager oversees all kitchen stations, starting and stopping
them as a coordinated unit. In a real kitchen, the Head Chef manages
the brigade - here, this class does that job.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chefchat.kitchen.bus import BaseStation, KitchenBus

if TYPE_CHECKING:
    pass


class Brigade:
    """Manages the kitchen brigade (all station actors).

    Responsibilities:
    - Spawn and supervise all stations
    - Coordinate startup/shutdown sequences
    - Provide access to the central bus
    """

    def __init__(self) -> None:
        """Initialize the brigade with a fresh kitchen bus."""
        self._bus = KitchenBus()
        self._stations: dict[str, BaseStation] = {}
        self._running = False

    @property
    def bus(self) -> KitchenBus:
        """Get the kitchen bus for external access."""
        return self._bus

    def register(self, station: BaseStation) -> None:
        """Register a station with the brigade.

        Args:
            station: The station to add to the brigade
        """
        self._stations[station.name] = station

    def get_station(self, name: str) -> BaseStation | None:
        """Get a station by name.

        Args:
            name: The station name to look up

        Returns:
            The station if found, None otherwise
        """
        return self._stations.get(name)

    async def open_kitchen(self) -> None:
        """Start all stations and the bus ('the kitchen opens').

        Stations are started in registration order.
        The bus starts first to be ready for messages.
        """
        # Fire up the bus first
        await self._bus.start()

        # Start each station
        for station in self._stations.values():
            await station.start()

        self._running = True

    async def close_kitchen(self) -> None:
        """Stop all stations and the bus ('the kitchen closes').

        Stations are stopped in reverse order, then the bus.
        Allows all pending messages to be processed first.
        """
        self._running = False

        # Stop stations in reverse order
        for station in reversed(list(self._stations.values())):
            await station.stop()

        # Stop the bus last
        await self._bus.stop()

    async def wait_for_completion(self) -> None:
        """Wait for all queued work to complete."""
        # Wait for the bus queue to drain
        await self._bus._queue.join()

    @property
    def is_open(self) -> bool:
        """Check if the kitchen is open (running)."""
        return self._running

    @property
    def station_names(self) -> list[str]:
        """Get list of registered station names."""
        return list(self._stations.keys())

    @property
    def station_count(self) -> int:
        """Get number of registered stations."""
        return len(self._stations)


async def create_default_brigade() -> Brigade:
    """Create a brigade with the standard stations.

    This is a factory function that sets up the default kitchen
    configuration with Sous Chef, Line Cooks, and Sommelier.

    Returns:
        A fully configured Brigade ready to open
    """
    # Imports kept inside to avoid circulars at module import time
    from chefchat.kitchen.brain import KitchenBrain
    from chefchat.kitchen.stations.expeditor import Expeditor
    from chefchat.kitchen.stations.line_cook import LineCook
    from chefchat.kitchen.stations.sommelier import Sommelier
    from chefchat.kitchen.stations.sous_chef import SousChef

    brigade = Brigade()

    # Initialize the brain
    brain = KitchenBrain()

    # The planning station (orchestrator)
    sous_chef = SousChef(brigade.bus)
    brigade.register(sous_chef)

    # The coding station (needs brain)
    line_cook = LineCook(brigade.bus, brain)
    brigade.register(line_cook)

    # The dependency/package station
    sommelier = Sommelier(brigade.bus)
    brigade.register(sommelier)

    # The QA / testing station
    expeditor = Expeditor(brigade.bus)
    brigade.register(expeditor)

    return brigade
