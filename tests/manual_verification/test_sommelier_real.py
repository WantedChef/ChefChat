from __future__ import annotations

import asyncio

from chefchat.kitchen.bus import ChefMessage, KitchenBus
from chefchat.kitchen.manager import KitchenManager
from chefchat.kitchen.stations.sommelier import Sommelier


async def verify_sommelier():
    print("🍷 Testing Sommelier (Real PyPI check)...")
    bus = KitchenBus()
    manager = KitchenManager()
    sommelier = Sommelier(bus, manager)

    # We need to capture the messages sent by Sommelier
    captured_messages = []

    async def mock_send(message: ChefMessage):
        if message.sender == "sommelier":
            captured_messages.append(message)

    bus.subscribe("tui", mock_send)
    bus.subscribe("test_runner", mock_send)  # Subscribe ourselves

    # Start the bus
    await bus.start()

    # Send a request to verify 'requests' (which definitely exists)
    await sommelier.handle(
        ChefMessage(
            sender="test_runner",
            recipient="sommelier",
            action="verify_package",
            payload={"package": "requests"},
        )
    )

    # Give it a moment (it does network calls now!)
    await asyncio.sleep(2)

    # Check results
    found = False
    for msg in captured_messages:
        if msg.action == "package_verified":
            print(f"✅ Received verification: {msg.payload}")
            if msg.payload.get("exists") and msg.payload.get("package") == "requests":
                found = True

    if found:
        print("🎉 SUCCESS: Sommelier correctly verified 'requests' on PyPI.")
    else:
        print("❌ FAILURE: Sommelier did not verify 'requests'.")

    await bus.stop()


if __name__ == "__main__":
    asyncio.run(verify_sommelier())
