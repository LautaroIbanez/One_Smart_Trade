"""Tests for TransparencyService."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from app.services.transparency_service import (
    TransparencyService,
    VerificationStatus,
    HashVerification,
    TrackingErrorRolling,
    DrawdownDivergence,
    TransparencySemaphore,
)
from app.db.models import RecommendationORM, ExportAuditORM


@pytest.fixture
def transparency_service():
    return TransparencyService()


@pytest.fixture
def mock_recommendation():
    rec = Mock(spec=RecommendationORM)
    rec.id = 1
    rec.created_at = datetime.utcnow()
    rec.code_commit = "abc123def456"
    rec.dataset_version = "sha256:dataset123"
    rec.params_digest = "sha256:params123"
    rec.status = "closed"
    rec.exit_price = 45000.0
    rec.exit_reason = "TP"
    rec.entry_optimal = 42000.0
    rec.take_profit = 45000.0
    rec.stop_loss = 40000.0
    rec.exit_price_pct = 7.14
    rec.signal = "BUY"
    return rec


@pytest.fixture
def mock_export_audit():
    audit = Mock(spec=ExportAuditORM)
    audit.id = 1
    audit.timestamp = datetime.utcnow()
    audit.export_params = {
        "commit_hash": "abc123def456",
        "dataset_hash": "sha256:dataset123",
        "params_hash": "sha256:params123",
    }
    return audit


class TestHashVerification:
    """Test hash verification functionality."""

    @patch("app.services.transparency_service.get_git_commit_hash")
    @patch("app.services.transparency_service.get_dataset_version_hash")
    @patch("app.services.transparency_service.get_params_digest")
    @patch("app.services.transparency_service.SessionLocal")
    def test_verify_hashes_pass(
        self,
        mock_session_local,
        mock_get_params,
        mock_get_dataset,
        mock_get_commit,
        transparency_service,
        mock_recommendation,
    ):
        """Test hash verification when all hashes match."""
        mock_get_commit.return_value = "abc123def456"
        mock_get_dataset.return_value = "sha256:dataset123"
        mock_get_params.return_value = "sha256:params123"

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.first.return_value = mock_recommendation

        verifications = transparency_service.verify_hashes()

        assert len(verifications) == 3
        assert all(v.status == VerificationStatus.PASS for v in verifications)

    @patch("app.services.transparency_service.get_git_commit_hash")
    @patch("app.services.transparency_service.get_dataset_version_hash")
    @patch("app.services.transparency_service.get_params_digest")
    @patch("app.services.transparency_service.SessionLocal")
    def test_verify_hashes_warn_on_change(
        self,
        mock_session_local,
        mock_get_params,
        mock_get_dataset,
        mock_get_commit,
        transparency_service,
        mock_recommendation,
    ):
        """Test hash verification when hashes have changed."""
        mock_get_commit.return_value = "new123commit"
        mock_get_dataset.return_value = "sha256:newdataset"
        mock_get_params.return_value = "sha256:newparams"

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.first.return_value = mock_recommendation

        verifications = transparency_service.verify_hashes()

        assert len(verifications) == 3
        assert all(v.status == VerificationStatus.WARN for v in verifications)

    @patch("app.services.transparency_service.SessionLocal")
    def test_verify_hashes_no_recommendations(
        self,
        mock_session_local,
        transparency_service,
    ):
        """Test hash verification when no recommendations exist."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.first.return_value = None

        verifications = transparency_service.verify_hashes()

        assert len(verifications) == 1
        assert verifications[0].status == VerificationStatus.UNKNOWN


class TestTrackingErrorRolling:
    """Test rolling tracking error calculation."""

    @pytest.mark.asyncio
    @patch("app.services.transparency_service.SessionLocal")
    async def test_get_tracking_error_rolling_insufficient_data(
        self,
        mock_session_local,
        transparency_service,
    ):
        """Test tracking error with insufficient data."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        result = await transparency_service.get_tracking_error_rolling(30)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.transparency_service.SessionLocal")
    async def test_get_tracking_error_rolling_sufficient_data(
        self,
        mock_session_local,
        transparency_service,
        mock_recommendation,
    ):
        """Test tracking error with sufficient data."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            mock_recommendation,
            mock_recommendation,
        ]

        result = await transparency_service.get_tracking_error_rolling(30)

        assert result is not None
        assert isinstance(result, TrackingErrorRolling)
        assert result.period_days == 30


class TestDrawdownDivergence:
    """Test drawdown divergence calculation."""

    @pytest.mark.asyncio
    async def test_get_drawdown_divergence(
        self,
        transparency_service,
    ):
        """Test drawdown divergence calculation."""
        mock_service = MagicMock()
        mock_service.get_summary = AsyncMock(
            return_value={
                "tracking_error_metrics": {
                    "theoretical_max_drawdown": -0.10,
                    "realistic_max_drawdown": -0.12,
                }
            }
        )
        transparency_service.performance_service = mock_service

        result = await transparency_service.get_drawdown_divergence()

        assert result is not None
        assert isinstance(result, DrawdownDivergence)
        assert result.theoretical_max_dd == -0.10
        assert result.realistic_max_dd == -0.12
        assert result.divergence_pct > 0

    @pytest.mark.asyncio
    async def test_get_drawdown_divergence_no_data(
        self,
        transparency_service,
    ):
        """Test drawdown divergence when no data available."""
        mock_service = MagicMock()
        mock_service.get_summary = AsyncMock(
            return_value={
                "tracking_error_metrics": {
                    "theoretical_max_drawdown": 0.0,
                }
            }
        )
        transparency_service.performance_service = mock_service

        result = await transparency_service.get_drawdown_divergence()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_drawdown_divergence_error_with_fallback_stale(
        self,
        transparency_service,
    ):
        """Test drawdown divergence returns stale object when error status with fallback but no tracking_error_metrics."""
        mock_service = MagicMock()
        mock_service.get_summary = AsyncMock(
            return_value={
                "status": "error",
                "error_type": "DATA_STALE",
                "message": "Data freshness validation failed",
                "fallback_summary": {
                    "status": "success",
                    "source": "db_cache",
                    "metrics": {
                        "cagr": 15.5,
                        "sharpe": 1.2,
                    },
                    "period": {
                        "start": "2023-01-01T00:00:00",
                        "end": "2024-01-01T00:00:00",
                    },
                    # No tracking_error_metrics in fallback
                },
            }
        )
        transparency_service.performance_service = mock_service

        result = await transparency_service.get_drawdown_divergence()

        # Should return a stale object instead of None
        assert result is not None
        assert isinstance(result, DrawdownDivergence)
        assert result.metadata is not None
        assert result.metadata.get("is_stale") is True
        assert result.metadata.get("reason") == "tracking_error_metrics_missing"
        assert result.metadata.get("summary_status") == "error"
        assert result.metadata.get("has_fallback") is True
        # Values should be neutral (0.0)
        assert result.theoretical_max_dd == 0.0
        assert result.realistic_max_dd == 0.0
        assert result.divergence_pct == 0.0

    @pytest.mark.asyncio
    async def test_get_drawdown_divergence_error_with_fallback_has_metrics(
        self,
        transparency_service,
    ):
        """Test drawdown divergence uses fallback tracking_error_metrics when available."""
        mock_service = MagicMock()
        mock_service.get_summary = AsyncMock(
            return_value={
                "status": "error",
                "error_type": "DATA_STALE",
                "message": "Data freshness validation failed",
                "fallback_summary": {
                    "status": "success",
                    "source": "db_cache",
                    "tracking_error_metrics": {
                        "theoretical_max_drawdown": -0.10,
                        "realistic_max_drawdown": -0.12,
                    },
                },
            }
        )
        transparency_service.performance_service = mock_service

        result = await transparency_service.get_drawdown_divergence()

        # Should calculate divergence from fallback metrics
        assert result is not None
        assert isinstance(result, DrawdownDivergence)
        assert result.theoretical_max_dd == -0.10
        assert result.realistic_max_dd == -0.12
        assert result.divergence_pct > 0
        # Should not be marked as stale if metrics are available
        assert result.metadata is None or result.metadata.get("is_stale") is not True


class TestSemaphore:
    """Test semaphore status calculation."""

    @pytest.mark.asyncio
    @patch("app.services.transparency_service.TransparencyService.verify_hashes")
    @patch("app.services.transparency_service.TransparencyService.get_tracking_error_rolling", new_callable=AsyncMock)
    @patch(
        "app.services.transparency_service.TransparencyService.get_drawdown_divergence",
        new_callable=AsyncMock,
    )
    @patch("app.services.transparency_service.TransparencyService.get_audit_status")
    async def test_get_semaphore_pass(
        self,
        mock_audit,
        mock_drawdown,
        mock_tracking,
        mock_hashes,
        transparency_service,
    ):
        """Test semaphore when all checks pass."""
        mock_hashes.return_value = [
            HashVerification(
                hash_type="code_commit",
                current_hash="abc123",
                stored_hash="abc123",
                status=VerificationStatus.PASS,
                message="OK",
                timestamp=datetime.utcnow().isoformat(),
            )
        ]
        mock_tracking.return_value = TrackingErrorRolling(
            period_days=30,
            mean_deviation=0.01,
            max_divergence=0.02,
            correlation=0.95,
            rmse=0.01,
            annualized_tracking_error=2.0,
            timestamp=datetime.utcnow().isoformat(),
        )
        mock_drawdown.return_value = DrawdownDivergence(
            theoretical_max_dd=-0.10,
            realistic_max_dd=-0.11,
            divergence_pct=10.0,
            timestamp=datetime.utcnow().isoformat(),
        )
        mock_audit.return_value = {"total_exports": 10}

        semaphore = await transparency_service.get_semaphore()

        assert semaphore.overall_status == VerificationStatus.PASS

    @pytest.mark.asyncio
    @patch("app.services.transparency_service.TransparencyService.verify_hashes")
    @patch("app.services.transparency_service.TransparencyService.get_tracking_error_rolling", new_callable=AsyncMock)
    @patch(
        "app.services.transparency_service.TransparencyService.get_drawdown_divergence",
        new_callable=AsyncMock,
    )
    @patch("app.services.transparency_service.TransparencyService.get_audit_status")
    async def test_get_semaphore_fail_high_tracking_error(
        self,
        mock_audit,
        mock_drawdown,
        mock_tracking,
        mock_hashes,
        transparency_service,
    ):
        """Test semaphore when tracking error is too high."""
        mock_hashes.return_value = [
            HashVerification(
                hash_type="code_commit",
                current_hash="abc123",
                stored_hash="abc123",
                status=VerificationStatus.PASS,
                message="OK",
                timestamp=datetime.utcnow().isoformat(),
            )
        ]
        mock_tracking.return_value = TrackingErrorRolling(
            period_days=30,
            mean_deviation=0.05,
            max_divergence=0.10,
            correlation=0.85,
            rmse=0.05,
            annualized_tracking_error=15.0,  # Exceeds 10% threshold
            timestamp=datetime.utcnow().isoformat(),
        )
        mock_drawdown.return_value = None
        mock_audit.return_value = {"total_exports": 10}

        semaphore = await transparency_service.get_semaphore()

        assert semaphore.overall_status == VerificationStatus.FAIL
        assert semaphore.tracking_error_status == VerificationStatus.FAIL


class TestRunChecks:
    """Test run_checks method."""

    @pytest.mark.asyncio
    @patch(
        "app.services.transparency_service.TransparencyService.get_semaphore",
        new_callable=AsyncMock,
    )
    async def test_run_checks(
        self,
        mock_get_semaphore,
        transparency_service,
    ):
        """Test run_checks calls get_semaphore."""
        mock_semaphore = Mock(spec=TransparencySemaphore)
        mock_get_semaphore.return_value = mock_semaphore

        result = await transparency_service.run_checks()

        assert result == mock_semaphore
        mock_get_semaphore.assert_awaited_once()


class TestDashboardData:
    """Test dashboard data aggregation."""

    @pytest.mark.asyncio
    @patch(
        "app.services.transparency_service.TransparencyService.get_semaphore",
        new_callable=AsyncMock,
    )
    @patch("app.services.transparency_service.TransparencyService.get_tracking_error_rolling", new_callable=AsyncMock)
    @patch(
        "app.services.transparency_service.TransparencyService.get_drawdown_divergence",
        new_callable=AsyncMock,
    )
    @patch("app.services.transparency_service.TransparencyService.get_audit_status")
    @patch("app.services.transparency_service.TransparencyService.verify_hashes")
    @patch("app.services.transparency_service.get_git_commit_hash")
    @patch("app.services.transparency_service.get_dataset_version_hash")
    @patch("app.services.transparency_service.get_params_digest")
    async def test_get_dashboard_data(
        self,
        mock_params,
        mock_dataset,
        mock_commit,
        mock_hashes,
        mock_audit,
        mock_drawdown,
        mock_tracking,
        mock_semaphore,
        transparency_service,
    ):
        """Test dashboard data includes all required fields."""
        mock_semaphore.return_value = TransparencySemaphore(
            overall_status=VerificationStatus.PASS,
            hash_verification=VerificationStatus.PASS,
            dataset_verification=VerificationStatus.PASS,
            params_verification=VerificationStatus.PASS,
            tracking_error_status=VerificationStatus.PASS,
            drawdown_divergence_status=VerificationStatus.PASS,
            audit_status=VerificationStatus.PASS,
            last_verification=datetime.utcnow().isoformat(),
            details={},
        )
        mock_tracking.return_value = None
        mock_drawdown.return_value = None
        mock_audit.return_value = {}
        mock_hashes.return_value = []
        mock_commit.return_value = "abc123"
        mock_dataset.return_value = "sha256:dataset"
        mock_params.return_value = "sha256:params"

        data = await transparency_service.get_dashboard_data()

        assert "semaphore" in data
        assert "current_hashes" in data
        assert "hash_verifications" in data
        assert "tracking_error_rolling" in data
        assert "drawdown_divergence" in data
        assert "audit_status" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    @patch(
        "app.services.transparency_service.TransparencyService.get_semaphore",
        new_callable=AsyncMock,
    )
    @patch("app.services.transparency_service.TransparencyService.get_tracking_error_rolling", new_callable=AsyncMock)
    @patch(
        "app.services.transparency_service.TransparencyService.get_drawdown_divergence",
        new_callable=AsyncMock,
    )
    @patch("app.services.transparency_service.TransparencyService.get_audit_status")
    @patch("app.services.transparency_service.TransparencyService.verify_hashes")
    @patch("app.services.transparency_service.get_git_commit_hash")
    @patch("app.services.transparency_service.get_dataset_version_hash")
    @patch("app.services.transparency_service.get_params_digest")
    async def test_get_dashboard_data_error_with_fallback(
        self,
        mock_params,
        mock_dataset,
        mock_commit,
        mock_hashes,
        mock_audit,
        mock_drawdown,
        mock_tracking,
        mock_semaphore,
        transparency_service,
    ):
        """Test dashboard data maps fields from fallback_summary when summary_status is error."""
        # Mock performance service to return error with fallback
        mock_perf_service = MagicMock()
        mock_perf_service.get_summary = AsyncMock(
            return_value={
                "status": "error",
                "error_type": "DATA_STALE",
                "message": "Data freshness validation failed",
                "fallback_summary": {
                    "status": "success",
                    "source": "db_cache",
                    "metrics": {
                        "cagr": 15.5,
                        "sharpe": 1.2,
                        "max_drawdown": 12.3,
                    },
                    "period": {
                        "start": "2023-01-01T00:00:00",
                        "end": "2024-01-01T00:00:00",
                    },
                    "tracking_error_metrics": {
                        "theoretical_max_drawdown": -0.10,
                        "realistic_max_drawdown": -0.12,
                        "rmse": 95.5,
                    },
                },
            }
        )
        transparency_service.performance_service = mock_perf_service

        # Mock other services
        mock_semaphore.return_value = TransparencySemaphore(
            overall_status=VerificationStatus.WARN,  # Should be WARN due to stale data
            hash_verification=VerificationStatus.PASS,
            dataset_verification=VerificationStatus.PASS,
            params_verification=VerificationStatus.PASS,
            tracking_error_status=VerificationStatus.PASS,
            drawdown_divergence_status=VerificationStatus.WARN,  # WARN due to stale
            audit_status=VerificationStatus.PASS,
            last_verification=datetime.utcnow().isoformat(),
            details={},
        )
        mock_tracking.return_value = None
        # Mock drawdown to return stale object
        mock_drawdown.return_value = DrawdownDivergence(
            theoretical_max_dd=0.0,
            realistic_max_dd=0.0,
            divergence_pct=0.0,
            timestamp=datetime.utcnow().isoformat(),
            metadata={
                "is_stale": True,
                "reason": "tracking_error_metrics_missing",
                "summary_status": "error",
                "has_fallback": True,
            },
        )
        mock_audit.return_value = {}
        mock_hashes.return_value = []
        mock_commit.return_value = "abc123"
        mock_dataset.return_value = "sha256:dataset"
        mock_params.return_value = "sha256:params"

        data = await transparency_service.get_dashboard_data()

        # Verify dashboard includes all required fields
        assert "semaphore" in data
        assert "drawdown_divergence" in data
        assert "summary_status" in data
        assert data["summary_status"] == "error"
        
        # Verify fallback_summary is included
        assert "summary_fallback" in data
        assert data["summary_fallback"] is not None
        
        # Verify fields are mapped from fallback
        assert "summary_metrics" in data
        assert data["summary_metrics"] is not None
        assert data["summary_metrics"].get("cagr") == 15.5
        
        assert "summary_period" in data
        assert data["summary_period"] is not None
        assert data["summary_period"].get("start") == "2023-01-01T00:00:00"
        
        # Verify drawdown_divergence is populated (even if stale)
        assert data["drawdown_divergence"] is not None
        assert data["drawdown_divergence"].get("metadata", {}).get("is_stale") is True
        
        # Verify semaphore is populated
        assert data["semaphore"] is not None
        assert data["semaphore"]["drawdown_divergence_status"] == "warn"  # Should be WARN due to stale

    @pytest.mark.asyncio
    @patch("app.services.transparency_service.TransparencyService.verify_hashes")
    @patch("app.services.transparency_service.TransparencyService.get_tracking_error_rolling", new_callable=AsyncMock)
    @patch(
        "app.services.transparency_service.TransparencyService.get_drawdown_divergence",
        new_callable=AsyncMock,
    )
    @patch("app.services.transparency_service.TransparencyService.get_audit_status")
    async def test_get_semaphore_with_stale_drawdown(
        self,
        mock_audit,
        mock_drawdown,
        mock_tracking,
        mock_hashes,
        transparency_service,
    ):
        """Test semaphore handles stale drawdown_divergence correctly."""
        mock_hashes.return_value = [
            HashVerification(
                hash_type="code_commit",
                current_hash="abc123",
                stored_hash="abc123",
                status=VerificationStatus.PASS,
                message="OK",
                timestamp=datetime.utcnow().isoformat(),
            )
        ]
        mock_tracking.return_value = TrackingErrorRolling(
            period_days=30,
            mean_deviation=0.01,
            max_divergence=0.02,
            correlation=0.95,
            rmse=0.01,
            annualized_tracking_error=2.0,
            timestamp=datetime.utcnow().isoformat(),
        )
        # Mock stale drawdown_divergence
        mock_drawdown.return_value = DrawdownDivergence(
            theoretical_max_dd=0.0,
            realistic_max_dd=0.0,
            divergence_pct=0.0,
            timestamp=datetime.utcnow().isoformat(),
            metadata={
                "is_stale": True,
                "reason": "tracking_error_metrics_missing",
            },
        )
        mock_audit.return_value = {"total_exports": 10}

        semaphore = await transparency_service.get_semaphore()

        # Should be WARN due to stale data, not PASS
        assert semaphore.drawdown_divergence_status == VerificationStatus.WARN
        assert semaphore.overall_status == VerificationStatus.WARN

