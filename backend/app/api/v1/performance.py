"""Performance endpoints."""
from fastapi import APIRouter, HTTPException, Query, Response

from app.backtesting.guardrails import GuardrailChecker, GuardrailConfig
from app.models.performance import (
    PerformanceMetrics,
    PerformancePeriod,
    PerformanceSummaryResponse,
    RiskProfile,
    RollingMetrics,
)
from app.services.monitoring_service import ContinuousMonitoringService
from app.services.performance_service import PerformanceService
from app.services.kpis_reporting_service import KPIsReportingService
from app.core.logging import logger

router = APIRouter()
performance_service = PerformanceService()
monitoring_service = ContinuousMonitoringService(asset="BTCUSDT", venue="binance")
kpis_service = KPIsReportingService()


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary():
    """
    Get backtesting performance summary with metrics and disclaimer.

    Returns comprehensive metrics including CAGR, Sharpe, Sortino, Max Drawdown,
    Win Rate, Profit Factor, Expectancy, Calmar, and rolling KPIs (monthly/quarterly).
    """
    try:
        result = await performance_service.get_summary()

        if result.get("status") == "error":
            error_type = result.get("error_type")
            if error_type == "CONFIG":
                raise HTTPException(
                    status_code=result.get("http_status", 400),
                    detail={
                        "message": result.get("message", "Strategy configuration error"),
                        "error_type": error_type,
                        "details": result.get("details", {}),
                    },
                )
            return PerformanceSummaryResponse(
                status="error",
                message=result.get("message", "Unknown error"),
                metrics=None,
                period=None,
                report_path=None,
            )

        metrics_dict = result.get("metrics", {})
        rolling_monthly = metrics_dict.get("rolling_monthly")
        rolling_quarterly = metrics_dict.get("rolling_quarterly")

        risk_profile_dict = metrics_dict.get("risk_profile")
        risk_profile = RiskProfile(**risk_profile_dict) if risk_profile_dict else None

        metrics = PerformanceMetrics(
            cagr=metrics_dict.get("cagr", 0.0),
            sharpe=metrics_dict.get("sharpe", 0.0),
            sortino=metrics_dict.get("sortino", 0.0),
            max_drawdown=metrics_dict.get("max_drawdown", 0.0),
            win_rate=metrics_dict.get("win_rate", 0.0),
            profit_factor=metrics_dict.get("profit_factor", 0.0),
            expectancy=metrics_dict.get("expectancy", 0.0),
            calmar=metrics_dict.get("calmar", 0.0),
            total_return=metrics_dict.get("total_return", 0.0),
            total_trades=metrics_dict.get("total_trades", 0),
            winning_trades=metrics_dict.get("winning_trades", 0),
            losing_trades=metrics_dict.get("losing_trades", 0),
            rolling_monthly=RollingMetrics(**rolling_monthly) if rolling_monthly else None,
            rolling_quarterly=RollingMetrics(**rolling_quarterly) if rolling_quarterly else None,
            risk_profile=risk_profile,
            tracking_error_rmse=metrics_dict.get("tracking_error_rmse"),
            tracking_error_max=metrics_dict.get("tracking_error_max"),
            orderbook_fallback_events=metrics_dict.get("orderbook_fallback_events"),
        )
        
        # Extract tracking error data from backtest result
        tracking_error = result.get("tracking_error")
        execution_stats = result.get("execution_stats", {})
        has_realistic_data = bool(result.get("equity_realistic") and len(result.get("equity_realistic", [])) > 0)
        
        tracking_error_rmse = None
        tracking_error_max = None
        if tracking_error and isinstance(tracking_error, dict):
            tracking_error_rmse = tracking_error.get("rmse")
            tracking_error_max_bps = tracking_error.get("max_divergence_bps")
            if tracking_error_max_bps is not None:
                tracking_error_max = tracking_error_max_bps
        
        orderbook_fallback_events = execution_stats.get("rejected_orders", 0)

        period_dict = result.get("period", {})
        period = PerformancePeriod(
            start=period_dict.get("start", ""),
            end=period_dict.get("end", ""),
        ) if period_dict else None

        # Deployment guardrails: prevent publishing if criteria not met
        oos_days = result.get("oos_days")
        metrics_status = result.get("metrics_status", "UNKNOWN")
        
        if oos_days is not None and oos_days < 120:
            logger.warning(
                "Summary blocked: insufficient OOS period",
                extra={"oos_days": oos_days, "required": 120}
            )
            return PerformanceSummaryResponse(
                status="error",
                message=f"Results cannot be published: OOS period ({oos_days} days) is less than required minimum (120 days)",
                metrics=None,
                period=period,
                report_path=None,
            )
        
        if metrics_status != "PASS":
            logger.warning(
                "Summary blocked: metrics status not PASS",
                extra={"metrics_status": metrics_status}
            )
            return PerformanceSummaryResponse(
                status="error",
                message=f"Results cannot be published: metrics status is '{metrics_status}' (required: 'PASS')",
                metrics=None,
                period=period,
                report_path=None,
            )

        response = PerformanceSummaryResponse(
            status="success",
            metrics=metrics,
            period=period,
            report_path=result.get("report_path"),
            message=None,
            tracking_error_rmse=tracking_error_rmse,
            tracking_error_max=tracking_error_max,
            orderbook_fallback_events=orderbook_fallback_events,
            has_realistic_data=has_realistic_data,
            tracking_error_metrics=result.get("tracking_error_metrics"),
            tracking_error_series=result.get("tracking_error_series"),
            tracking_error_cumulative=result.get("tracking_error_cumulative"),
            chart_banners=result.get("chart_banners"),
        )
        
        # Add equity data to response model (will be in response body but not in schema)
        response_dict = response.model_dump()
        response_dict["equity_theoretical"] = result.get("equity_theoretical", [])
        response_dict["equity_realistic"] = result.get("equity_realistic", [])
        response_dict["equity_curve"] = result.get("equity_curve", [])
        response_dict["equity_curve_theoretical"] = result.get("equity_curve_theoretical", [])
        response_dict["equity_curve_realistic"] = result.get("equity_curve_realistic", [])
        
        return response_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/health")
async def get_monitoring_health():
    """
    Get current performance monitoring health status with metrics and alerts.
    
    Returns current rolling metrics, regime probabilities, and any active alerts.
    """
    try:
        metrics = monitoring_service.get_current_metrics()
        alerts = monitoring_service.check_alerts()
        
        return {
            "status": "ok",
            "metrics": metrics,
            "alerts": alerts,
            "alerts_count": len(alerts),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/metrics")
async def get_monitoring_metrics():
    """
    Get current Prometheus performance metrics (rolling Sharpe, hit rate, equity slope, regime).
    
    Returns all current metric values from Prometheus gauges.
    """
    try:
        metrics = monitoring_service.get_current_metrics()
        return {
            "status": "ok",
            "metrics": metrics,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly")
async def get_monthly_performance():
    """
    Get detailed monthly performance with returns, streaks, and current drawdown.
    
    Returns:
    - Monthly returns table
    - Best/worst month
    - Current win/loss streak
    - Current drawdown
    """
    from app.services.performance_service import PerformanceService
    from app.core.database import SessionLocal
    from app.db.crud import get_recommendation_history, calculate_production_drawdown
    from datetime import datetime
    import pandas as pd

    perf_service = PerformanceService()
    
    # Get production trades from recommendations
    with SessionLocal() as db:
        recs = get_recommendation_history(db, limit=500)
        dd_info = calculate_production_drawdown(db)
    
    # Filter closed trades
    closed_trades = []
    for rec in recs:
        if rec.status == "closed" and rec.exit_price and rec.entry_optimal:
            exit_date = rec.closed_at or rec.created_at
            if rec.signal == "BUY":
                return_pct = ((rec.exit_price - rec.entry_optimal) / rec.entry_optimal) * 100
            elif rec.signal == "SELL":
                return_pct = ((rec.entry_optimal - rec.exit_price) / rec.entry_optimal) * 100
            else:
                return_pct = 0.0
            
            closed_trades.append({
                "date": exit_date,
                "return_pct": return_pct,
                "signal": rec.signal,
                "is_win": return_pct > 0,
            })
    
    if not closed_trades:
        return {
            "status": "no_data",
            "monthly_returns": [],
            "best_month": None,
            "worst_month": None,
            "current_streak": {"type": "none", "count": 0},
            "current_drawdown": dd_info.get("current_drawdown_pct", 0.0),
            "peak_equity": dd_info.get("peak_equity", 0.0),
            "current_equity": dd_info.get("current_equity", 0.0),
        }
    
    # Calculate monthly returns
    df_trades = pd.DataFrame(closed_trades)
    df_trades["date"] = pd.to_datetime(df_trades["date"])
    df_trades["year_month"] = df_trades["date"].dt.to_period("M")
    
    monthly_returns = []
    monthly_groups = df_trades.groupby("year_month")
    
    for period, group in monthly_groups:
        total_return = group["return_pct"].sum()
        trade_count = len(group)
        wins = group["is_win"].sum()
        losses = trade_count - wins
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0.0
        
        monthly_returns.append({
            "month": str(period),
            "year": period.year,
            "month_num": period.month,
            "return_pct": round(total_return, 2),
            "trade_count": trade_count,
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round(win_rate, 2),
        })
    
    # Sort by date (most recent first)
    monthly_returns.sort(key=lambda x: (x["year"], x["month_num"]), reverse=True)
    
    # Find best and worst month
    best_month = max(monthly_returns, key=lambda x: x["return_pct"]) if monthly_returns else None
    worst_month = min(monthly_returns, key=lambda x: x["return_pct"]) if monthly_returns else None
    
    # Calculate current streak (from most recent trades)
    sorted_trades = sorted(closed_trades, key=lambda x: x["date"], reverse=True)
    current_streak = {"type": "none", "count": 0}
    
    if sorted_trades:
        first_result = sorted_trades[0]["is_win"]
        streak_type = "win" if first_result else "loss"
        streak_count = 1
        
        for i in range(1, len(sorted_trades)):
            if sorted_trades[i]["is_win"] == first_result:
                streak_count += 1
            else:
                break
        
        current_streak = {"type": streak_type, "count": streak_count}
    
    # Get current drawdown
    current_dd_pct = dd_info.get("current_drawdown_pct", 0.0)
    peak_equity = dd_info.get("peak_equity", 0.0)
    current_equity = dd_info.get("current_equity", 0.0)
    
    return {
        "status": "ok",
        "monthly_returns": monthly_returns,
        "best_month": best_month,
        "worst_month": worst_month,
        "current_streak": current_streak,
        "current_drawdown": round(current_dd_pct, 2),
        "peak_equity": round(peak_equity, 2),
        "current_equity": round(current_equity, 2),
        "total_trades": len(closed_trades),
    }


@router.get("/monthly/export")
async def export_monthly_report(
    format: str = Query("csv", regex="^(csv|parquet)$"),
) -> Response:
    """
    Export monthly performance report with hashes for verification.
    
    Returns CSV or Parquet file with monthly returns, streaks, and drawdown data.
    Includes metadata: commit_hash, dataset_hash, params_hash.
    """
    from fastapi.responses import Response
    from app.utils.hashing import calculate_file_md5, calculate_file_sha256, get_git_commit_hash
    from app.utils.dataset_metadata import get_dataset_version_hash, get_params_digest
    from app.db.models import ExportAuditORM
    from app.core.database import SessionLocal
    from app.db.crud import get_recommendation_history, calculate_production_drawdown
    import io
    import pandas as pd
    
    # Get monthly performance data (reuse logic from get_monthly_performance)
    with SessionLocal() as db:
        recs = get_recommendation_history(db, limit=500)
        dd_info = calculate_production_drawdown(db)
    
    # Filter closed trades
    closed_trades = []
    for rec in recs:
        if rec.status == "closed" and rec.exit_price and rec.entry_optimal:
            exit_date = rec.closed_at or rec.created_at
            if rec.signal == "BUY":
                return_pct = ((rec.exit_price - rec.entry_optimal) / rec.entry_optimal) * 100
            elif rec.signal == "SELL":
                return_pct = ((rec.entry_optimal - rec.exit_price) / rec.entry_optimal) * 100
            else:
                return_pct = 0.0
            
            closed_trades.append({
                "date": exit_date,
                "return_pct": return_pct,
                "signal": rec.signal,
                "is_win": return_pct > 0,
            })
    
    if not closed_trades:
        raise HTTPException(status_code=404, detail="No monthly data available for export")
    
    # Calculate monthly returns
    df_trades = pd.DataFrame(closed_trades)
    df_trades["date"] = pd.to_datetime(df_trades["date"])
    df_trades["year_month"] = df_trades["date"].dt.to_period("M")
    
    export_records = []
    monthly_groups = df_trades.groupby("year_month")
    
    for period, group in monthly_groups:
        total_return = group["return_pct"].sum()
        trade_count = len(group)
        wins = group["is_win"].sum()
        losses = trade_count - wins
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0.0
        
        export_records.append({
            "month": str(period),
            "year": period.year,
            "month_num": period.month,
            "return_pct": round(total_return, 2),
            "trade_count": trade_count,
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round(win_rate, 2),
        })
    
    export_records.sort(key=lambda x: (x["year"], x["month_num"]), reverse=True)
    best_month = max(export_records, key=lambda x: x["return_pct"]) if export_records else None
    worst_month = min(export_records, key=lambda x: x["return_pct"]) if export_records else None
    
    sorted_trades = sorted(closed_trades, key=lambda x: x["date"], reverse=True)
    current_streak = {"type": "none", "count": 0}
    
    if sorted_trades:
        first_result = sorted_trades[0]["is_win"]
        streak_type = "win" if first_result else "loss"
        streak_count = 1
        
        for i in range(1, len(sorted_trades)):
            if sorted_trades[i]["is_win"] == first_result:
                streak_count += 1
            else:
                break
        
        current_streak = {"type": streak_type, "count": streak_count}
    
    # Add summary data
    summary = {
        "best_month": best_month,
        "worst_month": worst_month,
        "current_streak_type": current_streak.get("type"),
        "current_streak_count": current_streak.get("count"),
        "current_drawdown": round(dd_info.get("current_drawdown_pct", 0.0), 2),
        "peak_equity": round(dd_info.get("peak_equity", 0.0), 2),
        "current_equity": round(dd_info.get("current_equity", 0.0), 2),
        "total_trades": len(closed_trades),
    }
    
    # Create DataFrame
    df = pd.DataFrame(export_records)
    
    # Add summary as additional rows or metadata
    # For CSV, we'll add summary as a comment or separate section
    
    # Export to requested format
    buffer = io.BytesIO()
    if format == "csv":
        # Write summary header
        summary_lines = [
            "# Monthly Performance Report Summary",
            f"# Best Month: {summary['best_month']['month'] if summary['best_month'] else 'N/A'} ({summary['best_month']['return_pct'] if summary['best_month'] else 0}%)",
            f"# Worst Month: {summary['worst_month']['month'] if summary['worst_month'] else 'N/A'} ({summary['worst_month']['return_pct'] if summary['worst_month'] else 0}%)",
            f"# Current Streak: {summary['current_streak_type']} ({summary['current_streak_count']})",
            f"# Current Drawdown: {summary['current_drawdown']}%",
            f"# Peak Equity: {summary['peak_equity']}",
            f"# Current Equity: {summary['current_equity']}",
            f"# Total Trades: {summary['total_trades']}",
            "",
        ]
        csv_header = "\n".join(summary_lines).encode("utf-8")
        df.to_csv(buffer, index=False, encoding="utf-8")
        csv_data = csv_header + buffer.getvalue()
        content = csv_data
        media_type = "text/csv"
        file_ext = "csv"
    else:  # parquet
        df.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
        content = buffer.getvalue()
        media_type = "application/octet-stream"
        file_ext = "parquet"
    
    # Get metadata
    code_commit = get_git_commit_hash()
    dataset_hash = get_dataset_version_hash()
    params_hash = get_params_digest()
    
    metadata = {
        "commit_hash": code_commit,
        "dataset_hash": dataset_hash,
        "params_hash": params_hash,
    }
    
    # Calculate hashes
    md5_hash = calculate_file_md5(content)
    sha256_hash = calculate_file_sha256(content)
    
    # Create audit record
    with SessionLocal() as db:
        export_audit = ExportAuditORM(
            filters={"type": "monthly_report"},
            format=format,
            record_count=len(export_records),
            file_hash=sha256_hash,
            file_size_bytes=len(content),
            export_params={**metadata, "summary": summary},
        )
        db.add(export_audit)
        db.commit()
        logger.info(f"Monthly report export recorded: {export_audit.id}, {len(export_records)} records, format={format}")
    
    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"monthly_report_{timestamp}.{file_ext}"
    
    # Create response with headers
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-MD5": md5_hash,
            "X-Export-Metadata": str(metadata),
            "X-Export-Record-Count": str(len(export_records)),
            "X-Export-File-Hash": sha256_hash,
            "X-Export-Type": "monthly_report",
        },
    )


@router.get("/metrics")
async def get_daily_kpis(lookback_days: int = Query(30, ge=1, le=365, description="Number of days to look back")):
    """
    Get daily KPIs: win-rate 30d, avg RR, DD, HOLD count.
    
    Returns real-time KPI metrics calculated from recent recommendations.
    """
    try:
        kpis = kpis_service.calculate_daily_kpis(lookback_days=lookback_days)
        return {
            "status": "success",
            "kpis": kpis,
        }
    except Exception as e:
        logger.error(f"Failed to calculate daily KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/export")
async def export_daily_kpis(
    format: str = Query("json", regex="^(json|csv)$", description="Export format"),
    lookback_days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
):
    """
    Export daily KPI report in JSON or CSV format.
    
    Returns downloadable file with KPI metrics.
    """
    from fastapi.responses import Response
    
    try:
        report = kpis_service.generate_report(format=format, lookback_days=lookback_days)
        
        return Response(
            content=report["content"],
            media_type=report["media_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{report["filename"]}"',
            },
        )
    except Exception as e:
        logger.error(f"Failed to export daily KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

