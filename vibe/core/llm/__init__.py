from __future__ import annotations

from vibe.core.types import LLMMessage, Role

from .exceptions import (
    LLMAuthenticationError as LLMAuthenticationError,
    LLMConnectionError as LLMConnectionError,
    LLMContextWindowError as LLMContextWindowError,
    LLMError as LLMError,
    LLMGenerativeError as LLMGenerativeError,
    LLMRateLimitError as LLMRateLimitError,
)
from .types import BackendLike as BackendLike

# Aliases
Message = LLMMessage
MessageRole = Role
