"""
IC Autopilot Workflow - Main orchestrator using Agent Framework patterns.
Implements the 10-stage Investment Committee workflow with event emission.
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import structlog

from schemas import (
    WorkflowEvent, EventKind, EventLevel,
    MandateDSL, Universe, FundFeatures, PortfolioCandidate,
    ComplianceReport, RedTeamReport, Decision, RebalancePlan,
    ICMemo, RiskAppendix, AuditEvent,
)
from schemas.runs import RunMetadata, RunStatus, StageStatus
from services.event_bus import EventBus
from services.artifact_store import ArtifactStore
from services.run_store import RunStore

from worker.executors import (
    LoadMandateExecutor,
    BuildUniverseExecutor,
    ComputeFeaturesExecutor,
    GenerateCandidatesExecutor,
    ComplianceCheckExecutor,
    RedTeamExecutor,
    RepairLoopExecutor,
    RankSelectExecutor,
    RebalancePlannerExecutor,
    MemoWriterExecutor,
    AuditFinalizeExecutor,
)

logger = structlog.get_logger()


class ICWorkflow:
    """
    Investment Committee Autopilot Workflow.

    Two-layer orchestration:
    1. Deterministic workflow orchestrator (this class)
    2. Cognitive agents constrained by orchestrator policy (in executors)

    Stages:
    1. LoadMandateTemplate -> MandateDSL
    2. BuildUniverse -> Universe
    3. ComputeFeatures -> FundFeatures[]
    4. GenerateCandidates -> 3 candidates (A/B/C)
    5. VerifyCandidate (fan-out): ComplianceCheck + RedTeamScenarioSearch
    6. RepairLoop (if fails)
    7. RankAndSelect -> Decision
    8. RebalancePlanner -> RebalancePlan
    9. MemoWriter -> ICMemo + RiskAppendix
    10. AuditFinalize -> immutable audit bundle
    """

    def __init__(
        self,
        run_id: str,
        run_store: RunStore,
        event_bus: EventBus,
        artifact_store: ArtifactStore,
    ):
        self.run_id = run_id
        self.run_store = run_store
        self.event_bus = event_bus
        self.artifact_store = artifact_store

        # Workflow state
        self.run: Optional[RunMetadata] = None
        self.sequence = 0

        # Artifact blackboard
        self.mandate: Optional[MandateDSL] = None
        self.universe: Optional[Universe] = None
        self.features: List[FundFeatures] = []
        self.candidates: Dict[str, PortfolioCandidate] = {}
        self.compliance_reports: Dict[str, ComplianceReport] = {}
        self.redteam_reports: Dict[str, RedTeamReport] = {}
        self.decision: Optional[Decision] = None
        self.rebalance_plan: Optional[RebalancePlan] = None
        self.memo: Optional[ICMemo] = None
        self.risk_appendix: Optional[RiskAppendix] = None

    async def emit(
        self,
        kind: EventKind,
        message: str,
        stage_id: str = None,
        candidate_id: str = None,
        level: EventLevel = EventLevel.INFO,
        payload: Dict[str, Any] = None,
        duration_ms: int = None,
    ):
        """Emit a workflow event."""
        self.sequence += 1
        event = WorkflowEvent(
            run_id=self.run_id,
            kind=kind,
            level=level,
            stage_id=stage_id,
            candidate_id=candidate_id,
            message=message,
            sequence=self.sequence,
            payload=payload or {},
            duration_ms=duration_ms,
        )
        await self.event_bus.publish(event)

    async def execute_stage(
        self,
        stage_id: str,
        stage_name: str,
        executor_fn,
        **kwargs,
    ):
        """
        Execute a workflow stage with event emission.

        Args:
            stage_id: Stage identifier
            stage_name: Human-readable stage name
            executor_fn: Async function to execute
            **kwargs: Arguments to pass to executor
        """
        logger.info("stage_starting", run_id=self.run_id, stage_id=stage_id)

        # Update stage status
        await self.run_store.update_stage(self.run_id, stage_id, StageStatus.RUNNING)

        # Emit stage started
        await self.emit(
            EventKind.STAGE_STARTED,
            f"Starting {stage_name}",
            stage_id=stage_id,
        )

        start_time = time.time()

        try:
            # Execute the stage
            result = await executor_fn(**kwargs)
            duration_ms = int((time.time() - start_time) * 1000)

            # Update stage status
            await self.run_store.update_stage(
                self.run_id, stage_id, StageStatus.SUCCEEDED,
                duration_ms=duration_ms,
            )

            # Emit stage completed
            await self.emit(
                EventKind.STAGE_COMPLETED,
                f"{stage_name} completed",
                stage_id=stage_id,
                duration_ms=duration_ms,
            )

            logger.info("stage_completed", run_id=self.run_id, stage_id=stage_id, duration_ms=duration_ms)
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            # Update stage status
            await self.run_store.update_stage(
                self.run_id, stage_id, StageStatus.FAILED,
                duration_ms=duration_ms,
                error_message=str(e),
            )

            # Emit stage failed
            await self.emit(
                EventKind.STAGE_FAILED,
                f"{stage_name} failed: {str(e)}",
                stage_id=stage_id,
                level=EventLevel.ERROR,
                duration_ms=duration_ms,
            )

            logger.error("stage_failed", run_id=self.run_id, stage_id=stage_id, error=str(e))
            raise

    async def execute(self):
        """Execute the complete IC workflow."""
        logger.info("workflow_starting", run_id=self.run_id)

        # Load run metadata
        self.run = await self.run_store.get_run(self.run_id)
        if not self.run:
            raise ValueError(f"Run {self.run_id} not found")

        # Stage 1: Load Mandate
        await self.execute_stage(
            "load_mandate", "Load Mandate Template",
            self._load_mandate,
        )

        # Stage 2: Build Universe
        await self.execute_stage(
            "build_universe", "Build Universe",
            self._build_universe,
        )

        # Stage 3: Compute Features
        await self.execute_stage(
            "compute_features", "Compute Features",
            self._compute_features,
        )

        # Stage 4: Generate Candidates
        await self.execute_stage(
            "generate_candidates", "Generate Candidates",
            self._generate_candidates,
        )

        # Stage 5: Verify Candidates (fan-out)
        await self.execute_stage(
            "verify_candidates", "Verify Candidates",
            self._verify_candidates,
        )

        # Stage 6: Repair Loop (if needed)
        await self.execute_stage(
            "repair_loop", "Repair Loop",
            self._repair_loop,
        )

        # Stage 7: Rank and Select
        await self.execute_stage(
            "rank_select", "Rank and Select",
            self._rank_select,
        )

        # Stage 8: Rebalance Planner
        await self.execute_stage(
            "rebalance_plan", "Rebalance Planner",
            self._rebalance_plan,
        )

        # Stage 9: Write Memo
        await self.execute_stage(
            "write_memo", "Write Memo",
            self._write_memo,
        )

        # Stage 10: Audit Finalize
        await self.execute_stage(
            "audit_finalize", "Audit Finalize",
            self._audit_finalize,
        )

        logger.info("workflow_completed", run_id=self.run_id)

    # =========================================================================
    # Stage Implementations
    # =========================================================================

    async def _load_mandate(self):
        """Load and validate mandate template."""
        executor = LoadMandateExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )
        self.mandate = await executor.execute(self.run.mandate_id)
        return self.mandate

    async def _build_universe(self):
        """Build investment universe based on mandate."""
        executor = BuildUniverseExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )
        self.universe = await executor.execute(self.mandate)
        return self.universe

    async def _compute_features(self):
        """Compute features for all funds in universe."""
        executor = ComputeFeaturesExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )
        self.features = await executor.execute(self.universe)
        return self.features

    async def _generate_candidates(self):
        """Generate 3 portfolio candidates with diversity."""
        executor = GenerateCandidatesExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )
        candidates = await executor.execute(
            mandate=self.mandate,
            universe=self.universe,
            features=self.features,
            seed=self.run.seed,
        )
        self.candidates = {c.candidate_id: c for c in candidates}

        # Emit candidate created events
        for candidate in candidates:
            await self.emit(
                EventKind.CANDIDATE_CREATED,
                f"Candidate {candidate.candidate_id} created",
                candidate_id=candidate.candidate_id,
                payload={
                    "expected_return": candidate.expected_return,
                    "expected_volatility": candidate.expected_volatility,
                    "positions": candidate.total_positions,
                },
            )

        return candidates

    async def _verify_candidates(self):
        """Verify all candidates with compliance and red-team checks (fan-out)."""
        # Run compliance and red-team in parallel for each candidate
        tasks = []
        for candidate_id, candidate in self.candidates.items():
            tasks.append(self._verify_single_candidate(candidate_id, candidate))

        await asyncio.gather(*tasks)

    async def _verify_single_candidate(self, candidate_id: str, candidate: PortfolioCandidate):
        """Verify a single candidate with compliance and red-team."""
        # Compliance check
        compliance_executor = ComplianceCheckExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )

        await self.emit(
            EventKind.COMPLIANCE_CHECK,
            f"Running compliance check for {candidate_id}",
            candidate_id=candidate_id,
        )

        compliance_report = await compliance_executor.execute(candidate, self.mandate)
        self.compliance_reports[candidate_id] = compliance_report

        if compliance_report.passed:
            await self.emit(
                EventKind.CANDIDATE_PASSED,
                f"Candidate {candidate_id} passed compliance",
                candidate_id=candidate_id,
                payload={"rules_passed": compliance_report.rules_passed},
            )
        else:
            await self.emit(
                EventKind.CANDIDATE_FAILED,
                f"Candidate {candidate_id} failed compliance: {compliance_report.critical_failures}",
                candidate_id=candidate_id,
                level=EventLevel.WARN,
                payload={"failures": compliance_report.critical_failures},
            )

        # Red-team check
        redteam_executor = RedTeamExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )

        await self.emit(
            EventKind.REDTEAM_CHECK,
            f"Running red-team scenarios for {candidate_id}",
            candidate_id=candidate_id,
        )

        redteam_report = await redteam_executor.execute(candidate, self.run.seed)
        self.redteam_reports[candidate_id] = redteam_report

        if redteam_report.passed:
            await self.emit(
                EventKind.CANDIDATE_PASSED,
                f"Candidate {candidate_id} passed red-team",
                candidate_id=candidate_id,
                payload={"scenarios_tested": redteam_report.scenarios_tested},
            )
        else:
            await self.emit(
                EventKind.CANDIDATE_FAILED,
                f"Candidate {candidate_id} failed red-team: {redteam_report.breaking_scenarios}",
                candidate_id=candidate_id,
                level=EventLevel.WARN,
                payload={"breaking_scenarios": redteam_report.breaking_scenarios},
            )

    async def _repair_loop(self):
        """Attempt to repair failed candidates."""
        repair_executor = RepairLoopExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )

        for candidate_id, candidate in self.candidates.items():
            compliance = self.compliance_reports.get(candidate_id)
            redteam = self.redteam_reports.get(candidate_id)

            if (compliance and not compliance.passed) or (redteam and not redteam.passed):
                await self.emit(
                    EventKind.REPAIR_ITERATION,
                    f"Attempting repair for {candidate_id}",
                    candidate_id=candidate_id,
                    payload={"attempt": 1},
                )

                repaired_candidate, new_compliance, new_redteam = await repair_executor.execute(
                    candidate=candidate,
                    compliance_report=compliance,
                    redteam_report=redteam,
                    mandate=self.mandate,
                    max_attempts=3,
                )

                # Update artifacts
                if repaired_candidate:
                    self.candidates[candidate_id] = repaired_candidate
                    self.compliance_reports[candidate_id] = new_compliance
                    self.redteam_reports[candidate_id] = new_redteam

                    await self.emit(
                        EventKind.CANDIDATE_REPAIRED,
                        f"Candidate {candidate_id} repaired successfully",
                        candidate_id=candidate_id,
                    )

    async def _rank_select(self):
        """Rank candidates and select winner."""
        executor = RankSelectExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )

        self.decision = await executor.execute(
            candidates=self.candidates,
            compliance_reports=self.compliance_reports,
            redteam_reports=self.redteam_reports,
            mandate=self.mandate,
        )

        await self.emit(
            EventKind.DECISION_MADE,
            f"Selected candidate: {self.decision.selected_candidate}",
            payload={
                "winner": self.decision.selected_candidate,
                "scores": self.decision.candidate_scores,
            },
        )

        return self.decision

    async def _rebalance_plan(self):
        """Create rebalancing plan for selected candidate."""
        executor = RebalancePlannerExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )

        selected = self.candidates.get(self.decision.selected_candidate)
        self.rebalance_plan = await executor.execute(selected)

        return self.rebalance_plan

    async def _write_memo(self):
        """Generate IC memo and risk appendix."""
        executor = MemoWriterExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )

        selected = self.candidates.get(self.decision.selected_candidate)
        self.memo, self.risk_appendix = await executor.execute(
            candidate=selected,
            mandate=self.mandate,
            decision=self.decision,
            compliance=self.compliance_reports.get(self.decision.selected_candidate),
            redteam=self.redteam_reports.get(self.decision.selected_candidate),
            rebalance=self.rebalance_plan,
        )

        return self.memo

    async def _audit_finalize(self):
        """Finalize audit trail and create immutable bundle."""
        executor = AuditFinalizeExecutor(
            run_id=self.run_id,
            emit_fn=self.emit,
            artifact_store=self.artifact_store,
        )

        audit_event = await executor.execute(
            mandate=self.mandate,
            universe=self.universe,
            candidates=self.candidates,
            decision=self.decision,
            memo=self.memo,
        )

        await self.emit(
            EventKind.ARTIFACT_PERSISTED,
            "Audit bundle finalized",
            payload={"artifact_id": audit_event.artifact_id},
        )

        return audit_event
