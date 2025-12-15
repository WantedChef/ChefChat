from __future__ import annotations

from pydantic import ValidationError
import pytest

from chefchat.core.config import ModelConfig, ProviderConfig
from chefchat.core.llm.backend.generic import GenericBackend
from chefchat.core.llm.exceptions import BackendError
from chefchat.core.llm.format import ParsedToolCall, _compile_icase
from chefchat.core.types import LLMMessage, Role


class TestSecurityPatches:
    def test_parsed_tool_call_validation_size(self):
        # 1MB + 100 bytes of data approx
        large_string = "a" * (1024 * 1024 + 100)
        large_args = {"data": large_string}
        # json.dumps(large_args) will be > 1MB

        with pytest.raises(ValidationError) as excinfo:
            ParsedToolCall(tool_name="test", raw_args=large_args)
        assert "Tool arguments too large" in str(excinfo.value)

    def test_parsed_tool_call_validation_safe(self):
        safe_args = {"data": "safe"}
        # Should not raise
        ParsedToolCall(tool_name="test", raw_args=safe_args)

    def test_parsed_tool_call_validation_type(self):
        # raw_args must be dict
        with pytest.raises(ValidationError):
            ParsedToolCall(tool_name="test", raw_args="not a dict")

    def test_regex_complexity_limit(self):
        long_pattern = "a" * 1001
        assert _compile_icase(long_pattern) is None

    def test_regex_safe(self):
        assert _compile_icase("safe") is not None

    def test_error_sanitization(self):
        sensitive = "Error: Invalid API key sk-1234567890abcdef1234567890"
        sanitized = BackendError._sanitize_content(sensitive)
        assert "sk-***" in sanitized
        assert "sk-1234567890" not in sanitized

        sensitive_bearer = "Request failed with Bearer abcdef1234567890 token"
        sanitized_bearer = BackendError._sanitize_content(sensitive_bearer)
        # Expected: Bearer *** token
        assert "Bearer ***" in sanitized_bearer

    @pytest.mark.asyncio
    async def test_message_overhead_config(self):
        # Mock provider and model
        provider = ProviderConfig(
            name="test",
            api_base="http://test",
            message_overhead=10,  # custom overhead
        )
        backend = GenericBackend(provider=provider)
        model = ModelConfig(name="test-model", provider="test", alias="tm")

        messages = [LLMMessage(role=Role.user, content="hello")]

        count = await backend.count_tokens(model=model, messages=messages)

        provider_default = ProviderConfig(
            name="test_def",
            api_base="http://test",
            message_overhead=4,  # default
        )
        backend_default = GenericBackend(provider=provider_default)
        count_default = await backend_default.count_tokens(
            model=model, messages=messages
        )

        # The difference should exactly correspond to the overhead difference (10 - 4) * num_messages (1)
        assert count == count_default + 6
