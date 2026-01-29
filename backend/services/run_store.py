"""
Run metadata store using PostgreSQL for durable run state.
Supports run lifecycle, stage checkpointing, and queries.
"""

import json
import os
from datetime import datetime
from typing import Optional, List
import structlog
import asyncpg
from asyncpg import Pool

from schemas.runs import RunMetadata, RunStatus, StageStatus, create_new_run

logger = structlog.get_logger()

# PostgreSQL configuration
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "icautopilot")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PG_SCHEMA = os.getenv("PG_SCHEMA", "ic_autopilot")


class RunStore:
    """
    PostgreSQL-based run metadata store.

    Schema:
        ic_autopilot.runs - Run metadata
        ic_autopilot.stages - Stage checkpoints
        ic_autopilot.events_index - Event summary for querying
    """

    def __init__(self, pool: Pool):
        self.pool = pool

    @classmethod
    async def create(cls) -> "RunStore":
        """Factory method to create RunStore with connection pool."""
        pool = await asyncpg.create_pool(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            min_size=2,
            max_size=10,
        )

        store = cls(pool)
        await store._init_schema()
        logger.info("run_store_connected", host=PGHOST, database=PGDATABASE)
        return store

    async def _init_schema(self):
        """Initialize database schema if not exists."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA};

                CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.runs (
                    run_id VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    mandate_id VARCHAR(100) NOT NULL,
                    seed INTEGER DEFAULT 42,
                    config JSONB DEFAULT '{{}}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    duration_ms INTEGER,
                    current_stage VARCHAR(50),
                    stages_completed INTEGER DEFAULT 0,
                    progress_pct REAL DEFAULT 0,
                    selected_candidate VARCHAR(10),
                    error_message TEXT,
                    error_stage VARCHAR(50),
                    event_count INTEGER DEFAULT 0,
                    artifact_count INTEGER DEFAULT 0,
                    requested_by VARCHAR(100),
                    tags TEXT[],
                    metadata JSONB DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.stages (
                    run_id VARCHAR(50) REFERENCES {PG_SCHEMA}.runs(run_id) ON DELETE CASCADE,
                    stage_id VARCHAR(50),
                    stage_name VARCHAR(100),
                    stage_order INTEGER,
                    status VARCHAR(20) DEFAULT 'pending',
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    duration_ms INTEGER,
                    progress_pct REAL DEFAULT 0,
                    artifacts TEXT[],
                    error_message TEXT,
                    repair_attempts INTEGER DEFAULT 0,
                    PRIMARY KEY (run_id, stage_id)
                );

                CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.candidates (
                    run_id VARCHAR(50) REFERENCES {PG_SCHEMA}.runs(run_id) ON DELETE CASCADE,
                    candidate_id VARCHAR(10),
                    compliance_status VARCHAR(20) DEFAULT 'pending',
                    redteam_status VARCHAR(20) DEFAULT 'pending',
                    compliance_passed BOOLEAN,
                    redteam_passed BOOLEAN,
                    repair_attempts INTEGER DEFAULT 0,
                    is_selected BOOLEAN DEFAULT FALSE,
                    rejection_reason TEXT,
                    scores JSONB DEFAULT '{{}}',
                    PRIMARY KEY (run_id, candidate_id)
                );

                CREATE INDEX IF NOT EXISTS idx_runs_status ON {PG_SCHEMA}.runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_created ON {PG_SCHEMA}.runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_mandate ON {PG_SCHEMA}.runs(mandate_id);
            """)
            logger.info("run_store_schema_initialized")

    async def create_run(
        self,
        mandate_id: str,
        seed: int = 42,
        config: dict = None,
        requested_by: str = None,
    ) -> RunMetadata:
        """Create a new run with default stages."""
        run = create_new_run(mandate_id, seed, config)
        run.requested_by = requested_by

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Insert run
                await conn.execute(f"""
                    INSERT INTO {PG_SCHEMA}.runs
                    (run_id, mandate_id, seed, config, requested_by, tags)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, run.run_id, mandate_id, seed, json.dumps(config or {}), requested_by, [])

                # Insert stages
                for stage in run.stages:
                    await conn.execute(f"""
                        INSERT INTO {PG_SCHEMA}.stages
                        (run_id, stage_id, stage_name, stage_order)
                        VALUES ($1, $2, $3, $4)
                    """, run.run_id, stage.stage_id, stage.stage_name, stage.stage_order)

                # Insert candidates
                for candidate in run.candidates:
                    await conn.execute(f"""
                        INSERT INTO {PG_SCHEMA}.candidates
                        (run_id, candidate_id)
                        VALUES ($1, $2)
                    """, run.run_id, candidate.candidate_id)

        logger.info("run_created", run_id=run.run_id, mandate_id=mandate_id)
        return run

    async def get_run(self, run_id: str) -> Optional[RunMetadata]:
        """Get run metadata by ID."""
        async with self.pool.acquire() as conn:
            # Get run
            row = await conn.fetchrow(f"""
                SELECT * FROM {PG_SCHEMA}.runs WHERE run_id = $1
            """, run_id)

            if not row:
                return None

            run = RunMetadata(
                run_id=row["run_id"],
                status=RunStatus(row["status"]),
                mandate_id=row["mandate_id"],
                seed=row["seed"],
                config=json.loads(row["config"]) if row["config"] else {},
                created_at=row["created_at"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                duration_ms=row["duration_ms"],
                current_stage=row["current_stage"],
                stages_completed=row["stages_completed"] or 0,
                progress_pct=row["progress_pct"] or 0,
                selected_candidate=row["selected_candidate"],
                error_message=row["error_message"],
                error_stage=row["error_stage"],
                event_count=row["event_count"] or 0,
                artifact_count=row["artifact_count"] or 0,
                requested_by=row["requested_by"],
                tags=row["tags"] or [],
            )

            # Get stages
            stage_rows = await conn.fetch(f"""
                SELECT * FROM {PG_SCHEMA}.stages
                WHERE run_id = $1 ORDER BY stage_order
            """, run_id)

            from schemas.runs import StageMetadata
            for srow in stage_rows:
                run.stages.append(StageMetadata(
                    stage_id=srow["stage_id"],
                    stage_name=srow["stage_name"],
                    stage_order=srow["stage_order"],
                    status=StageStatus(srow["status"]),
                    started_at=srow["started_at"],
                    completed_at=srow["completed_at"],
                    duration_ms=srow["duration_ms"],
                    progress_pct=srow["progress_pct"] or 0,
                    artifacts=srow["artifacts"] or [],
                    error_message=srow["error_message"],
                    repair_attempts=srow["repair_attempts"] or 0,
                ))

            # Get candidates
            candidate_rows = await conn.fetch(f"""
                SELECT * FROM {PG_SCHEMA}.candidates WHERE run_id = $1
            """, run_id)

            from schemas.runs import CandidateProgress
            for crow in candidate_rows:
                run.candidates.append(CandidateProgress(
                    candidate_id=crow["candidate_id"],
                    compliance_status=StageStatus(crow["compliance_status"]),
                    redteam_status=StageStatus(crow["redteam_status"]),
                    compliance_passed=crow["compliance_passed"],
                    redteam_passed=crow["redteam_passed"],
                    repair_attempts=crow["repair_attempts"] or 0,
                    is_selected=crow["is_selected"] or False,
                    rejection_reason=crow["rejection_reason"],
                ))

            return run

    async def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        error_message: str = None,
        error_stage: str = None,
    ):
        """Update run status."""
        async with self.pool.acquire() as conn:
            now = datetime.utcnow()
            updates = {"status": status.value}

            if status == RunStatus.RUNNING:
                updates["started_at"] = now
            elif status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]:
                updates["completed_at"] = now

            if error_message:
                updates["error_message"] = error_message
            if error_stage:
                updates["error_stage"] = error_stage

            set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates.keys()))
            values = [run_id] + list(updates.values())

            await conn.execute(f"""
                UPDATE {PG_SCHEMA}.runs SET {set_clause} WHERE run_id = $1
            """, *values)

    async def update_stage(
        self,
        run_id: str,
        stage_id: str,
        status: StageStatus,
        duration_ms: int = None,
        artifacts: list = None,
        error_message: str = None,
    ):
        """Update stage status and metadata."""
        async with self.pool.acquire() as conn:
            now = datetime.utcnow()

            if status == StageStatus.RUNNING:
                await conn.execute(f"""
                    UPDATE {PG_SCHEMA}.stages
                    SET status = $3, started_at = $4
                    WHERE run_id = $1 AND stage_id = $2
                """, run_id, stage_id, status.value, now)
            else:
                await conn.execute(f"""
                    UPDATE {PG_SCHEMA}.stages
                    SET status = $3, completed_at = $4, duration_ms = $5,
                        artifacts = $6, error_message = $7
                    WHERE run_id = $1 AND stage_id = $2
                """, run_id, stage_id, status.value, now, duration_ms, artifacts or [], error_message)

            # Update run progress
            completed = await conn.fetchval(f"""
                SELECT COUNT(*) FROM {PG_SCHEMA}.stages
                WHERE run_id = $1 AND status IN ('succeeded', 'skipped')
            """, run_id)
            total = await conn.fetchval(f"""
                SELECT COUNT(*) FROM {PG_SCHEMA}.stages WHERE run_id = $1
            """, run_id)

            progress = (completed / total * 100) if total > 0 else 0
            await conn.execute(f"""
                UPDATE {PG_SCHEMA}.runs
                SET current_stage = $2, stages_completed = $3, progress_pct = $4
                WHERE run_id = $1
            """, run_id, stage_id, completed, progress)

    async def list_runs(
        self,
        status: Optional[RunStatus] = None,
        mandate_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[RunMetadata]:
        """List runs with optional filters."""
        async with self.pool.acquire() as conn:
            conditions = []
            params = []
            param_idx = 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status.value)
                param_idx += 1

            if mandate_id:
                conditions.append(f"mandate_id = ${param_idx}")
                params.append(mandate_id)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            params.extend([limit, offset])
            rows = await conn.fetch(f"""
                SELECT run_id FROM {PG_SCHEMA}.runs
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """, *params)

            runs = []
            for row in rows:
                run = await self.get_run(row["run_id"])
                if run:
                    runs.append(run)

            return runs

    async def close(self):
        """Close connection pool."""
        await self.pool.close()


# Singleton instance
_run_store: Optional[RunStore] = None


async def get_run_store() -> RunStore:
    """Get or create the singleton RunStore instance."""
    global _run_store
    if _run_store is None:
        _run_store = await RunStore.create()
    return _run_store
