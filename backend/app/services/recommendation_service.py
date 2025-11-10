"""Recommendation service."""
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from app.core.database import SessionLocal
from app.core.logging import logger
from app.data.curation import DataCuration
from app.db.crud import create_recommendation, get_latest_recommendation
from app.db.crud import get_recommendation_history as db_history
from app.quant.signal_engine import generate_signal


class RecommendationService:
    """Service for managing trading recommendations."""

    def __init__(self, session=None):
        self._cache: Optional[dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self.session = session
        self.curation = DataCuration()

    async def generate_recommendation(self) -> Optional[dict[str, Any]]:
        """Generate a new recommendation using curated datasets."""
        from app.quant.narrative import build_narrative

        try:
            latest_daily = self.curation.get_latest_curated("1d")
        except FileNotFoundError:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        try:
            latest_hourly = self.curation.get_latest_curated("1h")
        except FileNotFoundError:
            logger.warning("No 1h data available, using 1d as fallback")
            latest_hourly = latest_daily

        if latest_daily is None or latest_daily.empty:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        if latest_hourly is None or latest_hourly.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            latest_hourly = latest_daily

        try:
            signal = generate_signal(latest_hourly, latest_daily)
            if "close" in latest_hourly.columns:
                signal["current_price"] = float(latest_hourly["close"].iloc[-1])
            if "open_time" in latest_hourly.columns:
                ts = latest_hourly["open_time"].iloc[-1]
                signal["market_timestamp"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            signal["spot_source"] = "1h"
        except ValueError as exc:
            logger.warning(f"Recommendation invalidated by risk controls: {exc}")
            return {"status": "invalid", "reason": str(exc)}
        except Exception:
            logger.exception("Unexpected error during signal generation")
            return None
        analysis = build_narrative(signal)
        signal["analysis"] = analysis

        rec = None

        # Save recommendation if session is provided
        if self.session:
            rec = create_recommendation(self.session, signal)
        else:
            # Fallback to creating a new session
            with SessionLocal() as db:
                try:
                    rec = create_recommendation(db, signal)
                finally:
                    db.close()

        logger.info(f"Generated and saved recommendation: {signal['signal']}")
        return self._from_orm(rec) if rec else signal

    async def get_today_recommendation(self) -> Optional[dict[str, Any]]:
        """Get today's recommendation from DB or generate on-demand."""
        today = datetime.utcnow().date()

        # Check cache first
        if self._cache and self._cache_timestamp and self._cache_timestamp.date() == today:
            logger.debug("Returning cached recommendation")
            return self._cache

        # Try DB first
        with SessionLocal() as db:
            try:
                rec = get_latest_recommendation(db)
                if rec:
                    rec_date = rec.created_at.date()
                    if rec_date == today:
                        logger.info(f"Found today's recommendation in DB (created at {rec.created_at})")
                        result = self._from_orm(rec)
                        self._cache = result
                        self._cache_timestamp = rec.created_at
                        return result
                    else:
                        logger.debug(f"Latest recommendation is from {rec_date}, not today")
            finally:
                db.close()

        # Generate on-demand if not present
        logger.info("Generating recommendation on-demand")
        dc = DataCuration()
        try:
            df_1d = dc.get_latest_curated("1d")
        except FileNotFoundError:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        try:
            df_1h = dc.get_latest_curated("1h")
        except FileNotFoundError:
            logger.warning("No 1h data available, using 1d as fallback")
            df_1h = df_1d

        if df_1d is None or df_1d.empty:
            logger.warning("Cannot generate recommendation: no 1d curated data available")
            return None

        if df_1h is None or df_1h.empty:
            logger.warning("1h dataset empty, using 1d as fallback")
            df_1h = df_1d

        try:
            recommendation = generate_signal(df_1h, df_1d)
            # Add analysis if not present (will be generated in create_recommendation)
            if "analysis" not in recommendation or not recommendation["analysis"]:
                from app.quant.narrative import build_narrative
                recommendation["analysis"] = build_narrative(recommendation)
            if "close" in df_1h.columns:
                recommendation["current_price"] = float(df_1h["close"].iloc[-1])
            if "open_time" in df_1h.columns:
                ts = df_1h["open_time"].iloc[-1]
                recommendation["market_timestamp"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            recommendation["spot_source"] = "1h"

            result = None
            with SessionLocal() as db:
                try:
                    rec = create_recommendation(db, recommendation)
                    logger.info(f"Generated and saved recommendation: {recommendation['signal']}")
                    result = self._from_orm(rec)
                finally:
                    db.close()

            if result:
                self._cache = result
                self._cache_timestamp = datetime.utcnow()
            return result
        except ValueError as exc:
            logger.warning(f"Recommendation invalidated by risk controls: {exc}")
            return {"status": "invalid", "reason": str(exc)}
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}", exc_info=True)
            return None

    async def get_recommendation_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recommendation history from DB."""
        with SessionLocal() as db:
            try:
                recs = db_history(db, limit=limit)
                return [self._from_orm(r) for r in recs]
            finally:
                db.close()

    async def get_signal_performance(
        self,
        *,
        lookahead_days: int = 5,
        limit: int = 90,
    ) -> dict[str, Any]:
        """
        Cross recommendations with subsequent prices to measure realised performance.
        """
        lookahead_days = max(1, min(lookahead_days, 30))
        limit = max(1, min(limit, 365))

        with SessionLocal() as db:
            try:
                recs = db_history(db, limit=limit)
            finally:
                db.close()

        if not recs:
            return {
                "status": "no_data",
                "timeline": [],
                "equity_curve": [],
                "drawdown_curve": [],
                "win_rate": 0.0,
                "average_tracking_error": 0.0,
                "trades_evaluated": 0,
            }

        df_prices = self.curation.get_historical_curated("1d", days=365 * 5)
        if df_prices is None or df_prices.empty:
            return {
                "status": "no_prices",
                "timeline": [],
                "equity_curve": [],
                "drawdown_curve": [],
                "win_rate": 0.0,
                "average_tracking_error": 0.0,
                "trades_evaluated": 0,
            }

        df_prices = df_prices.copy()
        df_prices["date"] = pd.to_datetime(df_prices["open_time"]).dt.date
        df_prices.set_index("date", inplace=True)

        capital = 1.0
        equity_curve = [round(capital, 4)]
        drawdown_curve = [0.0]
        peak = capital

        timeline: list[dict[str, Any]] = []
        tracking_errors: list[float] = []
        wins = 0
        trades_count = 0

        sorted_recs = sorted(recs, key=lambda r: r.created_at)

        for rec in sorted_recs:
            rec_date = datetime.strptime(rec.date, "%Y-%m-%d").date()
            if rec_date not in df_prices.index:
                continue

            future_slice = df_prices.loc[rec_date:]
            if future_slice.empty or len(future_slice) < 2:
                continue

            window = future_slice.iloc[1 : lookahead_days + 1]
            if window.empty:
                continue

            exit_price = float(window.iloc[-1]["close"])
            exit_reason = "EXIT"
            hit_date = window.index[-1]
            entry_price = float(rec.entry_optimal)

            if rec.signal == "BUY":
                for idx, row in window.iterrows():
                    low = float(row["low"])
                    high = float(row["high"])
                    if low <= rec.stop_loss:
                        exit_price = float(rec.stop_loss)
                        exit_reason = "SL"
                        hit_date = idx
                        break
                    if high >= rec.take_profit:
                        exit_price = float(rec.take_profit)
                        exit_reason = "TP"
                        hit_date = idx
                        break
            elif rec.signal == "SELL":
                for idx, row in window.iterrows():
                    high = float(row["high"])
                    low = float(row["low"])
                    if high >= rec.stop_loss:
                        exit_price = float(rec.stop_loss)
                        exit_reason = "SL"
                        hit_date = idx
                        break
                    if low <= rec.take_profit:
                        exit_price = float(rec.take_profit)
                        exit_reason = "TP"
                        hit_date = idx
                        break

            if rec.signal == "BUY":
                return_pct = ((exit_price - entry_price) / entry_price) * 100
            elif rec.signal == "SELL":
                return_pct = ((entry_price - exit_price) / entry_price) * 100
            else:
                return_pct = 0.0

            if rec.signal in ("BUY", "SELL"):
                trades_count += 1
                if return_pct > 0:
                    wins += 1

            capital *= 1 + (return_pct / 100)
            peak = max(peak, capital)
            drawdown_pct = ((capital / peak) - 1) * 100 if peak > 0 else 0.0

            equity_curve.append(round(capital, 4))
            drawdown_curve.append(round(drawdown_pct, 2))

            target_level = None
            if exit_reason == "TP":
                target_level = float(rec.take_profit)
            elif exit_reason == "SL":
                target_level = float(rec.stop_loss)
            tracking_error = (
                abs(exit_price - target_level) / target_level * 100
                if target_level and target_level != 0
                else 0.0
            )
            if target_level:
                tracking_errors.append(tracking_error)

            timeline.append(
                {
                    "date": rec.date,
                    "signal": rec.signal,
                    "entry_price": round(entry_price, 2),
                    "stop_loss": round(float(rec.stop_loss), 2),
                    "take_profit": round(float(rec.take_profit), 2),
                    "exit_price": round(exit_price, 2),
                    "level_hit": exit_reason,
                    "holding_days": len(window),
                    "return_pct": round(return_pct, 2),
                    "tracking_error": round(tracking_error, 2),
                    "hit_date": hit_date.isoformat() if hasattr(hit_date, "isoformat") else str(hit_date),
                    "signal_breakdown": rec.signal_breakdown or {},
                }
            )

        average_tracking_error = float(sum(tracking_errors) / len(tracking_errors)) if tracking_errors else 0.0
        win_rate = (wins / trades_count * 100) if trades_count else 0.0

        return {
            "status": "ok",
            "timeline": timeline,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "win_rate": round(win_rate, 2),
            "average_tracking_error": round(average_tracking_error, 2),
            "trades_evaluated": trades_count,
        }

    def _from_orm(self, r) -> dict[str, Any]:
        """Convert ORM model to API response dict."""
        return {
            "signal": r.signal,
            "entry_range": {"min": r.entry_min, "max": r.entry_max, "optimal": r.entry_optimal},
            "stop_loss_take_profit": {
                "stop_loss": r.stop_loss,
                "take_profit": r.take_profit,
                "stop_loss_pct": r.stop_loss_pct,
                "take_profit_pct": r.take_profit_pct,
            },
            "confidence": r.confidence,
            "current_price": r.current_price,
            "market_timestamp": r.market_timestamp,
            "spot_source": r.spot_source,
            "analysis": r.analysis or "",
            "indicators": r.indicators or {},
            "risk_metrics": r.risk_metrics or {},
            "factors": r.factors or {},
            "signal_breakdown": r.signal_breakdown or {},
            "timestamp": r.created_at.isoformat(),
            "disclaimer": "This is not financial advice. Trading cryptocurrencies involves significant risk.",
        }

