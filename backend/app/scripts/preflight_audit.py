"""Standalone script to run preflight audit for CI/CD pipeline."""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import logger, setup_logging
from app.core.database import SessionLocal
from app.core.exceptions import RecommendationGenerationError
from app.db.crud import get_latest_recommendation
from app.services.preflight_audit_service import PreflightAuditService
from app.services.recommendation_service import RecommendationService


async def main():
    """Run preflight audit on latest recommendation or generate new one."""
    import argparse
    
    setup_logging()
    
    parser = argparse.ArgumentParser(description="Run preflight audit before publishing recommendations")
    parser.add_argument(
        "--recommendation-id",
        type=int,
        help="Recommendation ID to audit (if not provided, audits latest)",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate new recommendation and audit it (for CI/CD)",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        default=True,
        help="Exit with error code if audit fails (default: True)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for JSON report (optional)",
    )
    
    args = parser.parse_args()
    
    audit_service = PreflightAuditService()
    
    try:
        if args.generate:
            # Generate new recommendation and audit it
            logger.info("Generating new recommendation for audit...")
            recommendation_service = RecommendationService()
            
            try:
                # Generate recommendation (this will run audit internally)
                # If audit fails, this will raise RecommendationGenerationError
                result = await recommendation_service.generate_recommendation()
                
                logger.info("✅ Recommendation generated and audit passed")
                print("\n" + "=" * 80)
                print("PREFLIGHT AUDIT PASSED")
                print("=" * 80)
                print(f"Signal: {result.get('signal')}")
                print(f"Recommendation ID: {result.get('id', 'N/A')}")
                print("=" * 80)
                
                if args.output:
                    import json
                    with open(args.output, "w") as f:
                        json.dump(result, f, indent=2, default=str)
                    print(f"\nAudit report saved to: {args.output}")
                
                sys.exit(0)
            except RecommendationGenerationError as e:
                # Handle recommendation generation errors (including audit failures)
                logger.error(f"❌ Recommendation generation failed: {e.reason}")
                print("\n" + "=" * 80)
                print("RECOMMENDATION GENERATION FAILED")
                print("=" * 80)
                print(f"Status: {e.status}")
                print(f"Reason: {e.reason}")
                
                # If it's an audit failure, show failed checks
                if e.status == "audit_failed" and e.details.get("failed_checks"):
                    print("\nFailed Checks:")
                    for check in e.details.get("failed_checks", []):
                        print(f"  ❌ {check.get('name', 'unknown')}: {check.get('message', '')}")
                        if check.get("details"):
                            print(f"     Details: {check['details']}")
                
                if e.details:
                    print(f"\nDetails: {e.details}")
                print("=" * 80)
                
                if args.output:
                    import json
                    error_result = {
                        "status": e.status,
                        "reason": e.reason,
                        "details": e.details,
                    }
                    with open(args.output, "w") as f:
                        json.dump(error_result, f, indent=2, default=str)
                    print(f"\nError report saved to: {args.output}")
                
                if args.fail_on_error:
                    sys.exit(1)
                else:
                    sys.exit(0)
        else:
            # Audit existing recommendation
            with SessionLocal() as db:
                try:
                    if args.recommendation_id:
                        from sqlalchemy import select
                        from app.db.models import RecommendationORM
                        stmt = select(RecommendationORM).where(RecommendationORM.id == args.recommendation_id)
                        rec = db.execute(stmt).scalars().first()
                        if not rec:
                            logger.error(f"Recommendation {args.recommendation_id} not found")
                            sys.exit(1)
                    else:
                        rec = get_latest_recommendation(db)
                        if not rec:
                            logger.error("No recommendations found")
                            sys.exit(1)
                    
                    # Convert ORM to dict
                    recommendation_service = RecommendationService()
                    signal_payload = recommendation_service._from_orm(rec)
                    
                    # Run audit
                    audit_result = await audit_service.audit_recommendation(
                        signal_payload,
                        recommendation_id=rec.id,
                    )
                    
                    # Print results
                    print("\n" + "=" * 80)
                    print("PREFLIGHT AUDIT RESULTS")
                    print("=" * 80)
                    print(f"Recommendation ID: {rec.id}")
                    print(f"Signal: {rec.signal}")
                    print(f"Created: {rec.created_at}")
                    print(f"\nTotal Checks: {len(audit_result.checks)}")
                    print(f"Passed: {len(audit_result.get_passed_checks())}")
                    print(f"Failed: {len(audit_result.get_failed_checks())}")
                    print(f"\nOverall Status: {'✅ PASSED' if audit_result.all_checks_passed else '❌ FAILED'}")
                    print("\nCheck Details:")
                    for check in audit_result.checks:
                        status = "✅" if check.passed else "❌"
                        print(f"  {status} {check.name}: {check.message}")
                        if check.details and not check.passed:
                            print(f"     Details: {check.details}")
                    print("=" * 80)
                    
                    if args.output:
                        import json
                        with open(args.output, "w") as f:
                            json.dump(audit_result.to_dict(), f, indent=2, default=str)
                        print(f"\nAudit report saved to: {args.output}")
                    
                    if not audit_result.all_checks_passed and args.fail_on_error:
                        sys.exit(1)
                    
                finally:
                    db.close()
    
    except Exception as e:
        logger.error(f"Audit failed: {e}", exc_info=True)
        print(f"\n❌ Audit failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

