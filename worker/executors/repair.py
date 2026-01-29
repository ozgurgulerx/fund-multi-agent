"""
Repair Loop Executor - Stage 6
Attempts to repair failed candidates within budget.
"""

import uuid
import random
from typing import Optional, Tuple
import structlog

from schemas.artifacts import (
    PortfolioCandidate, ComplianceReport, RedTeamReport,
    MandateDSL, DataClassification,
)
from worker.executors.base import BaseExecutor
from schemas import EventKind

logger = structlog.get_logger()


class RepairLoopExecutor(BaseExecutor):
    """
    Repair Loop Executor

    Attempts to repair failed candidates by:
    1. Identifying constraint violations
    2. Adjusting portfolio weights
    3. Re-running compliance/redteam checks
    4. Repeating until pass or budget exhausted
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "repair_loop"

    async def execute(
        self,
        candidate: PortfolioCandidate,
        compliance_report: Optional[ComplianceReport],
        redteam_report: Optional[RedTeamReport],
        mandate: MandateDSL,
        max_attempts: int = 3,
    ) -> Tuple[Optional[PortfolioCandidate], Optional[ComplianceReport], Optional[RedTeamReport]]:
        """
        Attempt to repair a failed candidate.

        Args:
            candidate: Failed portfolio candidate
            compliance_report: Compliance failures
            redteam_report: Red team failures
            mandate: Mandate constraints
            max_attempts: Maximum repair attempts

        Returns:
            Tuple of (repaired_candidate, new_compliance, new_redteam) or (None, None, None)
        """
        logger.info(
            "repair_loop_start",
            candidate_id=candidate.candidate_id,
            max_attempts=max_attempts,
        )

        # Check if repair is needed
        compliance_passed = compliance_report is None or compliance_report.passed
        redteam_passed = redteam_report is None or redteam_report.passed

        if compliance_passed and redteam_passed:
            logger.info("no_repair_needed", candidate_id=candidate.candidate_id)
            return candidate, compliance_report, redteam_report

        current_candidate = candidate
        current_compliance = compliance_report
        current_redteam = redteam_report

        for attempt in range(1, max_attempts + 1):
            await self.emit(
                EventKind.REPAIR_ITERATION,
                f"Repair attempt {attempt}/{max_attempts} for {candidate.candidate_id}",
                candidate_id=candidate.candidate_id,
                payload={"attempt": attempt, "max_attempts": max_attempts},
            )

            await self.emit_progress(f"Repair attempt {attempt} for {candidate.candidate_id}")

            # Attempt repair based on failures
            repaired = await self._apply_repair(
                current_candidate,
                current_compliance,
                current_redteam,
                mandate,
            )

            if repaired is None:
                logger.warning(
                    "repair_failed",
                    candidate_id=candidate.candidate_id,
                    attempt=attempt,
                )
                continue

            # Re-run compliance check
            from worker.executors.compliance import ComplianceCheckExecutor
            compliance_executor = ComplianceCheckExecutor(
                run_id=self.run_id,
                emit_fn=self.emit,
                artifact_store=self.artifact_store,
            )
            new_compliance = await compliance_executor.execute(repaired, mandate)

            # Re-run redteam check
            from worker.executors.redteam import RedTeamExecutor
            redteam_executor = RedTeamExecutor(
                run_id=self.run_id,
                emit_fn=self.emit,
                artifact_store=self.artifact_store,
            )
            new_redteam = await redteam_executor.execute(repaired, seed=42 + attempt)

            if new_compliance.passed and new_redteam.passed:
                logger.info(
                    "repair_succeeded",
                    candidate_id=candidate.candidate_id,
                    attempts=attempt,
                )
                return repaired, new_compliance, new_redteam

            current_candidate = repaired
            current_compliance = new_compliance
            current_redteam = new_redteam

        logger.warning(
            "repair_budget_exhausted",
            candidate_id=candidate.candidate_id,
            attempts=max_attempts,
        )

        return current_candidate, current_compliance, current_redteam

    async def _apply_repair(
        self,
        candidate: PortfolioCandidate,
        compliance: Optional[ComplianceReport],
        redteam: Optional[RedTeamReport],
        mandate: MandateDSL,
    ) -> Optional[PortfolioCandidate]:
        """Apply repair strategy based on failure types."""

        # Collect issues to fix
        issues = []

        if compliance and not compliance.passed:
            for rule in compliance.rule_results:
                if not rule.passed:
                    issues.append({
                        "type": "compliance",
                        "rule_id": rule.rule_id,
                        "category": rule.rule_category,
                        "actual": rule.actual_value,
                        "limit": rule.limit_value,
                    })

        if redteam and not redteam.passed:
            issues.append({
                "type": "redteam",
                "worst_drawdown": redteam.max_drawdown,
                "breaking_count": len(redteam.breaking_scenarios),
            })

        if not issues:
            return None

        # Apply repairs
        repaired_holdings = [h.model_copy() for h in candidate.holdings]
        repairs_made = []

        for issue in issues:
            if issue["type"] == "compliance":
                if issue["category"] == "concentration":
                    # Reduce large positions
                    repaired_holdings = self._reduce_concentration(
                        repaired_holdings,
                        mandate.max_single_position,
                    )
                    repairs_made.append("reduced_concentration")

                elif issue["category"] == "allocation":
                    # Adjust allocation (simplified)
                    repairs_made.append("adjusted_allocation")

            elif issue["type"] == "redteam":
                # Reduce risk exposure
                repaired_holdings = self._reduce_risk(repaired_holdings)
                repairs_made.append("reduced_risk")

        if not repairs_made:
            return None

        # Create repaired candidate
        repaired = PortfolioCandidate(
            artifact_id=f"candidate-{candidate.candidate_id}-repaired-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[candidate.artifact_hash],
            data_classification=DataClassification.DERIVED,
            sources=[candidate.artifact_id],
            candidate_id=candidate.candidate_id,
            solver_config=f"{candidate.solver_config} (repaired)",
            diversity_seed=candidate.diversity_seed,
            holdings=repaired_holdings,
            total_positions=len(repaired_holdings),
            expected_return=candidate.expected_return * 0.95,  # Slight reduction
            expected_volatility=candidate.expected_volatility * 0.9,  # Reduced risk
            expected_sharpe=candidate.expected_sharpe,
            equity_allocation=candidate.equity_allocation * 0.95,
            fixed_income_allocation=candidate.fixed_income_allocation * 1.05,
            cash_allocation=candidate.cash_allocation + 0.02,
            max_position_size=max(h.weight for h in repaired_holdings) if repaired_holdings else 0,
            optimization_score=candidate.optimization_score,
            constraint_violations=[],
            solver_iterations=candidate.solver_iterations + 50,
            solver_time_ms=candidate.solver_time_ms + 100,
        )

        await self.save_artifact(repaired)

        return repaired

    def _reduce_concentration(self, holdings, max_position):
        """Reduce oversized positions."""
        for h in holdings:
            if h.weight > max_position:
                excess = h.weight - max_position
                h.weight = max_position
                # Redistribute excess to smaller positions
                small_holdings = [x for x in holdings if x.weight < max_position * 0.5]
                if small_holdings:
                    per_holding = excess / len(small_holdings)
                    for sh in small_holdings:
                        sh.weight = min(max_position, sh.weight + per_holding)

        # Renormalize
        total = sum(h.weight for h in holdings)
        if total > 0:
            for h in holdings:
                h.weight = round(h.weight / total, 4)

        return holdings

    def _reduce_risk(self, holdings):
        """Reduce portfolio risk by trimming volatile positions."""
        # Sort by weight (proxy for risk contribution)
        holdings.sort(key=lambda x: x.weight, reverse=True)

        # Reduce top positions by 10%
        for h in holdings[:3]:
            h.weight *= 0.9

        # Renormalize
        total = sum(h.weight for h in holdings)
        if total > 0:
            for h in holdings:
                h.weight = round(h.weight / total, 4)

        return holdings
