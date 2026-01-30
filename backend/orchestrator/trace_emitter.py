"""
Trace Event Emitter for Dynamic Orchestration.

Emits rich structured events for full UI visibility into orchestrator decisions.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel
import structlog

from backend.schemas.policy import InvestorPolicyStatement
from backend.orchestrator.agent_registry import AgentSelectionResult

logger = structlog.get_logger()


class TraceEmitter:
    """
    Emits rich trace events for orchestrator visibility.

    Event Types:
    - orchestrator.plan: Initial plan with selected/excluded agents
    - orchestrator.decision: Individual decisions (include/exclude/inject/select)
    - handover: Control transfer between agents
    - span.started / span.ended: Agent execution lifecycle
    - candidate.created / candidate.updated: Portfolio candidates
    - gate.*: Validation gates (compliance, stress, redteam, liquidity)
    - branch.fork / branch.join: Parallel execution
    - repair.started / repair.ended: Constraint repair loops
    - portfolio.update: Portfolio allocation updates
    """

    def __init__(
        self,
        run_id: str,
        event_callback: Callable,
        trace_id: Optional[str] = None,
    ):
        self.run_id = run_id
        self.trace_id = trace_id or f"trace-{uuid.uuid4().hex[:8]}"
        self.event_callback = event_callback
        self._span_stack: List[str] = []
        self._current_span_id: Optional[str] = None

    def _generate_span_id(self) -> str:
        """Generate a unique span ID."""
        return f"span-{uuid.uuid4().hex[:8]}"

    async def _emit(self, kind: str, message: str, payload: Dict[str, Any]):
        """Emit an event through the callback."""
        if self.event_callback:
            event = {
                "run_id": self.run_id,
                "kind": kind,
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "traceId": self.trace_id,
                    "spanId": self._current_span_id,
                    **payload,
                },
            }
            await self.event_callback(event_type=kind, payload=event["payload"])

            logger.debug(
                "trace_event_emitted",
                kind=kind,
                message=message[:50],
            )

    # =========================================================================
    # PLAN EVENTS
    # =========================================================================

    async def emit_plan(
        self,
        policy: InvestorPolicyStatement,
        selected_agents: List[AgentSelectionResult],
        excluded_agents: List[AgentSelectionResult],
    ):
        """Emit the initial execution plan."""
        payload = {
            "selectedAgents": [
                {
                    "id": a.agent_id,
                    "name": a.agent_name,
                    "reason": a.reason,
                    "category": "core" if a.category == "core" else "conditional",
                }
                for a in selected_agents
            ],
            "excludedAgents": [
                {
                    "id": a.agent_id,
                    "name": a.agent_name,
                    "reason": a.reason,
                }
                for a in excluded_agents
            ],
            "policySummary": {
                "riskTolerance": policy.risk_appetite.risk_tolerance,
                "maxVolatility": policy.risk_appetite.max_volatility,
                "maxDrawdown": policy.risk_appetite.max_drawdown,
                "esgEnabled": policy.preferences.esg_focus,
                "themes": policy.preferences.preferred_themes,
                "targetReturn": policy.benchmark_settings.target_return,
            },
            "estimatedAgentCount": len(selected_agents),
        }

        await self._emit(
            "orchestrator.plan",
            f"Execution plan created with {len(selected_agents)} agents",
            payload,
        )

    # =========================================================================
    # DECISION EVENTS
    # =========================================================================

    async def emit_decision(
        self,
        decision_type: str,
        reason: str,
        confidence: float = 0.9,
        inputs_considered: List[str] = None,
        alternatives: List[str] = None,
        added_agents: List[Dict[str, str]] = None,
        removed_agents: List[Dict[str, str]] = None,
        affected_candidate_ids: List[str] = None,
        selected_candidate_id: str = None,
        constraint_diff: List[Dict[str, Any]] = None,
        solver_switch: Dict[str, str] = None,
    ):
        """
        Emit an orchestrator decision.

        Decision types:
        - include_agent: Agent included in plan
        - exclude_agent: Agent excluded from plan
        - inject_agent: Agent dynamically added at runtime
        - remove_agent: Agent removed at runtime
        - select_candidate: Final portfolio selected
        - switch_solver: Optimization solver changed
        - tighten_constraints: Constraints made stricter
        - repair_constraints: Constraints repaired after violation
        - conflict_detected: Conflict between agents detected
        - conflict_resolved: Conflict resolved
        - checkpoint: Workflow checkpoint saved
        - commit: Final portfolio committed
        """
        payload = {
            "decisionType": decision_type,
            "reason": reason,
            "confidence": confidence,
            "inputsConsidered": inputs_considered or [],
            "alternatives": alternatives or [],
        }

        if added_agents:
            payload["addedAgents"] = added_agents
        if removed_agents:
            payload["removedAgents"] = removed_agents
        if affected_candidate_ids:
            payload["affectedCandidateIds"] = affected_candidate_ids
        if selected_candidate_id:
            payload["selectedCandidateId"] = selected_candidate_id
        if constraint_diff:
            payload["constraintDiff"] = constraint_diff
        if solver_switch:
            payload["solverSwitch"] = solver_switch

        await self._emit("orchestrator.decision", reason, payload)

    async def emit_include_agent(
        self,
        agent_id: str,
        agent_name: str,
        reason: str,
        inputs: List[str] = None,
    ):
        """Emit an agent inclusion decision."""
        await self.emit_decision(
            decision_type="include_agent",
            reason=reason,
            confidence=0.95,
            inputs_considered=inputs or ["policy_analysis"],
            added_agents=[{"id": agent_id, "name": agent_name, "reason": reason}],
        )

    async def emit_exclude_agent(
        self,
        agent_id: str,
        agent_name: str,
        reason: str,
        inputs: List[str] = None,
    ):
        """Emit an agent exclusion decision."""
        await self.emit_decision(
            decision_type="exclude_agent",
            reason=reason,
            confidence=0.90,
            inputs_considered=inputs or ["policy_analysis"],
            removed_agents=[{"id": agent_id, "name": agent_name, "reason": reason}],
        )

    async def emit_inject_agent(
        self,
        agent_id: str,
        agent_name: str,
        reason: str,
        trigger: str = None,
    ):
        """Emit a runtime agent injection decision."""
        await self.emit_decision(
            decision_type="inject_agent",
            reason=reason,
            confidence=0.85,
            inputs_considered=[trigger or "runtime_condition"],
            added_agents=[{"id": agent_id, "name": agent_name, "reason": reason}],
        )

    async def emit_select_candidate(
        self,
        candidate_id: str,
        reason: str,
        metrics: Dict[str, float] = None,
    ):
        """Emit a candidate selection decision."""
        inputs = []
        if metrics:
            inputs = [f"{k}={v:.2f}" for k, v in metrics.items()]

        await self.emit_decision(
            decision_type="select_candidate",
            reason=reason,
            confidence=0.95,
            inputs_considered=inputs,
            selected_candidate_id=candidate_id,
        )

    # =========================================================================
    # SPAN EVENTS (Agent Execution)
    # =========================================================================

    async def emit_span_started(
        self,
        agent_id: str,
        agent_name: str,
        objective: str,
    ) -> str:
        """Emit agent execution start. Returns span_id."""
        span_id = self._generate_span_id()
        parent_span_id = self._current_span_id

        self._span_stack.append(span_id)
        self._current_span_id = span_id

        payload = {
            "spanId": span_id,
            "parentSpanId": parent_span_id,
            "agentId": agent_id,
            "agentName": agent_name,
            "objective": objective,
        }

        await self._emit(
            "span.started",
            f"{agent_name} starting: {objective[:50]}",
            payload,
        )

        return span_id

    async def emit_span_ended(
        self,
        agent_id: str,
        agent_name: str,
        success: bool = True,
        result_summary: str = None,
    ):
        """Emit agent execution end."""
        span_id = self._current_span_id

        if self._span_stack:
            self._span_stack.pop()
            self._current_span_id = self._span_stack[-1] if self._span_stack else None

        payload = {
            "spanId": span_id,
            "agentId": agent_id,
            "agentName": agent_name,
            "success": success,
            "resultSummary": result_summary,
        }

        status = "completed" if success else "failed"
        await self._emit(
            "span.ended",
            f"{agent_name} {status}",
            payload,
        )

    # =========================================================================
    # HANDOVER EVENTS
    # =========================================================================

    async def emit_handover(
        self,
        from_agent: str,
        to_agent: str,
        reason: str,
        candidate_id: str = None,
        context: Dict[str, Any] = None,
    ):
        """Emit control handover between agents."""
        payload = {
            "fromAgent": from_agent,
            "toAgent": to_agent,
            "reason": reason,
        }
        if candidate_id:
            payload["candidateId"] = candidate_id
        if context:
            payload["context"] = context

        await self._emit(
            "handover",
            f"Handover: {from_agent} → {to_agent}",
            payload,
        )

    # =========================================================================
    # BRANCH EVENTS (Parallel Execution)
    # =========================================================================

    async def emit_branch_fork(
        self,
        branches: List[str],
        reason: str = None,
    ):
        """Emit parallel execution fork."""
        payload = {
            "branchType": "fork",
            "branches": branches,
            "reason": reason or f"Parallel execution of {len(branches)} agents",
        }

        await self._emit(
            "branch.fork",
            f"Forking to {', '.join(branches)}",
            payload,
        )

    async def emit_branch_join(
        self,
        branches: List[str],
        reason: str = None,
    ):
        """Emit parallel execution join."""
        payload = {
            "branchType": "join",
            "branches": branches,
            "reason": reason or f"Joining {len(branches)} parallel branches",
        }

        await self._emit(
            "branch.join",
            f"Joining from {', '.join(branches)}",
            payload,
        )

    # =========================================================================
    # CANDIDATE EVENTS
    # =========================================================================

    async def emit_candidate_created(
        self,
        candidate_id: str,
        solver: str,
        allocations: Dict[str, float] = None,
        metrics: Dict[str, float] = None,
    ):
        """Emit portfolio candidate creation."""
        payload = {
            "candidateId": candidate_id,
            "solver": solver,
            "status": "pending",
            "allocations": allocations or {},
            "metrics": metrics or {},
        }

        await self._emit(
            "candidate.created",
            f"Candidate {candidate_id} created by {solver}",
            payload,
        )

    async def emit_candidate_updated(
        self,
        candidate_id: str,
        status: str,
        allocations: Dict[str, float] = None,
        metrics: Dict[str, float] = None,
        rank: int = None,
        selection_reason: str = None,
    ):
        """Emit portfolio candidate update."""
        payload = {
            "candidateId": candidate_id,
            "status": status,
        }
        if allocations:
            payload["allocations"] = allocations
        if metrics:
            payload["metrics"] = metrics
        if rank is not None:
            payload["rank"] = rank
        if selection_reason:
            payload["selectionReason"] = selection_reason

        await self._emit(
            "candidate.updated",
            f"Candidate {candidate_id} → {status}",
            payload,
        )

    # =========================================================================
    # GATE EVENTS
    # =========================================================================

    async def emit_gate_result(
        self,
        gate_type: str,  # compliance, stress, redteam, liquidity
        candidate_id: str,
        passed: bool,
        details: Dict[str, Any] = None,
    ):
        """Emit validation gate result."""
        payload = {
            "gateType": gate_type,
            "candidateId": candidate_id,
            "passed": passed,
            "details": details or {},
        }

        status = "passed" if passed else "failed"
        await self._emit(
            f"gate.{gate_type}",
            f"{gate_type.title()} gate {status} for {candidate_id}",
            payload,
        )

    # =========================================================================
    # EVIDENCE EVENTS
    # =========================================================================

    async def emit_evidence(
        self,
        agent_id: str,
        agent_name: str,
        evidence_type: str,
        summary: str,
        confidence: float = 0.9,
        details: Dict[str, Any] = None,
    ):
        """Emit agent evidence."""
        payload = {
            "agentId": agent_id,
            "agentName": agent_name,
            "evidenceType": evidence_type,
            "summary": summary,
            "confidence": confidence,
            "details": details or {},
        }

        await self._emit(
            "agent.evidence",
            summary,
            payload,
        )

    # =========================================================================
    # PORTFOLIO EVENTS
    # =========================================================================

    async def emit_portfolio_update(
        self,
        allocations: Dict[str, float],
        metrics: Dict[str, float],
        candidate_id: str = None,
        is_intermediate: bool = True,
    ):
        """Emit portfolio allocation update."""
        payload = {
            "allocations": allocations,
            "metrics": metrics,
            "isIntermediate": is_intermediate,
        }
        if candidate_id:
            payload["candidateId"] = candidate_id

        status = "intermediate" if is_intermediate else "final"
        await self._emit(
            "portfolio.update",
            f"Portfolio {status} update",
            payload,
        )
