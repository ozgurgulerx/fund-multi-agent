"""
Rebalance Planner Executor - Stage 8
Creates rebalancing plan with trade list and execution guidance.
"""

import uuid
from typing import List
import structlog

from schemas.artifacts import (
    PortfolioCandidate, RebalancePlan, Trade, DataClassification,
)
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()


class RebalancePlannerExecutor(BaseExecutor):
    """
    Rebalance Planner Executor

    Creates a rebalancing plan from current portfolio to target:
    - Generates trade list (buys, sells, holds)
    - Estimates transaction costs
    - Provides execution guidance
    - Identifies liquidity concerns
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "rebalance_plan"

    async def execute(self, candidate: PortfolioCandidate) -> RebalancePlan:
        """
        Create rebalancing plan for selected candidate.

        For demo, assumes starting from cash (no current positions).

        Args:
            candidate: Selected portfolio candidate

        Returns:
            RebalancePlan artifact
        """
        logger.info("creating_rebalance_plan", candidate_id=candidate.candidate_id)

        await self.emit_progress("Generating trade list...")

        trades = []
        total_turnover = 0

        # Generate trades (from cash to target)
        for holding in candidate.holdings:
            # All positions are buys (from cash)
            trade = Trade(
                fund_accession=holding.fund_accession,
                fund_name=holding.fund_name,
                action="BUY",
                current_weight=0.0,
                target_weight=holding.weight,
                trade_weight=holding.weight,
                estimated_cost=holding.weight * 0.0010,  # 10bps assumed
            )
            trades.append(trade)
            total_turnover += holding.weight

        # Sort trades by size for execution priority
        trades.sort(key=lambda t: t.trade_weight, reverse=True)

        # Calculate totals
        total_buys = sum(1 for t in trades if t.action == "BUY")
        total_sells = sum(1 for t in trades if t.action == "SELL")
        total_holds = sum(1 for t in trades if t.action == "HOLD")

        # Estimate costs
        estimated_transaction_cost = sum(t.estimated_cost for t in trades)
        estimated_market_impact = total_turnover * 0.0005  # 5bps impact

        # Execution priority (large liquid trades first)
        execution_priority = [t.fund_accession for t in trades[:5]]

        # Liquidity warnings for large positions
        liquidity_warnings = []
        for trade in trades:
            if trade.trade_weight > 0.08:
                liquidity_warnings.append(
                    f"{trade.fund_name}: {trade.trade_weight:.1%} position may require multiple days to execute"
                )

        await self.emit_progress("Calculating costs and execution plan...")

        # Create plan
        plan = RebalancePlan(
            artifact_id=f"rebalance-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[candidate.artifact_hash],
            data_classification=DataClassification.DERIVED,
            sources=[candidate.artifact_id],
            candidate_id=candidate.candidate_id,
            trades=trades,
            total_buys=total_buys,
            total_sells=total_sells,
            total_holds=total_holds,
            total_turnover=round(total_turnover, 4),
            estimated_transaction_cost=round(estimated_transaction_cost, 6),
            estimated_market_impact=round(estimated_market_impact, 6),
            execution_priority=execution_priority,
            liquidity_warnings=liquidity_warnings,
        )

        # Save artifact
        await self.save_artifact(plan)

        logger.info(
            "rebalance_plan_created",
            trades=len(trades),
            turnover=total_turnover,
            cost=estimated_transaction_cost,
        )

        return plan
