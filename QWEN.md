# ChefChat CLI - Project Documentation

## Project Overview

ChefChat CLI is a sophisticated fork of Mistral Vibe that transforms it into a premium, culinary-themed AI coding assistant. The project features an advanced mode system, enhanced safety features, rich UI improvements, and delightful easter eggs to create a unique development experience.

Key features include:
- **Advanced Mode System**: 5 distinct operating modes (PLAN, NORMAL, AUTO, YOLO, ARCHITECT) that adapt to different workflow needs
- **Enhanced Safety**: ModeManager with granular control over tool execution and permissions
- **Premium REPL Interface**: Beautiful Rich + prompt_toolkit based interface with culinary theme
- **Culinary Personality**: Easter eggs like `/chef`, `/wisdom`, `/roast`, `/fortune`, and `/plate` commands
- **Comprehensive Tool Permissions**: Mode-based permissions for read/write operations

## Architecture

The project is organized into several main modules:

- `vibe/cli/` - Main CLI components including the REPL interface and mode management
- `vibe/core/` - Core functionality including agent, config, and utilities
- `vibe/modes/` - Modular mode system with security features and configuration
- `vibe/acp/` - Agent Client Protocol integration
- `vibe/setup/` - Onboarding and configuration setup
- `vibe/utils/` - Utility functions and helpers
- `tests/` - Test suite for the application

## Building and Running

### Prerequisites
- Python 3.12 or higher
- `uv` or `pip` package manager
- API key for your preferred AI provider (Mistral, OpenAI, etc.)

### Installation
```bash
# Using uv (recommended)
uv add mistral-vibe

# Using pip
pip install mistral-vibe
```

### Setup
```bash
# Start the setup wizard
vibe --setup
```

### Running ChefChat
```bash
# Start interactive REPL
vibe

# Start with a specific prompt
vibe "Help me refactor this Python function"

# Continue from last session
vibe --continue

# Resume a specific session
vibe --resume session_123
```

## Mode System

ChefChat features 5 distinct operating modes:

### PLAN Mode - "Measure Twice, Cut Once"
- Read-only exploration and planning
- Safe for codebase exploration
- No file modifications allowed
- Tool execution requires approval

### NORMAL Mode - "Safe and Steady" (Default)
- Ask confirmation before each tool execution
- Balances safety and efficiency
- Visual feedback for all actions

### AUTO Mode - "Trust and Execute"
- Auto-approve all tool executions
- Faster execution workflow
- Still provides explanations

### YOLO Mode - "Move Fast, Ship Faster"
- Maximum velocity under deadline pressure
- Minimal output, maximum speed
- Instant tool approval

### ARCHITECT Mode - "Design the Cathedral"
- High-level design focus
- Read-only design thinking
- System and pattern thinking

## Configuration

ChefChat uses a hierarchical configuration system:
1. Project-level: `./.vibe/config.toml`
2. User-level: `~/.vibe/config.toml`
3. Environment variables: `.env` files

Example configuration file:
```toml
# Model settings
active_model = "devstral-2"
system_prompt_id = "cli"

# Mode-specific settings
default_mode = "NORMAL"

# Tool permissions
[tools.bash]
permission = "ask"

[tools.read_file]
permission = "always"

# UI settings
vim_keybindings = false
textual_theme = "textual-dark"
```

## Development Conventions

- Python 3.12+ is required
- Code follows PEP 8 standards with ruff linter
- Type hints are used throughout the codebase
- Rich is used for all terminal UI components
- Pydantic is used for configuration management
- The codebase is organized into clear modules with well-defined responsibilities

## Advanced Features

- MCP (Model Context Protocol) server integration
- Session logging and management
- Multiple AI provider support (Mistral, OpenAI, custom)
- Custom tool development support
- Comprehensive testing framework
- Rich-text output and interactive UI

## Safety Features

- Mode-based permissions to prevent unauthorized operations
- Command validation to block suspicious commands
- Secure API key management
- Write operation detection with regex patterns
- File operation validation

## Version Information

Current version: 1.1.1

## License

ChefChat is licensed under the Apache License 2.0, maintaining compatibility with the original Mistral Vibe license.