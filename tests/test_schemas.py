"""
Tests for Pydantic schema validation.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError


class TestArtifactSchemas:
    """Test artifact schema validation."""

    def test_mandate_dsl_creation(self):
        """Test MandateDSL artifact creation."""
        from backend.schemas.artifacts import MandateDSL

        mandate = MandateDSL(
            run_id="run-123",
            stage_id="load_mandate",
            producer="test",
            mandate_id="test-mandate",
            mandate_version="1.0",
            objective="Test objective",
            constraints={"max_holdings": 50},
            risk_limits={"max_volatility": 0.15},
            benchmark="S&P 500",
        )

        assert mandate.mandate_id == "test-mandate"
        assert mandate.artifact_type == "mandate_dsl"
        assert mandate.constraints["max_holdings"] == 50

    def test_mandate_dsl_hash(self):
        """Test that artifact hash is computed."""
        from backend.schemas.artifacts import MandateDSL

        mandate = MandateDSL(
            run_id="run-123",
            stage_id="load_mandate",
            producer="test",
            mandate_id="test-mandate",
            mandate_version="1.0",
            objective="Test",
            constraints={},
            risk_limits={},
            benchmark="SPX",
        )

        assert mandate.artifact_hash is not None
        assert len(mandate.artifact_hash) == 64  # SHA256

    def test_universe_artifact_creation(self):
        """Test UniverseArtifact creation."""
        from backend.schemas.artifacts import UniverseArtifact

        universe = UniverseArtifact(
            run_id="run-123",
            stage_id="build_universe",
            producer="test",
            filters_applied=["min_assets > 100M"],
            total_candidates=50,
            funds=[{"fund_id": "F1", "name": "Fund 1"}],
        )

        assert universe.total_candidates == 50
        assert len(universe.funds) == 1

    def test_portfolio_candidate_creation(self):
        """Test PortfolioCandidate creation."""
        from backend.schemas.artifacts import PortfolioCandidate

        candidate = PortfolioCandidate(
            run_id="run-123",
            stage_id="generate_candidates",
            producer="test",
            candidate_id="A",
            strategy_label="aggressive",
            holdings=[
                {"fund_id": "F1", "weight": 0.5, "name": "Fund 1"},
                {"fund_id": "F2", "weight": 0.5, "name": "Fund 2"},
            ],
            total_weight=1.0,
            expected_return=0.08,
            expected_volatility=0.12,
            sharpe_ratio=0.67,
        )

        assert candidate.candidate_id == "A"
        assert len(candidate.holdings) == 2
        assert candidate.total_weight == 1.0

    def test_compliance_report_creation(self):
        """Test ComplianceReport creation."""
        from backend.schemas.artifacts import ComplianceReport

        report = ComplianceReport(
            run_id="run-123",
            stage_id="verify_candidates",
            producer="test",
            candidate_id="A",
            rules_checked=5,
            rules_passed=4,
            rules_failed=1,
            is_compliant=False,
            violations=[{"rule": "max_weight", "message": "Position too large"}],
            warnings=[],
        )

        assert report.rules_checked == 5
        assert not report.is_compliant
        assert len(report.violations) == 1


class TestEventSchemas:
    """Test event schema validation."""

    def test_workflow_event_creation(self):
        """Test WorkflowEvent creation."""
        from backend.schemas.events import WorkflowEvent, EventKind

        event = WorkflowEvent(
            run_id="run-123",
            kind=EventKind.STAGE_STARTED,
            message="Starting build_universe stage",
        )

        assert event.run_id == "run-123"
        assert event.kind == EventKind.STAGE_STARTED
        assert event.event_id is not None

    def test_event_sse_serialization(self):
        """Test event SSE serialization."""
        from backend.schemas.events import WorkflowEvent, EventKind

        event = WorkflowEvent(
            run_id="run-123",
            kind=EventKind.PROGRESS_UPDATE,
            message="50% complete",
            data={"progress": 50},
        )

        sse_data = event.to_sse_data()
        assert isinstance(sse_data, str)
        assert "run-123" in sse_data
        assert "50% complete" in sse_data


class TestRunSchemas:
    """Test run metadata schemas."""

    def test_run_status_enum(self):
        """Test RunStatus enum values."""
        from backend.schemas.runs import RunStatus

        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.RUNNING.value == "running"
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.FAILED.value == "failed"

    def test_stage_status_enum(self):
        """Test StageStatus enum values."""
        from backend.schemas.runs import StageStatus

        assert StageStatus.PENDING.value == "pending"
        assert StageStatus.RUNNING.value == "running"
        assert StageStatus.SUCCEEDED.value == "succeeded"
        assert StageStatus.FAILED.value == "failed"
        assert StageStatus.REPAIRED.value == "repaired"
