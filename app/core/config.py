from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "MatchKash"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = "CHANGE_THIS_TO_A_SECURE_SECRET_KEY"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 Days
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/matchkash_db"
    
    # Third Party (Twilio / MonCash)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    
    class Config:
        env_file = ".env"

settings = Settings()