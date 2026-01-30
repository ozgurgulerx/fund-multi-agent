/**
 * Enhanced trace event types for dynamic orchestrator visibility.
 * Every event is designed to be rendered in the UI for full transparency.
 */

export type TraceEventType =
  // Run lifecycle
  | "run.started"
  | "run.completed"
  | "run.failed"
  // Span lifecycle (agent execution)
  | "span.started"
  | "span.ended"
  // Orchestrator events
  | "orchestrator.plan"
  | "orchestrator.decision"
  // Workflow control
  | "handover"
  | "branch.fork"
  | "branch.join"
  // Candidate lifecycle
  | "candidate.created"
  | "candidate.updated"
  // Gate validations
  | "gate.compliance"
  | "gate.stress"
  | "gate.redteam"
  | "gate.liquidity"
  // Repair loops
  | "repair.started"
  | "repair.ended"
  // Artifacts
  | "artifact.created"
  // Agent-specific
  | "agent.evidence"
  | "agent.reasoning"
  | "portfolio.update"
  | "portfolio.explanation";

export type ActorType = "orchestrator" | "agent" | "tool" | "system";

export type EventLevel = "debug" | "info" | "warn" | "error";

export type DecisionType =
  | "plan_created"
  | "include_agent"
  | "exclude_agent"
  | "inject_agent"
  | "remove_agent"
  | "select_candidate"
  | "switch_solver"
  | "tighten_constraints"
  | "repair_constraints"
  | "conflict_detected"
  | "conflict_resolved"
  | "checkpoint"
  | "commit";

export type CandidateStatus =
  | "pending"
  | "validating"
  | "passed"
  | "failed"
  | "selected"
  | "rejected";

export type GateType = "compliance" | "stress" | "redteam" | "liquidity";

/**
 * Core trace event structure.
 * All events in the system follow this format.
 */
export interface TraceEvent {
  ts: string;
  runId: string;
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  actorType: ActorType;
  actorName: string;
  eventType: TraceEventType;
  level?: EventLevel;
  candidateId?: string;
  message: string;
  data?: Record<string, unknown>;
}

/**
 * Orchestrator plan event data.
 * Emitted at the start of a run showing which agents will be included/excluded.
 */
export interface PlanEventData {
  selectedAgents: Array<{ id: string; name: string; reason: string; category: "core" | "conditional" }>;
  excludedAgents: Array<{ id: string; name: string; reason: string }>;
  policySummary: {
    riskTolerance: string;
    maxVolatility: number;
    maxDrawdown: number;
    esgEnabled: boolean;
    themes: string[];
    targetReturn: number;
  };
  estimatedAgentCount: number;
}

/**
 * Orchestrator decision event data.
 * Emitted whenever the orchestrator makes a decision.
 */
export interface DecisionEventData {
  decisionType: DecisionType;
  reason: string;
  confidence: number;
  inputsConsidered: string[];
  alternatives?: string[];
  // For inject/remove decisions
  addedAgents?: Array<{ id: string; name: string; reason: string }>;
  removedAgents?: Array<{ id: string; name: string; reason: string }>;
  // For candidate decisions
  affectedCandidateIds?: string[];
  selectedCandidateId?: string;
  // For constraint changes
  constraintDiff?: Array<{
    field: string;
    from: string | number;
    to: string | number;
    reason: string;
  }>;
  // For solver switch
  solverSwitch?: {
    from: string;
    to: string;
    reason: string;
  };
}

/**
 * Handover event data.
 * Emitted when control passes from one agent to another.
 */
export interface HandoverEventData {
  fromAgent: string;
  toAgent: string;
  reason: string;
  candidateId?: string;
  context?: Record<string, unknown>;
}

/**
 * Branch fork/join event data.
 * Emitted when parallel execution starts or ends.
 */
export interface BranchEventData {
  branchType: "fork" | "join";
  branches: string[];
  reason?: string;
}

/**
 * Candidate event data.
 * Emitted when a portfolio candidate is created or updated.
 */
export interface CandidateEventData {
  candidateId: string;
  solver: string;
  status: CandidateStatus;
  allocations?: Record<string, number>;
  metrics?: {
    expectedReturn?: number;
    volatility?: number;
    sharpe?: number;
    var95?: number;
    turnover?: number;
  };
  rank?: number;
  selectionReason?: string;
  gates?: Record<string, { passed: boolean; issues?: string[] }>;
}

/**
 * Gate event data.
 * Emitted when a validation gate is executed.
 */
export interface GateEventData {
  gateType: GateType;
  candidateId: string;
  passed: boolean;
  details: {
    // Compliance gate
    violations?: string[];
    // Stress gate
    breaches?: number;
    scenarios?: Array<{ name: string; impact: number; passed: boolean }>;
    // RedTeam gate
    severity?: "low" | "medium" | "high";
    vulnerabilities?: string[];
    // Liquidity gate
    turnover?: number;
    threshold?: number;
    slippage?: number;
  };
}

/**
 * Repair event data.
 * Emitted during constraint repair loops.
 */
export interface RepairEventData {
  repairType: "constraint" | "allocation" | "solver";
  candidateId: string;
  iteration: number;
  maxIterations: number;
  changes: Array<{
    field: string;
    from: string | number;
    to: string | number;
    reason: string;
  }>;
  success?: boolean;
}

/**
 * Agent evidence event data.
 */
export interface EvidenceEventData {
  agentId: string;
  agentName: string;
  evidenceType: "constraint" | "data" | "insight" | "warning" | "filter" | "forecast" | "validation" | "stress_test" | "optimization";
  summary: string;
  confidence: number;
  details?: Record<string, unknown>;
}

/**
 * Portfolio update event data.
 */
export interface PortfolioUpdateEventData {
  candidateId?: string;
  allocations: Record<string, number>;
  metrics: {
    expectedReturn?: number;
    volatility?: number;
    sharpe?: number;
    var95?: number;
  };
  isIntermediate?: boolean;
}

/**
 * Helper to create a trace event with proper defaults.
 */
export function createTraceEvent(
  runId: string,
  traceId: string,
  eventType: TraceEventType,
  actorType: ActorType,
  actorName: string,
  message: string,
  data?: Record<string, unknown>,
  options?: {
    spanId?: string;
    parentSpanId?: string;
    level?: EventLevel;
    candidateId?: string;
  }
): TraceEvent {
  return {
    ts: new Date().toISOString(),
    runId,
    traceId,
    spanId: options?.spanId || generateId(),
    parentSpanId: options?.parentSpanId,
    actorType,
    actorName,
    eventType,
    level: options?.level || "info",
    candidateId: options?.candidateId,
    message,
    data,
  };
}

/**
 * Generate a unique ID for spans/traces.
 */
export function generateId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`;
}
