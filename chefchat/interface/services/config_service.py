"""ConfigService - Business logic for configuration management.

This service encapsulates config-related business logic, extracted from
SystemCommandsMixin to enable testing and reuse without UI dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chefchat.core.config import VibeConfig


@dataclass
class ConfigInfo:
    """DTO representing configuration information for display."""

    active_model: str
    config_path: str
    log_path: str
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    provider_count: int = 0
    model_count: int = 0
    api_keys_configured: list[str] = field(default_factory=list)


@dataclass
class MCPServerInfo:
    """DTO representing MCP server information."""

    name: str
    command: str
    args: list[str]
    status: str  # "available" | "unavailable" | "unknown"
    tool_count: int = 0


class ConfigService:
    """Service for configuration management business logic.

    This class handles all configuration-related operations that don't
    require direct UI interaction.
    """

    def __init__(self, config: VibeConfig | None = None) -> None:
        """Initialize with optional VibeConfig instance.

        Args:
            config: The application configuration. If None, will be loaded on demand.
        """
        self._config = config

    def ensure_config(self) -> VibeConfig:
        """Ensure config is loaded, loading if necessary.

        Returns:
            The loaded VibeConfig.

        Raises:
            RuntimeError: If config cannot be loaded.
        """
        if self._config is None:
            from chefchat.core.config import VibeConfig

            self._config = VibeConfig.load()
        return self._config

    def get_config_info(self) -> ConfigInfo:
        """Get configuration information summary.

        Returns:
            ConfigInfo DTO with current config state.
        """
        config = self.ensure_config()

        # Determine config path
        config_path = self._get_config_path()

        # Determine log path
        log_path = self._get_log_path()

        # Count configured API keys
        api_keys = self._get_configured_api_keys()

        return ConfigInfo(
            active_model=config.active_model,
            config_path=str(config_path),
            log_path=str(log_path),
            mcp_servers=dict(config.mcp_servers) if config.mcp_servers else {},
            provider_count=len(config.providers) if hasattr(config, "providers") else 0,
            model_count=len(config.models),
            api_keys_configured=api_keys,
        )

    def get_log_path(self) -> Path:
        """Get the current log file path.

        Returns:
            Path to the log file.
        """
        return self._get_log_path()

    def reload_config(self) -> tuple[bool, str]:
        """Reload configuration from disk.

        Returns:
            Tuple of (success, message).
        """
        from chefchat.core.config import VibeConfig

        try:
            self._config = VibeConfig.load()
            return True, "Configuration reloaded successfully"
        except Exception as e:
            return False, f"Failed to reload config: {e}"

    def list_mcp_servers(self) -> list[MCPServerInfo]:
        """List configured MCP servers.

        Returns:
            List of MCPServerInfo objects.
        """
        config = self.ensure_config()
        servers = []

        if not config.mcp_servers:
            return servers

        for name, server_config in config.mcp_servers.items():
            servers.append(
                MCPServerInfo(
                    name=name,
                    command=server_config.get("command", "unknown"),
                    args=server_config.get("args", []),
                    status="available",  # Would need runtime check
                    tool_count=0,
                )
            )

        return servers

    def get_available_layouts(self) -> list[str]:
        """Get list of available TUI layouts.

        Returns:
            List of layout names.
        """
        return ["chat_only", "kitchen", "focused"]

    def validate_layout(self, layout: str) -> bool:
        """Check if a layout name is valid.

        Args:
            layout: Layout name to validate.

        Returns:
            True if valid, False otherwise.
        """
        return layout.lower() in self.get_available_layouts()

    def _get_config_path(self) -> Path:
        """Get the path to the config file."""
        from chefchat.core.config import VibeConfig

        # Try to get from VibeConfig class
        config_file = Path.home() / ".config" / "chefchat" / "config.toml"
        if hasattr(VibeConfig, "get_config_path"):
            try:
                config_file = VibeConfig.get_config_path()
            except Exception:
                pass
        return config_file

    def _get_log_path(self) -> Path:
        """Get the path to the log file."""
        # Default log location
        log_dir = Path.home() / ".local" / "share" / "chefchat" / "logs"

        # Check for environment override
        if env_log := os.getenv("CHEFCHAT_LOG_DIR"):
            log_dir = Path(env_log)

        return log_dir / "chefchat.log"

    def _get_configured_api_keys(self) -> list[str]:
        """Get list of configured API key names.

        Returns:
            List of environment variable names that have values set.
        """
        self.ensure_config()  # Ensure config is loaded
        configured: list[str] = []
        # Check common API key env vars
        key_vars = [
            "MISTRAL_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GROQ_API_KEY",
            "OPENROUTER_API_KEY",
            "GITHUB_TOKEN",
        ]

        for var in key_vars:
            if os.getenv(var):
                configured.append(var)

        return configured
