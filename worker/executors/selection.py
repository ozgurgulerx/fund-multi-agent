"""
Rank and Select Executor - Stage 7
Ranks candidates and selects winner using explicit scoring policy.
"""

import uuid
from typing import Dict
import structlog

from schemas.artifacts import (
    PortfolioCandidate, ComplianceReport, RedTeamReport,
    Decision, MandateDSL, DataClassification,
)
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()


class RankSelectExecutor(BaseExecutor):
    """
    Rank and Select Executor

    Ranks candidates using weighted scoring:
    - Compliance score (must pass)
    - Risk score (from redteam results)
    - Return score (expected return)
    - Sharpe score (risk-adjusted return)

    Selects the highest scoring candidate that passes all checks.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "rank_select"

    async def execute(
        self,
        candidates: Dict[str, PortfolioCandidate],
        compliance_reports: Dict[str, ComplianceReport],
        redteam_reports: Dict[str, RedTeamReport],
        mandate: MandateDSL,
    ) -> Decision:
        """
        Rank candidates and select winner.

        Args:
            candidates: Dict of candidate_id -> PortfolioCandidate
            compliance_reports: Dict of candidate_id -> ComplianceReport
            redteam_reports: Dict of candidate_id -> RedTeamReport
            mandate: Investment mandate

        Returns:
            Decision artifact with winner and rationale
        """
        logger.info("ranking_candidates", count=len(candidates))

        await self.emit_progress("Scoring and ranking candidates...")

        # Scoring weights (explicit policy)
        weights = {
            "compliance": 0.0,  # Pass/fail gate, not scored
            "risk": 0.30,
            "return": 0.35,
            "sharpe": 0.35,
        }

        candidate_scores = {}
        candidate_details = {}
        rejected = {}

        for candidate_id, candidate in candidates.items():
            compliance = compliance_reports.get(candidate_id)
            redteam = redteam_reports.get(candidate_id)

            # Check if candidate is eligible (passed compliance)
            if compliance and not compliance.passed:
                rejected[candidate_id] = f"Failed compliance: {compliance.critical_failures}"
                candidate_scores[candidate_id] = 0
                continue

            # Check if candidate passed redteam
            if redteam and not redteam.passed:
                rejected[candidate_id] = f"Failed red-team: {len(redteam.breaking_scenarios)} breaking scenarios"
                candidate_scores[candidate_id] = 0
                continue

            # Score the candidate
            scores = {}

            # Risk score (lower drawdown = higher score)
            if redteam:
                # Normalize drawdown to 0-1 score (0% drawdown = 1.0, -50% = 0.0)
                scores["risk"] = max(0, 1 + redteam.max_drawdown / 0.5)
            else:
                scores["risk"] = 0.5

            # Return score (normalize expected return)
            # Assume reasonable range is 0% to 20%
            scores["return"] = min(1.0, max(0, candidate.expected_return / 0.20))

            # Sharpe score (normalize Sharpe ratio)
            # Assume reasonable range is 0 to 2
            scores["sharpe"] = min(1.0, max(0, candidate.expected_sharpe / 2.0))

            # Weighted total
            total_score = (
                scores["risk"] * weights["risk"] +
                scores["return"] * weights["return"] +
                scores["sharpe"] * weights["sharpe"]
            )

            candidate_scores[candidate_id] = round(total_score, 4)
            candidate_details[candidate_id] = {
                "scores": scores,
                "expected_return": candidate.expected_return,
                "expected_volatility": candidate.expected_volatility,
                "expected_sharpe": candidate.expected_sharpe,
                "max_drawdown": redteam.max_drawdown if redteam else None,
                "compliance_passed": compliance.passed if compliance else None,
                "redteam_passed": redteam.passed if redteam else None,
            }

        # Select winner
        eligible_candidates = [c for c in candidate_scores if c not in rejected]

        if not eligible_candidates:
            # No candidates passed - select best of failed
            logger.warning("no_eligible_candidates", rejected=rejected)
            selected = max(candidate_scores.keys(), key=lambda x: candidate_scores[x])
            rationale = f"No candidates passed all checks. Selected {selected} as best available option."
        else:
            selected = max(eligible_candidates, key=lambda x: candidate_scores[x])
            winner_score = candidate_scores[selected]
            rationale = (
                f"Selected Candidate {selected} with score {winner_score:.3f}. "
                f"Expected return: {candidates[selected].expected_return:.2%}, "
                f"Expected Sharpe: {candidates[selected].expected_sharpe:.2f}."
            )

        await self.emit_progress(f"Selected winner: Candidate {selected}")

        # Create decision
        decision = Decision(
            artifact_id=f"decision-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[candidates[selected].artifact_hash],
            data_classification=DataClassification.DERIVED,
            sources=[c.artifact_id for c in candidates.values()],
            selected_candidate=selected,
            selection_rationale=rationale,
            candidate_scores=candidate_scores,
            scoring_weights=weights,
            candidate_comparison=candidate_details,
            rejected_candidates=rejected,
        )

        # Save artifact
        await self.save_artifact(decision)

        logger.info(
            "selection_complete",
            winner=selected,
            score=candidate_scores[selected],
        )

        return decision
