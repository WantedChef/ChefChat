import pytest
import respx
import os
import httpx
from httpx import Response
from chefchat.integrations.cliproxy.client import CLIProxyClient
from chefchat.kitchen.chefs.cliproxy import CliproxyChef

@pytest.mark.asyncio
async def test_cliproxy_client_completion():
    async with respx.mock(base_url="http://localhost:8080/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(return_value=Response(200, json={
            "choices": [{"message": {"content": "Hello world"}}]
        }))

        client = CLIProxyClient(base_url="http://localhost:8080/v1")
        response = await client.chat_completion("test-model", [{"role": "user", "content": "hi"}])
        assert response["choices"][0]["message"]["content"] == "Hello world"

@pytest.mark.asyncio
async def test_cliproxy_client_streaming():
    async with respx.mock(base_url="http://localhost:8080/v1") as respx_mock:
        stream_content = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
            'data: {"choices": [{"delta": {"content": " world"}}]}\n\n',
            'data: [DONE]\n\n'
        ]

        async def async_iter():
            for chunk in stream_content:
                yield chunk.encode('utf-8')

        respx_mock.post("/chat/completions").mock(return_value=Response(200, content=async_iter()))

        client = CLIProxyClient(base_url="http://localhost:8080/v1")
        stream = await client.chat_completion("test-model", [{"role": "user", "content": "hi"}], stream=True)

        parts = []
        async for part in stream:
            parts.append(part)

        assert "".join(parts) == "Hello world"

@pytest.mark.asyncio
async def test_cliproxy_chef():
    os.environ["CLIPROXY_BASE_URL"] = "http://localhost:8080/v1"

    async with respx.mock(base_url="http://localhost:8080/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(return_value=Response(200, json={
            "choices": [{"message": {"content": "Chef says hello"}}]
        }))

        chef = CliproxyChef()
        connected = chef.connect()
        assert connected

        result = await chef.cook_recipe({"prompt": "hi"})
        assert result == "Chef says hello"
