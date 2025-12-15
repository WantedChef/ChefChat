"""Tests for CLI REPL model command functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chefchat.cli.repl import ChefChatREPL
from chefchat.core.config import VibeConfig


@pytest.mark.asyncio
async def test_repl_model_list_basic():
    """Test that _model_list method exists and can be called."""
    # Create a minimal mock config
    config = MagicMock(spec=VibeConfig)
    config.models = []
    config.providers = []
    config.ui_theme = "chef-dark"
    config.emoji_enabled = True
    config.color_enabled = True
    config.file_indexer_parallel_walk = True
    config.file_indexer_max_workers = 4

    from chefchat.cli.mode_manager import VibeMode
    
    repl = ChefChatREPL(config, VibeMode.NORMAL)
    repl.console = MagicMock()  # Mock console for testing
    
    # Test that the method exists and can be called
    await repl._model_list()
    
    # Verify console.print was called
    assert repl.console.print.called


@pytest.mark.asyncio 
async def test_repl_model_help_basic():
    """Test that _model_show_help method exists and can be called."""
    # Create a minimal mock config
    config = MagicMock(spec=VibeConfig)
    config.models = []
    config.providers = []
    config.ui_theme = "chef-dark"
    config.emoji_enabled = True
    config.color_enabled = True
    config.file_indexer_parallel_walk = True
    config.file_indexer_max_workers = 4

    from chefchat.cli.mode_manager import VibeMode
    
    repl = ChefChatREPL(config, VibeMode.NORMAL)
    repl.console = MagicMock()  # Mock console for testing
    
    # Test that the method exists and can be called
    await repl._model_show_help()
    
    # Verify console.print was called
    assert repl.console.print.called


@pytest.mark.asyncio
async def test_repl_model_command_dispatch():
    """Test that model command dispatch works for basic subcommands."""
    # Create a minimal mock config
    config = MagicMock(spec=VibeConfig)
    config.models = []
    config.providers = []
    config.ui_theme = "chef-dark"
    config.emoji_enabled = True
    config.color_enabled = True
    config.file_indexer_parallel_walk = True
    config.file_indexer_max_workers = 4

    from chefchat.cli.mode_manager import VibeMode
    
    repl = ChefChatREPL(config, VibeMode.NORMAL)
    repl.console = MagicMock()  # Mock console for testing
    
    # Test help command dispatch
    with patch.object(repl, "_model_show_help") as mock_help:
        await repl._handle_model_command("help")
        mock_help.assert_called_once()
    
    # Test list command dispatch  
    with patch.object(repl, "_model_list") as mock_list:
        await repl._handle_model_command("list")
        mock_list.assert_called_once()
    
    # Test status command dispatch
    with patch.object(repl, "_model_status") as mock_status:
        await repl._handle_model_command("status")
        mock_status.assert_called_once()


@pytest.mark.asyncio
async def test_repl_model_command_interactive_fallback():
    """Test that model command without args falls back to interactive selection."""
    # Create a minimal mock config
    config = MagicMock(spec=VibeConfig)
    config.models = []
    config.providers = []
    config.ui_theme = "chef-dark"
    config.emoji_enabled = True
    config.color_enabled = True
    config.file_indexer_parallel_walk = True
    config.file_indexer_max_workers = 4

    from chefchat.cli.mode_manager import VibeMode
    
    repl = ChefChatREPL(config, VibeMode.NORMAL)
    repl.console = MagicMock()  # Mock console for testing
    
    # Test interactive selection fallback
    with patch.object(repl, "_model_select_interactive") as mock_interactive:
        await repl._handle_model_command("")
        mock_interactive.assert_called_once()


@pytest.mark.asyncio
async def test_repl_model_command_unknown_fallback():
    """Test that unknown model commands fall back to model selection."""
    # Create a minimal mock config
    config = MagicMock(spec=VibeConfig)
    config.models = []
    config.providers = []
    config.ui_theme = "chef-dark"
    config.emoji_enabled = True
    config.color_enabled = True
    config.file_indexer_parallel_walk = True
    config.file_indexer_max_workers = 4

    from chefchat.cli.mode_manager import VibeMode
    
    repl = ChefChatREPL(config, VibeMode.NORMAL)
    repl.console = MagicMock()  # Mock console for testing
    
    # Test unknown command fallback
    with patch.object(repl, "_model_select") as mock_select:
        await repl._handle_model_command("unknown-command")
        mock_select.assert_called_once_with("unknown-command")


def test_repl_model_methods_exist():
    """Test that all expected model methods exist on the REPL class."""
    from chefchat.cli.mode_manager import VibeMode
    from chefchat.core.config import VibeConfig
    
    # Create minimal config
    config = MagicMock(spec=VibeConfig)
    config.ui_theme = "chef-dark"
    config.emoji_enabled = True
    config.color_enabled = True
    config.file_indexer_parallel_walk = True
    config.file_indexer_max_workers = 4
    
    repl = ChefChatREPL(config, VibeMode.NORMAL)
    
    # Test that all expected methods exist
    expected_methods = [
        "_model_show_help",
        "_model_list", 
        "_model_select",
        "_model_info",
        "_model_status",
        "_model_speed",
        "_model_reasoning",
        "_model_multimodal",
        "_model_compare",
        "_model_manage_tui_only",
    ]
    
    for method_name in expected_methods:
        assert hasattr(repl, method_name), f"Method {method_name} should exist"
        assert callable(getattr(repl, method_name)), f"Method {method_name} should be callable"