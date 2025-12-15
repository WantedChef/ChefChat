"""Input validation utilities for kitchen stations.

Provides centralized validation for common input types to ensure
security and consistency across all stations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError


class ValidationError(Exception):
    """Raised when input validation fails."""


class InputValidator:
    """Centralized input validation for kitchen operations."""

    # Safety patterns
    DANGEROUS_CHARS = re.compile(r'[<>"\'\x00-\x1f\x7f-\x9f]')
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
            raise ValidationError("Payload must be a dictionary")

        # Check payload size (rough estimate)
        payload_str = str(payload)
        if len(payload_str.encode("utf-8")) > cls.MAX_MESSAGE_SIZE:
            raise ValidationError("Payload too large")

        # Recursively validate string values
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

        # Check for dangerous characters
        if cls.DANGEROUS_CHARS.search(value):
            raise ValidationError(
                f"Dangerous characters detected in {context}: {value}"
            )

    @classmethod
    def validate_ticket_id(cls, ticket_id: str) -> str:
        """Validate ticket ID format."""
        if not isinstance(ticket_id, str):
            raise ValidationError("Ticket ID must be a string")

        if not cls.TICKET_ID_PATTERN.match(ticket_id):
            raise ValidationError(f"Invalid ticket ID format: {ticket_id}")

        return ticket_id

    @classmethod
    def validate_station_name(cls, name: str) -> str:
        """Validate station name format."""
        if not isinstance(name, str):
            raise ValidationError("Station name must be a string")

        if not cls.STATION_NAME_PATTERN.match(name):
            raise ValidationError(f"Invalid station name format: {name}")

        return name

    @classmethod
    def validate_action(cls, action: str) -> str:
        """Validate action name."""
        if not isinstance(action, str):
            raise ValidationError("Action must be a string")

        # Only allow alphanumeric, underscore, and hyphen
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", action):
            raise ValidationError(f"Invalid action format: {action}")

        return action

    @classmethod
    def validate_command_length(cls, command: str) -> str:
        """Validate command length."""
        if not isinstance(command, str):
            raise ValidationError("Command must be a string")

        if len(command) > cls.MAX_COMMAND_LENGTH:
            raise ValidationError("Command too long")

        return command

    @classmethod
    def validate_path_length(cls, path: str) -> str:
        """Validate path length."""
        if not isinstance(path, str):
            raise ValidationError("Path must be a string")

        if len(path) > cls.MAX_PATH_LENGTH:
            raise ValidationError("Path too long")

        return path


class SafeMessage(BaseModel):
    """Pydantic model for safe message validation."""

    sender: str
    recipient: str
    action: str
    payload: dict[str, Any]

    def model_post_init(self, __context) -> None:
        """Validate message after initialization."""
        InputValidator.validate_station_name(self.sender)
        InputValidator.validate_station_name(self.recipient)
        InputValidator.validate_action(self.action)
        InputValidator.validate_message_payload(self.payload)
