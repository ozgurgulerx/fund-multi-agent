"""
Tests for IC workflow orchestration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestICWorkflow:
    """Test IC workflow orchestration."""

    @pytest.fixture
    def workflow(self, sample_run_id, mock_run_store, mock_event_bus, mock_artifact_store):
        """Create workflow instance with mocks."""
        from worker.workflow import ICWorkflow

        return ICWorkflow(
            run_id=sample_run_id,
            run_store=mock_run_store,
            event_bus=mock_event_bus,
            artifact_store=mock_artifact_store,
        )

    def test_workflow_initialization(self, workflow, sample_run_id):
        """Test workflow initializes correctly."""
        assert workflow.run_id == sample_run_id
        assert len(workflow.stages) == 10

    def test_workflow_stages_order(self, workflow):
        """Test workflow stages are in correct order."""
        expected_stages = [
            "load_mandate",
            "build_universe",
            "compute_features",
            "generate_candidates",
            "verify_candidates",
            "repair_loop",
            "rank_select",
            "rebalance_plan",
            "write_memo",
            "audit_finalize",
        ]

        actual_stages = [s["id"] for s in workflow.stages]
        assert actual_stages == expected_stages

    @pytest.mark.asyncio
    async def test_emit_event(self, workflow, mock_event_bus):
        """Test event emission."""
        from backend.schemas.events import EventKind

        await workflow.emit_event(
            kind=EventKind.STAGE_STARTED,
            message="Test message",
            data={"test": "data"},
        )

        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args
        event = call_args[0][0]
        assert event.kind == EventKind.STAGE_STARTED
        assert event.message == "Test message"


class TestExecutorBase:
    """Test base executor functionality."""

    @pytest.fixture
    def executor(self, sample_run_id, mock_event_bus, mock_artifact_store):
        """Create base executor instance."""
        from worker.executors.base import BaseExecutor

        class TestExecutor(BaseExecutor):
            stage_id = "test_stage"
            stage_name = "Test Stage"

            async def execute(self, context: dict) -> dict:
                return {"result": "success"}

        return TestExecutor(
            run_id=sample_run_id,
            event_bus=mock_event_bus,
            artifact_store=mock_artifact_store,
        )

    def test_executor_initialization(self, executor, sample_run_id):
        """Test executor initializes correctly."""
        assert executor.run_id == sample_run_id
        assert executor.stage_id == "test_stage"

    @pytest.mark.asyncio
    async def test_executor_emit_progress(self, executor, mock_event_bus):
        """Test progress emission."""
        await executor.emit_progress(50, "Halfway done")

        mock_event_bus.publish.assert_called()

    @pytest.mark.asyncio
    async def test_executor_save_artifact(self, executor, mock_artifact_store):
        """Test artifact saving."""
        from backend.schemas.artifacts import MandateDSL

        artifact = MandateDSL(
            run_id=executor.run_id,
            stage_id=executor.stage_id,
            producer=executor.__class__.__name__,
            mandate_id="test",
            mandate_version="1.0",
            objective="Test",
            constraints={},
            risk_limits={},
            benchmark="SPX",
        )

        await executor.save_artifact(artifact)

        mock_artifact_store.save.assert_called_once_with(artifact)


class TestStageExecution:
    """Test individual stage execution."""

    @pytest.mark.asyncio
    async def test_mandate_executor(self, sample_run_id, mock_event_bus, mock_artifact_store):
        """Test mandate executor."""
        from worker.executors.mandate import LoadMandateExecutor

        executor = LoadMandateExecutor(
            run_id=sample_run_id,
            event_bus=mock_event_bus,
            artifact_store=mock_artifact_store,
        )

        context = {"mandate_id": "balanced-growth-2024"}
        result = await executor.execute(context)

        assert "mandate" in result
        assert result["mandate"].mandate_id == "balanced-growth-2024"

    @pytest.mark.asyncio
    async def test_candidates_executor(self, sample_run_id, mock_event_bus, mock_artifact_store, sample_universe_artifact, sample_mandate_artifact):
        """Test candidates executor generates A/B/C."""
        from worker.executors.candidates import GenerateCandidatesExecutor

        executor = GenerateCandidatesExecutor(
            run_id=sample_run_id,
            event_bus=mock_event_bus,
            artifact_store=mock_artifact_store,
        )

        context = {
            "mandate": sample_mandate_artifact,
            "universe": sample_universe_artifact,
            "features": {"funds": []},
        }

        result = await executor.execute(context)

        assert "candidates" in result
        candidates = result["candidates"]
        assert len(candidates) == 3
        assert set(c.candidate_id for c in candidates) == {"A", "B", "C"}
