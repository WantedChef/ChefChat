"""Security utilities for redacting sensitive information."""

from __future__ import annotations

import re
from typing import Any


class SecurityRedactor:
    """Redacts sensitive information from logs and messages."""

    # Patterns for sensitive data
    API_KEY_PATTERNS = [
        # Generic API keys (alphanumeric, 20+ chars)
        r'(api[_-]?key["\'\s]*[:=]["\'\s]*)([a-zA-Z0-9]{20,})',
        # Bearer tokens
        r'(bearer["\'\s]*[:=]["\'\s]*)([a-zA-Z0-9._-]{20,})',
        # GitHub tokens (ghp_)
        r"(ghp_[a-zA-Z0-9]{36})",
        # OpenAI API keys (sk-)
        r"(sk-[a-zA-Z0-9]{48})",
        # Mistral API keys
        r"([a-zA-Z0-9_-]{32,})",  # General long tokens
    ]

    # Password patterns
    PASSWORD_PATTERNS = [
        r'(password["\'\s]*[:=]["\'\s]*)([^"\'\\s]{8,})',
        r'(passwd["\'\s]*[:=]["\'\s]*)([^"\'\\s]{8,})',
        r'(pwd["\'\s]*[:=]["\'\s]*)([^"\'\\s]{8,})',
    ]

    # URL patterns with credentials
    URL_CREDS_PATTERNS = [r"(https?://)([^:@]+:[^:@]+@)([^/]+)"]

    @classmethod
    def redact_sensitive_data(cls, text: str) -> str:
        """Redact sensitive information from text.

        Args:
            text: Text that may contain sensitive information

        Returns:
            Text with sensitive data redacted
        """
        if not isinstance(text, str):
            return str(text)

        redacted = text

        # Redact API keys
        for pattern in cls.API_KEY_PATTERNS:
            redacted = re.sub(pattern, cls._redact_match, redacted, flags=re.IGNORECASE)

        # Redact passwords
        for pattern in cls.PASSWORD_PATTERNS:
            redacted = re.sub(pattern, cls._redact_match, redacted, flags=re.IGNORECASE)

        # Redact URL credentials
        for pattern in cls.URL_CREDS_PATTERNS:
            redacted = re.sub(pattern, r"\1***@\3", redacted, flags=re.IGNORECASE)

        return redacted

    @staticmethod
    def _redact_match(match: re.Match) -> str:
        """Redact a regex match, preserving structure."""
        if match.groups():
            # Keep the key/label, redact the value
            prefix = match.group(1) if match.group(1) else ""
            redacted_value = "***REDACTED***"
            return f"{prefix}{redacted_value}"
        else:
            # Full match redaction
            return "***REDACTED***"

    @classmethod
    def redact_dict_keys(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive values in dictionary keys.

        Args:
            data: Dictionary to redact

        Returns:
            Dictionary with sensitive values redacted
        """
        redacted = {}

        for key, value in data.items():
            key_lower = key.lower()

            # Check if this is a sensitive key
            if any(
                sensitive in key_lower
                for sensitive in [
                    "api_key",
                    "apikey",
                    "api-key",
                    "token",
                    "password",
                    "passwd",
                    "pwd",
                    "secret",
                    "credential",
                ]
            ):
                if isinstance(value, str):
                    redacted[key] = cls.redact_sensitive_data(value)
                else:
                    redacted[key] = "***REDACTED***"
            else:
                # Recursively redact nested structures
                if isinstance(value, str):
                    redacted[key] = cls.redact_sensitive_data(value)
                elif isinstance(value, dict):
                    redacted[key] = cls.redact_dict_keys(value)
                elif isinstance(value, list):
                    redacted[key] = [
                        cls.redact_dict_keys(item)
                        if isinstance(item, dict)
                        else cls.redact_sensitive_data(item)
                        if isinstance(item, str)
                        else item
                        for item in value
                    ]
                else:
                    redacted[key] = value

        return redacted


# Monkey patch logging to auto-redact
import logging

original_logger_error = logging.Logger.error
original_logger_warning = logging.Logger.warning
original_logger_info = logging.Logger.info
original_logger_debug = logging.Logger.debug
original_logger_exception = logging.Logger.exception


def _safe_log_error(self, msg, *args, **kwargs):
    """Safe error logging with redaction."""
    if args:
        args = tuple(SecurityRedactor.redact_sensitive_data(str(arg)) for arg in args)
    if "extra" in kwargs:
        kwargs["extra"] = SecurityRedactor.redact_dict_keys(kwargs["extra"])
    original_logger_error(
        self, SecurityRedactor.redact_sensitive_data(msg), *args, **kwargs
    )


def _safe_log_warning(self, msg, *args, **kwargs):
    """Safe warning logging with redaction."""
    if args:
        args = tuple(SecurityRedactor.redact_sensitive_data(str(arg)) for arg in args)
    if "extra" in kwargs:
        kwargs["extra"] = SecurityRedactor.redact_dict_keys(kwargs["extra"])
    original_logger_warning(
        self, SecurityRedactor.redact_sensitive_data(msg), *args, **kwargs
    )


def _safe_log_info(self, msg, *args, **kwargs):
    """Safe info logging with redaction."""
    if args:
        args = tuple(SecurityRedactor.redact_sensitive_data(str(arg)) for arg in args)
    if "extra" in kwargs:
        kwargs["extra"] = SecurityRedactor.redact_dict_keys(kwargs["extra"])
    original_logger_info(
        self, SecurityRedactor.redact_sensitive_data(msg), *args, **kwargs
    )


def _safe_log_debug(self, msg, *args, **kwargs):
    """Safe debug logging with redaction."""
    if args:
        args = tuple(SecurityRedactor.redact_sensitive_data(str(arg)) for arg in args)
    if "extra" in kwargs:
        kwargs["extra"] = SecurityRedactor.redact_dict_keys(kwargs["extra"])
    original_logger_debug(
        self, SecurityRedactor.redact_sensitive_data(msg), *args, **kwargs
    )


def _safe_log_exception(self, msg, *args, **kwargs):
    """Safe exception logging with redaction."""
    if args:
        args = tuple(SecurityRedactor.redact_sensitive_data(str(arg)) for arg in args)
    if "extra" in kwargs:
        kwargs["extra"] = SecurityRedactor.redact_dict_keys(kwargs["extra"])
    original_logger_exception(
        self, SecurityRedactor.redact_sensitive_data(msg), *args, **kwargs
    )


def enable_automatic_redaction():
    """Enable automatic redaction for all logging."""
    logging.Logger.error = _safe_log_error
    logging.Logger.warning = _safe_log_warning
    logging.Logger.info = _safe_log_info
    logging.Logger.debug = _safe_log_debug
    logging.Logger.exception = _safe_log_exception
