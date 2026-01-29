"""
Tests for mandate executor.
"""

import pytest
from unittest.mock import AsyncMock


class TestLoadMandateExecutor:
    """Test mandate loading executor."""

    @pytest.fixture
    def executor(self, sample_run_id, mock_event_bus, mock_artifact_store):
        """Create executor instance."""
        from worker.executors.mandate import LoadMandateExecutor

        return LoadMandateExecutor(
            run_id=sample_run_id,
            event_bus=mock_event_bus,
            artifact_store=mock_artifact_store,
        )

    @pytest.mark.asyncio
    async def test_load_balanced_growth_mandate(self, executor):
        """Test loading balanced growth mandate."""
        context = {"mandate_id": "balanced-growth-2024"}
        result = await executor.execute(context)

        mandate = result["mandate"]
        assert mandate.mandate_id == "balanced-growth-2024"
        assert "balanced" in mandate.objective.lower()
        assert mandate.constraints["max_holdings"] == 50

    @pytest.mark.asyncio
    async def test_load_income_focus_mandate(self, executor):
        """Test loading income focus mandate."""
        context = {"mandate_id": "income-focus-2024"}
        result = await executor.execute(context)

        mandate = result["mandate"]
        assert mandate.mandate_id == "income-focus-2024"
        assert "income" in mandate.objective.lower()

    @pytest.mark.asyncio
    async def test_load_aggressive_growth_mandate(self, executor):
        """Test loading aggressive growth mandate."""
        context = {"mandate_id": "aggressive-growth-2024"}
        result = await executor.execute(context)

        mandate = result["mandate"]
        assert mandate.mandate_id == "aggressive-growth-2024"
        assert mandate.risk_limits["max_volatility"] > 0.15

    @pytest.mark.asyncio
    async def test_unknown_mandate_uses_default(self, executor):
        """Test unknown mandate falls back to default."""
        context = {"mandate_id": "unknown-mandate-xyz"}
        result = await executor.execute(context)

        mandate = result["mandate"]
        assert mandate is not None
        assert mandate.mandate_id == "unknown-mandate-xyz"

    @pytest.mark.asyncio
    async def test_mandate_artifact_saved(self, executor, mock_artifact_store):
        """Test mandate artifact is saved."""
        context = {"mandate_id": "balanced-growth-2024"}
        await executor.execute(context)

        mock_artifact_store.save.assert_called_once()
        saved_artifact = mock_artifact_store.save.call_args[0][0]
        assert saved_artifact.artifact_type == "mandate_dsl"
