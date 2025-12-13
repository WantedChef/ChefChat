"""Tests for KitchenFooter widget."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from textual.widgets import Static

from chefchat.interface.widgets.kitchen_ui import KitchenFooter
from chefchat.modes import MODE_CONFIGS, ModeManager, VibeMode


@pytest.fixture
def mode_manager():
    """Create a ModeManager instance for testing."""
    return ModeManager(initial_mode=VibeMode.NORMAL)


def test_kitchen_footer_initialization(mode_manager):
    """Test KitchenFooter can be instantiated."""
    footer = KitchenFooter(mode_manager, id="test-footer")
    assert footer._mode_manager == mode_manager
    assert footer.id == "test-footer"


def test_kitchen_footer_compose(mode_manager):
    """Test KitchenFooter composition creates correct widgets."""
    footer = KitchenFooter(mode_manager)
    widgets = list(footer.compose())

    # Should yield 8 Static widgets (added footer-model)
    assert len(widgets) == 8
    assert all(isinstance(w, Static) for w in widgets)

    # Check classes
    assert "footer-mode" in widgets[0].classes
    assert "footer-model" in widgets[1].classes
    assert "footer-label" in widgets[2].classes
    assert "footer-value" in widgets[3].classes
    assert "footer-sep" in widgets[4].classes
    assert "key-hint" in widgets[5].classes
    assert "key-hint" in widgets[6].classes
    assert "key-hint" in widgets[7].classes


def test_kitchen_footer_auto_status_classes(mode_manager):
    """Test auto-approve status class assignment."""
    # Test with auto-approve ON
    mode_manager.state.auto_approve = True
    footer = KitchenFooter(mode_manager)
    widgets = list(footer.compose())

    auto_value_widget = widgets[3]  # Fourth widget is the auto value (index 3)
    assert "auto-on" in auto_value_widget.classes
    assert str(auto_value_widget.render()) == "ON"

    # Test with auto-approve OFF
    mode_manager.state.auto_approve = False
    footer2 = KitchenFooter(mode_manager)
    widgets2 = list(footer2.compose())

    auto_value_widget2 = widgets2[3]
    assert "auto-off" in auto_value_widget2.classes
    assert str(auto_value_widget2.render()) == "OFF"


def test_kitchen_footer_refresh_mode(mode_manager):
    """Test refresh_mode updates widgets correctly."""
    footer = KitchenFooter(mode_manager)

    # Mock query_one to return test widgets
    mock_mode_widget = MagicMock(spec=Static)
    mock_auto_widget = MagicMock(spec=Static)

    def mock_query_one(selector, widget_type=None):
        if selector == ".footer-mode":
            return mock_mode_widget
        elif selector == ".footer-value":
            return mock_auto_widget
        raise Exception(f"Unexpected selector: {selector}")

    footer.query_one = mock_query_one

    # Refresh with NORMAL mode
    footer.refresh_mode()

    # Check mode widget was updated
    config = MODE_CONFIGS[VibeMode.NORMAL]
    expected_mode = f"{config.emoji} {VibeMode.NORMAL.value.upper()}"
    mock_mode_widget.update.assert_called_once_with(expected_mode)

    # Check auto widget was updated
    mock_auto_widget.update.assert_called_once()
    mock_auto_widget.remove_class.assert_called_once_with("auto-on", "auto-off")
    mock_auto_widget.add_class.assert_called_once()


def test_kitchen_footer_refresh_mode_handles_exceptions(mode_manager):
    """Test refresh_mode gracefully handles missing widgets."""
    footer = KitchenFooter(mode_manager)

    # Mock query_one to raise exception
    footer.query_one = MagicMock(side_effect=Exception("Widget not found"))

    # Should not raise exception
    footer.refresh_mode()


def test_kitchen_footer_mode_change(mode_manager):
    """Test footer updates when mode changes."""
    footer = KitchenFooter(mode_manager)

    # Change mode
    mode_manager.cycle_mode()

    # Mock widgets
    mock_mode_widget = MagicMock(spec=Static)
    mock_auto_widget = MagicMock(spec=Static)

    def mock_query_one(selector, widget_type=None):
        if selector == ".footer-mode":
            return mock_mode_widget
        elif selector == ".footer-value":
            return mock_auto_widget
        return MagicMock()

    footer.query_one = mock_query_one

    # Refresh
    footer.refresh_mode()

    # Verify new mode is reflected
    new_mode = mode_manager.current_mode
    config = MODE_CONFIGS[new_mode]
    expected = f"{config.emoji} {new_mode.value.upper()}"
    mock_mode_widget.update.assert_called_with(expected)

def test_kitchen_footer_refresh_model(mode_manager):
    """Test refresh_model updates widget."""
    footer = KitchenFooter(mode_manager)

    mock_model_widget = MagicMock(spec=Static)
    footer.query_one = MagicMock(return_value=mock_model_widget)

    footer.refresh_model("test-model")
    mock_model_widget.update.assert_called_with(" 🤖 test-model ")
