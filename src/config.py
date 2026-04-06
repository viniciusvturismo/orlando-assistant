from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Database
    database_url: str = "sqlite:///./orlando.db"

    # Twilio / WhatsApp
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""

    # App
    env: str = "development"
    log_level: str = "INFO"
    park_open_hour: int = 9
    park_close_hour: int = 22

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
