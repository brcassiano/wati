"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables and .env file.

    WATI-specific settings use the WATI_ prefix.
    LLM/provider keys use standard names (no prefix) for litellm compatibility.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # WATI API (prefix: WATI_)
    wati_base_url: str = Field(
        default="https://live-mt-server.wati.io",
        description="Base URL including tenant ID, e.g. https://live-mt-server.wati.io/304506",
        validation_alias=AliasChoices("wati_base_url", "WATI_BASE_URL"),
    )
    wati_api_token: str = Field(
        default="",
        validation_alias=AliasChoices("wati_api_token", "WATI_API_TOKEN"),
    )

    # LLM (no prefix — litellm convention)
    llm_model: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        validation_alias=AliasChoices("llm_model", "LLM_MODEL"),
    )
    llm_fallback_models: str = Field(
        default="",
        validation_alias=AliasChoices("llm_fallback_models", "LLM_FALLBACK_MODELS"),
    )

    # Provider API keys (no prefix — litellm reads these from env directly)
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("anthropic_api_key", "ANTHROPIC_API_KEY"),
    )
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("openrouter_api_key", "OPENROUTER_API_KEY"),
    )
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("openai_api_key", "OPENAI_API_KEY"),
    )

    # Agent behavior (prefix: WATI_)
    use_mock_api: bool = Field(
        default=False,
        validation_alias=AliasChoices("use_mock_api", "WATI_USE_MOCK_API"),
    )
    dry_run_default: bool = Field(
        default=True,
        validation_alias=AliasChoices("dry_run_default", "WATI_DRY_RUN_DEFAULT"),
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("log_level", "WATI_LOG_LEVEL"),
    )

    # Webhook server (prefix: WATI_)
    webhook_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("webhook_enabled", "WATI_WEBHOOK_ENABLED"),
    )
    webhook_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("webhook_host", "WATI_WEBHOOK_HOST"),
    )
    webhook_port: int = Field(
        default=8080,
        validation_alias=AliasChoices("webhook_port", "WATI_WEBHOOK_PORT"),
    )
    webhook_path: str = Field(
        default="/webhook/status",
        validation_alias=AliasChoices("webhook_path", "WATI_WEBHOOK_PATH"),
    )

    # Slack notifications (no prefix — third-party service)
    slack_webhook_url: str = Field(
        default="",
        validation_alias=AliasChoices("slack_webhook_url", "SLACK_WEBHOOK_URL"),
    )
