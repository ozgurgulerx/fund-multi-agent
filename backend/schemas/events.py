"""
Workflow event schemas for SSE streaming.
Events are published to Redis Streams and consumed by the SSE endpoint.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


class EventLevel(str, Enum):
    """Event severity level."""
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class EventKind(str, Enum):
    """
    Event types for workflow progress tracking.
    Each event kind maps to specific UI updates.
    """
    # Lifecycle events
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"

    # Stage events
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    STAGE_SKIPPED = "stage_skipped"

    # Agent/executor events
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    EXECUTOR_STARTED = "executor_started"
    EXECUTOR_COMPLETED = "executor_completed"

    # Tool events
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"

    # Candidate events (for fan-out visualization)
    CANDIDATE_CREATED = "candidate_created"
    CANDIDATE_PASSED = "candidate_passed"
    CANDIDATE_FAILED = "candidate_failed"
    CANDIDATE_REPAIRED = "candidate_repaired"

    # Verification events
    COMPLIANCE_CHECK = "compliance_check"
    REDTEAM_CHECK = "redteam_check"
    REPAIR_ITERATION = "repair_iteration"

    # Decision events
    DECISION_MADE = "decision_made"
    ARTIFACT_PERSISTED = "artifact_persisted"

    # Progress events
    PROGRESS_UPDATE = "progress_update"
    HEARTBEAT = "heartbeat"


class WorkflowEvent(BaseModel):
    """
    Event schema for real-time workflow progress streaming.
    Published to Redis Streams, consumed by SSE endpoint.
    """
    # Identification
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = Field(description="Workflow run identifier")

    # Timing
    ts: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    sequence: int = Field(default=0, description="Event sequence number within run")

    # Classification
    level: EventLevel = Field(default=EventLevel.INFO)
    kind: EventKind = Field(description="Event type")

    # Context
    stage_id: Optional[str] = Field(default=None, description="Current stage ID")
    stage_name: Optional[str] = Field(default=None, description="Current stage name")
    candidate_id: Optional[str] = Field(default=None, description="Candidate ID (A/B/C) for fan-out events")

    # Actor
    agent_name: Optional[str] = Field(default=None, description="Agent that triggered event")
    executor_name: Optional[str] = Field(default=None, description="Executor that triggered event")
    tool_name: Optional[str] = Field(default=None, description="Tool being called")

    # Content
    message: str = Field(description="Short human-readable message")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Additional event data (keep small)")

    # Tracing
    trace_id: Optional[str] = Field(default=None, description="OpenTelemetry trace ID")
    span_id: Optional[str] = Field(default=None, description="OpenTelemetry span ID")
    parent_span_id: Optional[str] = Field(default=None)

    # Progress (for stage events)
    progress_pct: Optional[float] = Field(default=None, ge=0, le=100, description="Stage progress percentage")
    duration_ms: Optional[int] = Field(default=None, description="Duration in milliseconds")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_sse_data(self) -> str:
        """Format event for SSE transmission."""
        return self.model_dump_json()


class EventBatch(BaseModel):
    """Batch of events for bulk operations."""
    events: list[WorkflowEvent] = Field(default_factory=list)
    run_id: str
    from_sequence: int
    to_sequence: int


# Event factory functions for common events
def stage_started_event(
    run_id: str,
    stage_id: str,
    stage_name: str,
    sequence: int = 0,
    trace_id: Optional[str] = None
) -> WorkflowEvent:
    """Create a stage started event."""
    return WorkflowEvent(
        run_id=run_id,
        kind=EventKind.STAGE_STARTED,
        stage_id=stage_id,
        stage_name=stage_name,
        sequence=sequence,
        message=f"Stage '{stage_name}' started",
        trace_id=trace_id
    )


def stage_completed_event(
    run_id: str,
    stage_id: str,
    stage_name: str,
    duration_ms: int,
    sequence: int = 0,
    artifacts: list[str] = None,
    trace_id: Optional[str] = None
) -> WorkflowEvent:
    """Create a stage completed event."""
    return WorkflowEvent(
        run_id=run_id,
        kind=EventKind.STAGE_COMPLETED,
        stage_id=stage_id,
        stage_name=stage_name,
        sequence=sequence,
        duration_ms=duration_ms,
        message=f"Stage '{stage_name}' completed in {duration_ms}ms",
        payload={"artifacts": artifacts or []},
        trace_id=trace_id
    )


def candidate_event(
    run_id: str,
    candidate_id: str,
    kind: EventKind,
    message: str,
    sequence: int = 0,
    stage_id: Optional[str] = None,
    payload: Dict[str, Any] = None
) -> WorkflowEvent:
    """Create a candidate-related event."""
    return WorkflowEvent(
        run_id=run_id,
        kind=kind,
        candidate_id=candidate_id,
        stage_id=stage_id,
        sequence=sequence,
        message=message,
        payload=payload or {}
    )


def tool_called_event(
    run_id: str,
    tool_name: str,
    executor_name: str,
    sequence: int = 0,
    stage_id: Optional[str] = None,
    trace_id: Optional[str] = None
) -> WorkflowEvent:
    """Create a tool called event."""
    return WorkflowEvent(
        run_id=run_id,
        kind=EventKind.TOOL_CALLED,
        tool_name=tool_name,
        executor_name=executor_name,
        stage_id=stage_id,
        sequence=sequence,
        message=f"Tool '{tool_name}' called by {executor_name}",
        trace_id=trace_id
    )


def heartbeat_event(run_id: str, sequence: int = 0) -> WorkflowEvent:
    """Create a heartbeat event for SSE keepalive."""
    return WorkflowEvent(
        run_id=run_id,
        kind=EventKind.HEARTBEAT,
        sequence=sequence,
        message="heartbeat"
    )
