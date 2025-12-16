"""Custom exceptions for Telegram bot error handling."""

from __future__ import annotations


class TelegramBotError(Exception):
    """Base exception for Telegram bot errors."""

    pass


class TimeoutError(TelegramBotError):
    """Raised when API calls timeout."""

    pass


class ContextError(TelegramBotError):
    """Raised when context management fails."""

    pass


class ModelError(TelegramBotError):
    """Raised when model inference fails."""

    pass


class MessageError(TelegramBotError):
    """Raised when message sending/editing fails."""

    pass


class SessionError(TelegramBotError):
    """Raised when session management fails."""

    pass


class RateLimitError(TelegramBotError):
    """Raised when rate limits are exceeded."""

    pass


class ApprovalError(TelegramBotError):
    """Raised when approval system fails."""

    pass


class CLIError(TelegramBotError):
    """Raised when CLI provider execution fails."""

    pass


def classify_error(error: Exception) -> TelegramBotError:
    """Classify generic exceptions into specific error types."""
    error_str = str(error).lower()

    if "timeout" in error_str or "timed out" in error_str:
        return TimeoutError(f"Request timed out: {error}")
    elif "context" in error_str or "memory" in error_str:
        return ContextError(f"Context management error: {error}")
    elif "model" in error_str or "inference" in error_str or "api" in error_str:
        return ModelError(f"Model inference error: {error}")
    elif "message" in error_str or "parse" in error_str or "send" in error_str:
        return MessageError(f"Message handling error: {error}")
    elif "session" in error_str:
        return SessionError(f"Session management error: {error}")
    elif "rate" in error_str or "limit" in error_str:
        return RateLimitError(f"Rate limit exceeded: {error}")
    elif "approval" in error_str:
        return ApprovalError(f"Approval system error: {error}")
    elif "cli" in error_str:
        return CLIError(f"CLI provider error: {error}")
    else:
        return TelegramBotError(f"Unexpected error: {error}")


def get_user_friendly_message(error: TelegramBotError) -> str:
    """Get user-friendly error message for display."""
    if isinstance(error, TimeoutError):
        return "⏰ The request took too long. Please try again."
    elif isinstance(error, ContextError):
        return "🧠 Memory context issue. Starting fresh conversation."
    elif isinstance(error, ModelError):
        return "🤖 AI model error. Please try again or switch models."
    elif isinstance(error, MessageError):
        return "📝 Message formatting issue. Please try again."
    elif isinstance(error, SessionError):
        return "🔄 Session error. Please restart the conversation."
    elif isinstance(error, RateLimitError):
        return "⚡ Too many requests. Please wait a moment."
    elif isinstance(error, ApprovalError):
        return "🔐 Approval system error. Please try again."
    elif isinstance(error, CLIError):
        return "💻 CLI execution error. Please check your command."
    else:
        return "❌ Something went wrong. Please try again."
