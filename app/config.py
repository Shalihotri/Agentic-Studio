from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agentic Garden"
    app_env: str = "development"
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    google_model: str = Field(default="gemini-2.5-flash", alias="GOOGLE_MODEL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")

    snowflake_account: str = Field(default="", alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str = Field(default="", alias="SNOWFLAKE_USER")
    snowflake_password: str = Field(default="", alias="SNOWFLAKE_PASSWORD")
    snowflake_warehouse: str = Field(default="", alias="SNOWFLAKE_WAREHOUSE")
    snowflake_database: str = Field(default="", alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str = Field(default="", alias="SNOWFLAKE_SCHEMA")
    snowflake_role: str | None = Field(default=None, alias="SNOWFLAKE_ROLE")
    snowflake_authenticator: str = Field(
        default="snowflake",
        alias="SNOWFLAKE_AUTHENTICATOR",
    )

    gmail_credentials_file: Path = Field(
        default=Path("credentials/gmail-oauth-client.json"),
        alias="GMAIL_CREDENTIALS_FILE",
    )
    gmail_token_file: Path = Field(
        default=Path("credentials/gmail-token.json"),
        alias="GMAIL_TOKEN_FILE",
    )
    gmail_client_id: str = Field(default="", alias="GMAIL_CLIENT_ID")
    gmail_client_secret: str = Field(default="", alias="GMAIL_CLIENT_SECRET")
    gmail_sender_email: str = Field(default="", alias="GMAIL_SENDER_EMAIL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
