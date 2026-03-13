from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "MatchKash"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = "CHANGE_THIS_TO_A_SECURE_SECRET_KEY"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 Days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7 Days
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:your_password@localhost/matchkash_db"
    
    # Third Party (Twilio)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    # Third Party (MonCash / NatCash)
    MONCASH_API_KEY: Optional[str] = None  # <--- THIS WAS MISSING
    
    # Pydantic V2 Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore" # This prevents the app from crashing if .env has extra variables
    )

settings = Settings()