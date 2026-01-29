"""
Run and stage metadata schemas for workflow state management.
Stored in Cosmos DB or PostgreSQL for durability.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class RunStatus(str, Enum):
    """Workflow run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(str, Enum):
    """Individual stage status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPAIRED = "repaired"  # Failed then recovered


class StageMetadata(BaseModel):
    """
    Metadata for a single workflow stage.
    Used for checkpointing and progress tracking.
    """
    stage_id: str = Field(description="Unique stage identifier")
    stage_name: str = Field(description="Human-readable stage name")
    stage_order: int = Field(description="Execution order (1-10)")

    # Status
    status: StageStatus = Field(default=StageStatus.PENDING)

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Progress
    progress_pct: float = Field(default=0, ge=0, le=100)

    # Artifacts produced
    artifacts: List[str] = Field(default_factory=list, description="Artifact IDs produced")

    # Error info
    error_message: Optional[str] = None
    error_code: Optional[str] = None

    # Repair tracking
    repair_attempts: int = Field(default=0)
    max_repair_attempts: int = Field(default=3)


class CandidateProgress(BaseModel):
    """Progress tracking for individual candidates (A/B/C)."""
    candidate_id: str = Field(description="Candidate identifier (A, B, C)")

    # Status
    compliance_status: StageStatus = Field(default=StageStatus.PENDING)
    redteam_status: StageStatus = Field(default=StageStatus.PENDING)

    # Results
    compliance_passed: Optional[bool] = None
    redteam_passed: Optional[bool] = None

    # Repair
    repair_attempts: int = 0
    is_repaired: bool = False

    # Selection
    is_selected: bool = False
    rejection_reason: Optional[str] = None

    # Scores
    optimization_score: Optional[float] = None
    compliance_score: Optional[float] = None
    risk_score: Optional[float] = None
    final_score: Optional[float] = None


class RunMetadata(BaseModel):
    """
    Complete metadata for a workflow run.
    Primary record for run tracking in database.
    """
    # Identification
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique run identifier")

    # Status
    status: RunStatus = Field(default=RunStatus.PENDING)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Configuration
    mandate_id: str = Field(description="Mandate used for this run")
    seed: int = Field(default=42, description="Random seed for reproducibility")
    config: Dict[str, Any] = Field(default_factory=dict, description="Run configuration overrides")

    # Progress
    current_stage: Optional[str] = Field(default=None, description="Currently executing stage")
    stages_completed: int = Field(default=0)
    total_stages: int = Field(default=10)
    progress_pct: float = Field(default=0, ge=0, le=100)

    # Stage details
    stages: List[StageMetadata] = Field(default_factory=list)

    # Candidate tracking
    candidates: List[CandidateProgress] = Field(default_factory=list)
    selected_candidate: Optional[str] = None

    # Artifacts
    artifact_count: int = Field(default=0)
    artifacts_index: Dict[str, str] = Field(default_factory=dict, description="artifact_type -> latest artifact_id")

    # Error handling
    error_message: Optional[str] = None
    error_stage: Optional[str] = None

    # Audit
    event_count: int = Field(default=0)
    last_event_at: Optional[datetime] = None

    # User context
    requested_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    def get_stage(self, stage_id: str) -> Optional[StageMetadata]:
        """Get stage metadata by ID."""
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    def update_progress(self):
        """Recalculate progress percentage from stage completion."""
        if not self.stages:
            self.progress_pct = 0
            return

        completed = sum(1 for s in self.stages if s.status in [StageStatus.SUCCEEDED, StageStatus.SKIPPED])
        self.stages_completed = completed
        self.progress_pct = (completed / len(self.stages)) * 100


# Default stage configuration
DEFAULT_STAGES = [
    StageMetadata(stage_id="load_mandate", stage_name="Load Mandate Template", stage_order=1),
    StageMetadata(stage_id="build_universe", stage_name="Build Universe", stage_order=2),
    StageMetadata(stage_id="compute_features", stage_name="Compute Features", stage_order=3),
    StageMetadata(stage_id="generate_candidates", stage_name="Generate Candidates", stage_order=4),
    StageMetadata(stage_id="verify_candidates", stage_name="Verify Candidates", stage_order=5),
    StageMetadata(stage_id="repair_loop", stage_name="Repair Loop", stage_order=6),
    StageMetadata(stage_id="rank_select", stage_name="Rank and Select", stage_order=7),
    StageMetadata(stage_id="rebalance_plan", stage_name="Rebalance Planner", stage_order=8),
    StageMetadata(stage_id="write_memo", stage_name="Write Memo", stage_order=9),
    StageMetadata(stage_id="audit_finalize", stage_name="Audit Finalize", stage_order=10),
]


def create_new_run(mandate_id: str, seed: int = 42, config: Dict[str, Any] = None) -> RunMetadata:
    """Factory function to create a new run with default stages."""
    run = RunMetadata(
        mandate_id=mandate_id,
        seed=seed,
        config=config or {},
        stages=[stage.model_copy(deep=True) for stage in DEFAULT_STAGES],
        candidates=[
            CandidateProgress(candidate_id="A"),
            CandidateProgress(candidate_id="B"),
            CandidateProgress(candidate_id="C"),
        ]
    )
    return run
