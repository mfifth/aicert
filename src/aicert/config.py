"""Configuration models for aicert."""

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ChaosConfig(BaseModel):
    """Configuration for FakeAdapter chaos mode.
    
    All probability values should be between 0 and 1.
    """
    
    seed: int = Field(default=1337, description="Random seed for reproducible chaos")
    p_invalid_json: float = Field(default=0.0, ge=0, le=1, description="Probability of returning invalid JSON")
    p_wrong_schema: float = Field(default=0.0, ge=0, le=1, description="Probability of JSON with wrong schema")
    p_extra_keys: float = Field(default=0.0, ge=0, le=1, description="Probability of JSON with extra keys")
    p_wrapped_json: float = Field(default=0.0, ge=0, le=1, description="Probability of JSON wrapped in markdown fence")
    p_non_json: float = Field(default=0.0, ge=0, le=1, description="Probability of non-JSON response")
    p_timeout: float = Field(default=0.0, ge=0, le=1, description="Probability of timeout")
    p_http_429: float = Field(default=0.0, ge=0, le=1, description="Probability of HTTP 429 error")
    p_http_500: float = Field(default=0.0, ge=0, le=1, description="Probability of HTTP 500 error")


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    id: str = Field(..., description="Provider identifier")
    provider: Literal["openai", "anthropic", "openai_compatible", "fake"] = Field(
        ..., description="Provider type"
    )
    model: str = Field(..., description="Model identifier")
    temperature: float = Field(..., description="Temperature for sampling")
    base_url: Optional[str] = Field(
        None, description="Base URL for openai_compatible provider"
    )
    chaos: Optional[ChaosConfig] = Field(
        None, description="Chaos mode configuration (fake provider only)"
    )


class ValidationConfig(BaseModel):
    """Configuration for output validation."""

    extract_json: bool = Field(default=True, description="Extract JSON from response")
    allow_extra_keys: bool = Field(
        default=False, description="Allow extra keys in JSON output"
    )


class ThresholdsConfig(BaseModel):
    """Configuration for pass/fail thresholds."""

    min_stability: int = Field(default=85, description="Minimum stability percentage")
    min_compliance: int = Field(default=95, description="Minimum compliance percentage")
    max_cost_usd: Optional[float] = Field(None, description="Maximum cost in USD")
    p95_latency_ms: Optional[int] = Field(None, description="P95 latency in milliseconds")


class CIConfig(BaseModel):
    """Configuration for CI mode."""

    runs: int = Field(default=10, description="Number of runs in CI mode")
    save_on_fail: bool = Field(
        default=True, description="Save results on test failure"
    )


class Config(BaseModel):
    """Main configuration for aicert."""

    project: str = Field(..., description="Project name")

    providers: list[ProviderConfig] = Field(
        ..., description="List of LLM provider configurations"
    )

    prompt_file: str = Field(..., description="Path to prompt file")
    cases_file: str = Field(..., description="Path to test cases file (JSONL)")
    schema_file: str = Field(..., description="Path to JSON schema file")

    runs: int = Field(default=50, description="Number of test runs")
    concurrency: int = Field(default=10, description="Number of concurrent requests")
    timeout_s: int = Field(default=30, description="Timeout for requests in seconds")

    validation: ValidationConfig = Field(
        default_factory=ValidationConfig, description="Validation settings"
    )

    thresholds: ThresholdsConfig = Field(
        default_factory=ThresholdsConfig, description="Pass/fail thresholds"
    )

    ci: CIConfig = Field(default_factory=CIConfig, description="CI mode settings")

    @field_validator("providers", mode="before")
    @classmethod
    def ensure_providers_list(cls, v):
        """Ensure providers is a list."""
        if isinstance(v, dict):
            return [v]
        return v

    @property
    def primary_provider(self) -> ProviderConfig:
        """Get the primary provider (first one)."""
        return self.providers[0]


class ConfigLoadError(Exception):
    """Error raised when configuration loading fails."""

    def __init__(self, message: str, config_path: Optional[str] = None, hint: Optional[str] = None):
        self.message = message
        self.config_path = config_path
        self.hint = hint
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message with context."""
        parts = []
        if self.config_path:
            parts.append(f"[bold red]Config file: {self.config_path}[/bold red]")
        parts.append(f"[bold red]Error:[/bold red] {self.message}")
        if self.hint:
            parts.append(f"[bold yellow]Hint:[/bold yellow] {self.hint}")
        return "\n".join(parts)


def load_config(path: str) -> Config:
    """Load configuration from YAML file.

    Args:
        path: Path to the YAML config file.

    Returns:
        Config object with validated settings.

    Raises:
        ConfigLoadError: If the file cannot be loaded or validation fails.
        FileNotFoundError: If referenced files don't exist.
    """
    import yaml

    config_path = Path(path)
    config_dir = config_path.parent

    try:
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigLoadError(
            message=f"Config file not found: {path}",
            config_path=str(config_path.resolve()),
            hint="Make sure the path is correct and the file exists."
        )
    except yaml.YAMLError as e:
        raise ConfigLoadError(
            message=f"Invalid YAML in config file: {e}",
            config_path=str(config_path.resolve()),
            hint="Check for syntax errors like incorrect indentation or missing colons."
        )

    try:
        config = Config(**config_data)
    except Exception as e:
        raise ConfigLoadError(
            message=f"Configuration validation failed: {e}",
            config_path=str(config_path.resolve()),
            hint="Check that all required fields are present and have the correct types."
        )

    # Validate referenced files exist, resolving relative to config directory
    errors: list[str] = []

    for field_name in ["prompt_file", "cases_file", "schema_file"]:
        file_path = getattr(config, field_name)
        resolved_path = config_dir / file_path
        if not resolved_path.exists():
            errors.append(
                f"{field_name}: '{file_path}' not found "
                f"(resolved to: {resolved_path})"
            )

    if errors:
        raise ConfigLoadError(
            message="Referenced files not found:\n  - " + "\n  - ".join(errors),
            config_path=str(config_path.resolve()),
            hint="Make sure all file paths are correct and files exist. Paths are resolved relative to the config file directory."
        )

    return config
