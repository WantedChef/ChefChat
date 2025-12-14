from __future__ import annotations

import os
from pathlib import Path
import re
import shlex

from chefchat.core.compatibility import StrEnum

try:
    import tomllib
except ImportError:
    import tomli as tomllib
from typing import Annotated, Any, Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_core import to_jsonable_python
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
import tomli_w

from chefchat.core.prompts import SystemPrompt
from chefchat.core.tools.base import BaseToolConfig


def get_vibe_home() -> Path:
    if vibe_home := os.getenv("VIBE_HOME"):
        return Path(vibe_home).expanduser().resolve()
    return Path.home() / ".vibe"


GLOBAL_CONFIG_DIR = get_vibe_home()
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.toml"
GLOBAL_ENV_FILE = GLOBAL_CONFIG_DIR / ".env"
DEFAULT_MAX_TOKENS = 8192


def resolve_config_file() -> Path:
    for directory in (cwd := Path.cwd(), *cwd.parents):
        if (candidate := directory / ".vibe" / "config.toml").is_file():
            return candidate
    return GLOBAL_CONFIG_FILE


def load_api_keys_from_env() -> None:
    project_env_file = CONFIG_DIR / ".env"
    cwd_env_file = Path.cwd() / ".env"
    for env_file in (cwd_env_file, project_env_file, GLOBAL_ENV_FILE):
        if not env_file.is_file():
            continue

        env_vars = dotenv_values(env_file)
        for key, value in env_vars.items():
            if value:
                os.environ.setdefault(key, value)


CONFIG_FILE = resolve_config_file()
CONFIG_DIR = CONFIG_FILE.parent
AGENT_DIR = CONFIG_DIR / "agents"
PROMPT_DIR = CONFIG_DIR / "prompts"
INSTRUCTIONS_FILE = CONFIG_DIR / "instructions.md"
HISTORY_FILE = CONFIG_DIR / "vibehistory"
PROJECT_DOC_FILENAMES = ["AGENTS.md", "VIBE.md", ".chefchat.md"]


class MissingAPIKeyError(RuntimeError):
    def __init__(self, env_key: str, provider_name: str) -> None:
        super().__init__(
            f"Missing {env_key} environment variable for {provider_name} provider"
        )
        self.env_key = env_key
        self.provider_name = provider_name


class MissingPromptFileError(RuntimeError):
    def __init__(self, system_prompt_id: str, prompt_dir: str) -> None:
        super().__init__(
            f"Invalid system_prompt_id value: '{system_prompt_id}'. "
            f"Must be one of the available prompts ({', '.join(f'{p.name.lower()}' for p in SystemPrompt)}), "
            f"or correspond to a .md file in {prompt_dir}"
        )
        self.system_prompt_id = system_prompt_id
        self.prompt_dir = prompt_dir


class WrongBackendError(RuntimeError):
    def __init__(self, backend: Backend, is_mistral_api: bool) -> None:
        super().__init__(
            f"Wrong backend '{backend}' for {'' if is_mistral_api else 'non-'}"
            f"mistral API. Use '{Backend.MISTRAL}' for mistral API and '{Backend.GENERIC}' for others."
        )
        self.backend = backend
        self.is_mistral_api = is_mistral_api


class TomlFileSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self.toml_data = self._load_toml()

    def _load_toml(self) -> dict[str, Any]:
        file = CONFIG_FILE
        try:
            with file.open("rb") as f:
                return tomllib.load(f)
        except FileNotFoundError:
            return {}
        except tomllib.TOMLDecodeError as e:
            raise RuntimeError(f"Invalid TOML in {file}: {e}") from e
        except OSError as e:
            raise RuntimeError(f"Cannot read {file}: {e}") from e

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        return self.toml_data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return self.toml_data


class ProjectContextConfig(BaseSettings):
    max_chars: int = 40_000
    default_commit_count: int = 5
    max_doc_bytes: int = 32 * 1024
    truncation_buffer: int = 1_000
    max_depth: int = 3
    max_files: int = 1000
    max_dirs_per_level: int = 20
    timeout_seconds: float = 2.0


class SessionLoggingConfig(BaseSettings):
    save_dir: str = ""
    session_prefix: str = "session"
    enabled: bool = True

    @field_validator("save_dir", mode="before")
    @classmethod
    def set_default_save_dir(cls, v: str) -> str:
        if not v:
            return str(get_vibe_home() / "logs" / "session")
        return v

    @field_validator("save_dir", mode="after")
    @classmethod
    def expand_save_dir(cls, v: str) -> str:
        return str(Path(v).expanduser().resolve())


class Backend(StrEnum):
    MISTRAL = "mistral"
    GENERIC = "generic"


class ProviderConfig(BaseModel):
    name: str
    api_base: str
    api_key_env_var: str = ""
    api_style: str = "openai"
    backend: Backend = Backend.GENERIC
    features: set[str] = Field(default_factory=set, description="Provider capabilities")


class _MCPBase(BaseModel):
    name: str = Field(description="Short alias used to prefix tool names")
    prompt: str | None = Field(
        default=None, description="Optional usage hint appended to tool descriptions"
    )

    @field_validator("name", mode="after")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", v)
        normalized = normalized.strip("_-")
        return normalized[:256]


class _MCPHttpFields(BaseModel):
    url: str = Field(description="Base URL of the MCP HTTP server")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Additional HTTP headers when using 'http' transport (e.g., Authorization or X-API-Key)."
        ),
    )
    api_key_env: str = Field(
        default="",
        description=(
            "Environment variable name containing an API token to send for HTTP transport."
        ),
    )
    api_key_header: str = Field(
        default="Authorization",
        description=(
            "HTTP header name to carry the token when 'api_key_env' is set (e.g., 'Authorization' or 'X-API-Key')."
        ),
    )
    api_key_format: str = Field(
        default="Bearer {token}",
        description=(
            "Format string for the header value when 'api_key_env' is set. Use '{token}' placeholder."
        ),
    )

    def http_headers(self) -> dict[str, str]:
        hdrs = dict(self.headers or {})
        env_var = (self.api_key_env or "").strip()
        if env_var and (token := os.getenv(env_var)):
            target = (self.api_key_header or "").strip() or "Authorization"
            if not any(h.lower() == target.lower() for h in hdrs):
                try:
                    value = (self.api_key_format or "{token}").format(token=token)
                except Exception:
                    value = token
                hdrs[target] = value
        return hdrs


class MCPHttp(_MCPBase, _MCPHttpFields):
    transport: Literal["http"]


class MCPStreamableHttp(_MCPBase, _MCPHttpFields):
    transport: Literal["streamable-http"]


class MCPStdio(_MCPBase):
    transport: Literal["stdio"]
    command: str | list[str]
    args: list[str] = Field(default_factory=list)

    def argv(self) -> list[str]:
        base = (
            shlex.split(self.command)
            if isinstance(self.command, str)
            else list(self.command or [])
        )
        return [*base, *self.args] if self.args else base


MCPServer = Annotated[
    MCPHttp | MCPStreamableHttp | MCPStdio, Field(discriminator="transport")
]


class ModelConfig(BaseModel):
    name: str
    provider: str
    alias: str
    temperature: float = 0.2
    max_tokens: int | None = None
    input_price: float = 0.0  # Price per million input tokens
    output_price: float = 0.0  # Price per million output tokens
    features: set[str] = Field(default_factory=set, description="Model capabilities")
    multimodal: bool = Field(default=False, description="Supports image/video input")
    max_file_size: int = Field(default=0, description="Max file size for uploads (MB)")
    rate_limits: dict[str, int] = Field(
        default_factory=dict, description="TPM/RPM limits"
    )

    @model_validator(mode="before")
    @classmethod
    def _default_alias_to_name(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "alias" not in data or data["alias"] is None:
                data["alias"] = data.get("name")
        return data


DEFAULT_PROVIDERS = [
    ProviderConfig(
        name="mistral",
        api_base="https://api.mistral.ai/v1",
        api_key_env_var="MISTRAL_API_KEY",
        backend=Backend.MISTRAL,
    ),
    ProviderConfig(
        name="openai",
        api_base="https://api.openai.com/v1",
        api_key_env_var="OPENAI_API_KEY",
        api_style="openai",
        backend=Backend.GENERIC,
    ),
    ProviderConfig(
        name="llamacpp",
        api_base="http://127.0.0.1:8080/v1",
        api_key_env_var="",  # NOTE: if you wish to use --api-key in llama-server, change this value
    ),
    ProviderConfig(
        name="groq",
        api_base="https://api.groq.com/openai/v1",
        api_key_env_var="GROQ_API_KEY",
        api_style="openai",
        backend=Backend.GENERIC,
        features={"speed", "multimodal", "tool_use", "reasoning", "vision", "speech"},
    ),
]

DEFAULT_MODELS = [
    ModelConfig(
        name="codestral-25-08",
        provider="mistral",
        alias="devstral-2512",
        input_price=0.4,
        output_price=2.0,
    ),
    ModelConfig(
        name="devstral-2-25-12",
        provider="mistral",
        alias="devstral-2",
        input_price=0.4,
        output_price=2.0,
    ),
    ModelConfig(
        name="codestral-25-08",
        provider="mistral",
        alias="mistral-vibe-cli",
        input_price=0.4,
        output_price=2.0,
    ),
    ModelConfig(
        name="gpt-4o",
        provider="openai",
        alias="gpt4o",
        temperature=0.2,
        input_price=2.5,
        output_price=10.0,
    ),
    ModelConfig(
        name="gpt-4o-mini",
        provider="openai",
        alias="gpt4o-mini",
        temperature=0.2,
        input_price=0.15,
        output_price=0.60,
    ),
    ModelConfig(
        name="gpt-4-turbo",
        provider="openai",
        alias="gpt4-turbo",
        temperature=0.2,
        input_price=10.0,
        output_price=30.0,
    ),
    ModelConfig(
        name="gpt-3.5-turbo",
        provider="openai",
        alias="gpt35",
        temperature=0.2,
        input_price=0.5,
        output_price=1.5,
    ),
    ModelConfig(
        name="devstral",
        provider="llamacpp",
        alias="local",
        input_price=0.0,
        output_price=0.0,
    ),
    # Groq Native Models
    ModelConfig(
        name="llama-3.1-8b-instant",
        provider="groq",
        alias="groq-8b",
        temperature=0.2,
        input_price=0.05,
        output_price=0.08,
        max_tokens=131072,
        features={"speed", "low_cost"},
        rate_limits={"tpm": 250000, "rpm": 1000},
    ),
    ModelConfig(
        name="llama-3.3-70b-versatile",
        provider="groq",
        alias="groq-70b",
        temperature=0.2,
        input_price=0.59,
        output_price=0.79,
        max_tokens=32768,
        features={"versatile", "balanced"},
        rate_limits={"tpm": 300000, "rpm": 1000},
    ),
    # Meta Llama Models via Groq
    ModelConfig(
        name="meta-llama/llama-4-scout-17b-16e-instruct",
        provider="groq",
        alias="llama-scout",
        temperature=0.2,
        input_price=0.11,
        output_price=0.34,
        max_tokens=8192,
        multimodal=True,
        max_file_size=20,
        features={"multimodal", "vision", "tool_use", "fast"},
        rate_limits={"tpm": 300000, "rpm": 1000},
    ),
    ModelConfig(
        name="meta-llama/llama-4-maverick-17b-128e-instruct",
        provider="groq",
        alias="llama-maverick",
        temperature=0.2,
        input_price=0.20,
        output_price=0.60,
        max_tokens=8192,
        multimodal=True,
        max_file_size=20,
        features={"multimodal", "vision", "tool_use", "premium"},
        rate_limits={"tpm": 300000, "rpm": 1000},
    ),
    # Kimi Models via Groq
    ModelConfig(
        name="moonshotai/kimi-k2-instruct-0905",
        provider="groq",
        alias="kimi-k2",
        temperature=0.3,
        input_price=1.00,
        output_price=3.00,
        max_tokens=16384,
        features={"reasoning", "large_context", "coding"},
        rate_limits={"tpm": 250000, "rpm": 1000},
    ),
    # OpenAI Models via Groq
    ModelConfig(
        name="openai/gpt-oss-120b",
        provider="groq",
        alias="gpt-oss-120b",
        temperature=0.2,
        input_price=0.15,
        output_price=0.60,
        max_tokens=65536,
        features={"reasoning", "browser_tools", "balanced"},
        rate_limits={"tpm": 250000, "rpm": 1000},
    ),
    ModelConfig(
        name="openai/gpt-oss-20b",
        provider="groq",
        alias="gpt-oss-20b",
        temperature=0.2,
        input_price=0.075,
        output_price=0.30,
        max_tokens=65536,
        features={"speed", "browser_tools", "cost_effective"},
        rate_limits={"tpm": 250000, "rpm": 1000},
    ),
    # Qwen Models via Groq
    ModelConfig(
        name="qwen/qwen3-32b",
        provider="groq",
        alias="qwen-32b",
        temperature=0.2,
        input_price=0.29,
        output_price=0.59,
        max_tokens=40960,
        features={"multilingual", "balanced"},
        rate_limits={"tpm": 300000, "rpm": 1000},
    ),
]


class VibeConfig(BaseSettings):
    active_model: str = "groq-8b"
    vim_keybindings: bool = False
    disable_welcome_banner_animation: bool = False
    displayed_workdir: str = ""
    fun_mode: bool = True
    color_enabled: bool = True
    emoji_enabled: bool = True
    ui_theme: str = "chef-dark"
    auto_compact_threshold: int = 200_000
    context_warnings: bool = False
    textual_theme: str = "textual-dark"
    instructions: str = ""
    workdir: Path | None = Field(default=None, exclude=True)
    system_prompt_id: str = "cli"
    include_commit_signature: bool = True
    include_model_info: bool = True
    include_project_context: bool = True
    include_prompt_detail: bool = True
    file_indexer_parallel_walk: bool = True
    file_indexer_max_workers: int | None = 4
    enable_update_checks: bool = True
    api_timeout: float = 720.0
    providers: list[ProviderConfig] = Field(
        default_factory=lambda: list(DEFAULT_PROVIDERS)
    )
    models: list[ModelConfig] = Field(default_factory=lambda: list(DEFAULT_MODELS))

    project_context: ProjectContextConfig = Field(default_factory=ProjectContextConfig)
    session_logging: SessionLoggingConfig = Field(default_factory=SessionLoggingConfig)
    tools: dict[str, BaseToolConfig] = Field(default_factory=dict)
    tool_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Additional directories to search for custom tools. "
            "Each path may be absolute or relative to the current working directory."
        ),
    )

    mcp_servers: list[MCPServer] = Field(
        default_factory=list, description="Preferred MCP server configuration entries."
    )

    enabled_tools: list[str] = Field(
        default_factory=list,
        description=(
            "An explicit list of tool names/patterns to enable. If set, only these"
            " tools will be active. Supports exact names, glob patterns (e.g.,"
            " 'serena_*'), and regex with 're:' prefix or regex-like patterns (e.g.,"
            " 're:^serena_.*' or 'serena.*')."
        ),
    )
    disabled_tools: list[str] = Field(
        default_factory=list,
        description=(
            "A list of tool names/patterns to disable. Ignored if 'enabled_tools'"
            " is set. Supports exact names, glob patterns (e.g., 'bash*'), and"
            " regex with 're:' prefix or regex-like patterns."
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="VIBE_", case_sensitive=False, extra="forbid"
    )

    @property
    def effective_workdir(self) -> Path:
        return self.workdir if self.workdir is not None else Path.cwd()

    @property
    def system_prompt(self) -> str:
        try:
            return SystemPrompt[self.system_prompt_id.upper()].read()
        except KeyError:
            pass

        custom_sp_path = (PROMPT_DIR / self.system_prompt_id).with_suffix(".md")
        if not custom_sp_path.is_file():
            raise MissingPromptFileError(self.system_prompt_id, str(PROMPT_DIR))
        return custom_sp_path.read_text()

    def get_active_model(self) -> ModelConfig:
        for model in self.models:
            if self.active_model in {model.alias, model.name}:
                return model
        raise ValueError(
            f"Active model '{self.active_model}' not found in configuration."
        )

    def get_provider_for_model(self, model: ModelConfig) -> ProviderConfig:
        for provider in self.providers:
            if provider.name == model.provider:
                return provider
        raise ValueError(
            f"Provider '{model.provider}' for model '{model.name}' not found in configuration."
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Define the priority of settings sources.

        Note: dotenv_settings is intentionally excluded. API keys and other
        non-config environment variables are stored in .env but loaded manually
        into os.environ for use by providers. Only VIBE_* prefixed environment
        variables (via env_settings) and TOML config are used for Pydantic settings.
        """
        return (
            init_settings,
            env_settings,
            TomlFileSettingsSource(settings_cls),
            file_secret_settings,
        )

    @model_validator(mode="after")
    def _check_api_key(self) -> VibeConfig:
        try:
            active_model = self.get_active_model()
            provider = self.get_provider_for_model(active_model)
            api_key_env = provider.api_key_env_var
            if api_key_env and not os.getenv(api_key_env):
                raise MissingAPIKeyError(api_key_env, provider.name)
        except ValueError:
            pass
        return self

    @model_validator(mode="after")
    def _check_api_backend_compatibility(self) -> VibeConfig:
        try:
            active_model = self.get_active_model()
            provider = self.get_provider_for_model(active_model)
            MISTRAL_API_BASES = [
                "https://codestral.mistral.ai",
                "https://api.mistral.ai",
            ]
            is_mistral_api = any(
                provider.api_base.startswith(api_base) for api_base in MISTRAL_API_BASES
            )
            if (is_mistral_api and provider.backend != Backend.MISTRAL) or (
                not is_mistral_api and provider.backend != Backend.GENERIC
            ):
                raise WrongBackendError(provider.backend, is_mistral_api)

        except ValueError:
            pass
        return self

    @field_validator("workdir", mode="before")
    @classmethod
    def _expand_workdir(cls, v: Any) -> Path | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None

        if isinstance(v, str):
            v = Path(v).expanduser().resolve()
        elif isinstance(v, Path):
            v = v.expanduser().resolve()
        if not v.is_dir():
            raise ValueError(
                f"Tried to set {v} as working directory, path doesn't exist"
            )
        return v

    @field_validator("tools", mode="before")
    @classmethod
    def _normalize_tool_configs(cls, v: Any) -> dict[str, BaseToolConfig]:
        if not isinstance(v, dict):
            return {}

        normalized: dict[str, BaseToolConfig] = {}
        for tool_name, tool_config in v.items():
            if isinstance(tool_config, BaseToolConfig):
                normalized[tool_name] = tool_config
            elif isinstance(tool_config, dict):
                normalized[tool_name] = BaseToolConfig.model_validate(tool_config)
            else:
                normalized[tool_name] = BaseToolConfig()

        return normalized

    @model_validator(mode="after")
    def _validate_model_uniqueness(self) -> VibeConfig:
        seen_aliases: set[str] = set()
        for model in self.models:
            if model.alias in seen_aliases:
                raise ValueError(
                    f"Duplicate model alias found: '{model.alias}'. Aliases must be unique."
                )
            seen_aliases.add(model.alias)
        return self

    @model_validator(mode="after")
    def _check_system_prompt(self) -> VibeConfig:
        _ = self.system_prompt
        return self

    @classmethod
    def save_updates(cls, updates: dict[str, Any]) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        current_config = TomlFileSettingsSource(cls).toml_data

        def deep_merge(target: dict, source: dict) -> None:
            for key, value in source.items():
                if (
                    key in target
                    and isinstance(target.get(key), dict)
                    and isinstance(value, dict)
                ):
                    deep_merge(target[key], value)
                elif (
                    key in target
                    and isinstance(target.get(key), list)
                    and isinstance(value, list)
                ):
                    if key in {"providers", "models"}:
                        target[key] = value
                    else:
                        target[key] = list(set(value + target[key]))
                else:
                    target[key] = value

        deep_merge(current_config, updates)
        cls.dump_config(
            to_jsonable_python(current_config, exclude_none=True, fallback=str)
        )

    @classmethod
    def dump_config(cls, config: dict[str, Any]) -> None:
        with CONFIG_FILE.open("wb") as f:
            tomli_w.dump(config, f)

    @classmethod
    def _get_agent_config(cls, agent: str | None) -> dict[str, Any] | None:
        if agent is None:
            return None

        agent_config_path = (AGENT_DIR / agent).with_suffix(".toml")
        try:
            return tomllib.load(agent_config_path.open("rb"))
        except FileNotFoundError:
            raise ValueError(
                f"Config '{agent}.toml' for agent not found in {AGENT_DIR}"
            )

    @classmethod
    def _migrate(cls) -> None:
        if not CONFIG_FILE.exists():
            return

        try:
            with CONFIG_FILE.open("rb") as f:
                config = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return

        needs_save = False

        if (
            "auto_compact_threshold" not in config
            or config["auto_compact_threshold"] == 100_000  # noqa: PLR2004
        ):
            config["auto_compact_threshold"] = 200_000
            needs_save = True

        if needs_save:
            cls.dump_config(config)

    @classmethod
    def load(cls, agent: str | None = None, **overrides: Any) -> VibeConfig:
        cls._migrate()
        agent_config = cls._get_agent_config(agent)
        init_data = {**(agent_config or {}), **overrides}
        return cls(**init_data)

    @classmethod
    def create_default(cls) -> dict[str, Any]:
        try:
            config = cls()
        except MissingAPIKeyError:
            config = cls.model_construct()

        config_dict = config.model_dump(mode="json", exclude_none=True)

        from chefchat.core.tools.manager import ToolManager

        tool_defaults = ToolManager.discover_tool_defaults()
        if tool_defaults:
            config_dict["tools"] = tool_defaults

        return config_dict


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_cached_config: VibeConfig | None = None


def get_config(agent: str | None = None, force_reload: bool = False) -> VibeConfig:
    """Get the global config (cached singleton).

    This provides efficient access to the config from anywhere in the codebase,
    avoiding redundant file reads and parsing.

    Args:
        agent: Optional agent name to load config for
        force_reload: If True, reload config even if cached

    Returns:
        The global VibeConfig instance

    Example:
        >>> from chefchat.core.config import get_config
        >>> config = get_config()
        >>> print(config.active_model)
    """
    global _cached_config

    if _cached_config is None or force_reload:
        _cached_config = VibeConfig.load(agent)

    return _cached_config


def clear_config_cache() -> None:
    """Clear the cached config, forcing a reload on next access."""
    global _cached_config
    _cached_config = None
