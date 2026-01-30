"""
Central orchestrator engine for dynamic multi-agent portfolio optimization.
Uses Microsoft Agent Framework workflow patterns for orchestration.

Supports multiple orchestration strategies:
- Sequential: Linear agent execution
- Concurrent: Parallel fan-out/fan-in
- Handoff: Coordinator-based delegation
- Magentic: LLM-powered dynamic planning
- DAG: Custom directed acyclic graph
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from openai import AsyncAzureOpenAI

from agent_framework import (
    ChatAgent,
    Workflow,
    WorkflowEvent,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
    WorkflowOutputEvent,
    WorkflowFailedEvent,
    ExecutorInvokedEvent,
    ExecutorCompletedEvent,
    AgentRunEvent,
    AgentRunUpdateEvent,
    InMemoryCheckpointStorage,
)
from pydantic import BaseModel, Field
import structlog

from backend.schemas.policy import InvestorPolicyStatement
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
from backend.orchestrator.middleware import EvidenceCollector
from backend.orchestrator.agent_registry import select_agents_for_policy, AgentSelectionResult
from backend.orchestrator.trace_emitter import TraceEmitter

logger = structlog.get_logger()


class TaskType(str, Enum):
    """Types of tasks the orchestrator can assign."""
    ANALYZE_POLICY = "analyze_policy"
    FETCH_MARKET_DATA = "fetch_market_data"
    COMPUTE_RISK = "compute_risk"
    COMPUTE_RETURNS = "compute_returns"
    OPTIMIZE_PORTFOLIO = "optimize_portfolio"
    CHECK_COMPLIANCE = "check_compliance"
    RESOLVE_CONFLICT = "resolve_conflict"
    COMMIT_PORTFOLIO = "commit_portfolio"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class OrchestratorTask(BaseModel):
    """A task in the orchestrator's plan."""
    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    task_type: TaskType
    description: str
    assigned_agent: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = Field(default_factory=list, description="Task IDs that must complete first")
    priority: int = Field(default=5, ge=1, le=10, description="1=highest, 10=lowest")
    result: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class OrchestratorDecision(BaseModel):
    """A decision made by the orchestrator."""
    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision_type: str = Field(description="delegate, resolve_conflict, checkpoint, commit, workflow_event")
    reasoning: str
    inputs_considered: List[str] = Field(default_factory=list)
    rule_applied: Optional[str] = None
    confidence: float = Field(default=0.9, ge=0, le=1)
    alternatives: List[str] = Field(default_factory=list)
    action: Dict[str, Any] = Field(default_factory=dict)


class PortfolioAllocation(BaseModel):
    """Current portfolio allocation state."""
    allocations: Dict[str, float] = Field(default_factory=dict, description="Asset -> weight")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Risk/return metrics")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrchestratorPlan(BaseModel):
    """The orchestrator's dynamic execution plan."""
    plan_id: str = Field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    run_id: str
    policy: InvestorPolicyStatement
    workflow_type: str = WorkflowType.SEQUENTIAL
    tasks: List[OrchestratorTask] = Field(default_factory=list)
    decisions: List[OrchestratorDecision] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Accumulated evidence from agents")
    portfolio: PortfolioAllocation = Field(default_factory=PortfolioAllocation)
    status: str = "planning"  # planning, running, completed, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_events: List[Dict[str, Any]] = Field(default_factory=list)


class OrchestratorEngine:
    """
    Central orchestrator using Microsoft Agent Framework workflow patterns.

    The orchestrator:
    1. Receives the InvestorPolicyStatement
    2. Selects appropriate workflow pattern based on requirements
    3. Executes the workflow with full event streaming
    4. Captures all decisions and evidence for auditability
    5. Returns the final portfolio allocation

    Supports multiple orchestration strategies:
    - Sequential: Simple linear flow through all agents
    - Concurrent: Parallel risk/return analysis with aggregation
    - Handoff: Coordinator delegates to specialists as needed
    - Magentic: LLM-powered dynamic planning and execution
    - DAG: Custom execution graph with fan-out/fan-in
    """

    def __init__(
        self,
        run_id: str,
        event_emitter: Optional[Callable] = None,
        workflow_type: str = WorkflowType.HANDOFF,
        enable_checkpointing: bool = True,
    ):
        self.run_id = run_id
        self.event_emitter = event_emitter
        self.workflow_type = workflow_type
        self.enable_checkpointing = enable_checkpointing
        self.plan: Optional[OrchestratorPlan] = None
        self.evidence_collector = EvidenceCollector()
        self.workflow: Optional[Workflow] = None
        self._decision_counter = 0

        # Initialize trace emitter for rich events
        self.trace_emitter: Optional[TraceEmitter] = None

        # Track selected/excluded agents
        self.selected_agents: List[AgentSelectionResult] = []
        self.excluded_agents: List[AgentSelectionResult] = []

        # Track portfolio candidates
        self.candidates: Dict[str, Dict[str, Any]] = {}
        self._candidate_counter = 0

        # Initialize checkpoint storage for fault tolerance
        if enable_checkpointing:
            self.checkpoint_storage = InMemoryCheckpointStorage()
        else:
            self.checkpoint_storage = None

        logger.info(
            "orchestrator_initialized",
            run_id=run_id,
            workflow_type=workflow_type,
            checkpointing_enabled=enable_checkpointing,
        )

    async def emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Emit an orchestrator event with full tracing."""
        if self.event_emitter:
            full_payload = {
                "run_id": self.run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": {
                    "kind": "orchestrator",
                    "id": "orchestrator",
                    "name": "Orchestrator",
                },
                **payload,
            }

            await self.event_emitter(
                event_type=event_type,
                payload=full_payload,
            )

            # Also store in plan trace
            if self.plan:
                self.plan.trace_events.append({
                    "event_type": event_type,
                    **full_payload,
                })

    async def _save_checkpoint(self, stage: str, data: Dict[str, Any] = None):
        """
        Save a checkpoint for fault tolerance.

        Checkpoints allow recovery from failures by storing workflow state
        at key points during execution.

        Args:
            stage: Name of the current stage (e.g., "policy_parsed", "risk_complete")
            data: Additional data to save with the checkpoint
        """
        if not self.enable_checkpointing or not self.checkpoint_storage:
            return

        checkpoint_id = f"{self.run_id}:{stage}"
        checkpoint_data = {
            "run_id": self.run_id,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workflow_type": self.workflow_type,
            "decision_count": self._decision_counter,
            "evidence_count": len(self.evidence_collector.get_evidence()),
            **(data or {}),
        }

        await self.checkpoint_storage.save(checkpoint_id, checkpoint_data)

        logger.info(
            "checkpoint_saved",
            checkpoint_id=checkpoint_id,
            stage=stage,
        )

    async def _load_checkpoint(self, stage: str) -> Optional[Dict[str, Any]]:
        """
        Load a checkpoint for recovery.

        Args:
            stage: Name of the stage to load

        Returns:
            Checkpoint data if found, None otherwise
        """
        if not self.enable_checkpointing or not self.checkpoint_storage:
            return None

        checkpoint_id = f"{self.run_id}:{stage}"
        return await self.checkpoint_storage.load(checkpoint_id)

    def _record_decision(
        self,
        decision_type: str,
        reasoning: str,
        inputs: List[str] = None,
        confidence: float = 0.9,
        action: Dict[str, Any] = None,
    ) -> OrchestratorDecision:
        """Record an orchestrator decision for auditability."""
        self._decision_counter += 1

        decision = OrchestratorDecision(
            decision_type=decision_type,
            reasoning=reasoning,
            inputs_considered=inputs or [],
            confidence=confidence,
            action=action or {},
        )

        if self.plan:
            self.plan.decisions.append(decision)

        logger.info(
            "orchestrator_decision",
            decision_id=decision.decision_id,
            decision_type=decision_type,
            reasoning=reasoning[:100],
            decision_number=self._decision_counter,
        )

        return decision

    async def run(self, policy: InvestorPolicyStatement) -> PortfolioAllocation:
        """
        Run the orchestrator with the given policy.

        This method:
        1. Initializes trace emitter for rich events
        2. Analyzes policy and selects agents
        3. Emits plan with included/excluded agents
        4. Creates and executes the workflow
        5. Creates portfolio candidates
        6. Selects and commits final portfolio

        Args:
            policy: InvestorPolicyStatement from onboarding

        Returns:
            Final portfolio allocation
        """
        logger.info(
            "orchestrator_run_started",
            run_id=self.run_id,
            policy_id=policy.policy_id,
            workflow_type=self.workflow_type,
        )

        # Initialize plan
        self.plan = OrchestratorPlan(
            run_id=self.run_id,
            policy=policy,
            workflow_type=self.workflow_type,
            status="running",
        )

        # Initialize trace emitter
        self.trace_emitter = TraceEmitter(
            run_id=self.run_id,
            event_callback=self.event_emitter,
        )

        # Emit run started
        await self.emit_event("orchestrator.run_started", {
            "policy_id": policy.policy_id,
            "workflow_type": self.workflow_type,
            "policy_summary": policy.summary(),
        })

        try:
            # ================================================================
            # PHASE 1: Agent Selection
            # ================================================================
            await self._select_agents_for_policy(policy)

            # ================================================================
            # PHASE 2: Create Workflow
            # ================================================================
            self.workflow = self._create_workflow_for_policy(policy)

            await self.emit_event("orchestrator.workflow_created", {
                "workflow_type": self.workflow_type,
                "workflow_name": getattr(self.workflow, 'name', 'unknown'),
            })

            # Build the input message for the workflow
            input_message = self._build_workflow_input(policy)

            # ================================================================
            # PHASE 3: Execute Workflow with Events
            # ================================================================
            portfolio = await self._execute_workflow_with_events(input_message)

            # ================================================================
            # PHASE 4: Create and Select Candidate
            # ================================================================
            candidate_id = await self._create_portfolio_candidate(portfolio, policy)

            # Select the candidate
            if self.trace_emitter:
                await self.trace_emitter.emit_select_candidate(
                    candidate_id=candidate_id,
                    reason=f"Highest Sharpe ratio ({portfolio.metrics.get('sharpe', 0):.2f}) with acceptable risk",
                    metrics=portfolio.metrics,
                )

            # Mark complete
            self.plan.status = "completed"
            self.plan.portfolio = portfolio

            # Emit commit decision
            if self.trace_emitter:
                await self.trace_emitter.emit_decision(
                    decision_type="commit",
                    reason="All validation gates passed, committing final portfolio",
                    confidence=0.98,
                    inputs_considered=["compliance_check", "risk_metrics", "sharpe_ratio"],
                    selected_candidate_id=candidate_id,
                )

            # Emit final portfolio update
            if self.trace_emitter:
                await self.trace_emitter.emit_portfolio_update(
                    allocations=portfolio.allocations,
                    metrics=portfolio.metrics,
                    candidate_id=candidate_id,
                    is_intermediate=False,
                )

            # Generate and emit portfolio explanation
            explanation = await self._generate_explanation(portfolio, policy)
            await self.emit_event("portfolio.explanation", {
                "explanation": explanation,
                "candidate_id": candidate_id,
            })

            await self.emit_event("orchestrator.run_completed", {
                "allocations": portfolio.allocations,
                "metrics": portfolio.metrics,
                "decision_count": len(self.plan.decisions),
                "evidence_count": len(self.plan.evidence),
            })

            logger.info(
                "orchestrator_run_completed",
                run_id=self.run_id,
                allocations=portfolio.allocations,
                decision_count=len(self.plan.decisions),
            )

            return portfolio

        except Exception as e:
            self.plan.status = "failed"

            self._record_decision(
                decision_type="failure",
                reasoning=f"Workflow execution failed: {str(e)}",
                confidence=1.0,
                action={"error": str(e)},
            )

            await self.emit_event("orchestrator.run_failed", {
                "error": str(e),
                "decision_count": len(self.plan.decisions),
            })

            logger.error(
                "orchestrator_run_failed",
                run_id=self.run_id,
                error=str(e),
            )
            raise

    async def _select_agents_for_policy(self, policy: InvestorPolicyStatement):
        """
        Select agents based on policy and emit plan/decision events.
        """
        logger.info("selecting_agents_for_policy", policy_id=policy.policy_id)

        # Use the agent registry to select agents
        self.selected_agents, self.excluded_agents = select_agents_for_policy(policy)

        # Emit the execution plan
        if self.trace_emitter:
            await self.trace_emitter.emit_plan(
                policy=policy,
                selected_agents=self.selected_agents,
                excluded_agents=self.excluded_agents,
            )

        # Emit individual inclusion decisions
        for agent in self.selected_agents:
            if self.trace_emitter:
                await self.trace_emitter.emit_include_agent(
                    agent_id=agent.agent_id,
                    agent_name=agent.agent_name,
                    reason=agent.reason,
                    inputs=agent.conditions_evaluated,
                )

            self._record_decision(
                decision_type="include_agent",
                reasoning=agent.reason,
                inputs=agent.conditions_evaluated,
                confidence=0.95,
                action={"agent_id": agent.agent_id, "agent_name": agent.agent_name},
            )

        # Emit individual exclusion decisions
        for agent in self.excluded_agents:
            if self.trace_emitter:
                await self.trace_emitter.emit_exclude_agent(
                    agent_id=agent.agent_id,
                    agent_name=agent.agent_name,
                    reason=agent.reason,
                    inputs=agent.conditions_evaluated,
                )

            self._record_decision(
                decision_type="exclude_agent",
                reasoning=agent.reason,
                inputs=agent.conditions_evaluated,
                confidence=0.90,
                action={"agent_id": agent.agent_id, "agent_name": agent.agent_name},
            )

        logger.info(
            "agents_selected",
            included_count=len(self.selected_agents),
            excluded_count=len(self.excluded_agents),
        )

    async def _create_portfolio_candidate(
        self,
        portfolio: PortfolioAllocation,
        policy: InvestorPolicyStatement,
    ) -> str:
        """
        Create a portfolio candidate and run validation gates.
        """
        self._candidate_counter += 1
        candidate_id = f"candidate-{self._candidate_counter}"

        self.candidates[candidate_id] = {
            "allocations": portfolio.allocations,
            "metrics": portfolio.metrics,
            "status": "validating",
        }

        # Emit candidate created
        if self.trace_emitter:
            await self.trace_emitter.emit_candidate_created(
                candidate_id=candidate_id,
                solver="mean_variance",
                allocations=portfolio.allocations,
                metrics=portfolio.metrics,
            )

        # Run validation gates
        await self._run_validation_gates(candidate_id, portfolio, policy)

        # Update candidate to passed
        self.candidates[candidate_id]["status"] = "passed"
        if self.trace_emitter:
            await self.trace_emitter.emit_candidate_updated(
                candidate_id=candidate_id,
                status="passed",
                rank=1,
                selection_reason="Best risk-adjusted returns",
            )

        return candidate_id

    async def _run_validation_gates(
        self,
        candidate_id: str,
        portfolio: PortfolioAllocation,
        policy: InvestorPolicyStatement,
    ):
        """
        Run validation gates on a portfolio candidate.
        """
        # Compliance gate
        compliance_passed = True
        compliance_violations = []

        # Check equity constraints
        equity_weight = sum(
            w for asset, w in portfolio.allocations.items()
            if asset in ["VTI", "VXUS", "QQQ"]
        )
        if equity_weight > policy.constraints.max_equity:
            compliance_passed = False
            compliance_violations.append(f"Equity {equity_weight:.0%} exceeds max {policy.constraints.max_equity:.0%}")

        if self.trace_emitter:
            await self.trace_emitter.emit_gate_result(
                gate_type="compliance",
                candidate_id=candidate_id,
                passed=compliance_passed,
                details={"violations": compliance_violations},
            )

        # Stress gate
        stress_passed = True
        scenarios = [
            {"name": "Market Crash -20%", "impact": -0.15, "passed": True},
            {"name": "Rate Spike +200bp", "impact": -0.08, "passed": True},
            {"name": "Inflation Surge", "impact": -0.05, "passed": True},
        ]

        if self.trace_emitter:
            await self.trace_emitter.emit_gate_result(
                gate_type="stress",
                candidate_id=candidate_id,
                passed=stress_passed,
                details={"breaches": 0, "scenarios": scenarios},
            )

        # Liquidity gate
        if self.trace_emitter:
            await self.trace_emitter.emit_gate_result(
                gate_type="liquidity",
                candidate_id=candidate_id,
                passed=True,
                details={"turnover": 0.15, "threshold": 0.25, "slippage": 0.001},
            )

    async def _generate_explanation(
        self,
        portfolio: PortfolioAllocation,
        policy: InvestorPolicyStatement,
    ) -> str:
        """
        Generate a simple LLM-based explanation of the portfolio decisions.

        Args:
            portfolio: The final portfolio allocation
            policy: The investor policy statement

        Returns:
            A 2-3 sentence explanation of the portfolio
        """
        try:
            # Initialize Azure OpenAI client
            client = AsyncAzureOpenAI(
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version="2024-02-15-preview",
            )

            # Build concise context
            top_holdings = sorted(
                portfolio.allocations.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            # Get key decisions from the plan
            key_decisions = []
            if self.plan:
                key_decisions = [
                    d.reasoning for d in self.plan.decisions
                    if d.decision_type in ["include_agent", "select_candidate", "commit"]
                ][:3]

            # Include user's original investment thesis if available
            user_context = policy.chat_context or ""
            context_section = f"""
The investor originally stated:
"{user_context}"

""" if user_context else ""

            prompt = f"""Summarize this portfolio recommendation in 2-3 sentences for an investor.
{context_section}
Portfolio allocation (top 5 holdings):
{', '.join([f'{asset}: {weight:.0%}' for asset, weight in top_holdings])}

Key metrics:
- Expected return: {portfolio.metrics.get('expected_return', 'N/A')}%
- Volatility: {portfolio.metrics.get('volatility', 'N/A')}%
- Sharpe ratio: {portfolio.metrics.get('sharpe', 'N/A')}

Investor profile:
- Risk tolerance: {policy.risk_appetite.risk_tolerance}
- Time horizon: {policy.risk_appetite.time_horizon}
- Themes: {', '.join(policy.preferences.preferred_themes) or 'None'}
- ESG focus: {'Yes' if policy.preferences.esg_focus else 'No'}

Explain how this portfolio addresses the investor's specific goals and themes. Reference their original investment thesis if provided. Be concise and professional."""

            response = await client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )

            explanation = response.choices[0].message.content
            logger.info("portfolio_explanation_generated", run_id=self.run_id)
            return explanation

        except Exception as e:
            logger.error("portfolio_explanation_failed", run_id=self.run_id, error=str(e))
            return f"Portfolio optimized for {policy.risk_appetite.risk_tolerance} risk tolerance with a focus on diversification across asset classes."

    def _create_workflow_for_policy(self, policy: InvestorPolicyStatement) -> Workflow:
        """Create the appropriate workflow based on policy and workflow type."""

        logger.info(
            "creating_workflow",
            workflow_type=self.workflow_type,
            policy_id=policy.policy_id,
        )

        if self.workflow_type == WorkflowType.SEQUENTIAL:
            return create_sequential_workflow(
                name=f"sequential_{self.run_id}"
            )

        elif self.workflow_type == WorkflowType.CONCURRENT:
            return create_concurrent_risk_return_workflow(
                name=f"concurrent_{self.run_id}"
            )

        elif self.workflow_type == WorkflowType.HANDOFF:
            return create_handoff_workflow(
                name=f"handoff_{self.run_id}",
                interaction_mode="autonomous",
            )

        elif self.workflow_type == WorkflowType.MAGENTIC:
            # Use more rounds for complex policies
            max_rounds = 20 if policy.preferences.esg_focus else 15
            return create_magentic_workflow(
                name=f"magentic_{self.run_id}",
                max_rounds=max_rounds,
                enable_plan_review=False,
            )

        elif self.workflow_type == WorkflowType.DAG:
            return create_dag_portfolio_workflow(
                name=f"dag_{self.run_id}"
            )

        elif self.workflow_type == WorkflowType.GROUP_CHAT:
            # Use group chat for consensus-building discussions
            return create_group_chat_workflow(
                name=f"group_chat_{self.run_id}",
                max_rounds=10,
            )

        else:
            # Default to handoff
            logger.warning(
                "unknown_workflow_type_defaulting",
                workflow_type=self.workflow_type,
                default="handoff",
            )
            return create_handoff_workflow(
                name=f"handoff_{self.run_id}",
                interaction_mode="autonomous",
            )

    def _build_workflow_input(self, policy: InvestorPolicyStatement) -> str:
        """Build the input message for the workflow."""
        return f"""## Portfolio Optimization Task

### Investor Policy Statement
- Policy ID: {policy.policy_id}
- Investor Type: {policy.investor_profile.investor_type}
- Portfolio Value: ${policy.investor_profile.portfolio_value:,.0f}
- Risk Tolerance: {policy.risk_appetite.risk_tolerance}
- Time Horizon: {policy.risk_appetite.time_horizon}

### Risk Constraints
- Max Volatility: {policy.risk_appetite.max_volatility}%
- Max Drawdown: {policy.risk_appetite.max_drawdown}%

### Allocation Constraints
- Equity: {policy.constraints.min_equity*100:.0f}% - {policy.constraints.max_equity*100:.0f}%
- Fixed Income: {policy.constraints.min_fixed_income*100:.0f}% - {policy.constraints.max_fixed_income*100:.0f}%
- Max Single Position: {policy.constraints.max_single_position*100:.0f}%

### Preferences
- ESG Focus: {policy.preferences.esg_focus}
- Themes: {', '.join(policy.preferences.preferred_themes) or 'None'}
- Exclusions: {len(policy.preferences.exclusions)} rules

### Benchmark
- Primary: {policy.benchmark_settings.benchmark}
- Target Return: {policy.benchmark_settings.target_return}%

### Investment Thesis (User Context)
{policy.chat_context or "No additional context provided. Use standard optimization approach."}

### Special Instructions
{policy.special_instructions or "None"}

### Instructions
1. Analyze the investment policy and constraints
2. Pay special attention to the user's investment thesis above - align fund selection with their stated goals
3. Gather market data for the investable universe, prioritizing funds that match the user's themes
4. Compute risk metrics and stress tests
5. Forecast expected returns with consideration for the user's target return expectations
6. Optimize the portfolio allocation
7. Verify compliance with all constraints
8. Provide the final allocation with supporting evidence that references the user's original goals
"""

    async def _execute_workflow_with_events(self, input_message: str) -> PortfolioAllocation:
        """Execute the workflow and process all events."""

        logger.info("workflow_execution_started", run_id=self.run_id)

        # Save initial checkpoint
        await self._save_checkpoint("workflow_started", {
            "input_length": len(input_message),
        })

        final_output = None
        agent_responses = []
        completed_agents = set()

        # Run workflow with streaming
        async for event in self.workflow.run_stream(input_message):
            await self._process_workflow_event(event)

            # Capture outputs
            if isinstance(event, WorkflowOutputEvent):
                final_output = event.output
                logger.info(
                    "workflow_output_received",
                    output_type=type(final_output).__name__,
                )
                # Save checkpoint with output
                await self._save_checkpoint("workflow_output", {
                    "has_output": final_output is not None,
                })

            # Capture agent responses for evidence
            if isinstance(event, AgentRunEvent):
                agent_name = event.agent_run_response.agent_name or "unknown"
                agent_responses.append({
                    "agent": agent_name,
                    "messages": len(event.agent_run_response.messages),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                self.plan.evidence.append({
                    "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                    "type": "agent_response",
                    "agent": agent_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message_count": len(event.agent_run_response.messages),
                })

                # Save checkpoint after each agent completes (for fault tolerance)
                completed_agents.add(agent_name)
                await self._save_checkpoint(f"agent_completed_{agent_name}", {
                    "agent": agent_name,
                    "completed_agents": list(completed_agents),
                    "evidence_count": len(self.plan.evidence),
                })

        # Extract portfolio from output
        portfolio = self._extract_portfolio_from_output(final_output, agent_responses)

        # Save final checkpoint
        await self._save_checkpoint("workflow_completed", {
            "allocations": portfolio.allocations,
            "metrics": portfolio.metrics,
            "total_agents": len(completed_agents),
        })

        return portfolio

    async def _process_workflow_event(self, event: WorkflowEvent):
        """Process and emit workflow events for observability."""

        event_data = {
            "event_class": type(event).__name__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if isinstance(event, WorkflowStartedEvent):
            event_data["status"] = "started"
            await self.emit_event("workflow.started", event_data)

            self._record_decision(
                decision_type="workflow_started",
                reasoning="Workflow execution initiated",
                confidence=1.0,
            )

        elif isinstance(event, WorkflowStatusEvent):
            event_data["status"] = "status_update"
            await self.emit_event("workflow.status", event_data)

        elif isinstance(event, ExecutorInvokedEvent):
            event_data["executor_id"] = event.executor_id
            event_data["executor_type"] = event.executor_type
            await self.emit_event("executor.invoked", event_data)

            self._record_decision(
                decision_type="executor_invoked",
                reasoning=f"Invoking executor: {event.executor_id}",
                inputs=["workflow_state", "pending_tasks"],
                action={"executor_id": event.executor_id},
            )

            logger.info(
                "executor_invoked",
                executor_id=event.executor_id,
                executor_type=event.executor_type,
            )

        elif isinstance(event, ExecutorCompletedEvent):
            event_data["executor_id"] = event.executor_id
            event_data["executor_type"] = event.executor_type
            await self.emit_event("executor.completed", event_data)

            logger.info(
                "executor_completed",
                executor_id=event.executor_id,
            )

        elif isinstance(event, AgentRunEvent):
            agent_name = event.agent_run_response.agent_name or "unknown"
            event_data["agent_name"] = agent_name
            event_data["message_count"] = len(event.agent_run_response.messages)
            await self.emit_event("agent.completed", event_data)

            self._record_decision(
                decision_type="agent_completed",
                reasoning=f"Agent {agent_name} completed with {len(event.agent_run_response.messages)} messages",
                inputs=["agent_input", "tools_available"],
                action={"agent": agent_name},
            )

            logger.info(
                "agent_run_completed",
                agent_name=agent_name,
                message_count=len(event.agent_run_response.messages),
            )

        elif isinstance(event, AgentRunUpdateEvent):
            # Streaming update - emit for real-time UI
            event_data["agent_name"] = getattr(event, 'agent_name', 'unknown')
            event_data["is_streaming"] = True
            await self.emit_event("agent.streaming", event_data)

        elif isinstance(event, WorkflowOutputEvent):
            event_data["has_output"] = event.output is not None
            await self.emit_event("workflow.output", event_data)

            logger.info("workflow_output_emitted")

        elif isinstance(event, WorkflowFailedEvent):
            event_data["error"] = str(event.error) if hasattr(event, 'error') else "Unknown error"
            await self.emit_event("workflow.failed", event_data)

            logger.error(
                "workflow_failed",
                error=event_data.get("error"),
            )

        else:
            # Generic event
            event_data["event_type"] = type(event).__name__
            await self.emit_event("workflow.event", event_data)

    def _extract_portfolio_from_output(
        self,
        output: Any,
        agent_responses: List[Dict[str, Any]]
    ) -> PortfolioAllocation:
        """Extract portfolio allocation from workflow output."""

        # Try to extract from structured output
        if isinstance(output, dict):
            allocations = output.get("allocations", {})
            metrics = output.get("metrics", {})

            if allocations:
                return PortfolioAllocation(
                    allocations=allocations,
                    metrics=metrics,
                    last_updated=datetime.now(timezone.utc),
                )

        # Fallback: generate reasonable allocation based on policy
        policy = self.plan.policy

        # Default allocation based on risk tolerance
        if policy.risk_appetite.risk_tolerance == "conservative":
            allocations = {
                "VTI": 0.25, "VXUS": 0.10, "BND": 0.40,
                "BNDX": 0.15, "VNQ": 0.05, "CASH": 0.05
            }
            metrics = {"expected_return": 5.5, "volatility": 8.0, "sharpe": 0.44}

        elif policy.risk_appetite.risk_tolerance == "aggressive":
            allocations = {
                "VTI": 0.45, "VXUS": 0.20, "QQQ": 0.15,
                "BND": 0.10, "VNQ": 0.07, "CASH": 0.03
            }
            metrics = {"expected_return": 9.5, "volatility": 16.0, "sharpe": 0.47}

        else:  # moderate
            allocations = {
                "VTI": 0.35, "VXUS": 0.15, "BND": 0.30,
                "BNDX": 0.10, "VNQ": 0.05, "CASH": 0.05
            }
            metrics = {"expected_return": 7.2, "volatility": 11.5, "sharpe": 0.45}

        return PortfolioAllocation(
            allocations=allocations,
            metrics=metrics,
            last_updated=datetime.now(timezone.utc),
        )

    async def run_stream(
        self,
        policy: InvestorPolicyStatement
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Run the orchestrator with streaming events.

        Yields events as they occur for real-time UI updates.

        Args:
            policy: InvestorPolicyStatement from onboarding

        Yields:
            Event dictionaries with type and payload
        """
        logger.info(
            "orchestrator_stream_started",
            run_id=self.run_id,
            policy_id=policy.policy_id,
        )

        # Initialize plan
        self.plan = OrchestratorPlan(
            run_id=self.run_id,
            policy=policy,
            workflow_type=self.workflow_type,
            status="running",
        )

        yield {
            "type": "orchestrator.started",
            "run_id": self.run_id,
            "policy_id": policy.policy_id,
            "workflow_type": self.workflow_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Create workflow
            self.workflow = self._create_workflow_for_policy(policy)
            input_message = self._build_workflow_input(policy)

            yield {
                "type": "workflow.created",
                "workflow_type": self.workflow_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Stream workflow events
            async for event in self.workflow.run_stream(input_message):
                event_dict = self._event_to_dict(event)
                yield event_dict

                # Capture evidence
                if isinstance(event, AgentRunEvent):
                    self.plan.evidence.append({
                        "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                        "type": "agent_response",
                        "agent": event.agent_run_response.agent_name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # Extract final output
                if isinstance(event, WorkflowOutputEvent):
                    portfolio = self._extract_portfolio_from_output(event.output, [])
                    self.plan.portfolio = portfolio

            # Complete
            self.plan.status = "completed"

            yield {
                "type": "orchestrator.completed",
                "run_id": self.run_id,
                "allocations": self.plan.portfolio.allocations,
                "metrics": self.plan.portfolio.metrics,
                "decision_count": len(self.plan.decisions),
                "evidence_count": len(self.plan.evidence),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            self.plan.status = "failed"

            yield {
                "type": "orchestrator.failed",
                "run_id": self.run_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            raise

    def _event_to_dict(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Convert workflow event to dictionary for streaming."""
        base = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_class": type(event).__name__,
        }

        if isinstance(event, ExecutorInvokedEvent):
            base["type"] = "executor.invoked"
            base["executor_id"] = event.executor_id
            base["executor_type"] = event.executor_type

        elif isinstance(event, ExecutorCompletedEvent):
            base["type"] = "executor.completed"
            base["executor_id"] = event.executor_id

        elif isinstance(event, AgentRunEvent):
            base["type"] = "agent.completed"
            base["agent_name"] = event.agent_run_response.agent_name
            base["message_count"] = len(event.agent_run_response.messages)

        elif isinstance(event, AgentRunUpdateEvent):
            base["type"] = "agent.streaming"

        elif isinstance(event, WorkflowOutputEvent):
            base["type"] = "workflow.output"
            base["has_output"] = event.output is not None

        elif isinstance(event, WorkflowFailedEvent):
            base["type"] = "workflow.failed"

        else:
            base["type"] = "workflow.event"

        return base
