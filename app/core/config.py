from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Employee Platform"
    database_url: str = "sqlite:///./ai_employee.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
