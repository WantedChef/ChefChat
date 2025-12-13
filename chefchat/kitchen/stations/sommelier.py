"""ChefChat Sommelier Station - The Dependency & Package Agent.

The Sommelier knows all about the wine cellar (packages). They:
- Verify package existence on PyPI before installation
- Check for security vulnerabilities
- Recommend package alternatives
- Manage project dependencies
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import httpx

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus, MessagePriority

if TYPE_CHECKING:
    pass


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
        latest_version = None
        yanked = False
        info_msg = ""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://pypi.org/pypi/{package_name}/json", timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    exists = True
                    info = data.get("info", {})
                    latest_version = info.get("version")
                    yanked = info.get("yanked", False)

                    if yanked:
                        is_safe = False
                        info_msg = f"Package '{package_name}' is YANKED on PyPI."
                    else:
                        info_msg = f"Found '{package_name}' v{latest_version}."
                        self._verified_packages.add(package_name)
                elif response.status_code == 404:
                    exists = False
                    info_msg = f"Package '{package_name}' not found on PyPI."
                else:
                    exists = False
                    info_msg = f"PyPI returned status {response.status_code}."

        except Exception as e:
            exists = False
            info_msg = f"Error checking PyPI: {e}"

        # Report back to requester
        await self.send(
            recipient=requester,
            action="package_verified",
            payload={
                "package": package_name,
                "exists": exists,
                "is_safe": is_safe,
                "recommended_version": latest_version or "unknown",
                "message": info_msg,
            },
        )

        # Also log to TUI for visibility
        if exists:
            log_type = (
                "system" if is_safe else "system"
            )  # Use system for both for now, maybe error for unsafe
            content = f"🍷 **Sommelier**: {info_msg}"
            if not is_safe:
                content = f"⚠️ **Sommelier**: {info_msg}"

            await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={"type": log_type, "content": content},
            )
        elif not exists and package_name:
            await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={"type": "system", "content": f"🍷 **Sommelier**: {info_msg}"},
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
        # For now, we only implemented verification.

        await self.send(
            recipient=requester,
            action="package_recommendations",
            payload={
                "use_case": use_case,
                "recommendations": [],
                "message": "Recommendation engine not yet fully trained (Phase 2).",
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

        vulnerabilities = []
        all_clear = True
        tool_used = "none"

        # Try using pip-audit if installed
        try:
            # Check if pip-audit is available first or just try running it
            # We assume uv is available since this is a uv project
            process = await asyncio.create_subprocess_exec(
                "uv",
                "run",
                "pip-audit",
                "-f",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if (
                process.returncode == 0 or process.returncode == 1
            ):  # 1 means vulnerabilities found but tool ran ok
                tool_used = "pip-audit"
                try:
                    audit_data = json.loads(stdout.decode())
                    if "dependencies" in audit_data:
                        for dep in audit_data["dependencies"]:
                            if dep.get("vulns"):
                                for vuln in dep["vulns"]:
                                    vulnerabilities.append({
                                        "package": dep.get("name"),
                                        "version": dep.get("version"),
                                        "id": vuln.get("id"),
                                        "description": vuln.get("description"),
                                    })
                                    all_clear = False
                except json.JSONDecodeError:
                    pass  # Failed to parse json
            else:
                # pip-audit might not be installed or failed
                pass

        except FileNotFoundError:
            # uv not found
            pass

        if tool_used == "none":
            await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={
                    "type": "system",
                    "content": "⚠️ **Sommelier**: `pip-audit` not found. Skipping deep security scan.",
                },
            )
        elif not all_clear:
            await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={
                    "type": "system",
                    "content": f"⚠️ **Sommelier**: Found {len(vulnerabilities)} vulnerabilities!",
                },
            )

        await self.send(
            recipient=requester,
            action="security_report",
            payload={
                "packages_checked": len(packages),
                "vulnerabilities": vulnerabilities,
                "all_clear": all_clear,
                "tool_used": tool_used,
            },
            priority=MessagePriority.HIGH,
        )
