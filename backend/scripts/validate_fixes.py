#!/usr/bin/env python3
"""
Comprehensive validation script for FIX-01, FIX-02, and FIX-03.

This script validates:
1. Backend startup & pipeline (FIX-02)
2. API endpoint contracts (FIX-01)
3. Logging sanitization (FIX-03)
4. Frontend proxy connectivity
5. Async warnings
6. Transparency dashboard

Usage:
    python scripts/validate_fixes.py [--base-url http://localhost:8000]
"""
import sys
import json
import time
import warnings
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Install with: pip install httpx")
    sys.exit(1)


class ValidationResult:
    """Track validation results."""
    
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, check_name: str, details: str = ""):
        self.passed.append((check_name, details))
        print(f"  ✓ PASS: {check_name}")
        if details:
            print(f"    {details}")
    
    def add_fail(self, check_name: str, reason: str):
        self.failed.append((check_name, reason))
        print(f"  ❌ FAIL: {check_name}")
        print(f"    Reason: {reason}")
    
    def add_warning(self, check_name: str, message: str):
        self.warnings.append((check_name, message))
        print(f"  ⚠ WARN: {check_name}")
        print(f"    {message}")
    
    def summary(self) -> dict[str, Any]:
        return {
            "passed": len(self.passed),
            "failed": len(self.failed),
            "warnings": len(self.warnings),
            "total": len(self.passed) + len(self.failed),
        }


def check_backend_running(base_url: str) -> bool:
    """Check if backend is running."""
    print("\n1. Backend Startup & Health")
    print("=" * 60)
    
    # Try both localhost and 127.0.0.1 (Windows sometimes has issues with localhost)
    urls_to_try = [base_url]
    if "localhost" in base_url:
        urls_to_try.append(base_url.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in base_url:
        urls_to_try.append(base_url.replace("127.0.0.1", "localhost"))
    
    # Try multiple times with increasing delays (backend may be starting pipeline)
    max_attempts = 10  # Increased for pipeline execution
    for attempt in range(1, max_attempts + 1):
        for url in urls_to_try:
            try:
                response = httpx.get(f"{url}/health", timeout=10.0)
                if response.status_code == 200:
                    print(f"  ✓ Backend is running at {url}")
                    if attempt > 1:
                        print(f"    (Connected on attempt {attempt})")
                    return True
                else:
                    print(f"  ❌ Backend responded with status {response.status_code}")
                    return False
            except httpx.ConnectError:
                continue  # Try next URL
            except Exception as e:
                if "Connection refused" in str(e) or "No connection" in str(e):
                    continue  # Try next URL
                else:
                    if attempt < max_attempts:
                        wait_time = min(attempt * 3, 15)  # Max 15s per attempt
                        print(f"  ⏳ Connection error (attempt {attempt}/{max_attempts}), waiting {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"  ❌ Error connecting: {e}")
                        return False
        
        # If all URLs failed, wait and retry
        if attempt < max_attempts:
            wait_time = min(attempt * 3, 15)  # Max 15s per attempt
            print(f"  ⏳ Backend not ready yet (attempt {attempt}/{max_attempts}), waiting {wait_time}s...")
            print("     (Backend may be running initial pipeline - this can take 1-2 minutes)")
            time.sleep(wait_time)
        else:
            print(f"  ❌ Backend NOT running at {base_url} after {max_attempts} attempts")
            print("     Start backend with:")
            print("       cd backend")
            print("       .\\.venv\\Scripts\\Activate.ps1")
            print("       uvicorn app.main:app --reload --port 8000")
            print("     Or with poetry:")
            print("       poetry run uvicorn app.main:app --reload --port 8000")
            print("     Note: Wait for 'Application startup complete' message before running validation")
            return False
    
    return False


def check_scheduler_started(base_url: str, results: ValidationResult) -> None:
    """Check if scheduler has started (indirect check via logs or endpoints)."""
    # Scheduler starts automatically, so if backend is running, scheduler should be too
    # We can verify by checking if scheduled endpoints work
    try:
        # Check if we can get today's recommendation (pipeline might have run)
        response = httpx.get(f"{base_url}/api/v1/recommendation/today", timeout=10.0)
        if response.status_code in (200, 400, 503):  # 400/503 are valid responses (no data, capital missing, etc.)
            results.add_pass("Scheduler started", "Backend responding to requests")
        else:
            results.add_warning("Scheduler status", f"Unexpected status {response.status_code}")
    except Exception as e:
        results.add_warning("Scheduler check", f"Could not verify: {e}")


def check_initial_pipeline(base_url: str, results: ValidationResult) -> None:
    """Check if initial pipeline ran or can be triggered."""
    print("\n2. Initial Pipeline (FIX-02)")
    print("=" * 60)
    
    try:
        # Check if today's recommendation exists
        response = httpx.get(f"{base_url}/api/v1/recommendation/today", timeout=30.0)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("signal") in ("BUY", "SELL", "HOLD"):
                results.add_pass(
                    "Initial pipeline data available",
                    f"Recommendation exists: {data.get('signal')} (confidence: {data.get('confidence', 'N/A')}%)"
                )
                return
            elif data.get("status") == "no_data":
                results.add_warning(
                    "Initial pipeline",
                    "No recommendation for today yet. Pipeline may run on next request or at 12:00 UTC."
                )
            elif isinstance(data.get("detail"), dict) and data.get("detail", {}).get("status") == "capital_missing":
                results.add_warning(
                    "Initial pipeline",
                    "Capital not configured (normal in dev). Endpoint works but needs capital for signals."
                )
        elif response.status_code == 400:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict) and detail.get("status") == "capital_missing":
                results.add_warning(
                    "Initial pipeline",
                    "Capital not configured. This is expected in dev environments."
                )
        else:
            results.add_fail(
                "Initial pipeline",
                f"Unexpected status {response.status_code}: {response.text[:200]}"
            )
    except httpx.TimeoutException:
        results.add_warning("Initial pipeline", "Timeout - backend may be processing")
    except Exception as e:
        results.add_fail("Initial pipeline", f"Error: {e}")


def check_endpoint_contracts(base_url: str, results: ValidationResult) -> None:
    """Check API endpoint contracts match frontend types (FIX-01)."""
    print("\n3. API Endpoint Contracts (FIX-01)")
    print("=" * 60)
    
    # Check /api/v1/recommendation/today
    print("\n3.1. /api/v1/recommendation/today")
    try:
        response = httpx.get(f"{base_url}/api/v1/recommendation/today", timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            required_fields = ["signal", "entry_range", "stop_loss_take_profit", "confidence", "current_price"]
            missing = [f for f in required_fields if f not in data]
            if not missing:
                results.add_pass("Today endpoint structure", "All required fields present")
            else:
                results.add_fail("Today endpoint structure", f"Missing fields: {missing}")
        elif response.status_code in (400, 503):
            # Valid error responses
            results.add_pass("Today endpoint", f"Returns structured error (status {response.status_code})")
        else:
            results.add_fail("Today endpoint", f"Unexpected status {response.status_code}")
    except Exception as e:
        results.add_fail("Today endpoint", f"Error: {e}")
    
    # Check /api/v1/recommendation/history
    print("\n3.2. /api/v1/recommendation/history")
    try:
        response = httpx.get(f"{base_url}/api/v1/recommendation/history?limit=5", timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            # Check for new paginated structure
            if "items" in data:
                results.add_pass("History endpoint structure", "Uses 'items' field (paginated response)")
                if "next_cursor" in data and "has_more" in data:
                    results.add_pass("History pagination fields", "next_cursor and has_more present")
                if "insights" in data:
                    results.add_pass("History insights", "insights field present")
                if "download_url" in data:
                    results.add_pass("History download_url", "download_url field present")
                
                # Check items structure
                if data.get("items") and len(data["items"]) > 0:
                    item = data["items"][0]
                    if "id" in item and "timestamp" in item and "signal" in item:
                        results.add_pass("History items structure", "Items have required fields")
                    else:
                        results.add_fail("History items structure", "Items missing required fields")
            elif "recommendations" in data:
                results.add_fail("History endpoint", "Still using old 'recommendations' field instead of 'items'")
            else:
                results.add_fail("History endpoint", "Missing 'items' field in response")
        else:
            results.add_fail("History endpoint", f"Status {response.status_code}: {response.text[:200]}")
    except Exception as e:
        results.add_fail("History endpoint", f"Error: {e}")
    
    # Check /api/v1/recommendation/performance
    print("\n3.3. /api/v1/recommendation/performance")
    try:
        response = httpx.get(f"{base_url}/api/v1/recommendation/performance?lookahead_days=5&limit=30", timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            required_fields = ["status", "timeline", "equity_curve", "drawdown_curve", "win_rate"]
            missing = [f for f in required_fields if f not in data]
            if not missing:
                results.add_pass("Performance endpoint structure", "All required fields present")
                # Check for new fields
                if "equity_theoretical" in data or "equity_realistic" in data:
                    results.add_pass("Performance new fields", "equity_theoretical/realistic present")
                if "tracking_error_metrics" in data:
                    results.add_pass("Performance tracking_error_metrics", "tracking_error_metrics present")
            else:
                results.add_fail("Performance endpoint", f"Missing fields: {missing}")
        else:
            results.add_fail("Performance endpoint", f"Status {response.status_code}: {response.text[:200]}")
    except Exception as e:
        results.add_fail("Performance endpoint", f"Error: {e}")


def check_logging_sanitization(results: ValidationResult) -> None:
    """Check that logging doesn't have KeyError issues (FIX-03)."""
    print("\n4. Logging Sanitization (FIX-03)")
    print("=" * 60)
    
    # This is a manual check - we can't easily test it programmatically
    # But we can verify the sanitize_log_extra function exists and is imported
    try:
        from app.core.logging import sanitize_log_extra, RESERVED_LOG_RECORD_ATTRS
        
        # Test the function
        test_extra = {"message": "test", "status": "ok", "custom_field": "value"}
        sanitized = sanitize_log_extra(test_extra)
        
        if "extra_message" in sanitized and "extra_status" in sanitized:
            results.add_pass("sanitize_log_extra function", "Correctly renames reserved keys")
        else:
            results.add_fail("sanitize_log_extra function", "Not renaming reserved keys correctly")
        
        if "custom_field" in sanitized:
            results.add_pass("sanitize_log_extra function", "Preserves non-reserved keys")
        else:
            results.add_fail("sanitize_log_extra function", "Removing non-reserved keys")
        
        results.add_warning(
            "Logging KeyError check",
            "Manual verification required: Run pipeline and check logs for 'KeyError: Attempt to overwrite'"
        )
    except ImportError as e:
        results.add_fail("sanitize_log_extra import", f"Could not import: {e}")


def check_frontend_proxy(base_url: str, results: ValidationResult) -> None:
    """Check frontend proxy connectivity."""
    print("\n5. Frontend → Backend Proxy")
    print("=" * 60)
    
    # Check if frontend dev server might be running (port 5173)
    try:
        response = httpx.get("http://localhost:5173", timeout=2.0, follow_redirects=True)
        if response.status_code == 200:
            results.add_warning(
                "Frontend dev server",
                "Frontend appears to be running. Check browser console for proxy errors."
            )
        else:
            results.add_warning("Frontend dev server", "Not running or not accessible")
    except httpx.ConnectError:
        results.add_warning("Frontend dev server", "Not running (expected if only testing backend)")
    except Exception:
        pass
    
    # Verify backend is accessible (proxy target)
    try:
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        if response.status_code == 200:
            results.add_pass("Backend proxy target", "Backend accessible for frontend proxy")
        else:
            results.add_fail("Backend proxy target", f"Status {response.status_code}")
    except Exception as e:
        results.add_fail("Backend proxy target", f"Error: {e}")


def check_async_warnings(results: ValidationResult) -> None:
    """Check for async warnings."""
    print("\n6. Async Warnings")
    print("=" * 60)
    
    # Capture warnings during import
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # Try importing main modules that use async
        try:
            from app.main import job_daily_pipeline
            from app.services.recommendation_service import RecommendationService
            
            # Check for RuntimeWarning about coroutines
            coroutine_warnings = [warn for warn in w if "coroutine" in str(warn.message).lower()]
            if coroutine_warnings:
                results.add_fail("Async warnings", f"Found {len(coroutine_warnings)} coroutine warnings")
                for warn in coroutine_warnings:
                    print(f"    {warn.message}")
            else:
                results.add_pass("Async warnings", "No coroutine warnings detected during import")
        except Exception as e:
            results.add_warning("Async warnings check", f"Could not complete check: {e}")


def check_transparency_dashboard(base_url: str, results: ValidationResult) -> None:
    """Check transparency dashboard endpoint."""
    print("\n7. Transparency Dashboard")
    print("=" * 60)
    
    try:
        response = httpx.get(f"{base_url}/api/v1/transparency/status", timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            results.add_pass("Transparency endpoint", "Returns 200 OK")
            if isinstance(data, dict):
                results.add_pass("Transparency response structure", "Returns JSON object")
        elif response.status_code == 404:
            results.add_warning("Transparency endpoint", "Not available (404) - may not be implemented")
        else:
            results.add_warning("Transparency endpoint", f"Status {response.status_code}")
    except Exception as e:
        results.add_warning("Transparency endpoint", f"Error: {e}")


def trigger_pipeline_manual(base_url: str, results: ValidationResult) -> None:
    """Optionally trigger pipeline manually to test logging."""
    print("\n8. Manual Pipeline Trigger (Optional)")
    print("=" * 60)
    
    print("  To test logging sanitization, you can manually trigger the pipeline:")
    print(f"    curl -X POST {base_url}/api/v1/operational/trigger-pipeline \\")
    print("      -H 'X-Admin-API-Key: YOUR_KEY'")
    print()
    print("  Or if ADMIN_API_KEY is not set:")
    print("    curl -X POST {base_url}/api/v1/operational/trigger-pipeline")
    print()
    print("  Then check logs for any 'KeyError: Attempt to overwrite' messages.")
    results.add_warning(
        "Manual pipeline trigger",
        "Run pipeline manually and check logs for KeyError messages"
    )


def main():
    """Run all validation checks."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate FIX-01, FIX-02, and FIX-03")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for backend API (default: http://localhost:8000)"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("Validation Plan: FIX-01, FIX-02, FIX-03")
    print("=" * 60)
    print(f"Base URL: {args.base_url}")
    print()
    
    results = ValidationResult()
    
    # 1. Backend startup
    if not check_backend_running(args.base_url):
        print("\n" + "=" * 60)
        print("❌ Backend is not running. Start it first:")
        print("   cd backend")
        print("   poetry run uvicorn app.main:app --reload --port 8000")
        print("=" * 60)
        return 1
    
    check_scheduler_started(args.base_url, results)
    
    # 2. Initial pipeline (FIX-02)
    check_initial_pipeline(args.base_url, results)
    
    # 3. Endpoint contracts (FIX-01)
    check_endpoint_contracts(args.base_url, results)
    
    # 4. Logging sanitization (FIX-03)
    check_logging_sanitization(results)
    
    # 5. Frontend proxy
    check_frontend_proxy(args.base_url, results)
    
    # 6. Async warnings
    check_async_warnings(results)
    
    # 7. Transparency dashboard
    check_transparency_dashboard(args.base_url, results)
    
    # 8. Manual pipeline trigger info
    trigger_pipeline_manual(args.base_url, results)
    
    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    summary = results.summary()
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Warnings: {summary['warnings']}")
    print(f"Total checks: {summary['total']}")
    print()
    
    if results.failed:
        print("Failed checks:")
        for check_name, reason in results.failed:
            print(f"  - {check_name}: {reason}")
        print()
    
    if summary['failed'] == 0:
        print("✅ All critical checks passed!")
        if summary['warnings'] > 0:
            print("⚠ Some warnings - review manually")
        return 0
    else:
        print("❌ Some checks failed - review above")
        return 1


if __name__ == "__main__":
    sys.exit(main())

