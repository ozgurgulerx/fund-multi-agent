"""
Build Universe Executor - Stage 2
Queries fund database to build eligible investment universe based on mandate constraints.
"""

import os
import uuid
from typing import List
import asyncpg
import structlog

from schemas.artifacts import Universe, FundInfo, MandateDSL, DataClassification
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()

# Database configuration
PGHOST = os.getenv("PGHOST", "aistartupstr.postgres.database.azure.com")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "fundrag")
PGUSER = os.getenv("PGUSER", "ozgurguler")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PG_SCHEMA = os.getenv("PG_FUND_SCHEMA", "nport_funds")


class BuildUniverseExecutor(BaseExecutor):
    """
    Stage 2: Build Universe

    Queries the fund database to build an investment universe
    filtered by mandate constraints (asset class, size, liquidity).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "build_universe"

    async def execute(self, mandate: MandateDSL) -> Universe:
        """
        Build investment universe from fund database.

        Args:
            mandate: Mandate definition with constraints

        Returns:
            Universe artifact with eligible funds
        """
        logger.info("building_universe", mandate_id=mandate.mandate_id)

        await self.emit_progress("Connecting to fund database...")

        # Connect to database - READ-ONLY CONNECTION
        # CRITICAL: This connection is READ-ONLY. Never modify nport_funds data.
        conn = await asyncpg.connect(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            ssl="require",
        )

        try:
            # Set connection to READ-ONLY mode to prevent accidental writes
            await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            await self.emit_progress("Querying funds and holdings...")

            # Query funds with asset allocation breakdown
            funds = await self._query_funds(conn)

            await self.emit_progress(f"Found {len(funds)} funds, filtering by mandate...")

            # Filter by mandate constraints
            eligible_funds = self._filter_by_mandate(funds, mandate)

            await self.emit_progress(f"Universe: {len(eligible_funds)} eligible funds")

            # Calculate universe statistics
            total_aum = sum(f.total_assets for f in eligible_funds)
            asset_class_breakdown = self._calculate_asset_breakdown(eligible_funds)
            manager_breakdown = self._calculate_manager_breakdown(eligible_funds)

            # Create Universe artifact
            universe = Universe(
                artifact_id=f"universe-{uuid.uuid4().hex[:8]}",
                run_id=self.run_id,
                stage_id=self.stage_id,
                producer=self.executor_name,
                parent_hashes=[mandate.artifact_hash],
                data_classification=DataClassification.DERIVED,
                sources=["nport_funds.fund_reported_info", "nport_funds.fund_reported_holding"],
                universe_name=f"Universe for {mandate.mandate_name}",
                filter_criteria={
                    "min_equity": mandate.min_equity,
                    "max_equity": mandate.max_equity,
                    "min_fixed_income": mandate.min_fixed_income,
                    "max_fixed_income": mandate.max_fixed_income,
                    "min_liquidity_ratio": mandate.min_liquidity_ratio,
                },
                funds=eligible_funds,
                total_fund_count=len(eligible_funds),
                total_aum=total_aum,
                asset_class_breakdown=asset_class_breakdown,
                manager_breakdown=manager_breakdown,
            )

            # Save artifact
            await self.save_artifact(universe)

            logger.info(
                "universe_built",
                fund_count=len(eligible_funds),
                total_aum=total_aum,
            )

            return universe

        finally:
            await conn.close()

    async def _query_funds(self, conn: asyncpg.Connection) -> List[FundInfo]:
        """Query fund database with asset allocation breakdown."""
        query = f"""
            WITH fund_allocations AS (
                SELECT
                    h.accession_number,
                    SUM(CASE WHEN h.asset_cat = 'EC' THEN COALESCE(h.percentage, 0) ELSE 0 END) as equity_pct,
                    SUM(CASE WHEN h.asset_cat = 'DBT' THEN COALESCE(h.percentage, 0) ELSE 0 END) as fixed_income_pct,
                    SUM(CASE WHEN h.asset_cat IN ('MF', 'STIV') THEN COALESCE(h.percentage, 0) ELSE 0 END) as cash_pct,
                    SUM(CASE WHEN h.asset_cat NOT IN ('EC', 'DBT', 'MF', 'STIV') THEN COALESCE(h.percentage, 0) ELSE 0 END) as other_pct,
                    COUNT(*) as holding_count
                FROM {PG_SCHEMA}.fund_reported_holding h
                GROUP BY h.accession_number
            )
            SELECT
                f.accession_number,
                f.series_name,
                f.series_id,
                r.registrant_name as manager_name,
                COALESCE(f.total_assets, 0) as total_assets,
                COALESCE(f.net_assets, 0) as net_assets,
                CASE
                    WHEN a.equity_pct > 0.6 THEN 'equity'
                    WHEN a.fixed_income_pct > 0.6 THEN 'fixed_income'
                    WHEN a.cash_pct > 0.4 THEN 'money_market'
                    ELSE 'balanced'
                END as primary_asset_class,
                COALESCE(a.holding_count, 0) as holding_count,
                COALESCE(a.equity_pct, 0) as equity_pct,
                COALESCE(a.fixed_income_pct, 0) as fixed_income_pct,
                COALESCE(a.cash_pct, 0) as cash_pct,
                COALESCE(a.other_pct, 0) as other_pct
            FROM {PG_SCHEMA}.fund_reported_info f
            JOIN {PG_SCHEMA}.registrant r ON f.accession_number = r.accession_number
            LEFT JOIN fund_allocations a ON f.accession_number = a.accession_number
            WHERE f.total_assets > 100000000  -- Min $100M AUM
            ORDER BY f.total_assets DESC
            LIMIT 200
        """

        rows = await conn.fetch(query)

        funds = []
        for row in rows:
            funds.append(FundInfo(
                accession_number=row["accession_number"],
                series_name=row["series_name"] or "Unknown",
                series_id=row["series_id"] or "",
                manager_name=row["manager_name"] or "Unknown",
                total_assets=float(row["total_assets"] or 0),
                net_assets=float(row["net_assets"] or 0),
                primary_asset_class=row["primary_asset_class"],
                holding_count=int(row["holding_count"] or 0),
                equity_pct=float(row["equity_pct"] or 0),
                fixed_income_pct=float(row["fixed_income_pct"] or 0),
                cash_pct=float(row["cash_pct"] or 0),
                other_pct=float(row["other_pct"] or 0),
            ))

        return funds

    def _filter_by_mandate(self, funds: List[FundInfo], mandate: MandateDSL) -> List[FundInfo]:
        """Filter funds by mandate constraints."""
        eligible = []

        for fund in funds:
            # Check equity constraints
            if fund.equity_pct < mandate.min_equity or fund.equity_pct > mandate.max_equity:
                continue

            # Check fixed income constraints
            if fund.fixed_income_pct < mandate.min_fixed_income or fund.fixed_income_pct > mandate.max_fixed_income:
                continue

            # Check liquidity (cash + liquid assets)
            liquidity = fund.cash_pct + (fund.equity_pct * 0.9)  # Assume 90% of equity is liquid
            if liquidity < mandate.min_liquidity_ratio * 0.5:  # Relaxed check
                continue

            eligible.append(fund)

        return eligible

    def _calculate_asset_breakdown(self, funds: List[FundInfo]) -> dict:
        """Calculate aggregate asset class breakdown."""
        if not funds:
            return {}

        total_aum = sum(f.total_assets for f in funds)
        if total_aum == 0:
            return {}

        return {
            "equity": sum(f.total_assets * f.equity_pct for f in funds) / total_aum,
            "fixed_income": sum(f.total_assets * f.fixed_income_pct for f in funds) / total_aum,
            "cash": sum(f.total_assets * f.cash_pct for f in funds) / total_aum,
            "other": sum(f.total_assets * f.other_pct for f in funds) / total_aum,
        }

    def _calculate_manager_breakdown(self, funds: List[FundInfo]) -> dict:
        """Count funds by manager."""
        breakdown = {}
        for fund in funds:
            manager = fund.manager_name
            breakdown[manager] = breakdown.get(manager, 0) + 1
        return dict(sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:10])
