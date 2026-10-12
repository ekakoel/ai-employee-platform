from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Employee Platform"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "sqlite:///./ai_employee.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Auth (Job 15)
    auth_enabled: bool = True
    # Deprecated: headers cannot authenticate users, even in development.
    allow_legacy_user_header: bool = False
    jwt_secret: str = "dev-change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15
    jwt_refresh_expire_minutes: int = 60 * 24 * 14

    storage_backend: str = "local"
    storage_local_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    worker_poll_seconds: int = 30

    # Job 23 — platform admin / support
    # Deprecated and ignored: platform grants use persisted admin privileges.
    platform_admin_emails: str = ""
    # Deprecated: company creation always requires a platform administrator.
    public_company_create: bool = False
    allow_impersonation: bool = False

    log_level: str = "INFO"
    log_json: bool = False

    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"

    # Job 26 — vector knowledge retrieval
    knowledge_vector: bool = False
    embedding_provider: str = "fake"  # fake | hash
    embedding_dims: int = 64
    hybrid_keyword_weight: float = 0.4
    hybrid_vector_weight: float = 0.6

    # Job 28 — LLM cost / budget (USD estimates; local models ≈ 0)
    llm_cost_per_1k_prompt_tokens: float = 0.0
    llm_cost_per_1k_completion_tokens: float = 0.0
    llm_daily_budget_usd: float = 0.0  # 0 = no soft limit

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value):
        normalized = str(value).strip().lower()
        aliases = {
            "dev": "development", "local": "development", "testing": "test",
            "prod": "production", "release": "production", "stage": "staging",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"development", "test", "staging", "production"}:
            raise ValueError("APP_ENV must identify development, test, staging, or production")
        return normalized

    @model_validator(mode="after")
    def check_security_configuration(self):
        self.validate_security()
        return self

    def validate_security(self) -> None:
        """Reject unsafe deployed settings without including secret values."""
        if not 1 <= self.jwt_expire_minutes <= 15:
            raise ValueError("JWT_EXPIRE_MINUTES must be between 1 and 15")
        if not 1 <= self.jwt_refresh_expire_minutes <= 60 * 24 * 14:
            raise ValueError("JWT_REFRESH_EXPIRE_MINUTES must be between 1 and 20160")
        environment = self.normalize_app_env(self.app_env)
        if environment in {"development", "test"}:
            return
        if not self.auth_enabled or self.allow_legacy_user_header:
            raise ValueError("Deployed environments require AUTH_ENABLED=true and ALLOW_LEGACY_USER_HEADER=false")
        if self.debug or self.public_company_create:
            raise ValueError("Deployed environments require DEBUG=false and PUBLIC_COMPANY_CREATE=false")
        secret = self.jwt_secret.strip()
        weak_markers = ("change-me", "changeme", "development", "dev-change", "placeholder", "replace-me")
        if len(secret) < 32 or any(marker in secret.lower() for marker in weak_markers):
            raise ValueError("Deployed environments require a non-development JWT signing secret of at least 32 characters")
        if self.jwt_algorithm not in {"HS256", "HS384", "HS512"}:
            raise ValueError("Unsupported deployed JWT signing algorithm")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_mode(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


settings = Settings()
