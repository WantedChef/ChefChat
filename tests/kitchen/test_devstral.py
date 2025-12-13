"""Tests for DevstralChef."""

import sys
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# We need to ensure we can patch 'mistralai' even if not installed
mock_mistral_module = MagicMock()
mock_mistral_class = MagicMock()
mock_mistral_module.Mistral = mock_mistral_class
sys.modules["mistralai"] = mock_mistral_module

from chefchat.kitchen.chefs.devstral import DevstralChef


@pytest.fixture
def mock_mistral():
    """Reset the mock for each test."""
    mock_mistral_class.reset_mock()
    return mock_mistral_class


def test_devstral_init():
    """Test initialization."""
    chef = DevstralChef()
    assert chef._model == "mistral-large-latest"
    assert chef._client is None


def test_devstral_connect_no_key():
    """Test connection fails without API key."""
    chef = DevstralChef()
    with patch("os.getenv", return_value=None):
        assert chef.connect() is False


def test_devstral_connect_with_key(mock_mistral):
    """Test connection with API key."""
    chef = DevstralChef()
    with patch("os.getenv", return_value="fake-key"):
        assert chef.connect() is True
        assert chef._client is not None
        mock_mistral.assert_called_once_with(api_key="fake-key")


@pytest.mark.asyncio
async def test_devstral_cook_recipe(mock_mistral):
    """Test cook_recipe generates response."""
    chef = DevstralChef()

    # Setup client mock
    mock_client = MagicMock()
    chef._client = mock_client

    # Mock chat response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Recipe Result"

    mock_client.chat.complete_async = AsyncMock(return_value=mock_response)

    ingredients = {"prompt": "Hello"}
    result = await chef.cook_recipe(ingredients)

    assert result == "Recipe Result"
    mock_client.chat.complete_async.assert_called_once()


@pytest.mark.asyncio
async def test_devstral_chat(mock_mistral):
    """Test chat delegates to cook_recipe."""
    chef = DevstralChef()
    # Mock cook_recipe to avoid full client setup
    chef.cook_recipe = AsyncMock(return_value="Chat Response")

    result = await chef.chat("Hello", [{"role": "assistant", "content": "Hi"}])

    assert result == "Chat Response"
    chef.cook_recipe.assert_called_once()
    args, _ = chef.cook_recipe.call_args
    ingredients = args[0]
    assert len(ingredients["messages"]) == 2
    assert ingredients["messages"][-1]["content"] == "Hello"
