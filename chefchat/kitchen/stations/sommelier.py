"""ChefChat Sommelier Station - The Dependency & Package Agent.

The Sommelier knows all about the wine cellar (packages). They:
- Verify package existence on PyPI before installation
- Check for security vulnerabilities
- Recommend package alternatives
- Manage project dependencies
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import json
import logging
from typing import TYPE_CHECKING

import httpx

from chefchat.kitchen.bus import BaseStation, ChefMessage, KitchenBus, MessagePriority

if TYPE_CHECKING:
    from chefchat.kitchen.manager import KitchenManager

logger = logging.getLogger(__name__)


class Sommelier(BaseStation):
    """The dependency and package verification station.

    Handles:
    - PyPI package verification
    - Security vulnerability checks
    - Dependency resolution
    - Package recommendations
    """

    def __init__(self, bus: KitchenBus, manager: KitchenManager) -> None:
        """Initialize the Sommelier station.

        Args:
            bus: The kitchen bus to connect to
            manager: The kitchen manager for LLM access
        """
        super().__init__("sommelier", bus)
        self.manager = manager
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

                if response.status_code == HTTPStatus.OK:
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
                elif response.status_code == HTTPStatus.NOT_FOUND:
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
            log_type = "system"  # Use system for both for now
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

        # Use the manager to generate recommendations with streaming
        try:
            generated_response = ""
            async for chunk in self.manager.stream_response(
                f"Identify the best packages for this use case: {use_case}",
                system=self.manager.RECOMMEND_SYSTEM_PROMPT,
            ):
                generated_response += chunk
                await self.send(
                    recipient="tui",
                    action="STREAM_UPDATE",
                    payload={"content": chunk, "full_content": generated_response},
                )

            # Final delivery
            await self.send(
                recipient=requester,
                action="package_recommendations",
                payload={
                    "use_case": use_case,
                    "recommendations": [],
                    "message": generated_response,
                },
            )

            # Announce completion
            await self.send(
                recipient="tui",
                action="status_update",
                payload={
                    "station": self.name,
                    "status": "complete",
                    "message": "🍷 Selection presented.",
                },
            )

        except Exception as e:
            await self.send(
                recipient="tui",
                action="LOG_MESSAGE",
                payload={"type": "error", "content": f"❌ **Sommelier Error**: {e}"},
            )
            await self.send(
                recipient=requester,
                action="package_recommendations",
                payload={
                    "use_case": use_case,
                    "error": str(e),
                    "message": "Could not generate recommendations.",
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

        vulnerabilities: list[dict] = []
        all_clear = True
        tool_used = "none"

        # Try using pip-audit if installed
        audit_result = await self._run_pip_audit()
        if audit_result is not None:
            tool_used = "pip-audit"
            vulnerabilities = self._parse_audit_results(audit_result)
            all_clear = len(vulnerabilities) == 0

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

    async def _run_pip_audit(self) -> bytes | None:
        """Run pip-audit and return stdout if successful.

        Returns:
            stdout bytes if pip-audit ran, None otherwise
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "uv",
                "run",
                "pip-audit",
                "-f",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            # 0 = clean, 1 = vulnerabilities found (but tool ran ok)
            if process.returncode in {0, 1}:
                return stdout
        except FileNotFoundError:
            pass  # uv not found
        return None

    def _parse_audit_results(self, stdout: bytes) -> list[dict]:
        """Parse pip-audit JSON output into vulnerability list.

        Args:
            stdout: Raw stdout bytes from pip-audit

        Returns:
            List of vulnerability dicts
        """
        vulnerabilities: list[dict] = []
        try:
            audit_data = json.loads(stdout.decode())
            for dep in audit_data.get("dependencies", []):
                for vuln in dep.get("vulns", []):
                    vulnerabilities.append({
                        "package": dep.get("name"),
                        "version": dep.get("version"),
                        "id": vuln.get("id"),
                        "description": vuln.get("description"),
                    })
        except json.JSONDecodeError:
            pass  # Failed to parse json
        return vulnerabilities
