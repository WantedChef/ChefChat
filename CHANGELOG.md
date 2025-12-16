# Changelog

All notable changes to ChefChat will be documented in this file.

## [1.0.7] - 2025-12-16

### 🚀 Major Features

#### Bot Infrastructure Overhaul
- **Enhanced Bash Tool**: `cd` command now works with persistent directory state across commands
- **Expanded Command Whitelist**: Added 50+ development tools including pytest, black, ruff, poetry, docker, etc.
- **Shell Built-ins Support**: Full support for shell built-ins like pushd, export, alias, etc.
- **Secure Environment Filtering**: Enhanced API key leakage prevention in subprocess environments

#### Security & Session Management
- **Rate Limiting**: Per-user rolling window rate limiting with configurable windows
- **Session Management**: Per-user session limits with override capability for admins
- **Tool Approval Workflow**: Approval system with TTL expiration for sensitive operations
- **Enhanced Input Validation**: Improved command injection prevention and path traversal protection

#### Model Management
- **5 New FREE OpenCode Models**: Added alpha-gd4, big-pickle, and expanded zen models
- **Live Model Fetching**: Real-time model fetching from provider APIs
- **Model Categorization**: Automatic categorization by features (coding, reasoning, speed, experimental)
- **Enhanced Model Service**: Better model discovery and comparison features

#### Discord Bot Enhancements
- **Mode Display**: Visual mode indicators with permissions and descriptions
- **Direct Git Commands**: Support for git commands without slash prefix
- **Enhanced Status Cards**: Rich status displays with mode snapshots
- **Better Error Handling**: Improved error messages and user feedback

### ⚡ Performance Optimizations

#### Telegram Bot Speed & Responsiveness
- **HTTP Timeout Reduction**: 720s → 60s (12x faster timeout handling)
- **Rate Limiting Increase**: 6 → 12 messages per 30 seconds (2x more responsive)
- **Memory Save Optimization**: Every 5 → 20 messages (4x less disk I/O)
- **Context Management**: 200K → 50K token threshold (4x faster context processing)
- **Active Context Size**: 50 → 20 messages (2.5x faster response generation)
- **Performance Logging**: Added response time tracking and error monitoring
- **Enhanced Error Handling**: Specific error types with user-friendly messages

#### Core Infrastructure
- **ACP Tool Refactoring**: Simplified ACP tool inheritance and state management
- **Better Error Messages**: More descriptive error messages for command failures
- **Session Cleanup**: Improved session cleanup and memory management
- **Type Safety**: Enhanced type hints and pydantic model validation

#### Configuration
- **Expanded Model Config**: Support for multimodal models, rate limits, and file size limits
- **Provider Management**: Better provider configuration and API key management
- **Security Settings**: Configurable denylists and allowlists for commands

### 🛡️ Security Fixes

- **Command Injection Prevention**: Enhanced validation for shell operators and metacharacters
- **Path Traversal Protection**: Improved path validation for file operations
- **API Key Sanitization**: Better filtering of sensitive environment variables
- **Session Isolation**: Proper session separation between users

### 🐛 Bug Fixes

- **CD Command Persistence**: Fixed working directory not persisting across bash commands
- **Model Loading**: Fixed model service initialization with missing API keys
- **Session Cleanup**: Fixed memory leaks in session management
- **Rate Limiting**: Fixed race conditions in rate limiting logic

### 📱 UI/UX Improvements

- **Better Help Messages**: More descriptive help text and examples
- **Enhanced Status Displays**: Rich status cards with mode information
- **Improved Error Feedback**: Clear error messages with suggested fixes
- **Progress Indicators**: Better feedback for long-running operations

## [1.0.6] - 2025-12-16

### 🚀 Major Features

#### Bot Infrastructure Overhaul
- **Enhanced Bash Tool**: `cd` command now works with persistent directory state across commands
- **Expanded Command Whitelist**: Added 50+ development tools including pytest, black, ruff, poetry, docker, etc.
- **Shell Built-ins Support**: Full support for shell built-ins like pushd, export, alias, etc.
- **Secure Environment Filtering**: Enhanced API key leakage prevention in subprocess environments

#### Security & Session Management
- **Rate Limiting**: Per-user rolling window rate limiting with configurable windows
- **Session Management**: Per-user session limits with override capability for admins
- **Tool Approval Workflow**: Approval system with TTL expiration for sensitive operations
- **Enhanced Input Validation**: Improved command injection prevention and path traversal protection

#### Model Management
- **5 New FREE OpenCode Models**: Added alpha-gd4, big-pickle, and expanded zen models
- **Live Model Fetching**: Real-time model fetching from provider APIs
- **Model Categorization**: Automatic categorization by features (coding, reasoning, speed, experimental)
- **Enhanced Model Service**: Better model discovery and comparison features

#### Discord Bot Enhancements
- **Mode Display**: Visual mode indicators with permissions and descriptions
- **Direct Git Commands**: Support for git commands without slash prefix
- **Enhanced Status Cards**: Rich status displays with mode snapshots
- **Better Error Handling**: Improved error messages and user feedback

### 🔧 Improvements

#### Core Infrastructure
- **ACP Tool Refactoring**: Simplified ACP tool inheritance and state management
- **Better Error Messages**: More descriptive error messages for command failures
- **Performance Optimizations**: Improved session cleanup and memory management
- **Type Safety**: Enhanced type hints and pydantic model validation

#### Configuration
- **Expanded Model Config**: Support for multimodal models, rate limits, and file size limits
- **Provider Management**: Better provider configuration and API key management
- **Security Settings**: Configurable denylists and allowlists for commands

### 🛡️ Security Fixes

- **Command Injection Prevention**: Enhanced validation for shell operators and metacharacters
- **Path Traversal Protection**: Improved path validation for file operations
- **API Key Sanitization**: Better filtering of sensitive environment variables

### 🎨 UI/UX Improvements

- **Better Help Messages**: More descriptive help text and examples
- **Enhanced Status Displays**: Rich status cards with mode information
- **Improved Error Feedback**: Clear error messages with suggested fixes
- **Progress Indicators**: Better feedback for long-running operations

## [1.0.5] - Previous Release

### Features
- Initial Telegram and Discord bot integration
- Basic model management
- Session management foundation
- Security command execution framework

---

## Version Format

We follow [Semantic Versioning](https://semver.org/).

- **MAJOR**: Breaking changes or major feature releases
- **MINOR**: New features or significant improvements  
- **PATCH**: Bug fixes and minor improvements

## Development

For development versions, we use the format `X.Y.Z-dev` where `dev` indicates development status.

---

*Note: This changelog only contains changes since 1.0.5. For earlier changes, see git history.*