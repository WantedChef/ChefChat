"""Input validation utilities for kitchen stations.

Provides centralized validation for common input types to ensure
security and consistency across all stations.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel


class InputValidationError(Exception):
    """Raised when input validation fails."""


class PathValidator:
    """Validates and sanitizes file paths to prevent traversal attacks."""

    @staticmethod
    def validate_file_path(file_path: str | Path, allowed_root: Path) -> Path | None:
        """Validate a file path is within allowed bounds.

        Args:
            file_path: The path to validate
            allowed_root: The root directory that paths must stay within

        Returns:
            Resolved absolute path if valid, None if invalid
        """
        try:
            # Convert to Path object
            path = Path(file_path)

            # Resolve to absolute path (this normalizes ../ etc.)
            resolved = path.resolve()

            # Make sure the allowed root is also resolved
            root = allowed_root.resolve()

            # Check if the resolved path is within the allowed root
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                # Path is outside allowed root
                return None

        except (OSError, ValueError):
            # Path resolution failed
            return None


class InputValidator:
    """Centralized input validation for kitchen operations."""

    # Safety patterns
    # Only control characters are dangerous for user content (backticks are common in markdown)
    DANGEROUS_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
    # For code/command contexts, be more restrictive but still allow quotes for user messages
    DANGEROUS_COMMAND_CHARS = re.compile(r"[<>\x00-\x1f\x7f-\x9f`]")
    # For actual command execution (not user content), use strict pattern
    DANGEROUS_EXEC_CHARS = re.compile(r'[<>"\'\x00-\x1f\x7f-\x9f`]')
    TICKET_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")
    STATION_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

    # Size limits
    MAX_MESSAGE_SIZE = 10_000_000  # 10MB
    MAX_COMMAND_LENGTH = 10_000
    MAX_PATH_LENGTH = 4_000

    @classmethod
    def validate_message_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate message payload for safety."""
        if not isinstance(payload, dict):
            raise InputValidationError("Payload must be a dictionary")

        # Check payload size (rough estimate)
        payload_str = str(payload)
        if len(payload_str.encode("utf-8")) > cls.MAX_MESSAGE_SIZE:
            raise InputValidationError("Payload too large")

        # Recursively validate string values with content-appropriate validation
        cls._validate_strings_in_dict(payload)

        return payload

    @classmethod
    def _validate_strings_in_dict(cls, obj: Any, path: str = "") -> None:
        """Recursively validate all string values in a dict."""
        if isinstance(obj, str):
            cls._validate_string(obj, path)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                cls._validate_strings_in_dict(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                cls._validate_strings_in_dict(
                    item, f"{path}[{i}]" if path else f"[{i}]"
                )

    @classmethod
    def _validate_string(cls, value: str, context: str = "") -> None:
        """Validate individual string for dangerous content."""
        if not value:
            return

        # Use context-appropriate validation
        dangerous_pattern = cls.DANGEROUS_CHARS
        if any(keyword in context.lower() for keyword in ["action", "command"]):
            # For action/command contexts, be more restrictive (but allow quotes for messages)
            dangerous_pattern = cls.DANGEROUS_COMMAND_CHARS

        # Check for dangerous characters
        if dangerous_pattern.search(value):
            raise InputValidationError(
                f"Dangerous characters detected in {context}: {value}"
            )

    @classmethod
    def validate_ticket_id(cls, ticket_id: str) -> str:
        """Validate ticket ID format."""
        if not isinstance(ticket_id, str):
            raise InputValidationError("Ticket ID must be a string")

        if not cls.TICKET_ID_PATTERN.match(ticket_id):
            raise InputValidationError(f"Invalid ticket ID format: {ticket_id}")

        return ticket_id

    @classmethod
    def validate_station_name(cls, name: str) -> str:
        """Validate station name format."""
        if not isinstance(name, str):
            raise InputValidationError("Station name must be a string")

        if not cls.STATION_NAME_PATTERN.match(name):
            raise InputValidationError(f"Invalid station name format: {name}")

        return name

    @classmethod
    def validate_action(cls, action: str) -> str:
        """Validate action name."""
        if not isinstance(action, str):
            raise InputValidationError("Action must be a string")

        # Only allow alphanumeric, underscore, and hyphen
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", action):
            raise InputValidationError(f"Invalid action format: {action}")

        return action

    @classmethod
    def validate_command_length(cls, command: str) -> str:
        """Validate command length."""
        if not isinstance(command, str):
            raise InputValidationError("Command must be a string")

        if len(command) > cls.MAX_COMMAND_LENGTH:
            raise InputValidationError("Command too long")

        return command

    @classmethod
    def validate_path_length(cls, path: str) -> str:
        """Validate path length."""
        if not isinstance(path, str):
            raise InputValidationError("Path must be a string")

        if len(path) > cls.MAX_PATH_LENGTH:
            raise InputValidationError("Path too long")

        return path


class SafeMessage(BaseModel):
    """Pydantic model for safe message validation."""

    sender: str
    recipient: str
    action: str
    payload: dict[str, Any]

    def model_post_init(self, __context: Any) -> None:
        """Validate message after initialization."""
        InputValidator.validate_station_name(self.sender)
        InputValidator.validate_station_name(self.recipient)
        InputValidator.validate_action(self.action)
        InputValidator.validate_message_payload(self.payload)
