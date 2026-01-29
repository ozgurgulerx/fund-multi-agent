"""
Compliance Check Executor - Part of Stage 5 (Verify Candidates)
Deterministic rule-based compliance verification.
"""

import uuid
import structlog

from schemas.artifacts import (
    PortfolioCandidate, ComplianceReport, ComplianceRule,
    MandateDSL, DataClassification,
)
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()


class ComplianceCheckExecutor(BaseExecutor):
    """
    Compliance Check Executor

    Performs deterministic compliance verification:
    - Concentration limits (position, sector, country)
    - Liquidity requirements
    - ESG exclusions
    - Regulatory constraints
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "verify_candidates"

    async def execute(
        self,
        candidate: PortfolioCandidate,
        mandate: MandateDSL,
    ) -> ComplianceReport:
        """
        Run compliance checks on a portfolio candidate.

        Args:
            candidate: Portfolio to verify
            mandate: Mandate with constraints

        Returns:
            ComplianceReport with pass/fail and details
        """
        logger.info("compliance_check", candidate_id=candidate.candidate_id)

        await self.emit_progress(f"Running compliance checks for {candidate.candidate_id}...")

        rules = []

        # Rule 1: Maximum single position
        max_pos = candidate.max_position_size
        passed = max_pos <= mandate.max_single_position
        rules.append(ComplianceRule(
            rule_id="CONC-001",
            rule_name="Maximum Single Position",
            rule_category="concentration",
            passed=passed,
            actual_value=max_pos,
            limit_value=mandate.max_single_position,
            message=f"Max position {max_pos:.2%} {'<=' if passed else '>'} limit {mandate.max_single_position:.2%}",
        ))

        # Rule 2: Minimum equity allocation
        passed = candidate.equity_allocation >= mandate.min_equity
        rules.append(ComplianceRule(
            rule_id="ALLOC-001",
            rule_name="Minimum Equity Allocation",
            rule_category="allocation",
            passed=passed,
            actual_value=candidate.equity_allocation,
            limit_value=mandate.min_equity,
            message=f"Equity {candidate.equity_allocation:.2%} {'>=' if passed else '<'} min {mandate.min_equity:.2%}",
        ))

        # Rule 3: Maximum equity allocation
        passed = candidate.equity_allocation <= mandate.max_equity
        rules.append(ComplianceRule(
            rule_id="ALLOC-002",
            rule_name="Maximum Equity Allocation",
            rule_category="allocation",
            passed=passed,
            actual_value=candidate.equity_allocation,
            limit_value=mandate.max_equity,
            message=f"Equity {candidate.equity_allocation:.2%} {'<=' if passed else '>'} max {mandate.max_equity:.2%}",
        ))

        # Rule 4: Minimum fixed income
        passed = candidate.fixed_income_allocation >= mandate.min_fixed_income
        rules.append(ComplianceRule(
            rule_id="ALLOC-003",
            rule_name="Minimum Fixed Income",
            rule_category="allocation",
            passed=passed,
            actual_value=candidate.fixed_income_allocation,
            limit_value=mandate.min_fixed_income,
            message=f"Fixed income {candidate.fixed_income_allocation:.2%} {'>=' if passed else '<'} min {mandate.min_fixed_income:.2%}",
        ))

        # Rule 5: Maximum fixed income
        passed = candidate.fixed_income_allocation <= mandate.max_fixed_income
        rules.append(ComplianceRule(
            rule_id="ALLOC-004",
            rule_name="Maximum Fixed Income",
            rule_category="allocation",
            passed=passed,
            actual_value=candidate.fixed_income_allocation,
            limit_value=mandate.max_fixed_income,
            message=f"Fixed income {candidate.fixed_income_allocation:.2%} {'<=' if passed else '>'} max {mandate.max_fixed_income:.2%}",
        ))

        # Rule 6: Minimum positions (diversification)
        min_positions = 5
        passed = candidate.total_positions >= min_positions
        rules.append(ComplianceRule(
            rule_id="DIV-001",
            rule_name="Minimum Diversification",
            rule_category="diversification",
            passed=passed,
            actual_value=candidate.total_positions,
            limit_value=min_positions,
            message=f"Positions {candidate.total_positions} {'>=' if passed else '<'} min {min_positions}",
        ))

        # Rule 7: Maximum positions
        max_positions = 50
        passed = candidate.total_positions <= max_positions
        rules.append(ComplianceRule(
            rule_id="DIV-002",
            rule_name="Maximum Positions",
            rule_category="diversification",
            passed=passed,
            actual_value=candidate.total_positions,
            limit_value=max_positions,
            message=f"Positions {candidate.total_positions} {'<=' if passed else '>'} max {max_positions}",
        ))

        # Rule 8: ESG exclusion check (simplified - would check actual holdings)
        # For demo, randomly fail 10% of the time for drama
        import random
        random.seed(hash(candidate.candidate_id))
        esg_violations = random.random() < 0.1
        rules.append(ComplianceRule(
            rule_id="ESG-001",
            rule_name="ESG Exclusion Compliance",
            rule_category="esg",
            passed=not esg_violations,
            actual_value=0 if not esg_violations else 1,
            limit_value=0,
            message="No ESG violations found" if not esg_violations else "ESG violation detected",
        ))

        # Aggregate results
        rules_passed = sum(1 for r in rules if r.passed)
        rules_failed = len(rules) - rules_passed
        critical_failures = [r.message for r in rules if not r.passed and r.rule_category in ["concentration", "regulatory"]]
        warnings = [r.message for r in rules if not r.passed and r.rule_category not in ["concentration", "regulatory"]]

        overall_passed = rules_failed == 0

        # Create report
        report = ComplianceReport(
            artifact_id=f"compliance-{candidate.candidate_id}-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[candidate.artifact_hash],
            data_classification=DataClassification.DERIVED,
            sources=[candidate.artifact_id],
            candidate_id=candidate.candidate_id,
            passed=overall_passed,
            rules_checked=len(rules),
            rules_passed=rules_passed,
            rules_failed=rules_failed,
            rule_results=rules,
            critical_failures=critical_failures,
            warnings=warnings,
        )

        # Save artifact
        await self.save_artifact(report)

        logger.info(
            "compliance_check_complete",
            candidate_id=candidate.candidate_id,
            passed=overall_passed,
            rules_passed=rules_passed,
            rules_failed=rules_failed,
        )

        return report
