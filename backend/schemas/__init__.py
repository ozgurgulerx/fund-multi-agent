"""
IC Autopilot Schemas - Pydantic models for all workflow artifacts.
Each artifact includes data classification, lineage, and audit metadata.
"""

from .artifacts import (
    ArtifactBase,
    MandateDSL,
    Universe,
    FundFeatures,
    PortfolioCandidate,
    ComplianceReport,
    RedTeamReport,
    Decision,
    RebalancePlan,
    ICMemo,
    RiskAppendix,
    AuditEvent,
)

from .events import (
    WorkflowEvent,
    EventLevel,
    EventKind,
)

from .runs import (
    RunStatus,
    RunMetadata,
    StageStatus,
    StageMetadata,
)

__all__ = [
    # Artifacts
    "ArtifactBase",
    "MandateDSL",
    "Universe",
    "FundFeatures",
    "PortfolioCandidate",
    "ComplianceReport",
    "RedTeamReport",
    "Decision",
    "RebalancePlan",
    "ICMemo",
    "RiskAppendix",
    "AuditEvent",
    # Events
    "WorkflowEvent",
    "EventLevel",
    "EventKind",
    # Runs
    "RunStatus",
    "RunMetadata",
    "StageStatus",
    "StageMetadata",
]
