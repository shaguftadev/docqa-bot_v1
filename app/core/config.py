from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated process configuration loaded from environment or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "SupportPilot AI"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://supportpilot:change-me@localhost:5432/supportpilot",
        min_length=1,
    )
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "supportpilot_documents"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = Field(default=384, gt=0)
    chunk_size: int = Field(default=800, gt=0)
    chunk_overlap: int = Field(default=120, ge=0)
    upload_max_mb: int = Field(default=20, gt=0)
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "supportpilot-ai"
    auth_enabled: bool = False
    cognito_issuer: str | None = None
    cognito_app_client_id: str | None = None
    cognito_tenant_claim: str = "tenant_id"
    cognito_resource_audience: str | None = None
    cognito_approval_scope: str = "support/approve"

    @field_validator("cognito_issuer", "cognito_app_client_id", "cognito_resource_audience", mode="before")
    @classmethod
    def blank_optional_cognito_settings(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_chunk_sizes(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.app_env.lower() != "local" and not self.auth_enabled:
            raise ValueError("AUTH_ENABLED must be true outside local development")
        if self.auth_enabled:
            if not self.cognito_issuer or not self.cognito_app_client_id:
                raise ValueError("COGNITO_ISSUER and COGNITO_APP_CLIENT_ID are required when auth is enabled")
            parsed_issuer = urlparse(self.cognito_issuer)
            if parsed_issuer.scheme != "https" or not parsed_issuer.netloc or parsed_issuer.query or parsed_issuer.fragment:
                raise ValueError("COGNITO_ISSUER must be an HTTPS issuer URL without query or fragment")
            if not self.cognito_tenant_claim.strip():
                raise ValueError("COGNITO_TENANT_CLAIM must not be empty")
            if not self.cognito_approval_scope.strip():
                raise ValueError("COGNITO_APPROVAL_SCOPE must not be empty")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Create settings once per process; tests can clear this cache."""
    return Settings()
