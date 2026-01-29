"""
Tests for compliance executor.
"""

import pytest
from unittest.mock import AsyncMock


class TestComplianceCheckExecutor:
    """Test compliance checking executor."""

    @pytest.fixture
    def executor(self, sample_run_id, mock_event_bus, mock_artifact_store):
        """Create executor instance."""
        from worker.executors.compliance import ComplianceCheckExecutor

        return ComplianceCheckExecutor(
            run_id=sample_run_id,
            event_bus=mock_event_bus,
            artifact_store=mock_artifact_store,
        )

    @pytest.fixture
    def valid_candidate(self, sample_run_id):
        """Create a valid candidate that should pass compliance."""
        from backend.schemas.artifacts import PortfolioCandidate

        return PortfolioCandidate(
            run_id=sample_run_id,
            stage_id="generate_candidates",
            producer="test",
            candidate_id="A",
            strategy_label="balanced",
            holdings=[
                {"fund_id": f"F{i}", "weight": 0.02, "name": f"Fund {i}"}
                for i in range(50)  # 50 holdings at 2% each = 100%
            ],
            total_weight=1.0,
            expected_return=0.08,
            expected_volatility=0.12,
            sharpe_ratio=0.67,
        )

    @pytest.fixture
    def invalid_candidate_weight(self, sample_run_id):
        """Create a candidate with weights not summing to 100%."""
        from backend.schemas.artifacts import PortfolioCandidate

        return PortfolioCandidate(
            run_id=sample_run_id,
            stage_id="generate_candidates",
            producer="test",
            candidate_id="B",
            strategy_label="broken",
            holdings=[
                {"fund_id": "F1", "weight": 0.5, "name": "Fund 1"},
                {"fund_id": "F2", "weight": 0.3, "name": "Fund 2"},
                # Missing 20% weight
            ],
            total_weight=0.8,  # Only 80%
            expected_return=0.06,
            expected_volatility=0.10,
            sharpe_ratio=0.60,
        )

    @pytest.fixture
    def sample_mandate(self, sample_run_id):
        """Create sample mandate for compliance checking."""
        from backend.schemas.artifacts import MandateDSL

        return MandateDSL(
            run_id=sample_run_id,
            stage_id="load_mandate",
            producer="test",
            mandate_id="test-mandate",
            mandate_version="1.0",
            objective="Test objective",
            constraints={
                "max_holdings": 100,
                "min_position_size": 0.01,
                "max_position_size": 0.10,
            },
            risk_limits={
                "max_volatility": 0.15,
                "max_drawdown": 0.20,
            },
            benchmark="S&P 500",
        )

    @pytest.mark.asyncio
    async def test_valid_candidate_passes(self, executor, valid_candidate, sample_mandate):
        """Test that a valid candidate passes compliance."""
        context = {
            "candidates": [valid_candidate],
            "mandate": sample_mandate,
        }

        result = await executor.execute(context)

        reports = result["compliance_reports"]
        assert len(reports) == 1
        assert reports[0].is_compliant

    @pytest.mark.asyncio
    async def test_invalid_weight_fails(self, executor, invalid_candidate_weight, sample_mandate):
        """Test that invalid weights fail compliance."""
        context = {
            "candidates": [invalid_candidate_weight],
            "mandate": sample_mandate,
        }

        result = await executor.execute(context)

        reports = result["compliance_reports"]
        assert len(reports) == 1
        assert not reports[0].is_compliant
        assert any("weight" in v["rule"].lower() for v in reports[0].violations)

    @pytest.mark.asyncio
    async def test_multiple_candidates(self, executor, valid_candidate, invalid_candidate_weight, sample_mandate):
        """Test checking multiple candidates."""
        context = {
            "candidates": [valid_candidate, invalid_candidate_weight],
            "mandate": sample_mandate,
        }

        result = await executor.execute(context)

        reports = result["compliance_reports"]
        assert len(reports) == 2
