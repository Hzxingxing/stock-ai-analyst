from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"

    mysql_host: str = Field(default="127.0.0.1", validation_alias="RESEARCH_MYSQL_HOST")
    mysql_port: int = Field(default=3306, validation_alias="RESEARCH_MYSQL_PORT")
    mysql_database: str = Field(default="stock_research", validation_alias="RESEARCH_MYSQL_DATABASE")
    mysql_user: str = Field(default="stock_research_app", validation_alias="RESEARCH_MYSQL_USER")
    mysql_password: SecretStr = Field(
        default=SecretStr(""), validation_alias="RESEARCH_MYSQL_PASSWORD"
    )

    redis_url: str = "redis://127.0.0.1:6379/0"

    auth_secret_key: SecretStr = SecretStr("development-only-secret-change-before-deploy")
    auth_cookie_secure: bool = False
    auth_token_hours: int = 24

    llm_base_url: str = Field(default="", validation_alias="LLM_BASE_URL")
    llm_model: str = "gemini-3-flash-preview"
    llm_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="LLM_API_KEY"
    )

    @model_validator(mode="after")
    def require_deployment_secrets(self) -> "Settings":
        if self.environment.lower() not in {"development", "dev", "test"}:
            if len(self.auth_secret_key.get_secret_value()) < 32:
                raise ValueError(
                    "AUTH_SECRET_KEY must contain at least 32 characters outside development"
                )
            if not self.mysql_password.get_secret_value():
                raise ValueError("RESEARCH_MYSQL_PASSWORD is required outside development")
        return self

    @property
    def async_database_url(self) -> str:
        return URL.create(
            "mysql+asyncmy",
            username=self.mysql_user,
            password=self.mysql_password.get_secret_value(),
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    @property
    def sync_database_url(self) -> str:
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password.get_secret_value(),
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    @property
    def jwt_secret(self) -> str:
        return self.auth_secret_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
