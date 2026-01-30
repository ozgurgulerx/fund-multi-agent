"""
Dynamic orchestrator for multi-agent portfolio optimization.
Uses Microsoft Agent Framework workflow patterns for orchestration.

Supports multiple orchestration strategies:
- Sequential: Linear agent execution
- Concurrent: Parallel fan-out/fan-in with aggregation
- Handoff: Coordinator-based delegation to specialists
- Magentic: LLM-powered dynamic planning and execution
- DAG: Custom directed acyclic graph workflows
"""

from backend.orchestrator.engine import (
    OrchestratorEngine,
    OrchestratorPlan,
    OrchestratorTask,
    OrchestratorDecision,
    PortfolioAllocation,
    TaskType,
    TaskStatus,
)
from backend.orchestrator.middleware import (
    wrap_agent_with_events,
    AgentEventEmitter,
    EvidenceCollector,
    EvidenceContextProvider,
    WorkflowStateContextProvider,
)
from backend.orchestrator.workflows import (
    WorkflowType,
    create_workflow,
    create_sequential_workflow,
    create_concurrent_risk_return_workflow,
    create_handoff_workflow,
    create_magentic_workflow,
    create_dag_portfolio_workflow,
    create_group_chat_workflow,
)
from backend.orchestrator.executors import (
    WorkflowState,
    PolicyParserExecutor,
    RiskReturnAggregatorExecutor,
    PortfolioFinalizerExecutor,
    ComplianceGateExecutor,
)
from backend.orchestrator.agent_registry import (
    AgentDefinition,
    AgentCondition,
    AgentSelectionResult,
    select_agents_for_policy,
    get_agent_registry,
    get_agent_by_id,
)
from backend.orchestrator.trace_emitter import TraceEmitter

__all__ = [
    # Engine
    "OrchestratorEngine",
    "OrchestratorPlan",
    "OrchestratorTask",
    "OrchestratorDecision",
    "PortfolioAllocation",
    "TaskType",
    "TaskStatus",
    # Middleware & Context Providers
    "wrap_agent_with_events",
    "AgentEventEmitter",
    "EvidenceCollector",
    "EvidenceContextProvider",
    "WorkflowStateContextProvider",
    # Workflows
    "WorkflowType",
    "create_workflow",
    "create_sequential_workflow",
    "create_concurrent_risk_return_workflow",
    "create_handoff_workflow",
    "create_magentic_workflow",
    "create_dag_portfolio_workflow",
    "create_group_chat_workflow",
    # Executors
    "WorkflowState",
    "PolicyParserExecutor",
    "RiskReturnAggregatorExecutor",
    "PortfolioFinalizerExecutor",
    "ComplianceGateExecutor",
    # Agent Registry
    "AgentDefinition",
    "AgentCondition",
    "AgentSelectionResult",
    "select_agents_for_policy",
    "get_agent_registry",
    "get_agent_by_id",
    # Trace Emitter
    "TraceEmitter",
]
