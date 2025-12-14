"""Multimodal configuration system for ChefChat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
import toml


class MultimodalConfig(BaseModel):
    """Configuration for multimodal features."""

    enabled: bool = Field(default=False, description="Enable multimodal support")
    auto_detect: bool = Field(
        default=True, description="Auto-enable for multimodal models"
    )
    max_image_size: int = Field(
        default=10 * 1024 * 1024, description="Max image size in bytes (10MB)"
    )
    supported_formats: set[str] = Field(
        default_factory=lambda: {"jpg", "jpeg", "png", "gif", "webp"},
        description="Supported image formats",
    )
    max_file_size_mb: int = Field(default=20, description="Max file size in MB")


class MultimodalManager:
    """Manager for multimodal capabilities and configuration."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.config_path = Path.home() / ".vibe" / "multimodal.toml"

    def is_model_multimodal(self, model_alias: str) -> bool:
        """Check if a model supports multimodal input."""
        try:
            model = self.config.get_model_by_alias(model_alias)
            return model.multimodal or "multimodal" in model.features
        except ValueError:
            return False

    def get_multimodal_config(self, model_alias: str) -> MultimodalConfig:
        """Get multimodal configuration for a model."""
        # Load from config file or use defaults
        config_data = {}
        if self.config_path.exists():
            try:
                config_data = toml.load(self.config_path).get(model_alias, {})
            except (toml.TOMLDecodeError, OSError):
                config_data = {}

        return MultimodalConfig(**config_data)

    def save_multimodal_config(
        self, model_alias: str, config: MultimodalConfig
    ) -> None:
        """Save multimodal configuration for a model."""
        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing config
        existing_config = {}
        if self.config_path.exists():
            try:
                existing_config = toml.load(self.config_path)
            except (toml.TOMLDecodeError, OSError):
                existing_config = {}

        # Update with new config for this model
        existing_config[model_alias] = config.model_dump(exclude_unset=True)

        # Save to file
        with open(self.config_path, "w", encoding="utf-8") as f:
            toml.dump(existing_config, f)

    def prepare_multimodal_request(
        self, messages: list[dict[str, Any]], model_alias: str
    ) -> list[dict[str, Any]]:
        """Prepare messages for multimodal model."""
        if not self.is_model_multimodal(model_alias):
            return messages

        processed_messages = []
        for msg in messages:
            if isinstance(msg, dict) and "image_path" in msg:
                # Convert image to base64 and format for API
                processed_msg = self._process_image_message(msg)
                processed_messages.append(processed_msg)
            else:
                processed_messages.append(msg)

        return processed_messages

    def _process_image_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Process a message with image content."""
        import base64
        from pathlib import Path

        image_path = message.get("image_path", "")
        if not image_path:
            return message

        try:
            path = Path(image_path)
            if not path.exists():
                return message

            # Check file size
            file_size = path.stat().st_size
            if file_size > 20 * 1024 * 1024:  # 20MB limit
                return message

            # Check file extension
            ext = path.suffix.lower().lstrip(".")
            if ext not in {"jpg", "jpeg", "png", "gif", "webp"}:
                return message

            # Read and encode image
            with open(path, "rb") as f:
                image_data = f.read()
                base64_data = base64.b64encode(image_data).decode("utf-8")

                # Get mime type
                mime_types = {
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "png": "image/png",
                    "gif": "image/gif",
                    "webp": "image/webp",
                }
                mime_type = mime_types.get(ext, "image/jpeg")

                # Create multimodal message
                return {
                    "role": message.get("role", "user"),
                    "content": [
                        {"type": "text", "text": message.get("content", "")},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_data}"
                            },
                        },
                    ],
                }
        except Exception:
            return message
