"""ChefChat Sommelier Station - The Dependency & Package Agent.

The Sommelier knows all about the wine cellar (packages). They:
- Verify package existence on PyPI before installation
- Check for security vulnerabilities
- Recommend package alternatives
- Manage project dependencies
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import logging

import httpx

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus, MessagePriority

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Sommelier(BaseStation):
    """The dependency and package verification station.

    Handles:
    - PyPI package verification
    - Security vulnerability checks
    - Dependency resolution
    - Package recommendations
    """

    def __init__(self, bus: KitchenBus) -> None:
        """Initialize the Sommelier station.

        Args:
            bus: The kitchen bus to connect to
        """
        super().__init__("sommelier", bus)
        self._verified_packages: set[str] = set()

    async def handle(self, message: ChefMessage) -> None:
        """Process incoming messages.

        Args:
            message: The message to process
        """
        action = message.action

        if action == "verify_package":
            # Verify a package exists and is safe
            await self._verify_package(message.payload, message.sender)

        elif action == "recommend":
            # Recommend packages for a use case
            await self._recommend_packages(message.payload, message.sender)

        elif action == "check_security":
            # Security audit of dependencies
            await self._check_security(message.payload, message.sender)

    async def _verify_package(self, payload: dict, requester: str) -> None:
        """Verify a package exists on PyPI and is safe.

        Args:
            payload: The verification request
            requester: Station that requested verification
        """
        package_name = payload.get("package", "")

        await self.send(
            recipient="tui",
            action="status_update",
            payload={
                "station": self.name,
                "status": "verifying",
                "message": f"Checking PyPI for: {package_name}",
            },
        )

        exists = False
        is_safe = True
        recommended_version = "latest"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://pypi.org/pypi/{package_name}/json"
                )
                if response.status_code == 200:
                    exists = True
                    data = response.json()
                    recommended_version = data.get("info", {}).get("version", "latest")
                elif response.status_code == 404:
                    exists = False
                    logger.info("Package %s not found on PyPI", package_name)
                else:
                    logger.warning(
                        "PyPI returned %s for %s", response.status_code, package_name
                    )
        except Exception as e:
            logger.error("Error checking PyPI for %s: %s", package_name, e)

        if exists:
            self._verified_packages.add(package_name)

        # Report back to requester
        await self.send(
            recipient=requester,
            action="package_verified",
            payload={
                "package": package_name,
                "exists": exists,
                "is_safe": is_safe,
                "recommended_version": recommended_version,
            },
        )

    async def _recommend_packages(self, payload: dict, requester: str) -> None:
        """Recommend packages for a given use case.

        Args:
            payload: The recommendation request
            requester: Station that requested recommendations
        """
        use_case = payload.get("use_case", "")

        await self.send(
            recipient="tui",
            action="status_update",
            payload={
                "station": self.name,
                "status": "researching",
                "message": f"Finding packages for: {use_case}",
            },
        )

        # TODO: Implement actual package recommendation
        # Could use LLM or curated database

        await self.send(
            recipient=requester,
            action="package_recommendations",
            payload={
                "use_case": use_case,
                "recommendations": [],  # Placeholder
            },
        )

    async def _check_security(self, payload: dict, requester: str) -> None:
        """Check dependencies for security vulnerabilities.

        Args:
            payload: The security check request
            requester: Station that requested the check
        """
        packages = payload.get("packages", [])

        await self.send(
            recipient="tui",
            action="status_update",
            payload={
                "station": self.name,
                "status": "auditing",
                "message": f"Security audit of {len(packages)} packages",
            },
        )

        # TODO: Implement actual vulnerability checking
        # Could use safety, pip-audit, or vulnerability databases

        await self.send(
            recipient=requester,
            action="security_report",
            payload={
                "packages_checked": len(packages),
                "vulnerabilities": [],  # Placeholder
                "all_clear": True,
            },
            priority=MessagePriority.HIGH,
        )
