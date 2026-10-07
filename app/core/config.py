from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Employee Platform"
    app_env: str = "development"  # development | staging | production
    debug: bool = True

    # Database (sqlite for local/tests, postgresql+psycopg for production)
    database_url: str = "sqlite:///./ai_employee.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Auth
    auth_enabled: bool = False  # when True, Bearer JWT preferred; X-User-ID still accepted in non-prod
    jwt_secret: str = "dev-change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # Object storage
    storage_backend: str = "local"  # local | s3 (s3 stub)
    storage_local_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""

    # Workers
    worker_poll_seconds: int = 30

    # Observability
    log_level: str = "INFO"
    log_json: bool = False

    # LLM
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
