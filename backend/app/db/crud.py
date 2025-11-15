"""CRUD helpers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from sqlalchemy import asc

from app.db.models import (
    BacktestResultORM,
    CooldownEventORM,
    DataRunORM,
    KnowledgeArticleORM,
    LeverageAlertORM,
    RecommendationORM,
    RunLogORM,
    StrategyChampionORM,
    UserReadingORM,
    UserRiskStateORM,
)


def _normalise_date_from_market_timestamp(market_timestamp: str | None, fallback: datetime) -> str:
    """
    Try to derive the recommendation date from the market timestamp.
    
    If market_timestamp is None or invalid, uses fallback.
    """
    if not market_timestamp:
        return fallback.strftime("%Y-%m-%d")
    
    try:
        # Try parsing ISO format
        if "T" in market_timestamp:
            dt = datetime.fromisoformat(market_timestamp.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(market_timestamp, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return fallback.strftime("%Y-%m-%d")


def _apply_payload_to_recommendation(rec: RecommendationORM, data: dict[str, Any]) -> None:
    """Apply payload data to recommendation ORM object."""
    rec.confidence = data["confidence"]
    rec.current_price = data["current_price"]
    rec.market_timestamp = data.get("market_timestamp", rec.market_timestamp)
    rec.spot_source = data.get("spot_source", rec.spot_source)
    rec.indicators = data.get("indicators", rec.indicators or {})
    rec.factors = data.get("factors", rec.factors or {})
    rec.risk_metrics = data["risk_metrics"]
    rec.signal_breakdown = data.get("signal_breakdown", rec.signal_breakdown or {})
    rec.analysis = data["analysis"]
    
    # Reset exit fields if reopening
    rec.exit_reason = None
    rec.exit_price = None
    rec.exit_price_pct = None


def create_recommendation(db: Session, payload: dict) -> RecommendationORM:
    """Create recommendation with persisted analysis and metadata."""
    from app.quant.narrative import build_narrative
    from app.models.audit import RecommendationSnapshot
    from app.utils.hashing import get_git_commit_hash, calculate_params_hash
    from app.utils.dataset_metadata import get_dataset_version_hash, get_params_digest
    from app.utils.worm_storage import WormRepository
    from app.core.logging import logger

    now = datetime.utcnow()
    data: dict[str, Any] = payload.copy()

    if not data.get("analysis"):
        data["analysis"] = build_narrative(data)

    open_rec = get_open_recommendation(db)
    if open_rec and open_rec.closed_at is None:
        open_rec.confidence = data["confidence"]
        open_rec.current_price = data["current_price"]
        open_rec.market_timestamp = data.get("market_timestamp", open_rec.market_timestamp)
        open_rec.spot_source = data.get("spot_source", open_rec.spot_source)
        open_rec.indicators = data.get("indicators", open_rec.indicators or {})
        open_rec.factors = data.get("factors", open_rec.factors or {})
        open_rec.risk_metrics = data["risk_metrics"]
        open_rec.signal_breakdown = data.get("signal_breakdown", open_rec.signal_breakdown or {})
        open_rec.analysis = data["analysis"]
        open_rec.created_at = now

        # Update traceability fields if provided
        if data.get("code_commit"):
            open_rec.code_commit = data["code_commit"]
        if data.get("dataset_version"):
            open_rec.dataset_version = data["dataset_version"]
        if data.get("params_digest"):
            open_rec.params_digest = data["params_digest"]
        if data.get("snapshot_json"):
            open_rec.snapshot_json = data["snapshot_json"]

        db.add(open_rec)
        db.commit()
        db.refresh(open_rec)
        db.expunge(open_rec)
        return open_rec

    market_timestamp = data.get("market_timestamp")
    date_str = _normalise_date_from_market_timestamp(market_timestamp, now)

    # Get traceability metadata
    code_commit = get_git_commit_hash()
    dataset_version = get_dataset_version_hash()
    params_digest = get_params_digest()

    # Create snapshot for WORM storage
    snapshot_json: dict[str, Any] | None = None
    try:
        snapshot = RecommendationSnapshot(
            payload=data,
            code_commit=code_commit or "",
            dataset_hash=dataset_version or "",
            params_hash=params_digest or "",
        )
        worm_repo = WormRepository()
        worm_snapshot_info = worm_repo.write_snapshot(snapshot.payload, snapshot.__dict__)
        snapshot_json = {
            "worm_uuid": worm_snapshot_info["uuid"],
            "worm_path": worm_snapshot_info["path"],
            "worm_hash": worm_snapshot_info["hash"],
        }
        logger.info(f"Snapshot persisted to WORM: {worm_snapshot_info['uuid']}")
    except Exception as e:
        logger.error(f"Failed to persist snapshot to WORM: {e}", exc_info=True)
        # Continue without WORM snapshot (non-critical)

    record: dict[str, Any] = {
        "date": date_str,
        "signal": data["signal"],
        "entry_min": data["entry_range"]["min"],
        "entry_max": data["entry_range"]["max"],
        "entry_optimal": data["entry_range"]["optimal"],
        "stop_loss": data["stop_loss_take_profit"]["stop_loss"],
        "take_profit": data["stop_loss_take_profit"]["take_profit"],
        "stop_loss_pct": data["stop_loss_take_profit"]["stop_loss_pct"],
        "take_profit_pct": data["stop_loss_take_profit"]["take_profit_pct"],
        "confidence": data["confidence"],
        "current_price": data["current_price"],
        "market_timestamp": market_timestamp,
        "spot_source": data.get("spot_source", "1d"),
        "indicators": data.get("indicators", {}),
        "factors": data.get("factors", {}),
        "risk_metrics": data["risk_metrics"],
        "signal_breakdown": data.get("signal_breakdown", {}),
        "analysis": data["analysis"],
        "code_commit": code_commit,
        "dataset_version": dataset_version,
        "params_digest": params_digest,
        "snapshot_json": snapshot_json,
        "created_at": now,
        "status": "open" if data["signal"] in {"BUY", "SELL"} else "inactive",
        "opened_at": now if data["signal"] in {"BUY", "SELL"} else None,
        "closed_at": None,
        "exit_reason": None,
        "exit_price": None,
        "exit_price_pct": None,
    }

    dialect_name = db.bind.dialect.name
    if dialect_name == "sqlite":
        insert_stmt = sqlite_insert(RecommendationORM).values(**record)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["date", "market_timestamp"],
            set_=record,
        )
        result = db.execute(stmt)
        db.commit()
        pk = result.lastrowid
        if pk is None:
            stmt = select(RecommendationORM).where(RecommendationORM.date == date_str).where(RecommendationORM.market_timestamp == market_timestamp)
            rec = db.execute(stmt).scalars().first()
            if rec:
                pk = rec.id
            else:
                raise ValueError("Failed to retrieve created recommendation")
        rec = db.get(RecommendationORM, pk)
        if rec:
            db.refresh(rec)
            db.expunge(rec)
        return rec
    else:
        rec = RecommendationORM(**record)
        db.add(rec)
        try:
            db.commit()
            db.refresh(rec)
            db.expunge(rec)
            return rec
        except Exception:
            db.rollback()
            existing = db.execute(
                select(RecommendationORM).where(RecommendationORM.date == date_str).where(RecommendationORM.market_timestamp == market_timestamp)
            ).scalars().first()
            if existing:
                _apply_payload_to_recommendation(existing, data)
                db.commit()
                db.refresh(existing)
                db.expunge(existing)
                return existing
            raise


def get_open_recommendation(db: Session) -> RecommendationORM | None:
    """Get the currently open recommendation, if any."""
    stmt = select(RecommendationORM).where(RecommendationORM.status == "open").where(RecommendationORM.closed_at.is_(None)).order_by(desc(RecommendationORM.created_at)).limit(1)
    return db.execute(stmt).scalars().first()


def get_latest_recommendation(db: Session) -> RecommendationORM | None:
    """Get the most recent recommendation by creation date."""
    stmt = select(RecommendationORM).order_by(desc(RecommendationORM.created_at)).limit(1)
    return db.execute(stmt).scalars().first()


def close_recommendation(
    db: Session,
    rec: RecommendationORM,
    *,
    exit_price: float,
    exit_reason: str,
    exit_at: datetime,
    exit_pct: float | None = None,
    user_id: str | UUID | None = None,
) -> RecommendationORM:
    """Close a recommendation and update user risk state."""
    rec.status = "closed"
    rec.exit_price = exit_price
    rec.exit_reason = exit_reason
    rec.closed_at = exit_at
    rec.exit_price_pct = exit_pct

    db.add(rec)
    
    # Update user risk state if user_id provided
    if user_id:
        from app.db.crud import update_user_risk_state
        update_user_risk_state(db, user_id, closed_trade=rec)

    db.commit()
    db.refresh(rec)
    return rec


def log_run(db: Session, run_type: str, status: str, message: str = "", details: dict | None = None) -> RunLogORM:
    now = datetime.utcnow()
    formatted_message = message
    if details:
        try:
            details_json = json.dumps(details, default=str)
        except TypeError:
            details_json = str(details)
        formatted_message = f"{message} | details={details_json}" if message else details_json

    rl = RunLogORM(run_type=run_type, status=status, message=formatted_message, started_at=now, finished_at=now)
    db.add(rl)
    db.commit()
    db.refresh(rl)
    return rl


def get_last_run(db: Session, run_type: str | None = None) -> RunLogORM | None:
    stmt = select(RunLogORM)
    if run_type:
        stmt = stmt.where(RunLogORM.run_type == run_type)

    stmt = stmt.order_by(desc(RunLogORM.finished_at)).limit(1)
    return db.execute(stmt).scalars().first()


def save_backtest_result(db: Session, version: str, start_date: str, end_date: str, metrics: dict) -> BacktestResultORM:
    """Save versioned backtest result."""
    result = BacktestResultORM(
        version=version,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def get_backtest_results(db: Session, limit: int = 10) -> list[BacktestResultORM]:
    stmt = select(BacktestResultORM).order_by(desc(BacktestResultORM.created_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_recommendation_history(db: Session, limit: int = 10) -> list[RecommendationORM]:
    stmt = select(RecommendationORM).order_by(desc(RecommendationORM.created_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_current_champion(db: Session) -> StrategyChampionORM | None:
    stmt = select(StrategyChampionORM).where(StrategyChampionORM.is_active == True).order_by(desc(StrategyChampionORM.promoted_at)).limit(1)
    return db.execute(stmt).scalars().first()


def get_champion_history(db: Session, limit: int = 10) -> list[StrategyChampionORM]:

    stmt = select(StrategyChampionORM).order_by(desc(StrategyChampionORM.promoted_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())


def record_champion_promotion(db: Session, record: dict[str, Any]) -> StrategyChampionORM:
    """Persist champion promotion event with linkage to previous champion."""
    previous = get_current_champion(db)
    if previous:
        previous.is_active = False
        previous.replaced_at = datetime.utcnow()
        db.add(previous)

    champion = StrategyChampionORM(
        params_id=record.get("params_id", ""),
        params_version=record.get("params_version"),
        objective=record.get("objective", ""),
        target_metric=record.get("target_metric", ""),
        target_value=float(record.get("target_value", 0.0) or 0.0),
        score=float(record.get("score", 0.0) or 0.0),
        metrics=record.get("metrics", {}) or {},
        trained_on_regime=record.get("trained_on_regime"),
        statistical_test=record.get("statistical_test"),
        engine_args=record.get("engine_args", {}) or {},
        execution_overrides=record.get("execution_overrides", {}) or {},
        drawdown_limit=record.get("drawdown_limit"),
        start_date=record.get("start_date"),
        end_date=record.get("end_date"),
        previous_champion_id=previous.id if previous else None,
        previous_params_id=previous.params_id if previous else None,
        previous_score=previous.score if previous else None,
        previous_metrics=previous.metrics if previous else None,
    )
    db.add(champion)
    db.commit()
    db.refresh(champion)
    return champion


def calculate_production_drawdown(db: Session) -> dict[str, Any]:
    """Calculate current production drawdown from closed recommendations."""
    stmt = (
        select(RecommendationORM)
        .where(RecommendationORM.status == "closed")
        .where(RecommendationORM.exit_price.isnot(None))
        .order_by(RecommendationORM.closed_at)
    )
    trades = list(db.execute(stmt).scalars().all())

    if not trades:
        return {"max_drawdown_pct": 0.0, "current_drawdown_pct": 0.0, "peak_capital": 1.0, "current_capital": 1.0, "equity_curve": [1.0]}

    capital = 1.0
    peak = capital
    max_drawdown = 0.0
    equity_curve: list[float] = [capital]

    for rec in trades:
        entry = float(rec.entry_optimal)
        exit_price = float(rec.exit_price)
        if entry <= 0:
            continue
        if rec.signal == "BUY":
            return_pct = (exit_price - entry) / entry
        elif rec.signal == "SELL":
            return_pct = (entry - exit_price) / entry
        else:
            return_pct = 0.0
        capital *= 1 + return_pct
        equity_curve.append(round(capital, 6))
        peak = max(peak, capital)
        if peak > 0:
            dd = 1 - (capital / peak)
            max_drawdown = max(max_drawdown, dd)

    current_drawdown = 1 - (capital / peak) if peak > 0 else 0.0

    return {
        "max_drawdown_pct": round(max_drawdown * 100.0, 2),
        "current_drawdown_pct": round(current_drawdown * 100.0, 2),
        "peak_capital": round(peak, 6),
        "current_capital": round(capital, 6),
        "equity_curve": equity_curve,
    }


def create_data_run(
    db: Session,
    *,
    venue: str,
    symbol: str,
    interval: str,
    start_time: str,
    end_time: str,
    status: str,
    row_count: int,
    checksum: str | None = None,
    message: str | None = None,
) -> DataRunORM:
    record = DataRunORM(
        venue=venue,
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        status=status,
        row_count=row_count,
        checksum=checksum,
        message=message,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_user_risk_state(db: Session, user_id: str | UUID) -> UserRiskStateORM | None:
    """Get user risk state."""
    from uuid import UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    return db.get(UserRiskStateORM, user_uuid)


def create_or_update_user_risk_state(
    db: Session,
    user_id: str | UUID,
    *,
    current_drawdown_pct: float | None = None,
    longest_losing_streak: int | None = None,
    current_losing_streak: int | None = None,
    longest_winning_streak: int | None = None,
    current_winning_streak: int | None = None,
    trades_last_24h: int | None = None,
    avg_exposure_pct: float | None = None,
    cooldown_until: datetime | None = None,
    cooldown_reason: str | None = None,
    current_equity: float | None = None,
    total_notional: float | None = None,
    effective_leverage: float | None = None,
    leverage_hard_stop: bool | None = None,
    leverage_hard_stop_since: datetime | None = None,
) -> UserRiskStateORM:
    """Create or update user risk state."""
    from uuid import UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    
    state = db.get(UserRiskStateORM, user_uuid)
    now = datetime.utcnow()
    
    if state is None:
        state = UserRiskStateORM(
            user_id=user_uuid,
            current_drawdown_pct=current_drawdown_pct or 0.0,
            longest_losing_streak=longest_losing_streak or 0,
            current_losing_streak=current_losing_streak or 0,
            longest_winning_streak=longest_winning_streak or 0,
            current_winning_streak=current_winning_streak or 0,
            trades_last_24h=trades_last_24h or 0,
            avg_exposure_pct=avg_exposure_pct or 0.0,
            cooldown_until=cooldown_until,
            cooldown_reason=cooldown_reason,
            current_equity=current_equity or 0.0,
            total_notional=total_notional or 0.0,
            effective_leverage=effective_leverage or 0.0,
            leverage_hard_stop=leverage_hard_stop or False,
            leverage_hard_stop_since=leverage_hard_stop_since,
            last_updated=now,
        )
        db.add(state)
    else:
        if current_drawdown_pct is not None:
            state.current_drawdown_pct = current_drawdown_pct
        if longest_losing_streak is not None:
            state.longest_losing_streak = longest_losing_streak
        if current_losing_streak is not None:
            state.current_losing_streak = current_losing_streak
        if longest_winning_streak is not None:
            state.longest_winning_streak = longest_winning_streak
        if current_winning_streak is not None:
            state.current_winning_streak = current_winning_streak
        if trades_last_24h is not None:
            state.trades_last_24h = trades_last_24h
        if avg_exposure_pct is not None:
            state.avg_exposure_pct = avg_exposure_pct
        if cooldown_until is not None:
            state.cooldown_until = cooldown_until
        if cooldown_reason is not None:
            state.cooldown_reason = cooldown_reason
        if current_equity is not None:
            state.current_equity = current_equity
        if total_notional is not None:
            state.total_notional = total_notional
        if effective_leverage is not None:
            state.effective_leverage = effective_leverage
        if leverage_hard_stop is not None:
            state.leverage_hard_stop = leverage_hard_stop
        if leverage_hard_stop_since is not None:
            state.leverage_hard_stop_since = leverage_hard_stop_since
        state.last_updated = now
    
    db.commit()
    db.refresh(state)
    return state


def update_user_risk_state(
    db: Session,
    user_id: str | UUID,
    *,
    closed_trade: RecommendationORM | None = None,
) -> UserRiskStateORM:
    """
    Update user risk state based on closed trade.
    
    Calculates:
    - Current drawdown from equity curve
    - Current and longest losing/winning streaks
    - Trades in last 24 hours
    - Average exposure percentage
    - Leverage and equity metrics
    """
    from uuid import UUID
    from datetime import timedelta
    
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    
    # Get all closed trades for user (for now, we use all trades since there's no user_id in recommendations)
    # In a multi-user system, you'd filter by user_id
    stmt = (
        select(RecommendationORM)
        .where(RecommendationORM.status == "closed")
        .where(RecommendationORM.exit_price.isnot(None))
        .order_by(RecommendationORM.closed_at)
    )
    all_trades = list(db.execute(stmt).scalars().all())
    
    if not all_trades:
        # Initialize state with defaults
        return create_or_update_user_risk_state(
            db,
            user_uuid,
            current_drawdown_pct=0.0,
            longest_losing_streak=0,
            current_losing_streak=0,
            longest_winning_streak=0,
            current_winning_streak=0,
            trades_last_24h=0,
            avg_exposure_pct=0.0,
        )
    
    # Calculate equity curve and drawdown
    capital = 1.0
    peak = capital
    max_drawdown = 0.0
    equity_curve: list[float] = [capital]
    
    for rec in all_trades:
        entry = float(rec.entry_optimal)
        exit_price = float(rec.exit_price)
        if entry <= 0:
            continue
        if rec.signal == "BUY":
            return_pct = (exit_price - entry) / entry
        elif rec.signal == "SELL":
            return_pct = (entry - exit_price) / entry
        else:
            return_pct = 0.0
        capital *= 1 + return_pct
        equity_curve.append(round(capital, 6))
        peak = max(peak, capital)
        if peak > 0:
            dd = 1 - (capital / peak)
            max_drawdown = max(max_drawdown, dd)
    
    current_drawdown_pct = round(max_drawdown * 100.0, 2)
    
    # Calculate streaks (from most recent to oldest)
    sorted_trades = sorted(all_trades, key=lambda r: r.closed_at or r.created_at, reverse=True)
    
    # Determine if most recent trade is win or loss
    current_winning_streak = 0
    current_losing_streak = 0
    longest_winning_streak = 0
    longest_losing_streak = 0
    
    if sorted_trades:
        # Calculate current streak
        first_trade = sorted_trades[0]
        if first_trade.exit_price_pct is not None:
            is_first_win = first_trade.exit_price_pct > 0
        else:
            # Calculate from entry/exit
            entry = float(first_trade.entry_optimal)
            exit = float(first_trade.exit_price)
            if first_trade.signal == "BUY":
                is_first_win = exit > entry
            elif first_trade.signal == "SELL":
                is_first_win = exit < entry
            else:
                is_first_win = False
        
        if is_first_win:
            current_winning_streak = 1
            current_losing_streak = 0
        else:
            current_winning_streak = 0
            current_losing_streak = 1
        
        # Continue counting streak
        for trade in sorted_trades[1:]:
            if trade.exit_price_pct is not None:
                is_win = trade.exit_price_pct > 0
            else:
                entry = float(trade.entry_optimal)
                exit = float(trade.exit_price)
                if trade.signal == "BUY":
                    is_win = exit > entry
                elif trade.signal == "SELL":
                    is_win = exit < entry
                else:
                    is_win = False
            
            if is_first_win and is_win:
                current_winning_streak += 1
            elif not is_first_win and not is_win:
                current_losing_streak += 1
            else:
                break
        
        # Calculate longest streaks (all trades)
        current_win = 0
        current_loss = 0
        for trade in sorted_trades:
            if trade.exit_price_pct is not None:
                is_win = trade.exit_price_pct > 0
            else:
                entry = float(trade.entry_optimal)
                exit = float(trade.exit_price)
                if trade.signal == "BUY":
                    is_win = exit > entry
                elif trade.signal == "SELL":
                    is_win = exit < entry
                else:
                    is_win = False
            
            if is_win:
                current_win += 1
                current_loss = 0
                longest_winning_streak = max(longest_winning_streak, current_win)
            else:
                current_loss += 1
                current_win = 0
                longest_losing_streak = max(longest_losing_streak, current_loss)
    
    # Count trades in last 24 hours
    trades_last_24h = sum(
        1
        for rec in all_trades
        if rec.closed_at and rec.closed_at >= last_24h
    )
    
    # Calculate average exposure (simplified: average of entry prices relative to current equity)
    # For now, we'll use a placeholder calculation
    avg_exposure_pct = 1.0  # Default 1% exposure per trade
    
    # Calculate cooldown based on rules
    from app.core.config import settings
    cooldown_until = None
    cooldown_reason = None
    
    # Check if cooldown should be triggered
    if current_losing_streak >= settings.COOLDOWN_LOSING_STREAK_THRESHOLD:
        cooldown_until = now + timedelta(hours=settings.COOLDOWN_LOSING_STREAK_HOURS)
        cooldown_reason = f"Racha perdedora de {current_losing_streak} trades"
    elif trades_last_24h > settings.COOLDOWN_MAX_TRADES_24H:
        cooldown_until = now + timedelta(hours=settings.COOLDOWN_OVERTRADING_HOURS)
        cooldown_reason = f"Sobreoperación: {trades_last_24h} trades en 24 horas"
    
    # Get current state to check if cooldown is already active
    current_state = get_user_risk_state(db, user_uuid)
    was_on_cooldown = current_state and current_state.cooldown_until and current_state.cooldown_until > now.replace(tzinfo=current_state.cooldown_until.tzinfo) if current_state and current_state.cooldown_until else False
    
    # Only create cooldown event if this is a new cooldown trigger
    if cooldown_until and (not was_on_cooldown or (current_state and current_state.cooldown_reason != cooldown_reason)):
        # Record cooldown event in audit trail
        cooldown_event = CooldownEventORM(
            user_id=user_uuid,
            triggered_at=now,
            cooldown_until=cooldown_until,
            reason=cooldown_reason or "Unknown",
            losing_streak=current_losing_streak,
            trades_last_24h=trades_last_24h,
            current_drawdown_pct=current_drawdown_pct,
        )
        db.add(cooldown_event)
    
    # If cooldown expired, clear it
    if current_state and current_state.cooldown_until:
        cooldown_dt = current_state.cooldown_until
        now_tz = now.replace(tzinfo=cooldown_dt.tzinfo) if cooldown_dt.tzinfo else now
        if cooldown_dt <= now_tz:
            cooldown_until = None
            cooldown_reason = None
    
    # Calculate current equity from equity curve
    current_equity = capital  # From equity curve calculation above
    
    # Calculate total notional from open positions
    # For now, we estimate based on open recommendations (in a real system, this would come from a positions table)
    open_positions_stmt = (
        select(RecommendationORM)
        .where(RecommendationORM.status == "open")
        .where(RecommendationORM.entry_optimal.isnot(None))
    )
    open_positions = list(db.execute(open_positions_stmt).scalars().all())
    
    total_notional = 0.0
    for pos in open_positions:
        # Estimate notional: assume 1% of equity per position (this should come from actual position sizing)
        # Notional = entry_price * size, where size = (equity * risk_pct) / entry_price = equity * risk_pct
        # So notional = entry_price * (equity * risk_pct / entry_price) = equity * risk_pct
        position_notional = current_equity * 0.01  # 1% of equity per open position
        total_notional += position_notional
    
    # Calculate effective leverage
    effective_leverage = abs(total_notional) / current_equity if current_equity > 0 else 0.0
    
    # Check leverage thresholds and handle hard stop
    leverage_hard_stop = False
    leverage_hard_stop_since = None
    
    if effective_leverage > settings.LEVERAGE_HARD_STOP_THRESHOLD:
        # Check if we should activate hard stop (persistence check)
        if current_state and current_state.effective_leverage and current_state.effective_leverage > settings.LEVERAGE_HARD_STOP_THRESHOLD:
            # Already above threshold, check persistence
            if current_state.leverage_hard_stop_since:
                # Hard stop already active
                leverage_hard_stop = True
                leverage_hard_stop_since = current_state.leverage_hard_stop_since
            else:
                # First time above threshold, check if it persists for required duration
                # For now, activate immediately if persistence is not tracked (can be enhanced)
                leverage_hard_stop = True
                leverage_hard_stop_since = now
        else:
            # First time crossing threshold, start tracking
            leverage_hard_stop_since = now
            leverage_hard_stop = False  # Will activate after persistence period
    else:
        # Below threshold, clear hard stop if active
        if current_state and current_state.leverage_hard_stop:
            # Leverage dropped below threshold, clear hard stop
            leverage_hard_stop = False
            leverage_hard_stop_since = None
            
            # Record resolution of hard stop
            if current_state.leverage_hard_stop_since:
                from app.core.logging import logger
                logger.info(
                    f"Leverage hard stop resolved for user {user_uuid}: leverage={effective_leverage:.2f}× (below {settings.LEVERAGE_HARD_STOP_THRESHOLD}×)"
                )
                record_leverage_alert(
                    db,
                    user_uuid,
                    leverage=effective_leverage,
                    equity=current_equity,
                    notional=total_notional,
                    threshold=settings.LEVERAGE_HARD_STOP_THRESHOLD,
                    alert_type="hard_stop_resolved",
                )
    
    # Record leverage alerts if threshold crossed
    if current_state:
        previous_leverage = current_state.effective_leverage or 0.0
        from app.core.logging import logger
        if effective_leverage > settings.LEVERAGE_WARNING_THRESHOLD and previous_leverage <= settings.LEVERAGE_WARNING_THRESHOLD:
            # Crossed warning threshold
            logger.warning(
                f"Leverage warning threshold crossed for user {user_uuid}: leverage={effective_leverage:.2f}× (above {settings.LEVERAGE_WARNING_THRESHOLD}×)"
            )
            record_leverage_alert(
                db,
                user_uuid,
                leverage=effective_leverage,
                equity=current_equity,
                notional=total_notional,
                threshold=settings.LEVERAGE_WARNING_THRESHOLD,
                alert_type="warning",
            )
        if effective_leverage > settings.LEVERAGE_HARD_STOP_THRESHOLD and previous_leverage <= settings.LEVERAGE_HARD_STOP_THRESHOLD:
            # Crossed hard stop threshold
            logger.warning(
                f"Leverage hard stop threshold crossed for user {user_uuid}: leverage={effective_leverage:.2f}× (above {settings.LEVERAGE_HARD_STOP_THRESHOLD}×)"
            )
            record_leverage_alert(
                db,
                user_uuid,
                leverage=effective_leverage,
                equity=current_equity,
                notional=total_notional,
                threshold=settings.LEVERAGE_HARD_STOP_THRESHOLD,
                alert_type="hard_stop",
            )
    
    # Update state (including cooldown and leverage fields)
    state = create_or_update_user_risk_state(
        db,
        user_uuid,
        current_drawdown_pct=current_drawdown_pct,
        longest_losing_streak=longest_losing_streak,
        current_losing_streak=current_losing_streak,
        longest_winning_streak=longest_winning_streak,
        current_winning_streak=current_winning_streak,
        trades_last_24h=trades_last_24h,
        avg_exposure_pct=avg_exposure_pct,
        cooldown_until=cooldown_until,
        cooldown_reason=cooldown_reason,
        current_equity=current_equity,
        total_notional=total_notional,
        effective_leverage=effective_leverage,
        leverage_hard_stop=leverage_hard_stop,
        leverage_hard_stop_since=leverage_hard_stop_since,
    )
    
    db.commit()
    return state


def record_leverage_alert(
    db: Session,
    user_id: str | UUID,
    *,
    leverage: float,
    equity: float,
    notional: float,
    threshold: float,
    alert_type: str,
) -> LeverageAlertORM:
    """Record a leverage alert event in the audit trail."""
    from uuid import UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    
    alert = LeverageAlertORM(
        user_id=user_uuid,
        triggered_at=datetime.utcnow(),
        leverage=leverage,
        equity=equity,
        notional=notional,
        threshold=threshold,
        alert_type=alert_type,
        resolved_at=None if alert_type != "hard_stop_resolved" else datetime.utcnow(),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_leverage_alerts(
    db: Session,
    user_id: str | UUID,
    *,
    limit: int = 50,
    alert_type: str | None = None,
    unresolved_only: bool = False,
) -> list[LeverageAlertORM]:
    """Get leverage alert history for a user."""
    from uuid import UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    
    stmt = select(LeverageAlertORM).where(LeverageAlertORM.user_id == user_uuid)
    
    if alert_type:
        stmt = stmt.where(LeverageAlertORM.alert_type == alert_type)
    
    if unresolved_only:
        stmt = stmt.where(LeverageAlertORM.resolved_at.is_(None))
    
    stmt = stmt.order_by(desc(LeverageAlertORM.triggered_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())


# Knowledge Base CRUD functions

def get_contextual_articles(
    db: Session,
    user_id: str | UUID,
    *,
    trigger_type: str | None = None,  # cooldown|leverage|drawdown|overtrading
    category: str | None = None,
    limit: int = 5,
) -> list[KnowledgeArticleORM]:
    """
    Get contextual articles based on trigger conditions and user reading history.
    
    Priority:
    1. Articles that match trigger conditions and haven't been read recently
    2. Articles in relevant category
    3. Unread articles
    """
    from uuid import UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    
    stmt = select(KnowledgeArticleORM).where(KnowledgeArticleORM.is_active == True)
    
    if category:
        stmt = stmt.where(KnowledgeArticleORM.category == category)
    
    # Filter by trigger conditions if provided
    if trigger_type:
        stmt = stmt.where(
            KnowledgeArticleORM.trigger_conditions.isnot(None)
        ).where(
            KnowledgeArticleORM.trigger_conditions.contains({"trigger": trigger_type})
        )
    
    # Get user's reading history
    user_readings_stmt = select(UserReadingORM).where(UserReadingORM.user_id == user_uuid)
    user_readings = {r.article_id: r for r in db.execute(user_readings_stmt).scalars().all()}
    
    # Order by priority (highest first), then by created_at (newest first)
    stmt = stmt.order_by(desc(KnowledgeArticleORM.priority), desc(KnowledgeArticleORM.created_at))
    all_articles = list(db.execute(stmt).scalars().all())
    
    # Prioritize unread or recently read articles
    prioritized = []
    for article in all_articles:
        reading = user_readings.get(article.id)
        if not reading:
            # Never read - highest priority
            prioritized.append((article, 1000))
        else:
            # Read before - lower priority, but still include if it's relevant
            prioritized.append((article, 100 - article.priority))
    
    # Sort by priority score
    prioritized.sort(key=lambda x: x[1], reverse=True)
    
    # Return top N articles
    return [article for article, _ in prioritized[:limit]]


def get_article_by_slug(db: Session, slug: str) -> KnowledgeArticleORM | None:
    """Get article by slug."""
    stmt = select(KnowledgeArticleORM).where(KnowledgeArticleORM.slug == slug).where(KnowledgeArticleORM.is_active == True)
    return db.execute(stmt).scalars().first()


def get_articles_by_category(
    db: Session,
    category: str,
    *,
    limit: int = 50,
) -> list[KnowledgeArticleORM]:
    """Get articles by category."""
    stmt = (
        select(KnowledgeArticleORM)
        .where(KnowledgeArticleORM.category == category)
        .where(KnowledgeArticleORM.is_active == True)
        .order_by(desc(KnowledgeArticleORM.priority), desc(KnowledgeArticleORM.created_at))
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def record_user_reading(
    db: Session,
    user_id: str | UUID,
    article_id: int,
    *,
    pdf_downloaded: bool = False,
) -> UserReadingORM:
    """Record or update user reading of an article."""
    from uuid import UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    
    # Check if reading record exists
    stmt = select(UserReadingORM).where(
        UserReadingORM.user_id == user_uuid,
        UserReadingORM.article_id == article_id,
    )
    reading = db.execute(stmt).scalars().first()
    
    now = datetime.utcnow()
    
    if reading:
        # Update existing reading
        reading.last_read_at = now
        reading.read_count += 1
        if pdf_downloaded and not reading.pdf_downloaded:
            reading.pdf_downloaded = True
            reading.pdf_downloaded_at = now
    else:
        # Create new reading record
        reading = UserReadingORM(
            user_id=user_uuid,
            article_id=article_id,
            first_read_at=now,
            last_read_at=now,
            read_count=1,
            pdf_downloaded=pdf_downloaded,
            pdf_downloaded_at=now if pdf_downloaded else None,
        )
        db.add(reading)
    
    db.commit()
    db.refresh(reading)
    return reading


def get_user_reading_history(
    db: Session,
    user_id: str | UUID,
    *,
    limit: int = 50,
) -> list[UserReadingORM]:
    """Get user's reading history."""
    from uuid import UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    
    stmt = (
        select(UserReadingORM)
        .where(UserReadingORM.user_id == user_uuid)
        .order_by(desc(UserReadingORM.last_read_at))
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())
