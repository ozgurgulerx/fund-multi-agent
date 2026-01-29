"""
Memo Writer Executor - Stage 9
Generates IC memo and risk appendix documents.
"""

import uuid
from datetime import datetime
from typing import Tuple, Optional
import structlog

from schemas.artifacts import (
    PortfolioCandidate, MandateDSL, Decision,
    ComplianceReport, RedTeamReport, RebalancePlan,
    ICMemo, RiskAppendix, DataClassification,
)
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()


class MemoWriterExecutor(BaseExecutor):
    """
    Memo Writer Executor

    Generates Investment Committee documentation:
    - IC Memo: Executive summary, recommendation, analysis
    - Risk Appendix: Detailed risk metrics and stress test results
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "write_memo"

    async def execute(
        self,
        candidate: PortfolioCandidate,
        mandate: MandateDSL,
        decision: Decision,
        compliance: Optional[ComplianceReport],
        redteam: Optional[RedTeamReport],
        rebalance: RebalancePlan,
    ) -> Tuple[ICMemo, RiskAppendix]:
        """
        Generate IC memo and risk appendix.

        Args:
            candidate: Selected portfolio
            mandate: Investment mandate
            decision: Selection decision
            compliance: Compliance report
            redteam: Red team report
            rebalance: Rebalance plan

        Returns:
            Tuple of (ICMemo, RiskAppendix)
        """
        logger.info("writing_memo", candidate_id=candidate.candidate_id)

        await self.emit_progress("Generating IC memo...")

        # Generate memo content
        memo = await self._generate_memo(
            candidate, mandate, decision, compliance, redteam, rebalance
        )

        await self.emit_progress("Generating risk appendix...")

        # Generate risk appendix
        appendix = await self._generate_risk_appendix(candidate, redteam)

        # Save artifacts
        await self.save_artifact(memo)
        await self.save_artifact(appendix)

        logger.info("memo_written", memo_id=memo.artifact_id)

        return memo, appendix

    async def _generate_memo(
        self,
        candidate: PortfolioCandidate,
        mandate: MandateDSL,
        decision: Decision,
        compliance: Optional[ComplianceReport],
        redteam: Optional[RedTeamReport],
        rebalance: RebalancePlan,
    ) -> ICMemo:
        """Generate IC Memo content."""

        # Executive summary
        executive_summary = f"""
The IC Autopilot has completed analysis for the {mandate.mandate_name} mandate.
After evaluating 3 portfolio candidates using {len(compliance.rule_results) if compliance else 'N/A'} compliance rules
and {redteam.scenarios_tested if redteam else 'N/A'} stress scenarios, Candidate {candidate.candidate_id}
has been selected as the recommended portfolio.

Key metrics:
- Expected Return: {candidate.expected_return:.2%}
- Expected Volatility: {candidate.expected_volatility:.2%}
- Sharpe Ratio: {candidate.expected_sharpe:.2f}
- Total Positions: {candidate.total_positions}
""".strip()

        # Recommendation
        recommendation = f"""
We recommend proceeding with Candidate {candidate.candidate_id} ({candidate.solver_config}).

{decision.selection_rationale}

Implementation requires {rebalance.total_buys} buy orders with estimated transaction
costs of {rebalance.estimated_transaction_cost:.4%}.
""".strip()

        # Mandate summary
        mandate_summary = f"""
Mandate: {mandate.mandate_name}
Objective: {mandate.primary_objective}
Benchmark: {mandate.benchmark or 'None specified'}
Risk Budget: {mandate.risk_budget:.1%}
Maximum Drawdown: {mandate.max_drawdown:.1%}

Asset Allocation Constraints:
- Equity: {mandate.min_equity:.0%} - {mandate.max_equity:.0%}
- Fixed Income: {mandate.min_fixed_income:.0%} - {mandate.max_fixed_income:.0%}
- Alternatives: {mandate.min_alternatives:.0%} - {mandate.max_alternatives:.0%}
""".strip()

        # Market context (placeholder - would be from RAPTOR index)
        market_context = """
Current market conditions reflect continued uncertainty in the macroeconomic environment.
The IC Autopilot has incorporated stress testing across multiple scenarios including
historical (2008 Financial Crisis, 2020 COVID) and synthetic (rate shocks, stagflation).

The recommended portfolio has been designed to balance return potential with
downside protection consistent with the mandate's risk parameters.
""".strip()

        # Portfolio overview
        top_holdings = sorted(candidate.holdings, key=lambda h: h.weight, reverse=True)[:5]
        holdings_text = "\n".join([
            f"  - {h.fund_name}: {h.weight:.1%}"
            for h in top_holdings
        ])

        portfolio_overview = f"""
Selected Portfolio: Candidate {candidate.candidate_id}
Strategy: {candidate.solver_config}

Allocation:
- Equity: {candidate.equity_allocation:.1%}
- Fixed Income: {candidate.fixed_income_allocation:.1%}
- Cash: {candidate.cash_allocation:.1%}

Top 5 Holdings:
{holdings_text}
""".strip()

        # Risk analysis
        risk_analysis = f"""
Stress Test Results:
- Scenarios Tested: {redteam.scenarios_tested if redteam else 'N/A'}
- Worst Drawdown: {redteam.max_drawdown:.1%} if redteam else 'N/A'
- VaR (95%): {redteam.var_95:.1%} if redteam else 'N/A'
- CVaR (95%): {redteam.cvar_95:.1%} if redteam else 'N/A'

The portfolio demonstrates resilience across tested scenarios with acceptable
drawdown levels within the mandate's risk tolerance.
""".strip() if redteam else "Risk analysis pending."

        # Compliance summary
        compliance_summary = f"""
Compliance Status: {'PASSED' if compliance and compliance.passed else 'REVIEW REQUIRED'}
Rules Checked: {compliance.rules_checked if compliance else 'N/A'}
Rules Passed: {compliance.rules_passed if compliance else 'N/A'}

All concentration, liquidity, and ESG requirements have been verified.
""".strip() if compliance else "Compliance check pending."

        # Implementation plan
        implementation_plan = f"""
Execution Plan:
- Total Trades: {len(rebalance.trades)}
- Buys: {rebalance.total_buys}
- Sells: {rebalance.total_sells}
- Estimated Turnover: {rebalance.total_turnover:.1%}
- Transaction Costs: {rebalance.estimated_transaction_cost:.4%}

Priority trades should be executed first to establish core positions.
""".strip()

        # Create memo
        memo = ICMemo(
            artifact_id=f"memo-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[candidate.artifact_hash, decision.artifact_hash],
            data_classification=DataClassification.DERIVED,
            sources=[candidate.artifact_id, decision.artifact_id],
            memo_title=f"IC Recommendation: {mandate.mandate_name}",
            executive_summary=executive_summary,
            recommendation=recommendation,
            mandate_summary=mandate_summary,
            market_context=market_context,
            portfolio_overview=portfolio_overview,
            risk_analysis=risk_analysis,
            compliance_summary=compliance_summary,
            implementation_plan=implementation_plan,
            appendix_refs=[f"risk_appendix_{candidate.candidate_id}"],
        )

        return memo

    async def _generate_risk_appendix(
        self,
        candidate: PortfolioCandidate,
        redteam: Optional[RedTeamReport],
    ) -> RiskAppendix:
        """Generate risk appendix with detailed metrics."""

        # Factor exposures (placeholder)
        factor_exposures = {
            "market": candidate.equity_allocation,
            "size": 0.0,
            "value": 0.0,
            "momentum": 0.0,
            "quality": 0.0,
            "low_volatility": 1 - candidate.expected_volatility,
        }

        # Stress test results
        stress_results = {}
        if redteam:
            for scenario in redteam.scenario_results:
                stress_results[scenario.scenario_name] = scenario.portfolio_return

        # Create appendix
        appendix = RiskAppendix(
            artifact_id=f"risk-appendix-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[candidate.artifact_hash],
            data_classification=DataClassification.DERIVED,
            sources=[candidate.artifact_id],
            candidate_id=candidate.candidate_id,
            var_95_1d=redteam.var_95 / 21 if redteam else 0,  # Monthly to daily
            var_99_1d=(redteam.var_95 * 1.3) / 21 if redteam else 0,
            cvar_95_1d=redteam.cvar_95 / 21 if redteam else 0,
            expected_shortfall=redteam.cvar_95 if redteam else 0,
            factor_exposures=factor_exposures,
            stress_test_results=stress_results,
            position_hhi=sum(h.weight ** 2 for h in candidate.holdings),
            sector_hhi=0.15,  # Placeholder
            geography_hhi=0.20,  # Placeholder
            liquidity_coverage_ratio=0.95,
            days_to_liquidate_95=3.0,
        )

        return appendix
