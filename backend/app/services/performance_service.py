"""Performance service for backtesting results."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

from app import __version__
from app.backtesting.engine import BacktestEngine
from app.backtesting.daily_strategy_adapter import DailyStrategyAdapter
from app.backtesting.metrics import calculate_metrics
from app.backtesting.report import build_campaign_report
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger, sanitize_log_extra
from app.db.crud import get_latest_backtest_result, save_backtest_result
from app.data.signal_data_provider import SignalDataProvider
from app.core.exceptions import DataFreshnessError
from app.quant.signal_engine import DailySignalEngine


class StrategyConfigurationError(Exception):
    """Raised when strategy configuration is missing or invalid."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class PerformanceService:
    """Service for backtesting performance metrics."""
    ERROR_CACHE_TTL_SECONDS = 300

    def __init__(self):
        self.engine = BacktestEngine()
        self.reports_dir = Path(settings.DATA_DIR) / "backtest_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(__file__).resolve().parents[3]
        self.docs_assets_dir = self.project_root / "docs" / "assets"
        self.docs_assets_dir.mkdir(parents=True, exist_ok=True)
        self.performance_config = self._load_performance_config()
        self.signal_engine = DailySignalEngine()
        self.signal_data_provider = SignalDataProvider(
            venue=settings.PERFORMANCE_STRATEGY_VENUE,
            symbol=settings.PERFORMANCE_STRATEGY_SYMBOL,
        )
        self._strategy_source = settings.PERFORMANCE_STRATEGY_SOURCE
        self._error_cache: dict[str, Any] | None = None

    def _load_performance_config(self) -> dict[str, Any]:
        """Load performance/tracking error configuration from YAML file."""
        defaults = {
            "tracking_error": {
                "max_rmse_pct": 0.03,
                "divergence_threshold_pct": 0.02,
            }
        }
        config_paths = [
            Path("config/performance.yaml"),
            Path("backend/config/performance.yaml"),
            self.project_root / "backend" / "config" / "performance.yaml",
        ]
        for path in config_paths:
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}
                        return raw
                except Exception as exc:
                    logger.warning("Failed to load performance config", extra=sanitize_log_extra({"path": str(path), "error": str(exc)}))
        return defaults

    def _resolve_strategy(self, *, allow_stale_data: bool = False) -> DailyStrategyAdapter:
        """Build the strategy object defined in settings."""
        if not self._strategy_source:
            raise StrategyConfigurationError(
                "Strategy configuration missing",
                details={"setting": "PERFORMANCE_STRATEGY_SOURCE"},
            )

        if self._strategy_source == "daily_signal_engine":
            validate_freshness = settings.PERFORMANCE_STRATEGY_VALIDATE_DATA and not allow_stale_data
            validate_gaps = settings.PERFORMANCE_STRATEGY_VALIDATE_DATA and not allow_stale_data
            if allow_stale_data and settings.PERFORMANCE_STRATEGY_VALIDATE_DATA:
                logger.info(
                    "allow_stale_inputs=True, disabling gap validation to permit cached datasets",
                    extra={"allow_stale_inputs": allow_stale_data},
                )

            try:
                inputs = self.signal_data_provider.get_validated_inputs(
                    validate_freshness=validate_freshness,
                    validate_gaps=validate_gaps,
                )
                self._clear_stale_error_cache_if_needed()
            except DataFreshnessError as exc:
                if allow_stale_data:
                    logger.info(
                        "DataFreshnessError caught with allow_stale_data=True, retrying with validation disabled",
                        extra={
                            "interval": exc.interval,
                            "latest_timestamp": exc.latest_timestamp,
                            "latest_candle_age_minutes": getattr(exc, "context_data", {}).get("age_minutes") if getattr(exc, "context_data", None) else None,
                            "threshold_minutes": exc.threshold_minutes,
                        },
                    )
                    try:
                        inputs = self.signal_data_provider.get_validated_inputs(
                            validate_freshness=False,
                            validate_gaps=False,
                            force_refresh=False,
                        )
                        self._clear_stale_error_cache_if_needed()
                    except Exception as retry_exc:
                        logger.warning(
                            "Failed to load strategy inputs even with validation disabled",
                            extra={"error": str(retry_exc), "original_error": str(exc)},
                        )
                        raise StrategyConfigurationError(
                            "Unable to materialize strategy datasets with stale data",
                            details={"setting": "PERFORMANCE_STRATEGY_SOURCE", "cause": str(retry_exc), "original_freshness_error": str(exc)},
                        ) from retry_exc
                else:
                    logger.warning(
                        "Signal data freshness validation failed",
                        extra={
                            "interval": exc.interval,
                            "latest_timestamp": exc.latest_timestamp,
                            "latest_candle_age_minutes": getattr(exc, "context_data", {}).get("age_minutes") if getattr(exc, "context_data", None) else None,
                            "threshold_minutes": exc.threshold_minutes,
                            "context": exc.context_data,
                            "allow_stale_data": allow_stale_data,
                        },
                    )
                    raise
            except Exception as exc:
                logger.error(
                    "Failed to load strategy inputs",
                    extra={"error": str(exc)},
                )
                raise StrategyConfigurationError(
                    "Unable to materialize strategy datasets",
                    details={"setting": "PERFORMANCE_STRATEGY_SOURCE", "cause": str(exc)},
                ) from exc

            return DailyStrategyAdapter(
                signal_engine=self.signal_engine,
                df_1h=inputs.df_1h,
                df_1d=inputs.df_1d,
                symbol=inputs.symbol,
            )

        raise StrategyConfigurationError(
            f"Unsupported strategy source '{self._strategy_source}'",
            details={"setting": "PERFORMANCE_STRATEGY_SOURCE"},
        )

    async def get_summary(self, use_cache: bool = True, *, allow_stale_inputs: bool = False, trigger_backfill: bool = True) -> dict[str, Any]:
        """Get performance summary from latest backtest.
        
        Args:
            use_cache: Whether to use cached results if available
            allow_stale_inputs: If True, always return cached data immediately (even if stale)
                               and enqueue background backfill instead of blocking
            trigger_backfill: If False, skip background backfill (used internally)
        """
        # CACHE-FIRST FAST PATH: When allow_stale_inputs=True, always return cached data immediately
        # This prevents UI requests from blocking on full backtests
        if allow_stale_inputs:
            cached_summary = self._get_db_cached_success_summary(max_age_seconds=None)
            if cached_summary:
                # Enrich with cache metadata
                cached_summary = self._enrich_with_cache_metadata(cached_summary, served_from_cache=True)
                logger.info(
                    "Serving cached summary immediately (allow_stale_inputs=True)",
                    extra={
                        "cache_age_seconds": cached_summary.get("cache_age_seconds"),
                        "cached_at": cached_summary.get("cached_at"),
                        "served_from_cache": True,
                    },
                )
                # Return immediately - background backfill will run asynchronously if needed
                # (triggered via BackgroundTasks in the API endpoint)
                return cached_summary
            
            # If no cache exists and allow_stale_inputs=True, check for cached errors with fallback
            # but don't block on backtest execution
            cached_error = self._get_cached_error(allow_stale_inputs=allow_stale_inputs)
            if cached_error:
                # If error has fallback summary, use it; otherwise return error
                fallback_summary = cached_error.get("fallback_summary")
                if fallback_summary and fallback_summary.get("metrics"):
                    # Return fallback summary with metadata indicating degraded mode
                    fallback_summary = self._enrich_with_cache_metadata(fallback_summary, served_from_cache=True)
                    fallback_summary["metadata"]["degraded_mode"] = True
                    fallback_summary["metadata"]["error_occurred"] = True
                    fallback_summary["metadata"]["error_type"] = cached_error.get("error_type")
                    return fallback_summary
                return cached_error
            
            # No cache at all - return empty placeholder that indicates backfill is needed
            # Background task will populate cache asynchronously
            return {
                "status": "success",
                "metrics": {},
                "period": None,
                "report_path": None,
                "metadata": {
                    "served_from_cache": False,
                    "cache_miss": True,
                    "backfill_queued": trigger_backfill,
                    "generated_at": datetime.utcnow().isoformat(),
                },
            }

        # STANDARD PATH: Check for cached result (for non-transparency callers)
        if use_cache:
            cached_summary = self._get_db_cached_success_summary(max_age_seconds=86400)
            if cached_summary:
                cached_summary = self._enrich_with_cache_metadata(cached_summary, served_from_cache=True)
                return cached_summary

        cached_error = self._get_cached_error(allow_stale_inputs=allow_stale_inputs)
        if cached_error:
            return cached_error

        # BLOCKING PATH: Run backtest synchronously (only for non-UI requests)
        # This should only be reached when allow_stale_inputs=False
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=5 * 365)

        try:
            strategy = self._resolve_strategy(allow_stale_data=allow_stale_inputs)
        except DataFreshnessError as exc:
            if allow_stale_inputs:
                logger.info(
                    "DataFreshnessError in get_summary with allow_stale_inputs=True, attempting to return cached summary",
                    extra={
                        "interval": exc.interval,
                        "latest_timestamp": exc.latest_timestamp,
                        "threshold_minutes": exc.threshold_minutes,
                    },
                )
                cached_summary = self._get_db_cached_success_summary(max_age_seconds=None)
                if cached_summary:
                    cached_summary["metadata"] = cached_summary.get("metadata", {})
                    cached_summary["metadata"]["served_with_stale_data"] = True
                    cached_summary["metadata"]["freshness_error"] = {
                        "interval": exc.interval,
                        "latest_timestamp": exc.latest_timestamp.isoformat() if isinstance(exc.latest_timestamp, datetime) else str(exc.latest_timestamp),
                        "threshold_minutes": exc.threshold_minutes,
                    }
                    return cached_summary
            stale_payload = self._build_data_stale_error(exc, allow_stale_inputs=allow_stale_inputs)
            return self._cache_error_response(stale_payload)
        except StrategyConfigurationError as exc:
            config_payload = self._build_config_error_response(exc)
            return self._cache_error_response(config_payload)

        try:
            result = await self.engine.run_backtest(start_date, end_date, strategy=strategy)
            if "error" in result:
                error_type = result.get("error_type", "UNKNOWN")
                error_details = result.get("details", result.get("error", "Unknown error"))
                error_response = {
                    "status": "error",
                    "message": result["error"],
                    "error_type": error_type,
                    "details": error_details,
                    "metrics": {}
                }
                return self._cache_error_response(error_response)

            metrics = calculate_metrics(result)
            charts, chart_banners = self._generate_charts(result)
            build_campaign_report()
            self._clear_error_cache()

            # Persist to DB with versioning
            with SessionLocal() as db:
                save_backtest_result(
                    db,
                    version=__version__,
                    start_date=result["start_date"],
                    end_date=result["end_date"],
                    metrics=metrics,
                )

            # Calculate OOS days and metrics status
            start_ts = pd.to_datetime(result["start_date"])
            end_ts = pd.to_datetime(result["end_date"])
            total_days = (end_ts - start_ts).days
            
            # Estimate OOS period (20% of total, minimum 120 days)
            oos_days = max(120, int(total_days * 0.2))
            
            # Check metrics status using guardrails
            from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
            checker = GuardrailChecker(GuardrailConfig())
            
            metrics_status = "PASS"
            tracking_error_summary = result.get("tracking_error") or {}
            annualized_te = tracking_error_summary.get("annualized_tracking_error")
            initial_capital = result.get("initial_capital") or 0.0
            tracking_error_annualized_pct = None
            if annualized_te is not None and initial_capital:
                tracking_error_annualized_pct = annualized_te / initial_capital

            guardrail_result = checker.check_all(
                max_drawdown_pct=metrics.get("max_drawdown"),
                risk_of_ruin=metrics.get("risk_of_ruin"),
                trade_count=metrics.get("total_trades", 0),
                duration_days=total_days,
                tracking_error_annualized_pct=tracking_error_annualized_pct,
            )
            if not guardrail_result.passed:
                metrics_status = "FAIL"

            # Extract tracking error and execution data for response
            tracking_error = tracking_error_summary
            tracking_error_metrics = result.get("tracking_error_metrics") or {}
            execution_stats = result.get("execution_stats", {})
            equity_theoretical = result.get("equity_theoretical", [])
            equity_realistic = result.get("equity_realistic", [])
            equity_curve = result.get("equity_curve", [])
            has_realistic_data = bool(result.get("equity_curve_realistic") or equity_realistic)
            tracking_error_series = result.get("tracking_error_series", [])
            tracking_error_cumulative = result.get("tracking_error_cumulative", [])
            
            summary = {
                "status": "success",
                "metrics": metrics,
                "period": {
                    "start": result["start_date"],
                    "end": result["end_date"],
                },
                "report_path": str((self.project_root / "docs" / "backtest-report.md").resolve()),
                "charts": charts,
                "chart_banners": chart_banners,
                "version": __version__,
                "oos_days": oos_days,
                "metrics_status": metrics_status,
                "equity_theoretical": equity_theoretical,
                "equity_realistic": equity_realistic,
                "equity_curve": equity_curve,
                "tracking_error": tracking_error,
                "tracking_error_metrics": tracking_error_metrics,
                "tracking_error_series": tracking_error_series,
                "tracking_error_cumulative": tracking_error_cumulative,
                "has_realistic_data": has_realistic_data,
            }
            # Add metadata indicating this was freshly generated
            summary = self._enrich_with_cache_metadata(summary, served_from_cache=False)
            return summary
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            error_response = {
                "status": "error",
                "message": str(e),
                "error_type": "EXCEPTION",
                "details": error_trace,
                "metrics": {}
            }
            return self._cache_error_response(error_response)

    def _cache_error_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Store error payload to avoid repeated engine calls."""
        timestamp = datetime.utcnow()
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault(
            "user_message",
            "Backtest engine temporarily unavailable. Showing the last error while retrying soon.",
        )
        metadata["last_attempt"] = timestamp.isoformat()
        metadata["cache_ttl_seconds"] = self.ERROR_CACHE_TTL_SECONDS
        payload["metadata"] = metadata
        self._error_cache = {"payload": payload, "timestamp": timestamp}
        return payload

    def _get_cached_error(self, *, allow_stale_inputs: bool) -> dict[str, Any] | None:
        """Return cached error response if still within TTL."""
        if not self._error_cache:
            return None
        timestamp = self._error_cache["timestamp"]
        age_seconds = (datetime.utcnow() - timestamp).total_seconds()
        if age_seconds > self.ERROR_CACHE_TTL_SECONDS:
            self._error_cache = None
            return None
        cached_payload = dict(self._error_cache["payload"])
        metadata = dict(cached_payload.get("metadata") or {})
        metadata["cached_error"] = True
        metadata["cache_expires_at"] = (timestamp + timedelta(seconds=self.ERROR_CACHE_TTL_SECONDS)).isoformat()
        metadata["retry_after_seconds"] = max(0, int(self.ERROR_CACHE_TTL_SECONDS - age_seconds))
        metadata["served_with_allow_stale_inputs"] = allow_stale_inputs
        cached_payload["metadata"] = metadata
        return cached_payload

    def _clear_error_cache(self) -> None:
        """Clear cached error after successful run."""
        self._error_cache = None

    def _clear_stale_error_cache_if_needed(self) -> None:
        """Clear cached stale-data errors once fresh inputs succeed."""
        if not self._error_cache:
            return
        payload = self._error_cache.get("payload") or {}
        if payload.get("error_type") == "DATA_STALE":
            self._clear_error_cache()

    def _enrich_with_cache_metadata(self, summary: dict[str, Any], *, served_from_cache: bool) -> dict[str, Any]:
        """Enrich summary with cache metadata fields for frontend."""
        metadata = summary.get("metadata", {})
        if served_from_cache:
            metadata["served_from_cache"] = True
            if "cached_at" in summary:
                metadata["generated_at"] = summary["cached_at"]
            else:
                metadata["generated_at"] = datetime.utcnow().isoformat()
        else:
            metadata["served_from_cache"] = False
            metadata["generated_at"] = datetime.utcnow().isoformat()
        summary["metadata"] = metadata
        return summary

    async def _run_backtest_and_cache(self, *, allow_stale_inputs: bool = False) -> dict[str, Any] | None:
        """
        Run backtest asynchronously and cache the result.
        
        This method is intended to be called from background tasks.
        Returns the summary if successful, None if failed (errors are logged).
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=5 * 365)
        
        try:
            strategy = self._resolve_strategy(allow_stale_data=allow_stale_inputs)
        except (DataFreshnessError, StrategyConfigurationError) as exc:
            logger.warning(
                "Background backfill failed during strategy resolution",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            return None
        
        try:
            logger.info("Starting background backtest backfill")
            result = await self.engine.run_backtest(start_date, end_date, strategy=strategy)
            
            if "error" in result:
                logger.warning(
                    "Background backtest failed with error",
                    extra={"error": result.get("error"), "error_type": result.get("error_type", "UNKNOWN")},
                )
                return None
            
            metrics = calculate_metrics(result)
            charts, chart_banners = self._generate_charts(result)
            build_campaign_report()
            self._clear_error_cache()
            
            # Persist to DB with versioning
            with SessionLocal() as db:
                save_backtest_result(
                    db,
                    version=__version__,
                    start_date=result["start_date"],
                    end_date=result["end_date"],
                    metrics=metrics,
                )
            
            logger.info(
                "Background backtest backfill completed successfully",
                extra={
                    "start_date": result["start_date"],
                    "end_date": result["end_date"],
                    "total_trades": metrics.get("total_trades", 0),
                },
            )
            
            # Return summary for potential immediate use
            start_ts = pd.to_datetime(result["start_date"])
            end_ts = pd.to_datetime(result["end_date"])
            total_days = (end_ts - start_ts).days
            oos_days = max(120, int(total_days * 0.2))
            
            from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
            checker = GuardrailChecker(GuardrailConfig())
            tracking_error_summary = result.get("tracking_error") or {}
            annualized_te = tracking_error_summary.get("annualized_tracking_error")
            initial_capital = result.get("initial_capital") or 0.0
            tracking_error_annualized_pct = None
            if annualized_te is not None and initial_capital:
                tracking_error_annualized_pct = annualized_te / initial_capital
            
            guardrail_result = checker.check_all(
                max_drawdown_pct=metrics.get("max_drawdown"),
                risk_of_ruin=metrics.get("risk_of_ruin"),
                trade_count=metrics.get("total_trades", 0),
                duration_days=total_days,
                tracking_error_annualized_pct=tracking_error_annualized_pct,
            )
            metrics_status = "PASS" if guardrail_result.passed else "FAIL"
            
            summary = {
                "status": "success",
                "metrics": metrics,
                "period": {
                    "start": result["start_date"],
                    "end": result["end_date"],
                },
                "report_path": str((self.project_root / "docs" / "backtest-report.md").resolve()),
                "charts": charts,
                "chart_banners": chart_banners,
                "version": __version__,
                "oos_days": oos_days,
                "metrics_status": metrics_status,
                "equity_theoretical": result.get("equity_theoretical", []),
                "equity_realistic": result.get("equity_realistic", []),
                "equity_curve": result.get("equity_curve", []),
                "tracking_error": tracking_error_summary,
                "tracking_error_metrics": result.get("tracking_error_metrics") or {},
                "tracking_error_series": result.get("tracking_error_series", []),
                "tracking_error_cumulative": result.get("tracking_error_cumulative", []),
                "has_realistic_data": bool(result.get("equity_curve_realistic") or result.get("equity_realistic")),
            }
            return self._enrich_with_cache_metadata(summary, served_from_cache=False)
            
        except Exception as e:
            logger.exception(
                "Background backtest backfill failed with exception",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return None

    def _get_db_cached_success_summary(self, *, max_age_seconds: int | None) -> dict[str, Any] | None:
        """Fetch the latest successful backtest summary stored in the DB."""
        with SessionLocal() as db:
            cached = get_latest_backtest_result(db)
            if not cached:
                return None
            age_seconds = (datetime.utcnow() - cached.created_at).total_seconds()
            if max_age_seconds is not None and age_seconds > max_age_seconds:
                return None
            
            # Extract tracking error metrics from cached metrics if available
            metrics = cached.metrics or {}
            tracking_error_metrics = metrics.get("tracking_error_metrics")
            
            # Try to extract equity data from metrics if available
            equity_theoretical = metrics.get("equity_theoretical", [])
            equity_realistic = metrics.get("equity_realistic", [])
            equity_curve = metrics.get("equity_curve", [])
            
            # Build response with tracking error fields
            response = {
                "status": "success",
                "metrics": metrics,
                "period": {
                    "start": cached.start_date,
                    "end": cached.end_date,
                },
                "report_path": str(self.reports_dir / "backtest-report.md"),
                "source": "db_cache",
                "cached_at": cached.created_at.isoformat(),
                "cache_age_seconds": age_seconds,
                # Include equity fields even if empty for frontend compatibility
                "equity_theoretical": equity_theoretical,
                "equity_realistic": equity_realistic,
                "equity_curve": equity_curve,
            }
            
            # Include tracking error metrics if available in cached data
            if tracking_error_metrics:
                response["tracking_error_metrics"] = tracking_error_metrics
                # Also populate tracking_error summary if we can derive it from metrics
                # The tracking_error_metrics contains fields like max_drawdown_divergence, rmse, etc.
                # which can be used for transparency calculations
                response["tracking_error"] = {
                    "max_drawdown_divergence": tracking_error_metrics.get("max_drawdown_divergence"),
                    "rmse": tracking_error_metrics.get("rmse"),
                    "mean_deviation": tracking_error_metrics.get("mean_deviation"),
                    "max_divergence": tracking_error_metrics.get("max_divergence"),
                }
            
            return response

    def _build_config_error_response(self, exc: StrategyConfigurationError) -> dict[str, Any]:
        """Standardize strategy configuration errors for caching."""
        metadata = {
            "error_scope": "strategy_configuration",
            "required_setting": exc.details.get("setting") if exc.details else None,
            "recovery_hints": [
                "Ensure PERFORMANCE_STRATEGY_SOURCE is configured",
                "Verify signal datasets exist and are readable",
                "Confirm environment variables in backend/app/core/config.py are set",
            ],
        }

        return {
            "status": "error",
            "message": str(exc),
            "error_type": "CONFIG",
            "details": exc.details,
            "metrics": {},
            "http_status": 400,
            "metadata": metadata,
        }

    def _build_data_stale_error(self, exc: DataFreshnessError, *, allow_stale_inputs: bool) -> dict[str, Any]:
        """Build a structured payload when signal data is stale."""
        latest_ts = exc.latest_timestamp
        if isinstance(latest_ts, datetime):
            latest_iso = latest_ts.isoformat()
        else:
            latest_iso = str(latest_ts) if latest_ts is not None else None

        context = dict(getattr(exc, "context_data", {}) or {})
        age_minutes = context.get("age_minutes")

        metadata = {
            "stale_interval": exc.interval,
            "latest_timestamp": latest_iso,
            "threshold_minutes": exc.threshold_minutes,
            "age_minutes": age_minutes,
            "latest_candle_age_minutes": age_minutes,
            "reference_time": context.get("reference_time"),
            "cached_inputs_available": self.signal_data_provider.has_cached_inputs(),
            "allow_stale_inputs_requested": allow_stale_inputs,
            "recovery_hints": [
                "Refresh curated OHLCV datasets",
                "Re-run ingestion pipeline",
                "Retry once new candles arrive",
            ],
        }

        dataset_snapshot = None
        try:
            dataset_snapshot = self.signal_data_provider.describe_dataset_freshness()
        except Exception as snapshot_exc:
            logger.warning(
                "Failed to collect dataset freshness snapshot",
                extra={"error": str(snapshot_exc)},
            )

        if dataset_snapshot:
            metadata["dataset_freshness"] = dataset_snapshot

        remediation_hint = "Ejecuta job_ingest_all para regenerar datasets 1h/1d antes de reintentar."
        metadata["recovery_hints"].append(remediation_hint)
        metadata["remediation"] = remediation_hint
        metadata["remediation_commands"] = ["job_ingest_all"]

        if allow_stale_inputs and not settings.PERFORMANCE_STRATEGY_VALIDATE_DATA:
            metadata["freshness_validation_disabled_globally"] = True

        details = {
            "interval": exc.interval,
            "latest_timestamp": latest_iso,
            "threshold_minutes": exc.threshold_minutes,
            "context": context,
        }
        if age_minutes is not None:
            details["age_minutes"] = age_minutes
            details["latest_candle_age_minutes"] = age_minutes

        self._emit_staleness_observability(
            interval=exc.interval,
            latest_timestamp=latest_iso,
            age_minutes=age_minutes,
            threshold_minutes=exc.threshold_minutes,
            allow_stale_inputs=allow_stale_inputs,
            dataset_snapshot=dataset_snapshot,
        )

        # Get fallback summary with rich metrics
        fallback_summary = self._get_db_cached_success_summary(max_age_seconds=None)
        historical_fallback = fallback_summary is not None
        
        # Ensure fallback_summary always has required fields, even if empty
        if not fallback_summary:
            fallback_summary = {
                "status": "success",
                "metrics": {},
                "period": None,
                "report_path": None,
                "source": "placeholder",
                "equity_theoretical": [],
                "equity_realistic": [],
                "equity_curve": [],
                "tracking_error_metrics": None,
                "tracking_error": None,
            }
        else:
            fallback_summary["source"] = "db_cache"
            # Ensure optional fields are present even if None/empty
            fallback_summary.setdefault("equity_theoretical", [])
            fallback_summary.setdefault("equity_realistic", [])
            fallback_summary.setdefault("equity_curve", [])
            fallback_summary.setdefault("tracking_error_metrics", None)
            fallback_summary.setdefault("tracking_error", None)

        metadata["fallback_summary_available"] = historical_fallback
        metadata["fallback_summary_source"] = fallback_summary.get("source")

        # Extract tracking error fields from fallback summary for downstream consumers
        tracking_error_metrics = fallback_summary.get("tracking_error_metrics")
        tracking_error = fallback_summary.get("tracking_error")
        
        # Build response with all optional fields populated to prevent frontend breakage
        response = {
            "status": "error",
            "message": exc.reason,
            "error_type": "DATA_STALE",
            "details": details,
            "metrics": fallback_summary.get("metrics") or {},
            "http_status": 503,
            "metadata": metadata,
            "fallback_summary": fallback_summary,
            # Include optional fields at top level for frontend compatibility
            "period": fallback_summary.get("period"),
            "equity_theoretical": fallback_summary.get("equity_theoretical", []),
            "equity_realistic": fallback_summary.get("equity_realistic", []),
            "equity_curve": fallback_summary.get("equity_curve", []),
        }
        
        # Include tracking error metrics if available in fallback summary
        if tracking_error_metrics:
            response["tracking_error_metrics"] = tracking_error_metrics
        if tracking_error:
            response["tracking_error"] = tracking_error
        
        return response

    def _emit_staleness_observability(
        self,
        *,
        interval: str,
        latest_timestamp: str | None,
        age_minutes: float | None,
        threshold_minutes: int | None,
        allow_stale_inputs: bool,
        dataset_snapshot: dict[str, Any] | None = None,
    ) -> None:
        """Emit structured telemetry for monitoring dashboards."""
        logger.warning(
            "Performance summary blocked: stale signal data",
            extra={
                "interval": interval,
                "latest_timestamp": latest_timestamp,
                "latest_candle_age_minutes": age_minutes,
                "threshold_minutes": threshold_minutes,
                "allow_stale_inputs_requested": allow_stale_inputs,
                "dataset_freshness": dataset_snapshot,
            },
        )

    def _generate_charts(self, backtest_result: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        charts: dict[str, str] = {}
        banners: list[str] = []
        equity_curve_records = backtest_result.get("equity_curve", [])
        trades = backtest_result.get("trades", [])
        equity_theoretical = backtest_result.get("equity_theoretical", [])
        equity_realistic = backtest_result.get("equity_realistic", [])
        tracking_error_summary = backtest_result.get("tracking_error") or {}
        tracking_error_metrics = backtest_result.get("tracking_error_metrics") or {}
        tracking_error_series = backtest_result.get("tracking_error_series", [])
        tracking_error_cumulative = backtest_result.get("tracking_error_cumulative", [])

        def _save_chart(fig: plt.Figure, filename: str) -> str:
            local_path = self.reports_dir / filename
            docs_path = self.docs_assets_dir / filename
            fig.savefig(local_path, dpi=150, bbox_inches="tight")
            fig.savefig(docs_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return str(docs_path.resolve())

        # Build consolidated equity DataFrame for plotting
        equity_df = pd.DataFrame(equity_curve_records)
        if equity_df.empty:
            curve_th = backtest_result.get("equity_curve_theoretical", [])
            curve_rl = backtest_result.get("equity_curve_realistic", [])
            if curve_th and curve_rl:
                df_th = pd.DataFrame(curve_th).rename(columns={"equity": "equity_theoretical"})
                df_rl = pd.DataFrame(curve_rl).rename(columns={"equity": "equity_realistic"})
                equity_df = pd.merge(df_th, df_rl, on="timestamp", how="outer")
        if not equity_df.empty:
            equity_df["timestamp"] = pd.to_datetime(equity_df["timestamp"])
            equity_df = equity_df.sort_values("timestamp")

        # Determine data availability and warnings
        has_realistic_data = (
            not equity_df.empty
            and "equity_realistic" in equity_df
            and equity_df["equity_realistic"].notna().any()
        )
        if not has_realistic_data:
            banners.append("WARNING: No hay curva realista para comparar contra la teórica.")
        
        if not tracking_error_series:
            banners.append("WARNING: No hay datos de ejecución realista; tracking error no disponible.")

        te_config = self.performance_config.get("tracking_error", {})
        initial_capital = backtest_result.get("initial_capital") or 0.0
        rmse_value = tracking_error_metrics.get("rmse") or tracking_error_summary.get("rmse")
        rmse_threshold_pct = te_config.get("max_rmse_pct")
        if (
            rmse_value is not None
            and initial_capital
            and rmse_threshold_pct is not None
            and (rmse_value / initial_capital) > rmse_threshold_pct
        ):
            banners.append(
                f"ALERT: Tracking error RMSE {rmse_value / initial_capital:.2%} supera el umbral configurado ({rmse_threshold_pct:.0%})."
            )

        divergence_threshold_pct = te_config.get("divergence_threshold_pct")
        divergence_threshold_bps = divergence_threshold_pct * 10000 if divergence_threshold_pct is not None else None
        max_divergence_bps = tracking_error_summary.get("max_divergence_bps")
        if (
            max_divergence_bps is not None
            and divergence_threshold_bps is not None
            and max_divergence_bps > divergence_threshold_bps
        ):
            banners.append(
                f"ALERT: Divergencia máxima {max_divergence_bps:.0f} bps supera el umbral ({divergence_threshold_bps:.0f} bps)."
            )

        # Dual equity curve chart
        if not equity_df.empty:
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(
                equity_df["timestamp"],
                equity_df["equity_theoretical"],
                color="#1d4ed8",
                label="Equity Teórica",
                linewidth=2,
            )
            if has_realistic_data:
                ax.plot(
                    equity_df["timestamp"],
                    equity_df["equity_realistic"],
                    color="#ef4444",
                    label="Equity Realista",
                    linewidth=2,
                )
            ax.set_title("Equity Teórica vs. Realista")
            ax.set_xlabel("Tiempo")
            ax.set_ylabel("Capital ($)")
            ax.grid(True, alpha=0.3)
            ax.legend()
            dual_chart_path = _save_chart(fig, "equity_dual.png")
            charts["equity_dual"] = dual_chart_path
            charts["equity_curve"] = dual_chart_path  # Legacy key

            # Drawdown chart (use realistic if available)
            reference_series = (
                equity_df["equity_realistic"] if has_realistic_data else equity_df["equity_theoretical"]
            ).astype(float)
            running_max = reference_series.cummax()
            drawdown = ((reference_series - running_max) / running_max).fillna(0.0) * 100
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.fill_between(equity_df["timestamp"], drawdown, color="#ef4444", alpha=0.3)
            ax.plot(equity_df["timestamp"], drawdown, color="#ef4444")
            ax.set_title("Drawdown (%)")
            ax.set_xlabel("Tiempo")
            ax.set_ylabel("Drawdown")
            ax.grid(True, alpha=0.3)
            charts["drawdown"] = _save_chart(fig, "drawdown.png")

        # Tracking error panel (instant + cumulative)
        if tracking_error_series:
            te_series_df = pd.DataFrame(tracking_error_series)
            te_series_df["timestamp"] = pd.to_datetime(te_series_df["timestamp"])
            te_series_df = te_series_df.sort_values("timestamp")

            if not tracking_error_cumulative:
                cumulative_values = te_series_df["tracking_error"].cumsum()
                te_cumulative_df = pd.DataFrame(
                    {
                        "timestamp": te_series_df["timestamp"],
                        "tracking_error_cumulative": cumulative_values,
                    }
                )
            else:
                te_cumulative_df = pd.DataFrame(tracking_error_cumulative)
                te_cumulative_df["timestamp"] = pd.to_datetime(te_cumulative_df["timestamp"])
                te_cumulative_df = te_cumulative_df.sort_values("timestamp")

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
            ax1.plot(
                te_series_df["timestamp"],
                te_series_df["tracking_error"],
                color="#f59e0b",
                linewidth=1,
            )
            ax1.axhline(y=0, color="black", linestyle="--", alpha=0.4)
            ax1.set_ylabel("Tracking Error ($)")
            ax1.set_title("Tracking Error Instantáneo (Real - Teórico)")
            ax1.grid(True, alpha=0.3)

            ax2.plot(
                te_cumulative_df["timestamp"],
                te_cumulative_df["tracking_error_cumulative"],
                color="#8b5cf6",
                linewidth=2,
            )
            ax2.axhline(y=0, color="black", linestyle="--", alpha=0.4)
            ax2.set_xlabel("Tiempo")
            ax2.set_ylabel("Tracking Error Acumulado ($)")
            ax2.set_title("Tracking Error Acumulado")
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()
            te_chart_path = _save_chart(fig, "tracking_error_panel.png")
            charts["tracking_error_panel"] = te_chart_path
            charts["tracking_error"] = te_chart_path  # Legacy key

        if trades:
            df = pd.DataFrame(trades)
            wins = int((df["pnl"] > 0).sum())
            losses = int((df["pnl"] <= 0).sum())
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.bar(["Ganadoras", "Perdedoras"], [wins, losses], color=["#22c55e", "#ef4444"], alpha=0.8)
            ax.set_title("Distribución de Trades")
            ax.set_ylabel("Número de operaciones")
            ax.grid(axis="y", alpha=0.2)
            charts["win_rate"] = _save_chart(fig, "win_rate.png")

        return charts, banners


_performance_service_singleton: PerformanceService | None = None


def get_performance_service() -> PerformanceService:
    """Return a shared PerformanceService instance for all callers."""
    global _performance_service_singleton
    if _performance_service_singleton is None:
        _performance_service_singleton = PerformanceService()
    return _performance_service_singleton
