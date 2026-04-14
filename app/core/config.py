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

    MONCASH_CLIENT_ID: Optional[str] = None
    MONCASH_CLIENT_SECRET: Optional[str] = None
    MONCASH_API_BASE_URL: str = "https://sandbox.moncashbutton.digicelgroup.com"

    # UPDATED NATCASH SETTINGS
    NATCASH_PARTNER_CODE: str = "XENTRA001"
    NATCASH_USERNAME: str = "Xentra_admin"
    NATCASH_PASSWORD: str = "Xentrasport$2026$"
    
    # You will need to get these two from the NatCash Sandbox Portal:
    NATCASH_PRIVATE_KEY: str = "YOUR_NATCASH_PRIVATE_KEY" 
    NATCASH_FUNCTION_CODE: str = "YOUR_NATCASH_FUNCTION_CODE" 
    
    NATCASH_API_BASE_URL: str = "https://testmerchantpay.natcom.com.ht/api"
    # Update this to your current ngrok/devtunnels URL for testing webhooks
    NATCASH_CALLBACK_URL: str = "https://wbsl64n9-8005.inc1.devtunnels.ms/api/v1/webhooks/natcash"
    
    # Pydantic V2 Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore" # This prevents the app from crashing if .env has extra variables
    )

settings = Settings()