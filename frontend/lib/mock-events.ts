/**
 * Dynamic mock event generator for the multi-agent orchestrator.
 *
 * Key features:
 * - Compiles execution plan based on policy (shows selected/excluded agents)
 * - Emits span events for agent execution
 * - Supports parallel branches (fork/join)
 * - Creates multiple candidates when ChallengerOptimizer is included
 * - Validates candidates through gates (compliance, stress, redteam, liquidity)
 * - Injects agents at runtime based on signals (infeasible, compliance failures)
 * - Full trace visibility for the UI
 */

import {
  type TraceEvent,
  type TraceEventType,
  type PlanEventData,
  type DecisionEventData,
  type HandoverEventData,
  type BranchEventData,
  type CandidateEventData,
  type GateEventData,
  type RepairEventData,
  type EvidenceEventData,
  type PortfolioUpdateEventData,
  generateId,
} from "./trace-events";

import {
  type PolicyInput,
  type RuntimeSignals,
  type AgentDefinition,
  compilePlan,
  getAgent,
  ORCHESTRATOR,
  DEFAULT_POLICY,
  AGENT_REGISTRY,
} from "./agent-registry";

// Re-export for compatibility
export type { PolicyInput as InvestorPolicy } from "./agent-registry";

/**
 * Legacy policy format from onboarding page.
 * This is the structure created by the onboarding UI.
 */
export interface LegacyPolicy {
  investor_profile?: {
    investor_type?: string;
    base_currency?: string;
    portfolio_value?: number;
  };
  risk_appetite?: {
    risk_tolerance?: string;
    max_volatility?: number;
    max_drawdown?: number;
    time_horizon?: string;
    liquidity_needs?: number;
  };
  constraints?: {
    min_equity?: number;
    max_equity?: number;
    min_fixed_income?: number;
    max_fixed_income?: number;
    min_cash?: number;
    max_cash?: number;
    max_single_position?: number;
    max_sector_exposure?: number;
    min_positions?: number;
  };
  preferences?: {
    esg_focus?: boolean;
    exclusions?: string[];
    preferred_themes?: string[];
    factor_tilts?: Record<string, number>;
    home_bias?: number;
  };
  benchmark_settings?: {
    benchmark?: string;
    target_return?: number;
    rebalance_frequency?: string;
    rebalance_threshold?: number;
  };
}

/**
 * Convert legacy policy format to PolicyInput format.
 */
function convertLegacyPolicy(legacy: LegacyPolicy): PolicyInput {
  const timeHorizonMap: Record<string, PolicyInput["timeHorizon"]> = {
    short: "<3y",
    medium: "3-7y",
    long: "7-15y",
    very_long: ">15y",
  };

  const rebalanceMap: Record<string, PolicyInput["benchmark"]["rebalanceFrequency"]> = {
    monthly: "monthly",
    quarterly: "quarterly",
    semi_annual: "semi_annual",
    annual: "annual",
  };

  return {
    riskTolerance: (legacy.risk_appetite?.risk_tolerance as PolicyInput["riskTolerance"]) || "moderate",
    maxVolatilityPct: legacy.risk_appetite?.max_volatility || 15,
    maxDrawdownPct: legacy.risk_appetite?.max_drawdown || 20,
    timeHorizon: timeHorizonMap[legacy.risk_appetite?.time_horizon || "medium"] || "3-7y",
    constraints: {
      equityMinPct: (legacy.constraints?.min_equity || 0.3) * 100,
      equityMaxPct: (legacy.constraints?.max_equity || 0.7) * 100,
      fixedIncomeMinPct: (legacy.constraints?.min_fixed_income || 0.2) * 100,
      fixedIncomeMaxPct: (legacy.constraints?.max_fixed_income || 0.6) * 100,
      maxSinglePositionPct: (legacy.constraints?.max_single_position || 0.1) * 100,
      minPositions: legacy.constraints?.min_positions || 10,
    },
    preferences: {
      esgEnabled: legacy.preferences?.esg_focus || false,
      themes: legacy.preferences?.preferred_themes || [],
      exclusions: legacy.preferences?.exclusions || [],
      homeBiasPct: (legacy.preferences?.home_bias || 0.6) * 100,
    },
    benchmark: {
      primary: legacy.benchmark_settings?.benchmark || "SPY",
      targetReturnPct: legacy.benchmark_settings?.target_return || 7,
      rebalanceFrequency: rebalanceMap[legacy.benchmark_settings?.rebalance_frequency || "quarterly"] || "quarterly",
    },
  };
}

/**
 * Check if a policy object is in the legacy format.
 */
function isLegacyPolicy(policy: unknown): policy is LegacyPolicy {
  if (typeof policy !== "object" || policy === null) return false;
  const p = policy as Record<string, unknown>;
  // Legacy format has risk_appetite, new format has riskTolerance
  return "risk_appetite" in p || "benchmark_settings" in p || "investor_profile" in p;
}

// Legacy interface for compatibility
export interface RunEvent {
  runId: string;
  ts: string;
  type: string;
  actor: {
    kind: "orchestrator" | "agent";
    id: string;
    name: string;
  };
  severity?: "info" | "warn" | "risk" | "error";
  payload: Record<string, unknown>;
  message?: string;
}

// ============================================
// Event Creation Helpers
// ============================================

let spanCounter = 0;

function createSpanId(): string {
  return `span-${++spanCounter}-${Math.random().toString(36).substring(2, 6)}`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function createEvent(
  runId: string,
  traceId: string,
  eventType: TraceEventType,
  actorType: "orchestrator" | "agent",
  actorName: string,
  message: string,
  data?: Record<string, unknown>,
  options?: {
    spanId?: string;
    parentSpanId?: string;
    level?: "debug" | "info" | "warn" | "error";
    candidateId?: string;
  }
): TraceEvent {
  return {
    ts: new Date().toISOString(),
    runId,
    traceId,
    spanId: options?.spanId || createSpanId(),
    parentSpanId: options?.parentSpanId,
    actorType,
    actorName,
    eventType,
    level: options?.level,
    candidateId: options?.candidateId,
    message,
    data,
  };
}

// Convert TraceEvent to legacy RunEvent for compatibility
function toRunEvent(event: TraceEvent): RunEvent {
  return {
    runId: event.runId,
    ts: event.ts,
    type: event.eventType,
    actor: {
      kind: event.actorType === "orchestrator" ? "orchestrator" : "agent",
      id: event.actorName.toLowerCase().replace(/\s+/g, "_"),
      name: event.actorName,
    },
    severity: event.level === "warn" ? "warn" : event.level === "error" ? "error" : "info",
    payload: event.data || {},
    message: event.message,
  };
}

// ============================================
// Dynamic Event Generator
// ============================================

interface GeneratorState {
  runId: string;
  traceId: string;
  policy: PolicyInput;
  speed: number;
  currentAgentIds: string[];
  candidates: Map<string, CandidateEventData>;
  signals: RuntimeSignals;
}

/**
 * Generate dynamic mock events based on policy.
 */
export async function* generateMockEvents(
  runId: string,
  speedMultiplier: number = 1,
  policy?: PolicyInput | LegacyPolicy
): AsyncGenerator<RunEvent> {
  const d = (ms: number) => delay(ms / speedMultiplier);
  const traceId = generateId();

  // Convert legacy policy format if needed
  let actualPolicy: PolicyInput;
  if (!policy) {
    actualPolicy = DEFAULT_POLICY;
  } else if (isLegacyPolicy(policy)) {
    actualPolicy = convertLegacyPolicy(policy);
  } else {
    actualPolicy = policy as PolicyInput;
  }

  spanCounter = 0;

  const state: GeneratorState = {
    runId,
    traceId,
    policy: actualPolicy,
    speed: speedMultiplier,
    currentAgentIds: [],
    candidates: new Map(),
    signals: {
      infeasible: false,
      turnoverPct: 0,
      complianceFailures: 0,
      stressBreaches: 0,
      redTeamSeverity: "low",
      dataQualityScore: 100,
      missingDataFields: [],
    },
  };

  // ============================================
  // 1. RUN STARTED
  // ============================================
  yield toRunEvent(
    createEvent(runId, traceId, "run.started", "orchestrator", "Orchestrator", "Portfolio optimization run started", {
      policy_summary: `${actualPolicy.riskTolerance} risk, ${actualPolicy.maxVolatilityPct}% max vol, ${actualPolicy.benchmark.targetReturnPct}% target`,
    })
  );
  await d(500);

  // ============================================
  // 2. COMPILE PLAN
  // ============================================
  const plan = compilePlan(actualPolicy);
  state.currentAgentIds = plan.executionOrder.map((a) => a.id);

  const planData: PlanEventData = {
    selectedAgents: plan.selected.map((s) => ({
      id: s.agent.id,
      name: s.agent.name,
      reason: s.reason,
      category: s.agent.category as "core" | "conditional",
    })),
    excludedAgents: plan.excluded.map((e) => ({
      id: e.agent.id,
      name: e.agent.name,
      reason: e.reason,
    })),
    policySummary: {
      riskTolerance: actualPolicy.riskTolerance,
      maxVolatility: actualPolicy.maxVolatilityPct,
      maxDrawdown: actualPolicy.maxDrawdownPct,
      esgEnabled: actualPolicy.preferences.esgEnabled,
      themes: actualPolicy.preferences.themes,
      targetReturn: actualPolicy.benchmark.targetReturnPct,
    },
    estimatedAgentCount: plan.selected.length,
  };

  yield toRunEvent(
    createEvent(
      runId,
      traceId,
      "orchestrator.plan",
      "orchestrator",
      "Orchestrator",
      `Compiled execution plan: ${plan.selected.length} agents selected, ${plan.excluded.length} excluded`,
      planData as unknown as Record<string, unknown>
    )
  );
  await d(500);

  // ============================================
  // 2a. EMIT INDIVIDUAL AGENT DECISIONS
  // ============================================

  // Emit decisions for conditional agents that were INCLUDED
  const conditionalSelected = plan.selected.filter(s => s.agent.category === "conditional");
  for (const selection of conditionalSelected) {
    yield toRunEvent(
      createEvent(
        runId,
        traceId,
        "orchestrator.decision",
        "orchestrator",
        "Orchestrator",
        `INCLUDE: ${selection.agent.name}`,
        {
          decisionType: "include_agent",
          reason: selection.reason,
          confidence: 0.95,
          inputsConsidered: [
            `risk_tolerance: ${actualPolicy.riskTolerance}`,
            `max_drawdown: ${actualPolicy.maxDrawdownPct}%`,
            `max_volatility: ${actualPolicy.maxVolatilityPct}%`,
            `themes: ${actualPolicy.preferences.themes.length} active`,
            `target_return: ${actualPolicy.benchmark.targetReturnPct}%`,
          ],
          addedAgents: [{ id: selection.agent.id, name: selection.agent.name, reason: selection.reason }],
          alternatives: [],
        } as DecisionEventData as unknown as Record<string, unknown>,
        { level: "info" }
      )
    );
    await d(300);
  }

  // Emit decisions for agents that were EXCLUDED
  for (const exclusion of plan.excluded) {
    yield toRunEvent(
      createEvent(
        runId,
        traceId,
        "orchestrator.decision",
        "orchestrator",
        "Orchestrator",
        `EXCLUDE: ${exclusion.agent.name}`,
        {
          decisionType: "exclude_agent",
          reason: exclusion.reason,
          confidence: 0.90,
          inputsConsidered: [
            `risk_tolerance: ${actualPolicy.riskTolerance}`,
            `max_drawdown: ${actualPolicy.maxDrawdownPct}%`,
            `target_return: ${actualPolicy.benchmark.targetReturnPct}%`,
          ],
          removedAgents: [{ id: exclusion.agent.id, name: exclusion.agent.name, reason: exclusion.reason }],
          alternatives: [],
        } as DecisionEventData as unknown as Record<string, unknown>,
        { level: "info" }
      )
    );
    await d(200);
  }

  await d(500);

  // ============================================
  // 3. EXECUTE AGENTS
  // ============================================

  // Policy Agent (always first)
  yield* executeAgent(state, "policy_agent", "Parsing investor policy statement", d);

  // Market Agent
  yield* executeHandover(state, "policy_agent", "market_agent", "Policy parsed, building universe", d);
  yield* executeAgent(state, "market_agent", "Retrieving market data and building universe", d);

  // Data Quality Agent
  yield* executeHandover(state, "data_quality_agent", "data_quality_agent", "Validating data quality", d);
  yield* executeAgent(state, "data_quality_agent", "Checking data freshness and completeness", d);

  // Fork: Risk + Return in parallel
  yield toRunEvent(
    createEvent(runId, traceId, "branch.fork", "orchestrator", "Orchestrator", "Forking: Risk and Return agents run in parallel", {
      branchType: "fork",
      branches: ["risk_agent", "return_agent"],
      reason: "Risk and return analysis can run concurrently",
    } as BranchEventData as unknown as Record<string, unknown>)
  );
  await d(300);

  // Execute both "in parallel" (sequentially for simplicity but shown as parallel)
  yield* executeAgent(state, "risk_agent", "Computing VaR and volatility constraints", d);
  yield* executeAgent(state, "return_agent", "Forecasting expected returns", d);

  yield toRunEvent(
    createEvent(runId, traceId, "branch.join", "orchestrator", "Orchestrator", "Join: Risk and Return completed", {
      branchType: "join",
      branches: ["risk_agent", "return_agent"],
    } as BranchEventData as unknown as Record<string, unknown>)
  );
  await d(300);

  // Conditional: Scenario Stress Agent
  if (state.currentAgentIds.includes("scenario_stress_agent")) {
    yield* executeAgent(state, "scenario_stress_agent", "Running stress test scenarios", d);

    // Simulate stress breaches for conservative profiles
    if (actualPolicy.riskTolerance === "conservative") {
      state.signals.stressBreaches = 2;
    }
  }

  // Conditional: Liquidity TC Agent
  if (state.currentAgentIds.includes("liquidity_tc_agent")) {
    yield* executeAgent(state, "liquidity_tc_agent", "Evaluating transaction costs and turnover", d);
  }

  // Conditional: Hedge Tail Agent
  if (state.currentAgentIds.includes("hedge_tail_agent")) {
    yield* executeAgent(state, "hedge_tail_agent", "Analyzing tail risk mitigation options", d);
  }

  // ============================================
  // 4. OPTIMIZATION (with candidates)
  // ============================================

  const hasChallengerOptimizer = state.currentAgentIds.includes("challenger_optimizer_agent");

  if (hasChallengerOptimizer) {
    // Fork: Multiple solvers
    yield toRunEvent(
      createEvent(runId, traceId, "branch.fork", "orchestrator", "Orchestrator", "Forking: Running parallel optimization solvers", {
        branchType: "fork",
        branches: ["mv_solver", "cvar_solver", "risk_parity_solver"],
        reason: "Comparing optimization approaches",
      } as BranchEventData as unknown as Record<string, unknown>)
    );
    await d(500);

    // Create 3 candidates
    yield* createCandidate(state, "candidate_mv", "Mean-Variance", d);
    yield* createCandidate(state, "candidate_cvar", "CVaR", d);
    yield* createCandidate(state, "candidate_rp", "Risk Parity", d);

    yield toRunEvent(
      createEvent(runId, traceId, "branch.join", "orchestrator", "Orchestrator", "Join: All solvers completed", {
        branchType: "join",
        branches: ["mv_solver", "cvar_solver", "risk_parity_solver"],
      } as BranchEventData as unknown as Record<string, unknown>)
    );
    await d(300);
  } else {
    // Single optimizer
    yield* executeAgent(state, "optimizer_agent", "Running mean-variance optimization", d);
    yield* createCandidate(state, "candidate_default", "Mean-Variance", d);
  }

  // ============================================
  // 5. GATE VALIDATION PER CANDIDATE
  // ============================================

  for (const [candidateId, candidate] of state.candidates) {
    // Compliance gate (always)
    yield* validateGate(state, candidateId, "compliance", d);

    // Stress gate (if stress agent was included)
    if (state.currentAgentIds.includes("scenario_stress_agent")) {
      yield* validateGate(state, candidateId, "stress", d);
    }

    // RedTeam gate (if included)
    if (state.currentAgentIds.includes("red_team_agent")) {
      yield* validateGate(state, candidateId, "redteam", d);
    }

    // Liquidity gate (if included)
    if (state.currentAgentIds.includes("liquidity_tc_agent")) {
      yield* validateGate(state, candidateId, "liquidity", d);
    }
  }

  // ============================================
  // 6. RUNTIME INJECTION DEMO (simulate infeasible for aggressive with low vol)
  // ============================================

  const shouldSimulateInfeasible =
    actualPolicy.riskTolerance === "aggressive" && actualPolicy.maxVolatilityPct < 12;

  if (shouldSimulateInfeasible) {
    state.signals.infeasible = true;

    // Inject Constraint Repair Agent
    yield toRunEvent(
      createEvent(
        runId,
        traceId,
        "orchestrator.decision",
        "orchestrator",
        "Orchestrator",
        "RUNTIME INJECTION: Constraint Repair Agent needed",
        {
          decisionType: "inject_agent",
          reason: "Optimization reported infeasible - aggressive profile with low volatility constraint",
          confidence: 0.95,
          inputsConsidered: [
            "optimizer_status: infeasible",
            "risk_tolerance: aggressive",
            `max_volatility: ${actualPolicy.maxVolatilityPct}%`,
          ],
          addedAgents: [{ id: "constraint_repair_agent", name: "Constraint Repair Agent", reason: "Repair infeasible constraints" }],
        } as DecisionEventData as unknown as Record<string, unknown>,
        { level: "warn" }
      )
    );
    await d(800);

    // Execute repair
    yield* executeRepairLoop(state, "candidate_default", d);

    // Mark as resolved
    state.signals.infeasible = false;
  }

  // ============================================
  // 7. SELECT WINNER
  // ============================================

  const candidateIds = Array.from(state.candidates.keys());
  const winnerId = candidateIds[0];
  const winner = state.candidates.get(winnerId)!;

  yield toRunEvent(
    createEvent(
      runId,
      traceId,
      "orchestrator.decision",
      "orchestrator",
      "Orchestrator",
      `Selected ${winner.solver} portfolio as optimal solution`,
      {
        decisionType: "select_candidate",
        reason: `Highest Sharpe ratio (${winner.metrics?.sharpe?.toFixed(2)}) with acceptable risk`,
        confidence: 0.94,
        inputsConsidered: candidateIds.map((id) => `${id}: Sharpe ${state.candidates.get(id)?.metrics?.sharpe?.toFixed(2)}`),
        selectedCandidateId: winnerId,
        affectedCandidateIds: candidateIds,
      } as DecisionEventData as unknown as Record<string, unknown>
    )
  );
  await d(500);

  // Update winner status
  yield toRunEvent(
    createEvent(runId, traceId, "candidate.updated", "orchestrator", "Orchestrator", `Candidate ${winnerId} selected as winner`, {
      candidateId: winnerId,
      solver: winner.solver,
      status: "selected",
      allocations: winner.allocations,
      metrics: winner.metrics,
    } as CandidateEventData as unknown as Record<string, unknown>)
  );
  await d(300);

  // Portfolio update
  yield toRunEvent(
    createEvent(runId, traceId, "portfolio.update", "orchestrator", "Orchestrator", "Final portfolio allocation committed", {
      candidateId: winnerId,
      allocations: winner.allocations,
      metrics: winner.metrics,
      isIntermediate: false,
    } as PortfolioUpdateEventData as unknown as Record<string, unknown>)
  );
  await d(300);

  // ============================================
  // 8. FINAL AGENTS
  // ============================================

  // Rebalance Planner (if included)
  if (state.currentAgentIds.includes("rebalance_planner_agent")) {
    yield* executeAgent(state, "rebalance_planner_agent", "Generating trade list and drift bands", d);
  }

  // Explain Memo Agent (always)
  yield* executeAgent(state, "explain_memo_agent", "Generating IC memo and decision explanations", d);

  // Emit portfolio explanation
  const explanationText = generatePortfolioExplanation(winner.allocations!, winner.metrics!, actualPolicy);
  yield toRunEvent(
    createEvent(runId, traceId, "portfolio.explanation", "explain_memo_agent", "Explain Memo Agent", "Portfolio explanation generated", {
      explanation: explanationText,
      candidateId: winnerId,
    })
  );
  await d(300);

  // Audit Provenance Agent (always)
  yield* executeAgent(state, "audit_provenance_agent", "Finalizing audit trail", d);

  // ============================================
  // 9. RUN COMPLETED
  // ============================================

  yield toRunEvent(
    createEvent(runId, traceId, "run.completed", "orchestrator", "Orchestrator", "Portfolio optimization completed successfully", {
      allocations: winner.allocations,
      metrics: winner.metrics,
      agentsExecuted: state.currentAgentIds.length,
      candidatesEvaluated: state.candidates.size,
    })
  );
}

// ============================================
// Agent Execution Helpers
// ============================================

async function* executeAgent(
  state: GeneratorState,
  agentId: string,
  objective: string,
  d: (ms: number) => Promise<void>
): AsyncGenerator<RunEvent> {
  const agent = getAgent(agentId);
  if (!agent) return;

  const spanId = createSpanId();

  // Span started
  yield toRunEvent(
    createEvent(
      state.runId,
      state.traceId,
      "span.started",
      "agent",
      agent.name,
      `${agent.name} started: ${objective}`,
      {
        agent_id: agentId,
        agent_name: agent.name,
        status: "running",
        current_objective: objective,
        progress: 0,
      },
      { spanId }
    )
  );
  await d(800);

  // Progress update
  yield toRunEvent(
    createEvent(
      state.runId,
      state.traceId,
      "span.started",
      "agent",
      agent.name,
      `${agent.name} processing...`,
      {
        agent_id: agentId,
        status: "running",
        progress: 50,
      },
      { spanId }
    )
  );
  await d(1200);

  // Evidence
  const evidence = generateEvidence(agentId, state.policy);
  yield toRunEvent(
    createEvent(state.runId, state.traceId, "agent.evidence", "agent", agent.name, evidence.summary, {
      agentId,
      agentName: agent.name,
      evidenceType: evidence.type,
      summary: evidence.summary,
      confidence: evidence.confidence,
    } as EvidenceEventData as unknown as Record<string, unknown>)
  );
  await d(500);

  // Span ended
  yield toRunEvent(
    createEvent(
      state.runId,
      state.traceId,
      "span.ended",
      "agent",
      agent.name,
      `${agent.name} completed`,
      {
        agent_id: agentId,
        status: "completed",
        progress: 100,
      },
      { spanId }
    )
  );
  await d(300);
}

async function* executeHandover(
  state: GeneratorState,
  fromAgentId: string,
  toAgentId: string,
  reason: string,
  d: (ms: number) => Promise<void>
): AsyncGenerator<RunEvent> {
  const fromAgent = getAgent(fromAgentId) || { name: fromAgentId };
  const toAgent = getAgent(toAgentId) || { name: toAgentId };

  yield toRunEvent(
    createEvent(state.runId, state.traceId, "handover", "orchestrator", "Orchestrator", `Handover: ${fromAgent.name} → ${toAgent.name}`, {
      fromAgent: fromAgent.name,
      toAgent: toAgent.name,
      reason,
    } as HandoverEventData as unknown as Record<string, unknown>)
  );
  await d(200);
}

async function* createCandidate(
  state: GeneratorState,
  candidateId: string,
  solver: string,
  d: (ms: number) => Promise<void>
): AsyncGenerator<RunEvent> {
  const allocations = generateAllocations(state.policy);
  const metrics = generateMetrics(state.policy, solver);

  const candidate: CandidateEventData = {
    candidateId,
    solver,
    status: "pending",
    allocations,
    metrics,
  };

  state.candidates.set(candidateId, candidate);

  yield toRunEvent(
    createEvent(
      state.runId,
      state.traceId,
      "candidate.created",
      "agent",
      `${solver} Optimizer`,
      `Created candidate ${candidateId} using ${solver}`,
      candidate as unknown as Record<string, unknown>,
      { candidateId }
    )
  );
  await d(600);

  // Intermediate portfolio update
  yield toRunEvent(
    createEvent(
      state.runId,
      state.traceId,
      "portfolio.update",
      "agent",
      `${solver} Optimizer`,
      `Candidate ${candidateId} portfolio: Sharpe ${metrics.sharpe?.toFixed(2)}`,
      {
        candidateId,
        allocations,
        metrics,
        isIntermediate: true,
      } as PortfolioUpdateEventData as unknown as Record<string, unknown>,
      { candidateId }
    )
  );
  await d(400);
}

async function* validateGate(
  state: GeneratorState,
  candidateId: string,
  gateType: "compliance" | "stress" | "redteam" | "liquidity",
  d: (ms: number) => Promise<void>
): AsyncGenerator<RunEvent> {
  const candidate = state.candidates.get(candidateId);
  if (!candidate) return;

  const gateResult = generateGateResult(gateType, state.policy);

  yield toRunEvent(
    createEvent(
      state.runId,
      state.traceId,
      `gate.${gateType}` as TraceEventType,
      "agent",
      `${gateType.charAt(0).toUpperCase() + gateType.slice(1)} Agent`,
      `Gate ${gateType}: ${gateResult.passed ? "PASSED" : "FAILED"} for ${candidateId}`,
      {
        gateType,
        candidateId,
        passed: gateResult.passed,
        details: gateResult.details,
      } as GateEventData as unknown as Record<string, unknown>,
      { candidateId, level: gateResult.passed ? "info" : "warn" }
    )
  );
  await d(500);

  // Update candidate gates
  if (!candidate.gates) {
    (candidate as unknown as { gates: Record<string, unknown> }).gates = {};
  }
  (candidate as unknown as { gates: Record<string, { passed: boolean }> }).gates[gateType] = { passed: gateResult.passed };

  if (gateResult.passed) {
    candidate.status = "passed";
  }
}

async function* executeRepairLoop(
  state: GeneratorState,
  candidateId: string,
  d: (ms: number) => Promise<void>
): AsyncGenerator<RunEvent> {
  // Repair started
  yield toRunEvent(
    createEvent(
      state.runId,
      state.traceId,
      "repair.started",
      "agent",
      "Constraint Repair Agent",
      "Starting constraint repair loop",
      {
        repairType: "constraint",
        candidateId,
        iteration: 1,
        maxIterations: 2,
        changes: [
          { field: "max_volatility_pct", from: state.policy.maxVolatilityPct, to: state.policy.maxVolatilityPct + 3, reason: "Relax volatility to allow feasible solution" },
        ],
      } as RepairEventData as unknown as Record<string, unknown>,
      { candidateId }
    )
  );
  await d(1000);

  // Repair ended
  yield toRunEvent(
    createEvent(state.runId, state.traceId, "repair.ended", "agent", "Constraint Repair Agent", "Constraint repair successful", {
      repairType: "constraint",
      candidateId,
      iteration: 1,
      maxIterations: 2,
      changes: [
        { field: "max_volatility_pct", from: state.policy.maxVolatilityPct, to: state.policy.maxVolatilityPct + 3, reason: "Volatility relaxed" },
      ],
      success: true,
    } as RepairEventData as unknown as Record<string, unknown>)
  );
  await d(500);
}

// ============================================
// Data Generation Helpers
// ============================================

function generateEvidence(agentId: string, policy: PolicyInput): { type: string; summary: string; confidence: number } {
  const evidenceMap: Record<string, { type: string; summary: string; confidence: number }> = {
    policy_agent: {
      type: "constraint",
      summary: `Policy parsed: ${policy.riskTolerance} risk, ${policy.maxVolatilityPct}% max vol`,
      confidence: 0.98,
    },
    market_agent: {
      type: "data",
      summary: `Built universe of ${45 + Math.floor(Math.random() * 20)} securities`,
      confidence: 0.95,
    },
    data_quality_agent: {
      type: "validation",
      summary: `Data quality score: ${92 + Math.floor(Math.random() * 8)}%`,
      confidence: 0.94,
    },
    risk_agent: {
      type: "constraint",
      summary: `Max equity for ${policy.maxDrawdownPct}% drawdown: ${Math.round(policy.maxDrawdownPct * 3)}%`,
      confidence: 0.91,
    },
    return_agent: {
      type: "forecast",
      summary: `Expected return: ${(policy.benchmark.targetReturnPct * 0.95).toFixed(1)}% achievable`,
      confidence: 0.85,
    },
    scenario_stress_agent: {
      type: "stress_test",
      summary: `Stress test: ${policy.riskTolerance === "conservative" ? "2 minor breaches" : "all scenarios passed"}`,
      confidence: 0.89,
    },
    liquidity_tc_agent: {
      type: "insight",
      summary: `Estimated turnover: ${20 + Math.floor(Math.random() * 30)}%, TC impact: ${(0.05 + Math.random() * 0.1).toFixed(2)}%`,
      confidence: 0.88,
    },
    hedge_tail_agent: {
      type: "insight",
      summary: `Tail hedge suggestion: ${policy.maxDrawdownPct <= 15 ? "Put spread overlay recommended" : "No overlay needed"}`,
      confidence: 0.82,
    },
    optimizer_agent: {
      type: "optimization",
      summary: `Optimal Sharpe: ${(0.4 + Math.random() * 0.3).toFixed(2)}, Vol: ${(8 + Math.random() * 8).toFixed(1)}%`,
      confidence: 0.92,
    },
    rebalance_planner_agent: {
      type: "insight",
      summary: `Trade list: ${8 + Math.floor(Math.random() * 10)} trades, drift band: ±5%`,
      confidence: 0.94,
    },
    explain_memo_agent: {
      type: "insight",
      summary: `IC memo generated with ${3 + Math.floor(Math.random() * 3)} key decision points`,
      confidence: 0.96,
    },
    audit_provenance_agent: {
      type: "validation",
      summary: `Audit trail finalized: ${15 + Math.floor(Math.random() * 10)} events recorded`,
      confidence: 0.99,
    },
  };

  return evidenceMap[agentId] || { type: "insight", summary: "Processing completed", confidence: 0.90 };
}

function generateAllocations(policy: PolicyInput): Record<string, number> {
  const isConservative = policy.riskTolerance === "conservative";
  const isAggressive = policy.riskTolerance === "aggressive" || policy.riskTolerance === "very_aggressive";

  if (isConservative) {
    return { BND: 0.35, VCSH: 0.15, BNDX: 0.10, VTI: 0.20, VXUS: 0.10, VNQ: 0.05, CASH: 0.05 };
  } else if (isAggressive) {
    return { VTI: 0.40, QQQ: 0.15, VXUS: 0.15, VWO: 0.05, BND: 0.15, VNQ: 0.05, CASH: 0.05 };
  } else {
    return { VTI: 0.35, VXUS: 0.15, BND: 0.30, BNDX: 0.10, VNQ: 0.05, CASH: 0.05 };
  }
}

function generateMetrics(
  policy: PolicyInput,
  solver: string
): { expectedReturn: number; volatility: number; sharpe: number; var95: number; turnover?: number } {
  const baseReturn =
    policy.riskTolerance === "conservative" ? 4.5 : policy.riskTolerance === "aggressive" ? 9.0 : 7.0;
  const baseVol =
    policy.riskTolerance === "conservative" ? 7.0 : policy.riskTolerance === "aggressive" ? 16.0 : 11.0;

  // Solver-specific adjustments
  const solverAdjust = {
    "Mean-Variance": { ret: 0, vol: 0, sharpe: 0.02 },
    CVaR: { ret: -0.3, vol: -1.0, sharpe: 0.01 },
    "Risk Parity": { ret: -0.5, vol: -2.0, sharpe: -0.02 },
  }[solver] || { ret: 0, vol: 0, sharpe: 0 };

  const expectedReturn = baseReturn + solverAdjust.ret + (Math.random() - 0.5);
  const volatility = baseVol + solverAdjust.vol + (Math.random() - 0.5) * 2;
  const sharpe = (expectedReturn - 2) / volatility + solverAdjust.sharpe;

  return {
    expectedReturn: Math.round(expectedReturn * 10) / 10,
    volatility: Math.round(volatility * 10) / 10,
    sharpe: Math.round(sharpe * 100) / 100,
    var95: Math.round(volatility * 0.08 * 100) / 100 / 100,
    turnover: 20 + Math.floor(Math.random() * 30),
  };
}

function generatePortfolioExplanation(
  allocations: Record<string, number>,
  metrics: { expectedReturn?: number; volatility?: number; sharpe?: number },
  policy: PolicyInput
): string {
  const topHoldings = Object.entries(allocations)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([asset, weight]) => `${asset} (${(weight * 100).toFixed(0)}%)`)
    .join(", ");

  const riskProfile = policy.riskTolerance === "conservative"
    ? "capital preservation with modest growth"
    : policy.riskTolerance === "aggressive"
    ? "growth-oriented with higher risk tolerance"
    : "balanced growth with moderate risk";

  const themes = policy.preferences.themes.length > 0
    ? ` with exposure to ${policy.preferences.themes.join(" and ")}`
    : "";

  return `This portfolio is designed for ${riskProfile}${themes}. The allocation is anchored by ${topHoldings}, targeting a ${metrics.expectedReturn?.toFixed(1)}% expected return with ${metrics.volatility?.toFixed(1)}% volatility (Sharpe ratio: ${metrics.sharpe?.toFixed(2)}). The diversified structure across domestic equities, international stocks, and fixed income helps manage drawdown risk while pursuing the ${policy.benchmark.targetReturnPct}% return target.`;
}

function generateGateResult(
  gateType: "compliance" | "stress" | "redteam" | "liquidity",
  policy: PolicyInput
): { passed: boolean; details: Record<string, unknown> } {
  switch (gateType) {
    case "compliance":
      return {
        passed: true,
        details: { violations: [], checks: ["exclusions", "concentration", "esg"] },
      };
    case "stress":
      const breaches = policy.riskTolerance === "conservative" ? Math.floor(Math.random() * 3) : 0;
      return {
        passed: breaches === 0,
        details: {
          breaches,
          scenarios: [
            { name: "rates_up_200bp", impact: -2.5, passed: true },
            { name: "equity_crash_20", impact: -8.0, passed: breaches === 0 },
            { name: "credit_spread_widen", impact: -1.5, passed: true },
          ],
        },
      };
    case "redteam":
      return {
        passed: true,
        details: { severity: "low", vulnerabilities: [] },
      };
    case "liquidity":
      const turnover = 25 + Math.floor(Math.random() * 20);
      const threshold = policy.riskTolerance === "conservative" ? 20 : 35;
      return {
        passed: turnover <= threshold * 1.5,
        details: { turnover, threshold, slippage: 0.05 },
      };
  }
}

// ============================================
// Public API
// ============================================

/**
 * Run a mock optimization and call the callback for each event.
 * Returns a function to abort the run.
 */
export function runMockOptimization(
  runId: string,
  onEvent: (event: RunEvent) => void,
  speedMultiplier: number = 1,
  policy?: PolicyInput | LegacyPolicy
): () => void {
  let aborted = false;

  (async () => {
    for await (const event of generateMockEvents(runId, speedMultiplier, policy)) {
      if (aborted) break;
      onEvent(event);
    }
  })();

  return () => {
    aborted = true;
  };
}

/**
 * Get all events for a complete run (for replay).
 */
export async function getAllMockEvents(runId: string, policy?: PolicyInput | LegacyPolicy): Promise<RunEvent[]> {
  const events: RunEvent[] = [];
  for await (const event of generateMockEvents(runId, 1000, policy)) {
    events.push(event);
  }
  return events;
}
