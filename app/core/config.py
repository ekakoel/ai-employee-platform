from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Employee Platform"
    app_env: str = "development"
    debug: bool = True

    database_url: str = "sqlite:///./ai_employee.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Auth (Job 15)
    auth_enabled: bool = False
    # When auth_enabled=True, still allow X-User-ID only if this is True (dev only)
    allow_legacy_user_header: bool = True
    jwt_secret: str = "dev-change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
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
    # Comma-separated emails granted platform admin on login/bootstrap
    platform_admin_emails: str = ""
    allow_impersonation: bool = False

    log_level: str = "INFO"
    log_json: bool = False

    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


settings = Settings()
