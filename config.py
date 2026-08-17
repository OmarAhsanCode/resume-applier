import os
import secrets
from typing import Type

class Config:
    """Base application configuration."""
    APP_ENV = os.getenv("APP_ENV", "development").lower()
    DEBUG = False
    TESTING = False
    
    # Secret Key
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Paths & Folders
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/jobs.db")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    GENERATED_RESUMES_DIR = os.getenv("GENERATED_RESUMES_DIR", "generated/resumes")
    CONFIG_DIR = os.getenv("CONFIG_DIR", "config")
    
    # Server & Request limits
    PORT = int(os.getenv("PORT", 5000))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))  # 16 MB limit
    
    # Security & Cookie Flags
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
    
    # PDF & LaTeX
    PDFLATEX_PATH = os.getenv("PDFLATEX_PATH", "pdflatex")
    PDFLATEX_TIMEOUT = int(os.getenv("PDFLATEX_TIMEOUT", 30))
    
    # AI & Cost Controls
    RESUME_MAX_ITERATIONS = int(os.getenv("RESUME_MAX_ITERATIONS", 5))
    BACKGROUND_RESUME_MAX_ITERATIONS = int(os.getenv("BACKGROUND_RESUME_MAX_ITERATIONS", 2))
    AI_REQUEST_TIMEOUT = int(os.getenv("AI_REQUEST_TIMEOUT", 30))
    
    # Rate Limiting (in-memory single worker limit)
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", 30))
    RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", 60))

    # Google Integrations
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")

    @classmethod
    def validate(cls):
        """Validate configuration settings."""
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ":memory:"
    RATE_LIMIT_ENABLED = False
    SECRET_KEY = "testing-secret-key-not-for-prod"


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() in ("true", "1", "yes")

    @classmethod
    def validate(cls):
        """Strict validation for production mode."""
        if not cls.SECRET_KEY or cls.SECRET_KEY in (
            "dev-secret-key-change-in-production",
            "change-me",
            "default",
            "secret"
        ):
            raise ValueError(
                "CRITICAL: Insecure or default SECRET_KEY detected in PRODUCTION mode. "
                "Set a strong SECRET_KEY environment variable before starting."
            )


def get_config() -> Type[Config]:
    """Returns the active configuration class based on APP_ENV or FLASK_ENV."""
    env = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").lower().strip()
    if env == "production":
        config = ProductionConfig
    elif env == "testing":
        config = TestingConfig
    else:
        config = DevelopmentConfig

    config.validate()
    return config
