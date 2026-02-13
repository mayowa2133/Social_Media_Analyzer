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
