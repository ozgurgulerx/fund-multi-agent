"""
Compute Features Executor - Stage 3
Computes fund features for optimization and analysis.
"""

import os
import uuid
from typing import List
import asyncpg
import structlog

from schemas.artifacts import FundFeatures, Universe, FundInfo, DataClassification
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()

# Database configuration
PGHOST = os.getenv("PGHOST", "aistartupstr.postgres.database.azure.com")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "fundrag")
PGUSER = os.getenv("PGUSER", "ozgurguler")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PG_SCHEMA = os.getenv("PG_FUND_SCHEMA", "nport_funds")


class ComputeFeaturesExecutor(BaseExecutor):
    """
    Stage 3: Compute Features

    Computes features for each fund in the universe:
    - Return features (monthly returns, annualized)
    - Risk features (volatility, Sharpe, drawdown)
    - Allocation features (asset class exposures)
    - Concentration features (HHI, top-10)
    - Quality features (credit rating, duration)
    - Liquidity features
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "compute_features"

    async def execute(self, universe: Universe) -> List[FundFeatures]:
        """
        Compute features for all funds in universe.

        Args:
            universe: Universe with eligible funds

        Returns:
            List of FundFeatures artifacts
        """
        logger.info("computing_features", fund_count=universe.total_fund_count)

        await self.emit_progress(f"Computing features for {universe.total_fund_count} funds...")

        # Connect to database
        conn = await asyncpg.connect(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            ssl="require",
        )

        try:
            features_list = []
            total = len(universe.funds)

            for i, fund in enumerate(universe.funds):
                if i % 20 == 0:
                    progress = (i / total) * 100
                    await self.emit_progress(
                        f"Processing fund {i+1}/{total}",
                        progress_pct=progress,
                    )

                features = await self._compute_fund_features(conn, fund)
                features_list.append(features)

            await self.emit_progress("Saving feature artifacts...")

            # Save all features
            for features in features_list:
                await self.save_artifact(features)

            logger.info("features_computed", count=len(features_list))

            return features_list

        finally:
            await conn.close()

    async def _compute_fund_features(
        self,
        conn: asyncpg.Connection,
        fund: FundInfo,
    ) -> FundFeatures:
        """Compute features for a single fund."""

        # Get monthly returns from database
        returns = await self._get_monthly_returns(conn, fund.accession_number)

        # Get concentration metrics
        concentration = await self._get_concentration_metrics(conn, fund.accession_number)

        # Compute derived features
        annualized_return = None
        volatility = None
        sharpe_ratio = None

        if returns["monthly_return_1"] is not None:
            # Simple annualization from available returns
            avg_monthly = sum(
                r for r in [returns["monthly_return_1"], returns["monthly_return_2"], returns["monthly_return_3"]]
                if r is not None
            ) / 3
            annualized_return = avg_monthly * 12
            volatility = abs(avg_monthly) * 3.46  # sqrt(12) approximation
            if volatility > 0:
                sharpe_ratio = annualized_return / volatility

        # Create features artifact
        features = FundFeatures(
            artifact_id=f"features-{fund.accession_number[:8]}-{uuid.uuid4().hex[:4]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            data_classification=DataClassification.DERIVED,
            sources=[f"fund:{fund.accession_number}"],
            accession_number=fund.accession_number,
            series_name=fund.series_name,
            monthly_return_1=returns["monthly_return_1"],
            monthly_return_2=returns["monthly_return_2"],
            monthly_return_3=returns["monthly_return_3"],
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            equity_exposure=fund.equity_pct,
            fixed_income_exposure=fund.fixed_income_pct,
            cash_exposure=fund.cash_pct,
            alternative_exposure=fund.other_pct,
            top_10_concentration=concentration["top_10"],
            sector_hhi=concentration["hhi"],
            liquidity_score=self._compute_liquidity_score(fund),
        )

        return features

    async def _get_monthly_returns(self, conn: asyncpg.Connection, accession_number: str) -> dict:
        """Get monthly return data."""
        query = f"""
            SELECT monthly_total_return1, monthly_total_return2, monthly_total_return3
            FROM {PG_SCHEMA}.monthly_total_return
            WHERE accession_number = $1
            LIMIT 1
        """

        row = await conn.fetchrow(query, accession_number)

        if row:
            return {
                "monthly_return_1": float(row["monthly_total_return1"]) if row["monthly_total_return1"] else None,
                "monthly_return_2": float(row["monthly_total_return2"]) if row["monthly_total_return2"] else None,
                "monthly_return_3": float(row["monthly_total_return3"]) if row["monthly_total_return3"] else None,
            }

        return {
            "monthly_return_1": None,
            "monthly_return_2": None,
            "monthly_return_3": None,
        }

    async def _get_concentration_metrics(self, conn: asyncpg.Connection, accession_number: str) -> dict:
        """Compute concentration metrics from holdings."""
        query = f"""
            WITH holding_pcts AS (
                SELECT percentage
                FROM {PG_SCHEMA}.fund_reported_holding
                WHERE accession_number = $1 AND percentage IS NOT NULL
                ORDER BY percentage DESC
            )
            SELECT
                COALESCE(SUM(CASE WHEN rn <= 10 THEN percentage ELSE 0 END), 0) as top_10,
                COALESCE(SUM(percentage * percentage), 0) as hhi
            FROM (
                SELECT percentage, ROW_NUMBER() OVER (ORDER BY percentage DESC) as rn
                FROM holding_pcts
            ) ranked
        """

        row = await conn.fetchrow(query, accession_number)

        if row:
            return {
                "top_10": float(row["top_10"] or 0),
                "hhi": float(row["hhi"] or 0),
            }

        return {"top_10": 0.0, "hhi": 0.0}

    def _compute_liquidity_score(self, fund: FundInfo) -> float:
        """Compute liquidity score based on asset allocation."""
        # Cash is most liquid, equity somewhat liquid, bonds less so
        score = (
            fund.cash_pct * 1.0 +
            fund.equity_pct * 0.8 +
            fund.fixed_income_pct * 0.5 +
            fund.other_pct * 0.3
        )
        return min(1.0, score)
