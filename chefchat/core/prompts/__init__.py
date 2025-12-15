from __future__ import annotations

from pathlib import Path
import re

from chefchat import CHEFCHAT_ROOT
from chefchat.core.compatibility import StrEnum

_PROMPTS_DIR = CHEFCHAT_ROOT / "core" / "prompts"


class Prompt(StrEnum):
    @property
    def path(self) -> Path:
        return (_PROMPTS_DIR / self.value).with_suffix(".md")

    def read(self) -> str:
        if not self.path.is_file():
            raise FileNotFoundError(f"Prompt file not found: {self.path}")
        raw = self.path.read_text(encoding="utf-8")
        # Remove control characters/NULLs that can break providers
        sanitized = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", raw).strip()
        if not sanitized:
            raise ValueError(f"Prompt file is empty after sanitization: {self.path}")
        return sanitized


class SystemPrompt(Prompt):
    CLI = "cli"
    TESTS = "tests"
    STRICT_JUGGERNAUT = "strict_juggernaut"


class UtilityPrompt(Prompt):
    COMPACT = "compact"
    DANGEROUS_DIRECTORY = "dangerous_directory"
    PROJECT_CONTEXT = "project_context"


__all__ = ["SystemPrompt", "UtilityPrompt"]
