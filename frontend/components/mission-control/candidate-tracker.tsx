"use client";

import { useOrchestratorStore, Candidate } from "@/store/orchestrator-store";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import {
  CheckCircle,
  XCircle,
  Clock,
  Trophy,
  ChevronDown,
  ChevronUp,
  Shield,
  Activity,
  Target,
  Zap,
  TrendingUp,
  AlertTriangle,
} from "lucide-react";

interface GateBadgeProps {
  name: string;
  passed?: boolean;
  pending?: boolean;
}

function GateBadge({ name, passed, pending }: GateBadgeProps) {
  if (pending) {
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-500/10 text-slate-400 border border-slate-500/20">
        <Clock className="w-3 h-3" />
        {name}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
        passed
          ? "bg-green-500/10 text-green-400 border border-green-500/20"
          : "bg-red-500/10 text-red-400 border border-red-500/20"
      }`}
    >
      {passed ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
      {name}
    </span>
  );
}

interface CandidateCardProps {
  candidate: Candidate;
  isSelected: boolean;
}

function CandidateCard({ candidate, isSelected }: CandidateCardProps) {
  const [expanded, setExpanded] = useState(false);

  const statusColors: Record<string, string> = {
    pending: "border-slate-500/30 bg-slate-500/5",
    validating: "border-amber-500/30 bg-amber-500/5",
    passed: "border-green-500/30 bg-green-500/5",
    failed: "border-red-500/30 bg-red-500/5",
    selected: "border-green-500/50 bg-green-500/10",
    rejected: "border-slate-500/30 bg-slate-500/5",
  };

  const statusIcons: Record<string, typeof CheckCircle> = {
    pending: Clock,
    validating: Activity,
    passed: CheckCircle,
    failed: XCircle,
    selected: Trophy,
    rejected: XCircle,
  };

  const StatusIcon = statusIcons[candidate.status] || Clock;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-lg border p-3 ${statusColors[candidate.status]} ${
        isSelected ? "ring-2 ring-green-500/50" : ""
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-2">
          <StatusIcon
            className={`w-5 h-5 mt-0.5 ${
              candidate.status === "selected"
                ? "text-green-500"
                : candidate.status === "failed" || candidate.status === "rejected"
                ? "text-red-500"
                : candidate.status === "validating"
                ? "text-amber-500"
                : "text-slate-400"
            }`}
          />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">
                {candidate.id}
              </span>
              <span className="text-xs px-1.5 py-0.5 rounded bg-surface-2 text-muted-foreground">
                {candidate.solver}
              </span>
              {isSelected && (
                <span className="text-xs px-1.5 py-0.5 rounded-full bg-green-500/20 text-green-400 border border-green-500/30">
                  Selected
                </span>
              )}
            </div>

            {/* Metrics */}
            {candidate.metrics && (
              <div className="flex flex-wrap gap-3 mt-2 text-xs">
                {candidate.metrics.expectedReturn !== undefined && (
                  <span className="flex items-center gap-1 text-green-400">
                    <TrendingUp className="w-3 h-3" />
                    {candidate.metrics.expectedReturn.toFixed(1)}%
                  </span>
                )}
                {candidate.metrics.volatility !== undefined && (
                  <span className="flex items-center gap-1 text-red-400">
                    <Activity className="w-3 h-3" />
                    {candidate.metrics.volatility.toFixed(1)}%
                  </span>
                )}
                {candidate.metrics.sharpe !== undefined && (
                  <span className="flex items-center gap-1 text-amber-400">
                    <Target className="w-3 h-3" />
                    {candidate.metrics.sharpe.toFixed(2)}
                  </span>
                )}
              </div>
            )}

            {/* Gates */}
            <div className="flex flex-wrap gap-1.5 mt-2">
              <GateBadge
                name="Compliance"
                passed={candidate.gates.compliance?.passed}
                pending={!candidate.gates.compliance}
              />
              <GateBadge
                name="Stress"
                passed={candidate.gates.stress?.passed}
                pending={!candidate.gates.stress}
              />
              <GateBadge
                name="Liquidity"
                passed={candidate.gates.liquidity?.passed}
                pending={!candidate.gates.liquidity}
              />
              {candidate.gates.redteam && (
                <GateBadge
                  name="RedTeam"
                  passed={candidate.gates.redteam.passed}
                />
              )}
            </div>

            {/* Selection Reason */}
            {candidate.selectionReason && (
              <p className="text-xs text-muted-foreground mt-2">
                {candidate.selectionReason}
              </p>
            )}
          </div>
        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 hover:bg-surface-2 rounded"
        >
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          )}
        </button>
      </div>

      <AnimatePresence>
        {expanded && candidate.allocations && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 pt-3 border-t border-border/30">
              <div className="text-xs text-muted-foreground mb-2">Allocations</div>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(candidate.allocations)
                  .sort(([, a], [, b]) => b - a)
                  .map(([asset, weight]) => (
                    <div key={asset} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{asset}</span>
                      <span className="font-mono">{(weight * 100).toFixed(1)}%</span>
                    </div>
                  ))}
              </div>

              {/* Gate Details */}
              {candidate.gates.stress?.scenarios && (
                <div className="mt-3">
                  <div className="text-xs text-muted-foreground mb-1">Stress Scenarios</div>
                  <div className="space-y-1">
                    {candidate.gates.stress.scenarios.map((scenario) => (
                      <div
                        key={scenario.name}
                        className="flex items-center justify-between text-xs"
                      >
                        <span className="text-muted-foreground">{scenario.name}</span>
                        <span
                          className={
                            scenario.passed ? "text-green-400" : "text-red-400"
                          }
                        >
                          {(scenario.impact * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {candidate.gates.compliance?.issues &&
                candidate.gates.compliance.issues.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3 text-amber-500" />
                      Compliance Issues
                    </div>
                    <ul className="text-xs text-amber-400 space-y-0.5">
                      {candidate.gates.compliance.issues.map((issue, i) => (
                        <li key={i}>• {issue}</li>
                      ))}
                    </ul>
                  </div>
                )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function CandidateTracker() {
  const candidates = useOrchestratorStore((state) => state.candidates);
  const portfolio = useOrchestratorStore((state) => state.portfolio);
  const status = useOrchestratorStore((state) => state.status);

  const candidateList = Object.values(candidates);

  // Determine selected candidate
  const selectedCandidateId = candidateList.find((c) => c.status === "selected")?.id;

  if (candidateList.length === 0) {
    if (status === "idle") {
      return (
        <div className="rounded-lg border border-border/30 bg-surface-1 p-4">
          <div className="text-center text-muted-foreground text-sm py-4">
            Portfolio candidates will appear during optimization
          </div>
        </div>
      );
    }

    return (
      <div className="rounded-lg border border-border/30 bg-surface-1 p-4">
        <div className="flex items-center justify-center gap-2 text-muted-foreground text-sm py-4">
          <Clock className="w-4 h-4 animate-pulse" />
          Awaiting optimization results...
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border/30 bg-surface-1 overflow-hidden">
      <div className="p-3 border-b border-border/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-amber-500" />
            <span className="text-sm font-medium">
              Portfolio Candidates
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            {candidateList.length} candidate{candidateList.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      <div className="p-3 space-y-3">
        <AnimatePresence>
          {candidateList
            .sort((a, b) => {
              // Selected first, then by rank, then by sharpe
              if (a.status === "selected") return -1;
              if (b.status === "selected") return 1;
              if (a.rank !== undefined && b.rank !== undefined) return a.rank - b.rank;
              const sharpeA = a.metrics?.sharpe ?? 0;
              const sharpeB = b.metrics?.sharpe ?? 0;
              return sharpeB - sharpeA;
            })
            .map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                isSelected={candidate.id === selectedCandidateId}
              />
            ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
