from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from chefchat.core.tools.base import BaseTool


def tool_to_mistral_format(tool: BaseTool) -> dict[str, Any]:
    """Convert a BaseTool instance to Mistral tool format.

    Args:
        tool: The BaseTool instance.

    Returns:
        Dictionary representing the tool in Mistral format.
    """
    schema = tool.get_parameters()

    return {
        "type": "function",
        "function": {
            "name": tool.get_name(),
            "description": tool.description,
            "parameters": schema,
        },
    }
