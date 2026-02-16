"""
Application configuration using Pydantic Settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = "postgresql://spc_user:spc_password@localhost:5432/social_performance_coach"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/api/auth/callback/google"
    YOUTUBE_API_KEY: str = ""  # For public data access without OAuth
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    AUDIT_UPLOAD_DIR: str = "/tmp/spc_uploads"
    AUDIT_UPLOAD_RETENTION_HOURS: int = 72
    DELETE_UPLOAD_AFTER_AUDIT: bool = False
    BLUEPRINT_CACHE_TTL_MINUTES: int = 60
    TRANSCRIPT_CACHE_TTL_SECONDS: int = 604800
    
    # Feature Flags
    ENABLE_TIKTOK_CONNECTORS: bool = False
    ENABLE_INSTAGRAM_CONNECTORS: bool = False
    ENABLE_WHISPER_TRANSCRIPTION: bool = False
    
    # Security
    JWT_SECRET: str = "change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    ENCRYPTION_KEY: str = "change_me_32_byte_key_for_prod"
    AUTO_CREATE_DB_SCHEMA: bool = True
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()


def require_youtube_api_key() -> str:
    """Return configured YouTube API key or raise a configuration error."""
    api_key = (settings.YOUTUBE_API_KEY or "").strip()
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is not configured")
    return api_key


def validate_security_settings() -> None:
    """Fail fast when insecure default secrets are still configured."""
    insecure_values = {
        "",
        "change_me_in_production",
        "change_me_32_byte_key_for_prod",
        "your_jwt_secret_change_in_production",
        "your_32_byte_encryption_key_here",
    }
    jwt_secret = (settings.JWT_SECRET or "").strip()
    encryption_key = (settings.ENCRYPTION_KEY or "").strip()

    if jwt_secret in insecure_values or len(jwt_secret) < 24:
        raise ValueError("JWT_SECRET is insecure. Configure a strong non-default secret (>=24 chars).")
    if encryption_key in insecure_values or len(encryption_key) < 32:
        raise ValueError("ENCRYPTION_KEY is insecure. Configure a strong non-default key (>=32 chars).")
