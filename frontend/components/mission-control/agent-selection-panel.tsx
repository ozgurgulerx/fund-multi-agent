"use client";

import { useOrchestratorStore } from "@/store/orchestrator-store";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import {
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Zap,
  Info,
  Shield,
  TrendingUp,
  Sliders,
  Database,
  Activity,
  AlertTriangle,
  Target,
  Scale,
  Users,
  FileText,
  type LucideIcon,
} from "lucide-react";

// Map agent IDs to icons
const agentIcons: Record<string, LucideIcon> = {
  market_agent: Database,
  risk_agent: Shield,
  return_agent: TrendingUp,
  optimizer_agent: Sliders,
  compliance_agent: CheckCircle,
  challenger_optimizer: Users,
  rebalance_planner: Scale,
  liquidity_tc_agent: Zap,
  esg_screening_agent: Shield,
  scenario_stress_agent: Activity,
  hedge_tail_agent: AlertTriangle,
  red_team_agent: Target,
  tax_optimizer_agent: FileText,
};

interface AgentCardProps {
  agent: {
    id: string;
    name: string;
    reason: string;
    category?: string;
  };
  included: boolean;
  injected?: boolean;
}

function AgentCard({ agent, included, injected }: AgentCardProps) {
  const Icon = agentIcons[agent.id] || Info;

  const bgColor = included
    ? injected
      ? "bg-amber-500/10 border-amber-500/30"
      : agent.category === "core"
      ? "bg-purple-500/10 border-purple-500/30"
      : "bg-green-500/10 border-green-500/30"
    : "bg-slate-500/5 border-slate-500/20";

  const textColor = included
    ? injected
      ? "text-amber-400"
      : agent.category === "core"
      ? "text-purple-400"
      : "text-green-400"
    : "text-slate-400";

  const iconColor = included
    ? injected
      ? "text-amber-500"
      : agent.category === "core"
      ? "text-purple-500"
      : "text-green-500"
    : "text-slate-500";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`rounded-lg border p-3 ${bgColor}`}
    >
      <div className="flex items-start gap-2">
        <div className={`p-1.5 rounded-md ${included ? (injected ? "bg-amber-500/20" : agent.category === "core" ? "bg-purple-500/20" : "bg-green-500/20") : "bg-slate-500/10"}`}>
          <Icon className={`w-4 h-4 ${iconColor}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-medium ${textColor}`}>
              {agent.name}
            </span>
            {injected && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
                Runtime
              </span>
            )}
            {!included && (
              <XCircle className="w-3 h-3 text-slate-500" />
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
            {agent.reason}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

export function AgentSelectionPanel() {
  const [expanded, setExpanded] = useState(true);
  const plan = useOrchestratorStore((state) => state.plan);
  const status = useOrchestratorStore((state) => state.status);

  const hasAgents = plan.selectedAgents.length > 0 || plan.excludedAgents.length > 0;

  if (!hasAgents && status === "idle") {
    return (
      <div className="rounded-lg border border-border/30 bg-surface-1 p-4">
        <div className="text-center text-muted-foreground text-sm py-4">
          Agent selection will appear when a run starts
        </div>
      </div>
    );
  }

  const coreAgents = plan.selectedAgents.filter((a) => a.category === "core");
  const conditionalAgents = plan.selectedAgents.filter((a) => a.category === "conditional");

  return (
    <div className="rounded-lg border border-border/30 bg-surface-1 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-surface-2 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-sm font-medium">{plan.selectedAgents.length}</span>
          </div>
          <span className="text-muted-foreground">|</span>
          <div className="flex items-center gap-1">
            <XCircle className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium">{plan.excludedAgents.length}</span>
          </div>
          {plan.runtimeInjections.length > 0 && (
            <>
              <span className="text-muted-foreground">|</span>
              <div className="flex items-center gap-1">
                <Zap className="w-4 h-4 text-amber-500" />
                <span className="text-sm font-medium text-amber-500">
                  +{plan.runtimeInjections.length}
                </span>
              </div>
            </>
          )}
          <span className="text-sm text-muted-foreground ml-2">agents</span>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-3 pt-0 space-y-4">
              {/* Policy Summary */}
              {plan.policySummary && (
                <div className="p-2 rounded-lg bg-surface-2 border border-border/20">
                  <div className="text-xs text-muted-foreground mb-1">Policy Profile</div>
                  <div className="flex flex-wrap gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      {plan.policySummary.riskTolerance}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                      Vol: {plan.policySummary.maxVolatility}%
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 border border-green-500/20">
                      Target: {plan.policySummary.targetReturn}%
                    </span>
                    {plan.policySummary.esgEnabled && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        ESG
                      </span>
                    )}
                    {plan.policySummary.themes.map((theme) => (
                      <span
                        key={theme}
                        className="text-xs px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20"
                      >
                        {theme}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Core Agents */}
              {coreAgents.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                    Core Agents ({coreAgents.length})
                  </div>
                  <div className="grid grid-cols-1 gap-2">
                    {coreAgents.map((agent) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        included={true}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Conditional Agents */}
              {conditionalAgents.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-green-500"></div>
                    Conditional Agents ({conditionalAgents.length})
                  </div>
                  <div className="grid grid-cols-1 gap-2">
                    {conditionalAgents.map((agent) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        included={true}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Runtime Injections */}
              {plan.runtimeInjections.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-amber-500"></div>
                    Runtime Injected ({plan.runtimeInjections.length})
                  </div>
                  <div className="grid grid-cols-1 gap-2">
                    {plan.runtimeInjections.map((agent) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        included={true}
                        injected={true}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Excluded Agents */}
              {plan.excludedAgents.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-slate-500"></div>
                    Excluded ({plan.excludedAgents.length})
                  </div>
                  <div className="grid grid-cols-1 gap-2">
                    {plan.excludedAgents.map((agent) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        included={false}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
