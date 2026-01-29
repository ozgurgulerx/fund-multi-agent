"""
Red Team Executor - Part of Stage 5 (Verify Candidates)
Adversarial scenario search to find breaking conditions.
"""

import uuid
import random
import structlog

from schemas.artifacts import (
    PortfolioCandidate, RedTeamReport, ScenarioResult,
    DataClassification,
)
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()

# Predefined stress scenarios
STRESS_SCENARIOS = [
    {
        "id": "2008_FINANCIAL_CRISIS",
        "name": "2008 Financial Crisis",
        "type": "historical",
        "description": "Lehman collapse and credit freeze",
        "equity_shock": -0.50,
        "bond_shock": -0.10,
        "vol_multiplier": 3.0,
    },
    {
        "id": "2020_COVID_CRASH",
        "name": "2020 COVID Crash",
        "type": "historical",
        "description": "March 2020 pandemic selloff",
        "equity_shock": -0.35,
        "bond_shock": 0.05,
        "vol_multiplier": 4.0,
    },
    {
        "id": "RATE_SHOCK_UP",
        "name": "Interest Rate Shock (+300bps)",
        "type": "synthetic",
        "description": "Rapid rate hike scenario",
        "equity_shock": -0.15,
        "bond_shock": -0.20,
        "vol_multiplier": 2.0,
    },
    {
        "id": "STAGFLATION",
        "name": "Stagflation Scenario",
        "type": "synthetic",
        "description": "High inflation with low growth",
        "equity_shock": -0.25,
        "bond_shock": -0.15,
        "vol_multiplier": 2.5,
    },
    {
        "id": "LIQUIDITY_CRISIS",
        "name": "Liquidity Crisis",
        "type": "adversarial",
        "description": "Severe market liquidity stress",
        "equity_shock": -0.30,
        "bond_shock": -0.05,
        "vol_multiplier": 3.5,
    },
    {
        "id": "CURRENCY_CRISIS",
        "name": "Currency Crisis",
        "type": "adversarial",
        "description": "Dollar collapse scenario",
        "equity_shock": -0.20,
        "bond_shock": -0.10,
        "vol_multiplier": 2.5,
    },
    {
        "id": "TECH_BUBBLE_BURST",
        "name": "Tech Bubble Burst",
        "type": "adversarial",
        "description": "Technology sector collapse",
        "equity_shock": -0.40,
        "bond_shock": 0.05,
        "vol_multiplier": 2.0,
    },
]


class RedTeamExecutor(BaseExecutor):
    """
    Red Team Executor

    Adversarial scenario search that attempts to break the portfolio:
    - Historical stress scenarios (2008, 2020)
    - Synthetic stress scenarios (rate shocks, stagflation)
    - Adversarial scenarios (designed to find weaknesses)

    Uses seeded random for reproducibility.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "verify_candidates"

    async def execute(
        self,
        candidate: PortfolioCandidate,
        seed: int = 42,
    ) -> RedTeamReport:
        """
        Run adversarial scenario search.

        Args:
            candidate: Portfolio to stress test
            seed: Random seed for reproducibility

        Returns:
            RedTeamReport with scenario results
        """
        logger.info("redteam_check", candidate_id=candidate.candidate_id, seed=seed)

        random.seed(seed + hash(candidate.candidate_id))

        await self.emit_progress(f"Running adversarial scenarios for {candidate.candidate_id}...")

        scenario_results = []
        breaking_scenarios = []
        worst_drawdown = 0
        worst_scenario = None

        for scenario in STRESS_SCENARIOS:
            await self.emit_progress(f"Testing: {scenario['name']}")

            result = self._run_scenario(candidate, scenario)
            scenario_results.append(result)

            if not result.passed:
                breaking_scenarios.append(scenario["id"])

            if result.portfolio_drawdown < worst_drawdown:
                worst_drawdown = result.portfolio_drawdown
                worst_scenario = result

        # Compute aggregate metrics
        avg_drawdown = sum(r.portfolio_drawdown for r in scenario_results) / len(scenario_results)
        max_drawdown = min(r.portfolio_drawdown for r in scenario_results)

        # VaR and CVaR estimates
        sorted_returns = sorted([r.portfolio_return for r in scenario_results])
        var_95 = sorted_returns[max(0, int(len(sorted_returns) * 0.05))]
        cvar_95 = sum(sorted_returns[:max(1, int(len(sorted_returns) * 0.05))]) / max(1, int(len(sorted_returns) * 0.05))

        # Overall pass/fail
        # Fail if any scenario causes > 35% drawdown or if too many breaking scenarios
        overall_passed = len(breaking_scenarios) <= 1 and worst_drawdown > -0.35

        # Create report
        report = RedTeamReport(
            artifact_id=f"redteam-{candidate.candidate_id}-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[candidate.artifact_hash],
            data_classification=DataClassification.DERIVED,
            sources=[candidate.artifact_id],
            candidate_id=candidate.candidate_id,
            seed=seed,
            scenarios_tested=len(scenario_results),
            search_budget=100,
            passed=overall_passed,
            worst_scenario=worst_scenario,
            scenario_results=scenario_results,
            avg_drawdown=round(avg_drawdown, 4),
            max_drawdown=round(max_drawdown, 4),
            var_95=round(var_95, 4),
            cvar_95=round(cvar_95, 4),
            breaking_scenarios=breaking_scenarios,
        )

        # Save artifact
        await self.save_artifact(report)

        logger.info(
            "redteam_complete",
            candidate_id=candidate.candidate_id,
            passed=overall_passed,
            breaking_count=len(breaking_scenarios),
            worst_drawdown=worst_drawdown,
        )

        return report

    def _run_scenario(
        self,
        candidate: PortfolioCandidate,
        scenario: dict,
    ) -> ScenarioResult:
        """Run a single stress scenario on the portfolio."""

        # Compute portfolio impact based on allocation
        equity_impact = candidate.equity_allocation * scenario["equity_shock"]
        bond_impact = candidate.fixed_income_allocation * scenario["bond_shock"]
        cash_impact = candidate.cash_allocation * 0  # Cash is safe

        total_return = equity_impact + bond_impact + cash_impact

        # Add some noise for realism
        noise = random.gauss(0, 0.02)
        total_return += noise

        # Compute drawdown (return is negative in stress)
        drawdown = min(0, total_return)

        # Check if VaR is breached (simplified)
        var_threshold = -0.15  # 15% VaR threshold
        var_breach = total_return < var_threshold

        # Determine severity
        if drawdown > -0.10:
            severity = "low"
        elif drawdown > -0.20:
            severity = "medium"
        elif drawdown > -0.30:
            severity = "high"
        else:
            severity = "critical"

        # Pass if drawdown is acceptable and VaR not breached
        passed = drawdown > -0.30 and not var_breach

        return ScenarioResult(
            scenario_id=scenario["id"],
            scenario_name=scenario["name"],
            scenario_type=scenario["type"],
            description=scenario["description"],
            portfolio_return=round(total_return, 4),
            portfolio_drawdown=round(drawdown, 4),
            var_breach=var_breach,
            severity=severity,
            passed=passed,
        )
