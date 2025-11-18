#!/usr/bin/env python3
"""Preview position sizing calculation for manual testing and QA."""
import argparse
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.backtesting.unified_risk_manager import UnifiedRiskManager
from app.backtesting.risk import RuinSimulator
from app.services.exposure_ledger_service import ExposureLedgerService
from app.core.config import settings


def preview_sizing(
    user: str,
    entry: float,
    stop: float,
    capital: float,
    drawdown: float = 0.0,
    win_rate: float | None = None,
    payoff: float | None = None,
    beta: float = 1.0,
    existing_positions: list[dict] | None = None,
) -> dict:
    """
    Preview position sizing calculation.
    
    Args:
        user: User identifier
        entry: Entry price
        stop: Stop loss price
        capital: Current equity
        drawdown: Current drawdown percentage
        win_rate: Win rate (0.0 to 1.0)
        payoff: Payoff ratio (avg_win / avg_loss)
        beta: Beta value for exposure calculation
        existing_positions: List of existing positions (optional)
        
    Returns:
        Dict with sizing results and validation checks
    """
    # Initialize risk manager
    risk_manager = UnifiedRiskManager(
        base_capital=capital,
        risk_budget_pct=1.0,
        max_drawdown_pct=50.0,
    )
    
    # Set current state
    peak_equity = capital / (1 - drawdown / 100.0) if drawdown > 0 else capital
    risk_manager.current_equity = capital
    risk_manager.peak_equity = peak_equity
    risk_manager.current_drawdown_pct = drawdown
    
    # Calculate base sizing
    sizing_result = risk_manager.size_trade(
        entry=entry,
        stop=stop,
        user_equity=capital,
        user_drawdown=drawdown,
        win_rate=win_rate,
        payoff_ratio=payoff,
    )
    
    notional = sizing_result.get("notional", 0.0)
    units = sizing_result.get("units", 0.0)
    
    # Calculate exposure profile
    exposure_multiplier = risk_manager.exposure_profile()
    
    # Calculate ruin risk if metrics available
    risk_of_ruin = 0.0
    ruin_adjustment = None
    if win_rate is not None and payoff is not None:
        ruin_sim = RuinSimulator()
        risk_of_ruin = ruin_sim.estimate(
            win_rate=win_rate,
            payoff_ratio=payoff,
            horizon=250,
            threshold=0.5,
        )
        
        # Check ruin adjustment
        RUIN_THRESHOLD = settings.RISK_OF_RUIN_MAX  # 5%
        if risk_of_ruin > RUIN_THRESHOLD:
            excess_ruin = risk_of_ruin - RUIN_THRESHOLD
            ruin_multiplier = max(0.1, 1.0 - (excess_ruin / RUIN_THRESHOLD))
            if ruin_multiplier < 0.2:
                ruin_adjustment = {"blocked": True, "multiplier": ruin_multiplier}
            else:
                adjusted_units = units * ruin_multiplier
                adjusted_notional = adjusted_units * entry
                ruin_adjustment = {
                    "blocked": False,
                    "multiplier": ruin_multiplier,
                    "original_units": units,
                    "adjusted_units": adjusted_units,
                    "original_notional": notional,
                    "adjusted_notional": adjusted_notional,
                }
    
    # Validate exposure limits
    exposure_ledger = ExposureLedgerService()
    existing_positions = existing_positions or []
    
    # Calculate current exposure
    current_notional = sum(pos.get("notional", 0.0) for pos in existing_positions)
    current_beta_adjusted = sum(
        pos.get("notional", 0.0) * abs(pos.get("beta", 1.0)) for pos in existing_positions
    )
    
    # Projected exposure with new position
    projected_notional = current_notional + notional
    projected_beta_adjusted = current_beta_adjusted + (notional * abs(beta))
    exposure_multiplier_projected = projected_beta_adjusted / capital if capital > 0 else 0.0
    exposure_limit = settings.EXPOSURE_LIMIT_MULTIPLIER  # 2.0
    
    # Check concentration
    symbol = "BTCUSDT"  # Default
    existing_symbol_notional = sum(
        pos.get("notional", 0.0)
        for pos in existing_positions
        if pos.get("symbol") == symbol
    )
    total_symbol_notional = existing_symbol_notional + notional
    concentration_limit = capital * 0.30  # 30%
    
    # Build validation results
    checks = {
        "equity_synced": capital > 0,
        "drawdown_ok": drawdown <= 50.0,  # Dynamic limit
        "ruin_risk_ok": risk_of_ruin <= 0.05,
        "exposure_ok": exposure_multiplier_projected <= exposure_limit,
        "concentration_ok": total_symbol_notional <= concentration_limit,
    }
    
    all_passed = all(checks.values())
    
    # Build result
    result = {
        "user": user,
        "sizing": {
            "units": units,
            "notional": notional,
            "entry": entry,
            "stop": stop,
            "risk_per_unit": abs(entry - stop),
            "risk_amount": units * abs(entry - stop),
            "risk_percentage": (units * abs(entry - stop) / capital * 100.0) if capital > 0 else 0.0,
        },
        "exposure": {
            "current_multiplier": current_beta_adjusted / capital if capital > 0 else 0.0,
            "projected_multiplier": exposure_multiplier_projected,
            "limit_multiplier": exposure_limit,
            "current_beta_adjusted": current_beta_adjusted,
            "projected_beta_adjusted": projected_beta_adjusted,
        },
        "concentration": {
            "current_symbol_notional": existing_symbol_notional,
            "projected_symbol_notional": total_symbol_notional,
            "limit_notional": concentration_limit,
            "symbol": symbol,
        },
        "risk_metrics": {
            "drawdown_pct": drawdown,
            "exposure_multiplier": exposure_multiplier,
            "risk_of_ruin": risk_of_ruin,
            "ruin_threshold": settings.RISK_OF_RUIN_MAX,
        },
        "validation_checks": checks,
        "all_checks_passed": all_passed,
    }
    
    if ruin_adjustment:
        result["ruin_adjustment"] = ruin_adjustment
        if ruin_adjustment.get("blocked"):
            result["sizing"]["status"] = "blocked"
            result["sizing"]["message"] = f"Riesgo de ruina ({risk_of_ruin:.2%}) demasiado alto"
        else:
            result["sizing"]["units"] = ruin_adjustment["adjusted_units"]
            result["sizing"]["notional"] = ruin_adjustment["adjusted_notional"]
    
    if not checks["exposure_ok"]:
        result["sizing"]["status"] = "blocked"
        result["sizing"]["message"] = (
            f"Exposición proyectada {exposure_multiplier_projected:.2f}× > límite {exposure_limit:.2f}×"
        )
    
    if not checks["concentration_ok"]:
        result["sizing"]["status"] = "blocked"
        result["sizing"]["message"] = (
            f"Concentración {total_symbol_notional:.2f} > límite {concentration_limit:.2f} (30%)"
        )
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Preview position sizing calculation")
    parser.add_argument("--user", required=True, help="User identifier")
    parser.add_argument("--entry", type=float, required=True, help="Entry price")
    parser.add_argument("--stop", type=float, required=True, help="Stop loss price")
    parser.add_argument("--capital", type=float, required=True, help="Current equity")
    parser.add_argument("--drawdown", type=float, default=0.0, help="Current drawdown percentage")
    parser.add_argument("--win-rate", type=float, help="Win rate (0.0 to 1.0)")
    parser.add_argument("--payoff", type=float, help="Payoff ratio (avg_win / avg_loss)")
    parser.add_argument("--beta", type=float, default=1.0, help="Beta value (default: 1.0)")
    parser.add_argument("--positions", type=str, help="JSON file with existing positions")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    # Load existing positions if provided
    existing_positions = None
    if args.positions:
        with open(args.positions, "r") as f:
            existing_positions = json.load(f)
    
    # Calculate sizing
    result = preview_sizing(
        user=args.user,
        entry=args.entry,
        stop=args.stop,
        capital=args.capital,
        drawdown=args.drawdown,
        win_rate=args.win_rate,
        payoff=args.payoff,
        beta=args.beta,
        existing_positions=existing_positions,
    )
    
    # Output
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"Position Sizing Preview for User: {result['user']}")
        print(f"{'='*60}\n")
        
        print("SIZING:")
        print(f"  Units: {result['sizing']['units']:.8f}")
        print(f"  Notional: ${result['sizing']['notional']:,.2f}")
        print(f"  Risk Amount: ${result['sizing']['risk_amount']:,.2f}")
        print(f"  Risk Percentage: {result['sizing']['risk_percentage']:.2f}%")
        if result['sizing'].get('status'):
            print(f"  Status: {result['sizing']['status']}")
            print(f"  Message: {result['sizing'].get('message', 'N/A')}")
        
        print("\nEXPOSURE:")
        print(f"  Current: {result['exposure']['current_multiplier']:.2f}×")
        print(f"  Projected: {result['exposure']['projected_multiplier']:.2f}×")
        print(f"  Limit: {result['exposure']['limit_multiplier']:.2f}×")
        
        print("\nCONCENTRATION:")
        print(f"  Current {result['concentration']['symbol']}: ${result['concentration']['current_symbol_notional']:,.2f}")
        print(f"  Projected: ${result['concentration']['projected_symbol_notional']:,.2f}")
        print(f"  Limit: ${result['concentration']['limit_notional']:,.2f} (30%)")
        
        print("\nRISK METRICS:")
        print(f"  Drawdown: {result['risk_metrics']['drawdown_pct']:.2f}%")
        print(f"  Exposure Multiplier: {result['risk_metrics']['exposure_multiplier']:.2%}")
        print(f"  Risk of Ruin: {result['risk_metrics']['risk_of_ruin']:.2%}")
        
        if result.get('ruin_adjustment'):
            adj = result['ruin_adjustment']
            if adj.get('blocked'):
                print(f"  ⚠️  RUIN RISK: BLOCKED (multiplier: {adj['multiplier']:.2%})")
            else:
                print(f"  ⚠️  RUIN ADJUSTMENT: {adj['multiplier']:.2%} multiplier applied")
        
        print("\nVALIDATION CHECKS:")
        for check, passed in result['validation_checks'].items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check.replace('_', ' ').title()}: {passed}")
        
        print(f"\n{'='*60}")
        if result['all_checks_passed']:
            print("✅ ALL CHECKS PASSED - Signal can be published")
        else:
            print("❌ SOME CHECKS FAILED - Signal should be blocked or adjusted")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

