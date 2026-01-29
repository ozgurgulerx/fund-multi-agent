"""
IC Autopilot API Server - FastAPI with SSE streaming.
Main entry point for the backend API.
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import structlog
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from schemas import WorkflowEvent, EventKind, RunStatus
from schemas.runs import RunMetadata
from services.event_bus import get_event_bus, close_event_bus
from services.artifact_store import get_artifact_store
from services.run_store import get_run_store

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup resources."""
    logger.info("starting_ic_autopilot_api")

    # Initialize services (lazy - will connect on first use)
    # Pre-warm connections can be added here if needed

    yield

    # Cleanup
    logger.info("shutting_down_ic_autopilot_api")
    await close_event_bus()


# Create FastAPI app
app = FastAPI(
    title="IC Autopilot API",
    description="Investment Committee Autopilot - Real-time workflow orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class StartRunRequest(BaseModel):
    """Request to start a new IC run."""
    mandate_id: str
    seed: Optional[int] = 42
    config: Optional[dict] = None


class StartRunResponse(BaseModel):
    """Response after starting a run."""
    run_id: str
    status: str
    message: str


class RunSummary(BaseModel):
    """Summary of a run for list views."""
    run_id: str
    status: str
    mandate_id: str
    created_at: datetime
    progress_pct: float
    current_stage: Optional[str]
    selected_candidate: Optional[str]


# ============================================================================
# Health & Info Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for k8s probes."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/ready")
async def readiness_check():
    """Readiness check - verifies dependencies."""
    checks = {"api": True}

    try:
        event_bus = await get_event_bus()
        await event_bus.redis.ping()
        checks["redis"] = True
    except Exception as e:
        checks["redis"] = False
        logger.error("redis_health_check_failed", error=str(e))

    try:
        run_store = await get_run_store()
        async with run_store.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = True
    except Exception as e:
        checks["postgres"] = False
        logger.error("postgres_health_check_failed", error=str(e))

    all_healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={"ready": all_healthy, "checks": checks}
    )


# ============================================================================
# IC Run Endpoints
# ============================================================================

@app.post("/api/ic/run", response_model=StartRunResponse)
async def start_run(request: StartRunRequest, background_tasks: BackgroundTasks):
    """
    Start a new Investment Committee run.

    Creates the run record, initializes stages, and starts the workflow.
    Returns immediately with run_id - use SSE to track progress.
    """
    try:
        run_store = await get_run_store()

        # Create run
        run = await run_store.create_run(
            mandate_id=request.mandate_id,
            seed=request.seed,
            config=request.config,
        )

        # Start workflow in background
        background_tasks.add_task(execute_workflow, run.run_id)

        logger.info("run_started", run_id=run.run_id, mandate_id=request.mandate_id)

        return StartRunResponse(
            run_id=run.run_id,
            status="started",
            message=f"IC run started. Subscribe to /api/ic/runs/{run.run_id}/events for progress."
        )

    except Exception as e:
        logger.error("run_start_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ic/runs/{run_id}")
async def get_run(run_id: str):
    """Get run status and metadata."""
    run_store = await get_run_store()
    run = await run_store.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return run.model_dump()


@app.get("/api/ic/runs/{run_id}/events")
async def stream_events(request: Request, run_id: str, since: Optional[str] = None):
    """
    SSE endpoint for real-time workflow events.

    Streams events as they occur. Supports reconnection via 'since' parameter
    or Last-Event-ID header.
    """
    # Get last event ID from query param or header
    last_event_id = since or request.headers.get("Last-Event-ID")

    logger.info("sse_connection_started", run_id=run_id, last_event_id=last_event_id)

    async def event_generator():
        """Generate SSE events from Redis stream."""
        event_bus = await get_event_bus()

        try:
            async for event in event_bus.subscribe(run_id, last_event_id):
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("sse_client_disconnected", run_id=run_id)
                    break

                yield {
                    "id": event.event_id,
                    "event": event.kind.value,
                    "data": event.to_sse_data(),
                    "retry": 5000,  # Retry in 5 seconds on disconnect
                }

        except asyncio.CancelledError:
            logger.info("sse_stream_cancelled", run_id=run_id)
        except Exception as e:
            logger.error("sse_stream_error", run_id=run_id, error=str(e))

    return EventSourceResponse(event_generator())


@app.get("/api/ic/runs/{run_id}/artifacts")
async def get_artifacts(run_id: str):
    """Get artifact index for a run."""
    artifact_store = await get_artifact_store()
    artifacts = await artifact_store.list_artifacts(run_id)

    return {
        "run_id": run_id,
        "artifacts": artifacts,
    }


@app.get("/api/ic/runs/{run_id}/artifacts/{artifact_type}")
async def get_artifact(run_id: str, artifact_type: str, version: Optional[int] = None):
    """Get a specific artifact."""
    artifact_store = await get_artifact_store()
    artifact = await artifact_store.load(run_id, artifact_type, version)

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return artifact


@app.get("/api/ic/runs/{run_id}/audit")
async def get_audit_log(run_id: str):
    """Get audit bundle for a run."""
    artifact_store = await get_artifact_store()
    bundle = await artifact_store.get_audit_bundle(run_id)

    return bundle


@app.get("/api/ic/runs")
async def list_runs(
    status: Optional[str] = None,
    mandate_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List IC runs with optional filters."""
    run_store = await get_run_store()

    status_enum = RunStatus(status) if status else None
    runs = await run_store.list_runs(status_enum, mandate_id, limit, offset)

    return {
        "runs": [RunSummary(
            run_id=r.run_id,
            status=r.status.value,
            mandate_id=r.mandate_id,
            created_at=r.created_at,
            progress_pct=r.progress_pct,
            current_stage=r.current_stage,
            selected_candidate=r.selected_candidate,
        ).model_dump() for r in runs],
        "count": len(runs),
        "limit": limit,
        "offset": offset,
    }


# ============================================================================
# Workflow Execution (Background Task)
# ============================================================================

async def execute_workflow(run_id: str):
    """
    Execute the IC workflow for a run.
    This is called as a background task and emits events via Redis.
    """
    from worker.workflow import ICWorkflow

    logger.info("workflow_execution_started", run_id=run_id)

    try:
        run_store = await get_run_store()
        event_bus = await get_event_bus()
        artifact_store = await get_artifact_store()

        # Update run status
        await run_store.update_run_status(run_id, RunStatus.RUNNING)

        # Emit run started event
        await event_bus.publish(WorkflowEvent(
            run_id=run_id,
            kind=EventKind.RUN_STARTED,
            message="IC Autopilot run started",
        ))

        # Execute workflow
        workflow = ICWorkflow(run_id, run_store, event_bus, artifact_store)
        await workflow.execute()

        # Update run status
        await run_store.update_run_status(run_id, RunStatus.COMPLETED)

        # Emit run completed event
        await event_bus.publish(WorkflowEvent(
            run_id=run_id,
            kind=EventKind.RUN_COMPLETED,
            message="IC Autopilot run completed successfully",
        ))

        logger.info("workflow_execution_completed", run_id=run_id)

    except Exception as e:
        logger.error("workflow_execution_failed", run_id=run_id, error=str(e))

        try:
            await run_store.update_run_status(
                run_id, RunStatus.FAILED, error_message=str(e)
            )
            await event_bus.publish(WorkflowEvent(
                run_id=run_id,
                kind=EventKind.RUN_FAILED,
                level="error",
                message=f"Run failed: {str(e)}",
            ))
        except Exception:
            pass


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "5001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
