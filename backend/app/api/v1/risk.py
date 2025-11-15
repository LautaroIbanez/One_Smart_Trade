"""Risk management endpoints."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.backtesting.risk_sizing import (
    AdaptiveRiskSizer,
    DrawdownController,
    RiskManager,
    RiskSizer,
)
from app.backtesting.volatility_targeting import CombinedSizer, KellySizer, VolatilityTargeting

router = APIRouter()


class SizingRequest(BaseModel):
    """Request model for position sizing calculation."""

    capital: float = Field(gt=0, description="Available capital in base currency")
    entry: float = Field(gt=0, description="Entry price")
    stop: float = Field(gt=0, description="Stop loss price")
    volatility: float | None = Field(
        None,
        ge=0,
        le=10.0,
        description="Expected volatility (ATR or std dev) for volatility targeting adjustment (optional)",
    )
    risk_budget_pct: float = Field(
        1.0,
        ge=0.1,
        le=10.0,
        description="Risk budget as percentage of capital (default: 1.0%)",
    )
    use_drawdown_adjustment: bool = Field(
        False,
        description="Apply drawdown-based risk reduction (requires current_drawdown_pct)",
    )
    current_drawdown_pct: float = Field(
        0.0,
        ge=0.0,
        le=100.0,
        description="Current drawdown percentage (required if use_drawdown_adjustment=True)",
    )
    regime_probabilities: dict[str, float] | None = Field(
        None,
        description="Regime probabilities for adaptive sizing (calm, balanced, stress)",
    )
    use_kelly: bool = Field(
        False,
        description="Use Kelly criterion sizing (requires win_rate and payoff_ratio)",
    )
    win_rate: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Win rate for Kelly sizing (0.0 to 1.0)",
    )
    payoff_ratio: float | None = Field(
        None,
        gt=0,
        description="Payoff ratio for Kelly sizing (avg_win / avg_loss)",
    )
    kelly_cap: float = Field(
        0.5,
        ge=0.1,
        le=1.0,
        description="Kelly truncation cap (fraction of full Kelly, default: 0.5)",
    )


class SizingResponse(BaseModel):
    """Response model for position sizing calculation."""

    units: float = Field(description="Recommended position size in units")
    notional: float = Field(description="Notional value (units * entry price)")
    risk_amount: float = Field(description="Maximum risk amount in base currency")
    risk_percentage: float = Field(description="Risk as percentage of capital")
    risk_per_unit: float = Field(description="Risk per unit (|entry - stop|)")
    explanation: str = Field(description="Explanation of sizing calculation")
    parameters: dict[str, Any] = Field(description="Parameters used in calculation")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")


@router.post("/sizing", response_model=SizingResponse)
async def calculate_sizing(request: SizingRequest) -> SizingResponse:
    """
    Calculate recommended position size based on risk parameters.
    
    Uses risk-based position sizing to determine the optimal position size
    such that the maximum loss (difference between entry and stop loss)
    equals a fixed percentage of capital.
    
    Supports:
    - Fixed risk percentage sizing
    - Drawdown-based risk adjustment
    - Volatility-based adjustment
    - Regime-based adaptive sizing
    """
    try:
        # Validate entry and stop prices
        if request.stop >= request.entry and request.stop > 0:
            raise HTTPException(
                status_code=400,
                detail="Stop loss must be below entry price for long positions (or above for short)",
            )
        
        # Calculate risk per unit
        risk_per_unit = abs(request.entry - request.stop)
        if risk_per_unit == 0:
            raise HTTPException(
                status_code=400,
                detail="Entry and stop prices must be different",
            )
        
        # Validate Kelly parameters if use_kelly is True
        if request.use_kelly:
            if request.win_rate is None or request.payoff_ratio is None:
                raise HTTPException(
                    status_code=400,
                    detail="win_rate and payoff_ratio are required when use_kelly=True",
                )
        
        # Determine which risk sizing method to use
        if request.regime_probabilities and request.use_drawdown_adjustment:
            # Adaptive risk sizer with drawdown adjustment
            adaptive_sizer = AdaptiveRiskSizer(
                base_risk_pct=request.risk_budget_pct / 100.0,
                calm_multiplier=1.5,
                balanced_multiplier=1.0,
                stress_multiplier=0.5,
            )
            
            if request.current_drawdown_pct > 0:
                dd_controller = DrawdownController(max_drawdown_pct=50.0)
                risk_manager = RiskManager(
                    risk_sizer=adaptive_sizer,
                    drawdown_controller=dd_controller,
                )
                
                # Calculate size with drawdown adjustment
                units = risk_manager.compute_size(
                    equity=request.capital,
                    entry=request.entry,
                    stop=request.stop,
                    current_dd_pct=request.current_drawdown_pct,
                    regime_probabilities=request.regime_probabilities,
                )
                effective_risk = risk_manager.get_effective_risk_budget(
                    base_risk_budget_pct=request.risk_budget_pct / 100.0,
                    current_dd_pct=request.current_drawdown_pct,
                    regime_probabilities=request.regime_probabilities,
                ) * 100.0
                
                sizing_method = "adaptive_with_drawdown"
                explanation = (
                    f"Position size calculated using adaptive risk sizing with drawdown adjustment. "
                    f"Base risk: {request.risk_budget_pct:.2f}%, "
                    f"Effective risk after adjustments: {effective_risk:.2f}%. "
                    f"Regime probabilities: {request.regime_probabilities}, "
                    f"Current drawdown: {request.current_drawdown_pct:.2f}%"
                )
            else:
                # Adaptive risk sizer without drawdown
                units = adaptive_sizer.compute_size(
                    equity=request.capital,
                    entry=request.entry,
                    stop=request.stop,
                    regime_probabilities=request.regime_probabilities,
                )
                effective_risk = request.risk_budget_pct
                sizing_method = "adaptive"
                explanation = (
                    f"Position size calculated using adaptive risk sizing based on regime probabilities. "
                    f"Base risk: {request.risk_budget_pct:.2f}%, "
                    f"Regime probabilities: {request.regime_probabilities}"
                )
        elif request.use_drawdown_adjustment:
            # Standard risk sizer with drawdown adjustment
            risk_sizer = RiskSizer(risk_budget_pct=request.risk_budget_pct / 100.0)
            dd_controller = DrawdownController(max_drawdown_pct=50.0)
            risk_manager = RiskManager(
                risk_sizer=risk_sizer,
                drawdown_controller=dd_controller,
            )
            
            units = risk_manager.compute_size(
                equity=request.capital,
                entry=request.entry,
                stop=request.stop,
                current_dd_pct=request.current_drawdown_pct,
            )
            effective_risk = risk_manager.get_effective_risk_budget(
                base_risk_budget_pct=request.risk_budget_pct / 100.0,
                current_dd_pct=request.current_drawdown_pct,
            ) * 100.0
            
            sizing_method = "fixed_with_drawdown"
            explanation = (
                f"Position size calculated with drawdown-based risk adjustment. "
                f"Base risk: {request.risk_budget_pct:.2f}%, "
                f"Effective risk: {effective_risk:.2f}% (current drawdown: {request.current_drawdown_pct:.2f}%)"
            )
        else:
            # Standard risk-based sizing or Kelly + risk combined
            if request.use_kelly and request.win_rate and request.payoff_ratio:
                # Use CombinedSizer with risk + Kelly + volatility
                risk_sizer = RiskSizer(risk_budget_pct=request.risk_budget_pct / 100.0)
                kelly_sizer = KellySizer(kelly_cap=request.kelly_cap)
                
                # Convert volatility from percentage to decimal if provided
                realized_vol = None
                if request.volatility is not None:
                    realized_vol = request.volatility / 100.0  # Convert % to decimal
                
                volatility_targeting = VolatilityTargeting(
                    target_volatility=0.10,  # 10% annualized
                )
                
                drawdown_controller = None
                if request.use_drawdown_adjustment:
                    drawdown_controller = DrawdownController(max_drawdown_pct=50.0)
                
                combined_sizer = CombinedSizer(
                    risk_sizer=risk_sizer,
                    kelly_sizer=kelly_sizer,
                    volatility_targeting=volatility_targeting,
                )
                
                result_dict = combined_sizer.compute_size(
                    capital=request.capital,
                    entry=request.entry,
                    stop=request.stop,
                    win_rate=request.win_rate,
                    payoff_ratio=request.payoff_ratio,
                    realized_vol=realized_vol,
                    current_dd_pct=request.current_drawdown_pct,
                    drawdown_controller=drawdown_controller,
                    regime_probabilities=request.regime_probabilities,
                )
                
                units = result_dict["units"]
                effective_risk = request.risk_budget_pct
                sizing_method = result_dict["sizing_method"]
                
                # Get Kelly info for explanation
                kelly_info = kelly_sizer.get_kelly_fraction(
                    request.win_rate,
                    request.payoff_ratio,
                    request.kelly_cap,
                )
                
                explanation = (
                    f"Position size calculated using combined sizing (risk-based + Kelly truncated). "
                    f"Risk budget: {request.risk_budget_pct:.2f}%, "
                    f"Kelly full: {kelly_info['full_kelly']:.4f}, "
                    f"Kelly truncated ({request.kelly_cap:.0%}): {kelly_info['truncated_kelly']:.4f}, "
                    f"Applied: {kelly_info['applied_fraction']:.4f}. "
                )
                
                if realized_vol:
                    vol_scale = result_dict["adjustments"].get("vol_scale", 1.0)
                    explanation += f"Volatility targeting: {vol_scale:.2f}x (realized: {request.volatility:.2f}%, target: 10%). "
                
                if request.current_drawdown_pct > 0:
                    dd_mult = result_dict["adjustments"].get("dd_multiplier", 1.0)
                    explanation += f"Drawdown adjustment: {dd_mult:.2f}x (DD: {request.current_drawdown_pct:.2f}%). "
            else:
                # Standard risk-based sizing
                risk_sizer = RiskSizer(risk_budget_pct=request.risk_budget_pct / 100.0)
                units = risk_sizer.compute_size(
                    equity=request.capital,
                    entry=request.entry,
                    stop=request.stop,
                )
                effective_risk = request.risk_budget_pct
                sizing_method = "fixed"
                explanation = (
                    f"Position size calculated using fixed risk percentage ({request.risk_budget_pct:.2f}% of capital). "
                    f"Maximum risk per trade: {request.capital * (request.risk_budget_pct / 100.0):.2f} "
                    f"(risk per unit: {risk_per_unit:.2f})"
                )
        
        # Apply volatility targeting adjustment if provided and not already applied
        warnings = []
        if request.volatility is not None and request.volatility > 0 and not request.use_kelly:
            # Volatility targeting: adjust size inversely proportional to volatility
            # Convert percentage to decimal for VolatilityTargeting
            realized_vol = request.volatility / 100.0
            volatility_targeting = VolatilityTargeting(target_volatility=0.10)
            
            vol_scale = volatility_targeting.get_scale_factor(realized_vol)
            units = volatility_targeting.adjust_units(units, realized_vol)
            sizing_method += "_vol_adjusted"
            
            explanation += f" Volatility targeting applied: {vol_scale:.2f}x (realized: {request.volatility:.2f}%, target: 10%)."
        
        # Calculate metrics
        notional = units * request.entry
        risk_amount = units * risk_per_unit
        risk_percentage_actual = (risk_amount / request.capital * 100.0) if request.capital > 0 else 0.0
        
        # Validation warnings
        if risk_percentage_actual > effective_risk * 1.1:
            warnings.append(
                f"Actual risk ({risk_percentage_actual:.2f}%) exceeds target ({effective_risk:.2f}%) by more than 10%"
            )
        
        if units < 0.001:
            warnings.append("Position size is very small (< 0.001 units), consider adjusting stop loss")
        
        if notional > request.capital:
            warnings.append(
                f"Notional value ({notional:.2f}) exceeds available capital ({request.capital:.2f})"
            )
        
        # Prepare parameters
        parameters = {
            "capital": request.capital,
            "entry": request.entry,
            "stop": request.stop,
            "risk_budget_pct": effective_risk,
            "risk_per_unit": risk_per_unit,
            "sizing_method": sizing_method,
        }
        
        if request.volatility is not None:
            parameters["volatility"] = request.volatility
        if request.current_drawdown_pct > 0:
            parameters["current_drawdown_pct"] = request.current_drawdown_pct
        if request.use_kelly and request.win_rate and request.payoff_ratio:
            kelly_sizer = KellySizer(kelly_cap=request.kelly_cap)
            kelly_info = kelly_sizer.get_kelly_fraction(
                request.win_rate,
                request.payoff_ratio,
                request.kelly_cap,
            )
            parameters["kelly"] = kelly_info
            parameters["win_rate"] = request.win_rate
            parameters["payoff_ratio"] = request.payoff_ratio
            parameters["kelly_cap"] = request.kelly_cap
        
        return SizingResponse(
            units=round(units, 8),
            notional=round(notional, 2),
            risk_amount=round(risk_amount, 2),
            risk_percentage=round(risk_percentage_actual, 2),
            risk_per_unit=round(risk_per_unit, 2),
            explanation=explanation,
            parameters=parameters,
            warnings=warnings,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating position size: {str(e)}")


@router.get("/sizing", response_model=SizingResponse)
async def get_sizing(
    capital: float = Query(gt=0, description="Available capital in base currency"),
    entry: float = Query(gt=0, description="Entry price"),
    stop: float = Query(gt=0, description="Stop loss price"),
    volatility: float | None = Query(
        None,
        ge=0,
        le=10.0,
        description="Expected volatility (ATR or std dev) for volatility targeting adjustment (optional)",
    ),
    risk_budget_pct: float = Query(
        1.0,
        ge=0.1,
        le=10.0,
        description="Risk budget as percentage of capital (default: 1.0%)",
    ),
    current_drawdown_pct: float = Query(
        0.0,
        ge=0.0,
        le=100.0,
        description="Current drawdown percentage for risk adjustment (optional)",
    ),
) -> SizingResponse:
    """
    Calculate recommended position size (GET version for simple requests).
    
    Convenience endpoint using query parameters instead of request body.
    """
    request = SizingRequest(
        capital=capital,
        entry=entry,
        stop=stop,
        volatility=volatility,
        risk_budget_pct=risk_budget_pct,
        use_drawdown_adjustment=current_drawdown_pct > 0,
        current_drawdown_pct=current_drawdown_pct,
        regime_probabilities=None,
        use_kelly=use_kelly,
        win_rate=win_rate,
        payoff_ratio=payoff_ratio,
        kelly_cap=kelly_cap,
    )
    
    return await calculate_sizing(request)


@router.get("/sizing/from-recommendation", response_model=SizingResponse)
async def get_sizing_from_recommendation(
    capital: float = Query(gt=0, description="Available capital in base currency"),
    risk_budget_pct: float = Query(
        1.0,
        ge=0.1,
        le=10.0,
        description="Risk budget as percentage of capital (default: 1.0%)",
    ),
    current_drawdown_pct: float = Query(
        0.0,
        ge=0.0,
        le=100.0,
        description="Current drawdown percentage for risk adjustment (optional)",
    ),
) -> SizingResponse:
    """
    Calculate position size using current recommendation's entry/stop levels.
    
    Automatically uses today's recommendation entry and stop loss prices,
    and current market volatility (ATR) if available.
    """
    from app.services.recommendation_service import RecommendationService
    from app.data.curation import DataCuration
    
    try:
        # Get current recommendation
        service = RecommendationService()
        recommendation = await service.get_today_recommendation()
        
        if not recommendation:
            raise HTTPException(
                status_code=404,
                detail="No recommendation available. Please provide entry/stop manually or generate a recommendation first.",
            )
        
        entry_range = recommendation.get("entry_range", {})
        stop_loss_tp = recommendation.get("stop_loss_take_profit", {})
        
        entry = entry_range.get("optimal")
        stop = stop_loss_tp.get("stop_loss")
        
        if not entry or not stop:
            raise HTTPException(
                status_code=400,
                detail="Current recommendation missing entry or stop loss information",
            )
        
        # Try to get volatility from curated data
        volatility = None
        try:
            curation = DataCuration()
            df_1d = curation.get_latest_curated("1d")
            if df_1d is not None and not df_1d.empty:
                # Try to get ATR or volatility
                if "atr_14" in df_1d.columns:
                    atr = float(df_1d["atr_14"].iloc[-1])
                    current_price = float(df_1d["close"].iloc[-1])
                    if current_price > 0:
                        volatility = (atr / current_price) * 100  # Convert to percentage
                elif "volatility_30" in df_1d.columns:
                    volatility = float(df_1d["volatility_30"].iloc[-1])
        except Exception:
            # Volatility is optional, continue without it
            pass
        
        # Get regime probabilities if available
        regime_probabilities = None
        if "regime_probabilities" in recommendation:
            regime_probabilities = recommendation["regime_probabilities"]
        
        request = SizingRequest(
            capital=capital,
            entry=entry,
            stop=stop,
            volatility=volatility,
            risk_budget_pct=risk_budget_pct,
            use_drawdown_adjustment=current_drawdown_pct > 0,
            current_drawdown_pct=current_drawdown_pct,
            regime_probabilities=regime_probabilities,
        )
        
        response = await calculate_sizing(request)
        
        # Add recommendation context to explanation
        response.explanation = (
            f"Position size based on today's recommendation. "
            f"Entry: {entry:.2f}, Stop: {stop:.2f}. "
            + response.explanation
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating position size from recommendation: {str(e)}")

