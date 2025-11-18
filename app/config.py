from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development")
    timezone: str = Field(default="UTC", alias="TZ")
    personality_prompt: str = Field(
        default="You're Nudgeme, a playful but reliable AI assistant who sends fun reminders with emojis."
    )

    # Google
    google_client_id: str = Field(validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(validation_alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="http://localhost:8000/oauth/google/callback", validation_alias="GOOGLE_REDIRECT_URI")
    google_calendar_id: str = Field(default="primary", validation_alias="GOOGLE_CALENDAR_ID")
    google_token_path: Path = Field(default=Path("data/google_token.json"), validation_alias="GOOGLE_TOKEN_PATH")

    # Twilio / SMS
    twilio_account_sid: str = Field(validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(validation_alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(validation_alias="TWILIO_FROM_NUMBER")
    user_phone_number: str = Field(validation_alias="USER_PHONE_NUMBER")

    # Optional LLM
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")

    # Reminder persistence
    reminder_state_path: Path = Field(default=Path("data/reminder_state.json"), validation_alias="REMINDER_STATE_PATH")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Provide a cached Settings instance."""

    return Settings()
