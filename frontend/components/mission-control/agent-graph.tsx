"use client";

import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Node,
  Edge,
  NodeProps,
  Handle,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import { motion } from "framer-motion";
import { useOrchestratorStore, Agent, AgentStatus } from "@/store/orchestrator-store";
import { getAgent } from "@/lib/agent-registry";
import {
  Brain,
  TrendingUp,
  Shield,
  Sliders,
  CheckCircle,
  FileText,
  Database,
  FileSearch,
  Activity,
  Zap,
  AlertTriangle,
  Target,
  Scale,
  Wrench,
  Users,
  ClipboardCheck,
  type LucideIcon,
} from "lucide-react";

// Icon mapping from agent IDs to Lucide icons
const agentIcons: Record<string, LucideIcon> = {
  orchestrator: Brain,
  policy_agent: FileText,
  market_agent: Database,
  data_quality_agent: FileSearch,
  risk_agent: Shield,
  return_agent: TrendingUp,
  optimizer_agent: Sliders,
  compliance_agent: CheckCircle,
  scenario_stress_agent: Activity,
  liquidity_tc_agent: Zap,
  hedge_tail_agent: AlertTriangle,
  challenger_optimizer_agent: Users,
  red_team_agent: Target,
  rebalance_planner_agent: Scale,
  constraint_repair_agent: Wrench,
  explain_memo_agent: ClipboardCheck,
  audit_provenance_agent: FileText,
};

const statusColors: Record<AgentStatus, string> = {
  idle: "border-gray-500/50 bg-gray-500/5",
  queued: "border-blue-500/50 bg-blue-500/10",
  running: "border-amber-500 bg-amber-500/10 animate-pulse",
  waiting: "border-yellow-500/50 bg-yellow-500/10",
  blocked: "border-red-500 bg-red-500/10 animate-shake",
  completed: "border-green-500 bg-green-500/10",
  failed: "border-red-600 bg-red-600/10",
};

const statusDots: Record<AgentStatus, string> = {
  idle: "bg-gray-500",
  queued: "bg-blue-500",
  running: "bg-amber-500 animate-pulse",
  waiting: "bg-yellow-500",
  blocked: "bg-red-500",
  completed: "bg-green-500",
  failed: "bg-red-600",
};

function AgentNode({ data }: NodeProps<{ agent: Agent; isInjected?: boolean }>) {
  const agent = data.agent;
  const Icon = agentIcons[agent.id] || Brain;
  const isOrchestrator = agent.id === "orchestrator";
  const isInjected = data.isInjected;

  // Use agent's color from registry or default
  const agentDef = getAgent(agent.id);

  // Get description for tooltip
  const description = agentDef?.description || "";

  return (
    <motion.div
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
      className={`
        relative px-3 py-2 rounded-xl border-2 transition-all group cursor-pointer
        ${statusColors[agent.status]}
        ${isOrchestrator ? "min-w-[150px]" : "min-w-[140px]"}
        ${isInjected ? "ring-2 ring-amber-500/50 ring-offset-1 ring-offset-background" : ""}
      `}
      title={`${agent.name}\n${description}`}
    >
      {/* Connection handles */}
      <Handle type="target" position={Position.Top} className="!bg-amber-500 !w-2 !h-2 !opacity-0" />
      <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-2 !h-2 !opacity-0" />
      <Handle type="source" position={Position.Left} className="!bg-amber-500 !w-2 !h-2 !opacity-0" />
      <Handle type="source" position={Position.Right} className="!bg-amber-500 !w-2 !h-2 !opacity-0" />

      <div className="flex items-center gap-2 mb-1">
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDots[agent.status]}`} />
        <Icon className={`w-4 h-4 flex-shrink-0 ${agentDef?.color || "text-gray-400"}`} />
        <span className="font-medium text-xs text-foreground whitespace-nowrap">
          {agent.shortName || agent.name}
        </span>
      </div>

      {/* Always show description for completed/idle agents, objective for running */}
      {agent.status === "running" && agent.currentObjective ? (
        <p className="text-[10px] text-muted-foreground truncate max-w-[120px]">
          {agent.currentObjective}
        </p>
      ) : description && agent.status !== "idle" ? (
        <p className="text-[9px] text-muted-foreground/70 truncate max-w-[120px]">
          {description.split(" ").slice(0, 4).join(" ")}...
        </p>
      ) : null}

      {agent.status === "running" && agent.progress > 0 && (
        <div className="mt-1 h-1 bg-surface-2 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-amber-500"
            initial={{ width: 0 }}
            animate={{ width: `${agent.progress}%` }}
          />
        </div>
      )}

      {/* Injected badge */}
      {isInjected && (
        <div className="absolute -top-2 -right-2 px-1.5 py-0.5 text-[8px] bg-amber-500 text-white rounded-full">
          INJECTED
        </div>
      )}

      {/* Hover tooltip with full details */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-surface-1 border border-border rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 min-w-[200px]">
        <div className="font-medium text-sm mb-1">{agent.name}</div>
        <p className="text-xs text-muted-foreground">{description}</p>
        <div className="mt-2 flex items-center gap-2 text-[10px]">
          <span className={`px-1.5 py-0.5 rounded ${statusColors[agent.status]}`}>
            {agent.status}
          </span>
          {agentDef?.category && (
            <span className="text-muted-foreground">{agentDef.category}</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

const nodeTypes = { agent: AgentNode };

export function AgentGraph() {
  const agents = useOrchestratorStore((state) => state.agents);
  const plan = useOrchestratorStore((state) => state.plan);
  const handovers = useOrchestratorStore((state) => state.handovers);

  // Build nodes DYNAMICALLY - only show agents that have been activated (not idle)
  const { nodes, edges } = useMemo(() => {
    const nodeList: Node[] = [];
    const edgeList: Edge[] = [];

    // Get IDs of agents that have been activated (status is not idle)
    const activatedAgentIds = Object.entries(agents)
      .filter(([id, agent]) => agent.status !== "idle" || id === "orchestrator")
      .map(([id]) => id);

    // Get IDs of runtime-injected agents
    const injectedIds = plan.runtimeInjections.map(a => a.id);

    // Agent row positions for layout
    const agentRows: Record<string, number> = {
      orchestrator: 0,
      policy_agent: 1,
      market_agent: 2,
      data_quality_agent: 2,
      risk_agent: 3,
      return_agent: 3,
      scenario_stress_agent: 4,
      challenger_optimizer_agent: 4,
      optimizer_agent: 5,
      compliance_agent: 6,
      liquidity_tc_agent: 6,
      hedge_tail_agent: 6,
      red_team_agent: 6,
      rebalance_planner_agent: 7,
      constraint_repair_agent: 7,
      explain_memo_agent: 8,
      audit_provenance_agent: 8,
    };

    const rowY: Record<number, number> = {
      0: 0,
      1: 80,
      2: 160,
      3: 240,
      4: 320,
      5: 400,
      6: 480,
      7: 560,
      8: 640,
      9: 720,
    };

    // Group activated agents by row
    const rowAgents: Record<number, string[]> = {};
    for (const id of activatedAgentIds) {
      const row = agentRows[id] ?? 9;
      if (!rowAgents[row]) rowAgents[row] = [];
      rowAgents[row].push(id);
    }

    // Calculate positions and create nodes
    for (const [rowStr, agentIds] of Object.entries(rowAgents)) {
      const row = parseInt(rowStr);
      const count = agentIds.length;
      // Wider spacing for rows with 2 agents (bottom rows) to ensure names are visible
      const spacing = count <= 2 ? 180 : 140;
      const startX = 200 - ((count - 1) * spacing) / 2;

      agentIds.forEach((id, idx) => {
        const agent = agents[id];
        if (agent) {
          nodeList.push({
            id,
            type: "agent",
            position: { x: startX + idx * spacing, y: rowY[row] ?? 700 },
            data: {
              agent,
              isInjected: injectedIds.includes(id),
            },
          });
        }
      });
    }

    // Create edges from handovers (showing actual control flow)
    const seenEdges = new Set<string>();
    for (const handover of handovers) {
      // Only add edge if both agents are in the graph
      if (activatedAgentIds.includes(handover.from) && activatedAgentIds.includes(handover.to)) {
        const edgeId = `${handover.from}-${handover.to}`;
        if (!seenEdges.has(edgeId)) {
          seenEdges.add(edgeId);
          edgeList.push({
            id: edgeId,
            source: handover.from,
            target: handover.to,
            animated: agents[handover.to]?.status === "running",
            style: { stroke: "#f59e0b", strokeWidth: 2 },
          });
        }
      }
    }

    // If no handovers yet but we have activated agents, show edges based on execution order
    if (handovers.length === 0 && activatedAgentIds.length > 1) {
      // Sort by row to create sequential edges
      const sortedAgents = [...activatedAgentIds]
        .filter(id => id !== "orchestrator")
        .sort((a, b) => (agentRows[a] ?? 99) - (agentRows[b] ?? 99));

      // Add edge from orchestrator to first agent
      if (sortedAgents.length > 0) {
        const firstAgent = sortedAgents[0];
        edgeList.push({
          id: `o-${firstAgent}`,
          source: "orchestrator",
          target: firstAgent,
          animated: agents[firstAgent]?.status === "running",
          style: { stroke: "#666", strokeWidth: 1 },
        });
      }

      // Add sequential edges
      for (let i = 0; i < sortedAgents.length - 1; i++) {
        const from = sortedAgents[i];
        const to = sortedAgents[i + 1];
        const edgeId = `seq-${from}-${to}`;
        if (!seenEdges.has(edgeId)) {
          seenEdges.add(edgeId);
          edgeList.push({
            id: edgeId,
            source: from,
            target: to,
            animated: agents[to]?.status === "running",
            style: { stroke: "#666", strokeWidth: 1, strokeDasharray: "5,5" },
          });
        }
      }
    }

    return { nodes: nodeList, edges: edgeList };
  }, [agents, plan.runtimeInjections, handovers]);

  // Calculate stats
  const runningCount = Object.values(agents).filter(a => a.status === "running").length;
  const completedCount = Object.values(agents).filter(a => a.status === "completed").length;
  const activatedCount = Object.values(agents).filter(a => a.status !== "idle").length;
  const totalInPlan = plan.selectedAgents.length + plan.runtimeInjections.length;

  return (
    <div className="h-full w-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        panOnDrag
        zoomOnScroll
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "smoothstep",
          style: { stroke: "#666" },
        }}
      >
        <Background color="#333" gap={20} size={1} />
        <Controls showZoom={false} showFitView={true} showInteractive={false} />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-surface-1 rounded-lg p-3 border border-border/30 text-xs">
        <div className="font-medium mb-2">Status</div>
        <div className="space-y-1">
          {[
            { status: "queued", label: "Queued" },
            { status: "running", label: "Running" },
            { status: "completed", label: "Done" },
          ].map((item) => (
            <div key={item.status} className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${statusDots[item.status as AgentStatus]}`} />
              <span className="text-muted-foreground">{item.label}</span>
            </div>
          ))}
        </div>

        {/* Stats */}
        {totalInPlan > 0 && (
          <div className="mt-3 pt-3 border-t border-border/30">
            <div className="text-muted-foreground">
              {completedCount}/{totalInPlan} complete
            </div>
            <div className="text-blue-400">
              {activatedCount - 1} agents active
            </div>
            {plan.runtimeInjections.length > 0 && (
              <div className="text-amber-400 mt-1">
                +{plan.runtimeInjections.length} injected
              </div>
            )}
          </div>
        )}
      </div>

      {/* Pending agents indicator */}
      {totalInPlan > 0 && activatedCount < totalInPlan + 1 && (
        <div className="absolute top-4 right-4 bg-surface-1 rounded-lg p-3 border border-border/30 text-xs">
          <div className="font-medium mb-2">Pending</div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {plan.selectedAgents
              .filter(a => agents[a.id]?.status === "idle")
              .slice(0, 5)
              .map((a) => (
                <div key={a.id} className="flex items-center gap-2 text-muted-foreground">
                  <div className="w-2 h-2 rounded-full bg-gray-500" />
                  <span>{a.name}</span>
                </div>
              ))}
            {plan.selectedAgents.filter(a => agents[a.id]?.status === "idle").length > 5 && (
              <div className="text-muted-foreground">
                +{plan.selectedAgents.filter(a => agents[a.id]?.status === "idle").length - 5} more
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
