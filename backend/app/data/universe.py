"""Market universe configuration for multi-asset support."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from typing_extensions import assert_never


@dataclass(frozen=True, slots=True)
class AssetSpec:
    """Specification for a tradeable asset across venues and asset classes."""

    symbol: str
    venue: str
    quote: str
    asset_class: Literal["crypto", "index", "forex", "commodity"]

    def __post_init__(self) -> None:
        """Validate asset specification."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if not self.venue:
            raise ValueError("venue cannot be empty")
        if not self.quote:
            raise ValueError("quote cannot be empty")
        if self.asset_class not in ("crypto", "index", "forex", "commodity"):
            raise ValueError(f"Unsupported asset_class: {self.asset_class}")

    @property
    def storage_key(self) -> str:
        """Generate storage partition key: {venue}/{symbol}."""
        return f"{self.venue}/{self.symbol}"

    @property
    def display_name(self) -> str:
        """Human-readable asset identifier."""
        return f"{self.symbol}@{self.venue}"


@dataclass(frozen=True, slots=True)
class MarketUniverseConfig:
    """Configuration for market universe with multiple assets and venues."""

    assets: tuple[AssetSpec, ...]
    default_interval: str = "1d"
    default_lookback_days: int = 365 * 5

    def __post_init__(self) -> None:
        """Validate universe configuration."""
        if not self.assets:
            raise ValueError("Universe must contain at least one asset")
        symbols = {asset.symbol for asset in self.assets}
        if len(symbols) != len(self.assets):
            raise ValueError("Duplicate symbols found in universe")

    def get_asset(self, symbol: str, venue: str | None = None) -> AssetSpec | None:
        """Retrieve asset specification by symbol and optional venue."""
        for asset in self.assets:
            if asset.symbol == symbol:
                if venue is None or asset.venue == venue:
                    return asset
        return None

    def get_assets_by_venue(self, venue: str) -> tuple[AssetSpec, ...]:
        """Retrieve all assets for a specific venue."""
        return tuple(asset for asset in self.assets if asset.venue == venue)

    def get_assets_by_class(self, asset_class: Literal["crypto", "index", "forex", "commodity"]) -> tuple[AssetSpec, ...]:
        """Retrieve all assets for a specific asset class."""
        return tuple(asset for asset in self.assets if asset.asset_class == asset_class)


DEFAULT_UNIVERSE = MarketUniverseConfig(
    assets=(
        AssetSpec(symbol="BTCUSDT", venue="binance", quote="USDT", asset_class="crypto"),
        AssetSpec(symbol="ETHUSDT", venue="binance", quote="USDT", asset_class="crypto"),
    )
)

EXTENDED_UNIVERSE = MarketUniverseConfig(
    assets=(
        AssetSpec(symbol="BTCUSDT", venue="binance", quote="USDT", asset_class="crypto"),
        AssetSpec(symbol="ETHUSDT", venue="binance", quote="USDT", asset_class="crypto"),
        AssetSpec(symbol="NQ=F", venue="yfinance", quote="USD", asset_class="index"),
    )
)





