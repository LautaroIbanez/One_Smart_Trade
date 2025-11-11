"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database
    DATABASE_URL: str = "sqlite:///./data/trading.db"

    # Binance API
    BINANCE_API_BASE_URL: str = "https://api.binance.com/api/v3"
    BINANCE_RATE_LIMIT_REQUESTS: int = 1200
    BINANCE_RATE_LIMIT_WINDOW: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"

    # Scheduler
    SCHEDULER_TIMEZONE: str = "UTC"
    RECOMMENDATION_UPDATE_TIME: str = "12:00"

    # Preflight maintenance
    PRESTART_MAINTENANCE: bool = True
    PRESTART_LOOKBACK_DAYS: int = 30
    PRESTART_BACKFILL_CHUNK: int = 900
    PRESTART_BACKFILL_PAUSE_SECONDS: float = 0.2

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Data paths
    DATA_DIR: str = "./data"
    RAW_DATA_DIR: str = "./data/raw"
    CURATED_DATA_DIR: str = "./data/curated"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

