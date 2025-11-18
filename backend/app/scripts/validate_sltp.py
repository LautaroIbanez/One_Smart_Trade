"""Script to validate SL/TP levels against historical orderbook data and generate reports."""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import logger
from app.services.sltp_validation_service import SLTPValidationService


async def main():
    """Run SL/TP validation and generate report."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate SL/TP levels against historical orderbook data")
    parser.add_argument(
        "--weeks",
        type=int,
        default=1,
        help="Number of weeks to look back (default: 1)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (ISO format: YYYY-MM-DD). If not provided, uses weeks back from today.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (ISO format: YYYY-MM-DD). If not provided, uses today.",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)",
    )
    parser.add_argument(
        "--venue",
        type=str,
        default="binance",
        help="Trading venue (default: binance)",
    )
    parser.add_argument(
        "--fulfillment-threshold",
        type=float,
        default=0.7,
        help="Minimum fulfillment rate threshold (default: 0.7)",
    )
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=7,
        help="Days to look ahead for validation (default: 7)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for JSON report (optional)",
    )
    
    args = parser.parse_args()
    
    # Determine date range
    if args.start_date and args.end_date:
        start_date = datetime.fromisoformat(args.start_date)
        end_date = datetime.fromisoformat(args.end_date)
    else:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=args.weeks)
    
    logger.info(f"Validating SL/TP levels from {start_date.date()} to {end_date.date()}")
    
    service = SLTPValidationService(venue=args.venue, symbol=args.symbol)
    
    try:
        report = await service.validate_period(
            start_date=start_date,
            end_date=end_date,
            lookahead_days=args.lookahead_days,
            fulfillment_threshold=args.fulfillment_threshold,
        )
        
        # Print summary
        print("\n" + "=" * 80)
        print("SL/TP VALIDATION REPORT")
        print("=" * 80)
        print(f"Period: {report.period_start.date()} to {report.period_end.date()}")
        print(f"Total Recommendations: {report.total_recommendations}")
        print(f"Recommendations Validated: {report.recommendations_validated}")
        print("\nFulfillment Metrics:")
        print(f"  SL Fulfillment Rate: {report.sl_fulfillment_rate:.2f}%")
        print(f"  TP Fulfillment Rate: {report.tp_fulfillment_rate:.2f}%")
        print(f"  Both Fulfilled: {report.both_fulfilled_rate:.2f}%")
        print(f"  Neither Fulfilled: {report.neither_fulfilled_rate:.2f}%")
        
        if report.avg_sl_distance_bps:
            print("\nDistance Metrics:")
            print(f"  Avg SL Distance: {report.avg_sl_distance_bps:.2f} bps")
            print(f"  Avg TP Distance: {report.avg_tp_distance_bps:.2f} bps" if report.avg_tp_distance_bps else "")
            print(f"  SL Range: {report.min_sl_distance_bps:.2f} - {report.max_sl_distance_bps:.2f} bps")
            print(f"  TP Range: {report.min_tp_distance_bps:.2f} - {report.max_tp_distance_bps:.2f} bps" if report.min_tp_distance_bps and report.max_tp_distance_bps else "")
        
        print("\nHeuristic Adjustment:")
        if report.heuristic_adjustment_needed:
            print(f"  ⚠️  ADJUSTMENT NEEDED: {report.adjustment_reason}")
            print(f"\n  Low Fulfillment Recommendations: {len(report.low_fulfillment_recommendations)}")
            if report.low_fulfillment_recommendations:
                print("\n  Recommendations with neither SL nor TP touched:")
                for rec in report.low_fulfillment_recommendations[:10]:  # Show first 10
                    print(f"    - ID {rec['recommendation_id']}: {rec['signal']} @ {rec['entry']:.2f}, "
                          f"SL={rec['stop_loss']:.2f}, TP={rec['take_profit']:.2f}")
        else:
            print("  ✓ No adjustment needed - fulfillment rates are acceptable")
        
        print("\n" + "=" * 80)
        
        # Save to file if requested
        if args.output:
            import json
            output_data = {
                "period": {
                    "start": report.period_start.isoformat(),
                    "end": report.period_end.isoformat(),
                },
                "summary": {
                    "total_recommendations": report.total_recommendations,
                    "recommendations_validated": report.recommendations_validated,
                },
                "fulfillment_metrics": {
                    "sl_fulfillment_rate_pct": round(report.sl_fulfillment_rate, 2),
                    "tp_fulfillment_rate_pct": round(report.tp_fulfillment_rate, 2),
                    "both_fulfilled_rate_pct": round(report.both_fulfilled_rate, 2),
                    "neither_fulfilled_rate_pct": round(report.neither_fulfilled_rate, 2),
                },
                "distance_metrics": {
                    "avg_sl_distance_bps": round(report.avg_sl_distance_bps, 2) if report.avg_sl_distance_bps else None,
                    "avg_tp_distance_bps": round(report.avg_tp_distance_bps, 2) if report.avg_tp_distance_bps else None,
                    "min_sl_distance_bps": round(report.min_sl_distance_bps, 2) if report.min_sl_distance_bps else None,
                    "max_sl_distance_bps": round(report.max_sl_distance_bps, 2) if report.max_sl_distance_bps else None,
                    "min_tp_distance_bps": round(report.min_tp_distance_bps, 2) if report.min_tp_distance_bps else None,
                    "max_tp_distance_bps": round(report.max_tp_distance_bps, 2) if report.max_tp_distance_bps else None,
                },
                "low_fulfillment_recommendations": report.low_fulfillment_recommendations,
                "heuristic_adjustment": {
                    "needed": report.heuristic_adjustment_needed,
                    "reason": report.adjustment_reason,
                },
            }
            
            with open(args.output, "w") as f:
                json.dump(output_data, f, indent=2)
            
            print(f"\nReport saved to: {args.output}")
        
        # Exit with error code if adjustment needed
        if report.heuristic_adjustment_needed:
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        print(f"\n❌ Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

