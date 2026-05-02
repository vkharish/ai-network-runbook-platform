from enum import Enum
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    VLLM = "vllm"  # Phase 3: on-prem OpenAI-compatible endpoint


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class LogFormat(str, Enum):
    JSON = "json"
    TEXT = "text"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ai-network-runbook-platform"
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_debug: bool = False
    app_secret_key: str = Field(..., min_length=32)
    credential_encryption_key: str = Field(..., min_length=32)
    app_allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.app_allowed_origins.split(",")]

    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection_name: str = "runbook_embeddings"

    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    embedding_provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    embedding_model: str = "text-embedding-3-small"

    reranker_enabled: bool = False  # set RERANKER_ENABLED=true to enable cross-encoder

    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON

    # ---------------------------------------------------------------------------
    # HashiCorp Vault
    # ---------------------------------------------------------------------------
    vault_enabled: bool = False
    vault_addr: str = "http://localhost:8200"
    vault_token: str = ""                      # dev/testing only
    vault_role_id: str = ""                    # AppRole production auth
    vault_secret_id: str = ""
    vault_mount_path: str = "secret"
    vault_device_prefix: str = "devices"

    # ---------------------------------------------------------------------------
    # ServiceNow
    # ---------------------------------------------------------------------------
    snow_enabled: bool = False
    snow_instance_url: str = ""                # e.g. "dev12345.service-now.com"
    snow_username: str = ""
    snow_password: str = ""
    snow_webhook_secret: str = ""              # HMAC shared secret for inbound webhooks
    snow_auto_create_incidents: bool = True

    # ---------------------------------------------------------------------------
    # NetBox device sync
    # ---------------------------------------------------------------------------
    netbox_enabled: bool = False
    netbox_url: str = ""                       # e.g. "https://netbox.corp.local"
    netbox_token: str = ""
    netbox_sync_interval_minutes: int = 30

    # ---------------------------------------------------------------------------
    # Slack
    # ---------------------------------------------------------------------------
    slack_enabled: bool = False
    slack_bot_token: str = ""                  # xoxb-...
    slack_channel: str = ""                    # e.g. "#noc-alerts"
    slack_signing_secret: str = ""             # HMAC validation of interactive payloads

    # ---------------------------------------------------------------------------
    # Microsoft Teams
    # ---------------------------------------------------------------------------
    teams_enabled: bool = False
    teams_webhook_url: str = ""                # Incoming webhook URL from Teams connector

    # ---------------------------------------------------------------------------
    # OpenTelemetry distributed tracing
    # ---------------------------------------------------------------------------
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "ai-network-runbook-platform"

    # ---------------------------------------------------------------------------
    # Multi-tenant site isolation
    # ---------------------------------------------------------------------------
    multitenancy_enabled: bool = False

    # ---------------------------------------------------------------------------
    # vLLM on-prem endpoint (Phase 3 — VLLM provider)
    # ---------------------------------------------------------------------------
    vllm_base_url: str = "http://localhost:8080/v1"  # OpenAI-compatible base URL
    vllm_model: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    # ---------------------------------------------------------------------------
    # Phase 3: Intelligence features (all off by default)
    # ---------------------------------------------------------------------------
    feedback_enabled: bool = False          # Diagnosis feedback → RAG reranking adjustment
    correlation_enabled: bool = False       # Incident correlation via embedding similarity
    runbook_autogen_enabled: bool = False   # Auto-generate runbooks from resolved incidents
    predictive_enabled: bool = False        # Predictive anomaly detection on device metrics

    # ---------------------------------------------------------------------------
    # SSO / OIDC
    # ---------------------------------------------------------------------------
    oidc_enabled: bool = False
    oidc_discovery_url: str = ""               # /.well-known/openid-configuration URL
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:8000/api/v1/auth/oidc/callback"
    oidc_admin_groups: str = ""                # comma-separated group names → ADMIN role
    oidc_engineer_groups: str = ""             # comma-separated group names → ENGINEER role
    oidc_sync_roles: bool = False              # sync role from OIDC groups on every login

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == AppEnv.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
