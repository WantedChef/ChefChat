"""Tests for KitchenManager."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chefchat.kitchen.core import ChefBrain
from chefchat.kitchen.manager import KitchenManager


class FakeChef(ChefBrain):
    """Fake chef for testing."""

    def __init__(self):
        self.connected = False

    def connect(self, api_key=None):
        self.connected = True
        return True

    async def cook_recipe(self, ingredients, preferences=None):
        return f"Cooked: {ingredients.get('prompt', '')}"

    async def chat(self, user_input, history):
        return f"Chat: {user_input}"


def test_manager_init():
    """Test manager initialization."""
    manager = KitchenManager(chef_name="devstral")
    assert manager.chef_name == "devstral"
    assert manager._chef is None


def test_manager_lazy_load_success():
    """Test lazy loading of a chef."""
    manager = KitchenManager(chef_name="fake")

    with patch("importlib.import_module") as mock_import:
        # Mock module and class
        mock_module = MagicMock()
        mock_module.FakeChef = FakeChef
        mock_import.return_value = mock_module

        chef = manager.chef

        assert isinstance(chef, FakeChef)
        assert chef.connected
        assert manager._chef is chef
        mock_import.assert_called_once_with("chefchat.kitchen.chefs.fake")


def test_manager_load_failure_fallback():
    """Test fallback when loading fails."""
    manager = KitchenManager(chef_name="nonexistent")

    with patch("importlib.import_module", side_effect=ImportError("No module")):
        chef = manager.chef

        # Should be a simulated chef (which is just an instance of ChefBrain)
        assert isinstance(chef, ChefBrain)
        assert manager._chef is chef

        # Verify simulated behavior
        assert chef.connect() is True


@pytest.mark.asyncio
async def test_manager_delegation():
    """Test manager delegates methods to chef."""
    manager = KitchenManager(chef_name="fake")

    with patch("importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_module.FakeChef = FakeChef
        mock_import.return_value = mock_module

        # Test generate_plan
        plan = await manager.generate_plan("Build app")
        assert plan == "Cooked: Build app"

        # Test write_code
        code = await manager.write_code("Plan", "Context")
        assert "Cooked: Plan:\nPlan" in code
