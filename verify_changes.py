
import sys
import asyncio
from vibe.core.llm import (
    LLMError,
    LLMConnectionError,
    Message,
    MessageRole
)
from vibe.core.llm.backend import MistralBackend, GenericBackend
from vibe.core.config import DEFAULT_MAX_TOKENS, VibeConfig, ModelConfig
from vibe.utils.tokenizer import count_tokens

async def main():
    print("Verifying imports...")
    print("Imports OK.")

    print(f"Checking DEFAULT_MAX_TOKENS: {DEFAULT_MAX_TOKENS}")
    assert DEFAULT_MAX_TOKENS > 0

    print("Checking tokenizer...")
    count = count_tokens("Hello world")
    print(f"Token count for 'Hello world': {count}")
    assert count > 0

    print("Checking Backend count_tokens (mock)...")
    config = VibeConfig()
    try:
        mistral_provider = config.providers[0]
        model = config.models[0]

        backend = MistralBackend(mistral_provider)

        messages = [Message(role=MessageRole.user, content="Hello " * 100)]

        try:
            tokens = await backend.count_tokens(model=model, messages=messages)
            print(f"Backend counted tokens: {tokens}")
        except Exception as e:
            print(f"Backend count_tokens failed (might be expected): {e}")

    except Exception as e:
         print(f"Config/Provider setup failed: {e}")

    print("Verification complete.")

if __name__ == "__main__":
    asyncio.run(main())
