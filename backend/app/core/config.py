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

    # Risk alerts
    RISK_RUIN_ALERT_THRESHOLD: float = 0.05
    RISK_OF_RUIN_MAX: float = 0.05  # Maximum acceptable risk of ruin (5%)
    PRODUCTION_DD_ALERT_BUFFER: float = 0.9

    # Data paths
    DATA_DIR: str = "./data"
    RAW_DATA_DIR: str = "./data/raw"
    CURATED_DATA_DIR: str = "./data/curated"

    # User management (for single-user system)
    DEFAULT_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    # Cooldown limits
    COOLDOWN_LOSING_STREAK_THRESHOLD: int = 3
    COOLDOWN_LOSING_STREAK_HOURS: int = 24
    COOLDOWN_MAX_TRADES_24H: int = 8
    COOLDOWN_OVERTRADING_HOURS: int = 12

    # Leverage limits
    LEVERAGE_WARNING_THRESHOLD: float = 2.0
    LEVERAGE_HARD_STOP_THRESHOLD: float = 3.0
    LEVERAGE_HARD_STOP_PERSISTENCE_MINUTES: int = 60  # Must persist for 60 minutes to trigger hard stop
    
    # Exposure limits
    EXPOSURE_LIMIT_MULTIPLIER: float = 2.0  # Maximum beta-adjusted exposure multiplier (2.0 = 2x equity)
    EXPOSURE_ALERT_THRESHOLD_PCT: float = 0.8  # Alert when exposure exceeds 80% of limit
    EXPOSURE_ALERT_PERSISTENCE_MINUTES: int = 15  # Alert must persist for 15 minutes

    # Livelihood defaults
    DEFAULT_EXPENSES_TARGET_USD: float = 1200.0
    MARKET_EXPENSES_OVERRIDES_JSON: str = "{}"  # Optional JSON mapping market->default expenses

    # Compliance and retention
    WORM_RETENTION_DAYS: int = 365
    HASH_TTL_DAYS: int = 365
    EXPORT_ROLES_ALLOWED: str = "admin,analyst,read-only"

    # Data freshness validation
    DATA_FRESHNESS_THRESHOLD_MINUTES: int = 90  # Maximum age (minutes) for latest candles before rejecting recommendation
    
    # Data gap validation
    DATA_GAP_TOLERANCE_CANDLES: int = 2  # Maximum number of missing candles allowed before blocking recommendation
    DATA_GAP_CHECK_LOOKBACK_DAYS: int = 30  # Number of days to check for gaps before generating recommendation
    
    # Liquidity guardrails
    LIQUIDITY_MIN_NOTIONAL_USD: float = 1000.0  # Minimum notional value required at SL/TP levels
    LIQUIDITY_TOLERANCE_PCT: float = 0.5  # Price tolerance percentage for depth check (0.5%)
    RR_FLOOR: float = 1.2  # Minimum risk/reward ratio required (configurable per strategy)
    
    # Backtest validation (mandatory before signal publication)
    BACKTEST_ENABLED: bool = True  # Enable mandatory backtesting
    BACKTEST_LOOKBACK_DAYS: int = 90  # Days of historical data for backtest
    BACKTEST_MIN_SHARPE: float = 0.0  # Minimum Sharpe ratio required (0.0 = non-negative)
    BACKTEST_MAX_DRAWDOWN_PCT: float = 50.0  # Maximum drawdown percentage allowed
    BACKTEST_COMMISSION_RATE: float = 0.001  # 0.1% commission rate
    BACKTEST_SLIPPAGE_BPS: float = 5.0  # 5 basis points slippage
    PERFORMANCE_STRATEGY_SOURCE: str | None = "daily_signal_engine"
    PERFORMANCE_STRATEGY_VENUE: str = "binance"
    PERFORMANCE_STRATEGY_SYMBOL: str = "BTCUSDT"
    PERFORMANCE_STRATEGY_VALIDATE_DATA: bool = True
    
    # Tracking error monitoring (SL/TP achievability)
    TRACKING_ERROR_THRESHOLD_BPS: float = 50.0  # Alert if tracking error exceeds 50 bps (0.5%)
    TRACKING_ERROR_CHECK_LOOKAHEAD_DAYS: int = 7  # Days to look ahead for price evaluation
    
    # Auto-shutdown guardrails
    AUTO_SHUTDOWN_ENABLED: bool = True  # Enable auto-shutdown policy
    AUTO_SHUTDOWN_MIN_ROLLING_SHARPE: float = 0.2  # Minimum rolling Sharpe ratio (annualized)
    AUTO_SHUTDOWN_LOOKBACK_TRADES: int = 50  # Number of trades to look back for rolling metrics
    AUTO_SHUTDOWN_MIN_TRADES_FOR_SHARPE: int = 2  # Minimum trades required to compute Sharpe
    AUTO_SHUTDOWN_ALLOW_MISSING_DATA_IN_DEV: bool = True  # Allow bypass in dev/test when Sharpe data is missing (prod always requires data)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

