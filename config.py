from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
        env_file_encoding='utf-8'
    )
    
    # App
    PROJECT_NAME: str = "Breakdown Assistance Technician/Admin Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Database - Load from environment
    DATABASE_URL: str
    
    # Redis - Load from environment
    REDIS_URL: str
    REDIS_LOCATION_EXPIRE: int = 300
    
    # JWT - Load from environment
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Stripe - Load from environment
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    
    # Platform fee percentage (e.g., 20% of driver earnings)
    PLATFORM_FEE_PERCENT: float = 20.0
    
    # OpenAI API
    OPENAI_API_KEY: str = ""

    # UTHO S3 Storage - Load from environment
    UTHO_ACCESS_KEY: str = ""
    UTHO_SECRET_KEY: str = ""
    UTHO_BUCKET: str = ""
    UTHO_REGION: str = "ap-south-1"
    UTHO_ENDPOINT: str = ""
    UTHO_BUCKET_URL: str = ""
    
    # Mapbox - Load from environment
    MAPBOX_TOKEN: str = ""
    # WebSocket access keys (set in .env for production)
    DRIVER_WS_KEY: str = "driver-secret"
    CUSTOMER_WS_KEY: str = "customer-secret"
 
    TECHNICIAN_ACCEPT_TIMEOUT_SECONDS: int = 60
    MAX_TECHNICIANS_TO_NOTIFY: int = 5
    
    # UK Map bounds (for validation)
    UK_LAT_MIN: float = 49.9
    UK_LAT_MAX: float = 60.9
    UK_LNG_MIN: float = -8.2
    UK_LNG_MAX: float = 1.8
    
    # Twilio Verify - Load from environment variables (REQUIRED)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_VERIFY_SERVICE_SID: str = ""
    TWILIO_PHONE_NUMBER: str = ""  # For sending SMS

settings = Settings()