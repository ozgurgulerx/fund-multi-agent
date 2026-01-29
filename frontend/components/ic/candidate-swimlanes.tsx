"use client";

import { motion } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  Shield,
  Swords,
  Trophy,
  Wrench,
} from "lucide-react";
import { CandidateProgress, StageStatus } from "@/store/ic-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface CandidateSwimlanes {
  candidates: CandidateProgress[];
  selectedCandidate?: string;
  expanded?: boolean;
}

const candidateColors = {
  A: {
    border: "border-blue-500/50",
    bg: "bg-blue-500/10",
    text: "text-blue-500",
    gradient: "from-blue-500 to-blue-600",
  },
  B: {
    border: "border-purple-500/50",
    bg: "bg-purple-500/10",
    text: "text-purple-500",
    gradient: "from-purple-500 to-purple-600",
  },
  C: {
    border: "border-emerald-500/50",
    bg: "bg-emerald-500/10",
    text: "text-emerald-500",
    gradient: "from-emerald-500 to-emerald-600",
  },
};

const statusIcons: Record<StageStatus, typeof CheckCircle2> = {
  pending: Clock,
  running: Loader2,
  succeeded: CheckCircle2,
  failed: XCircle,
  skipped: Clock,
  repaired: Wrench,
};

export function CandidateSwimlanes({
  candidates,
  selectedCandidate,
  expanded = false,
}: CandidateSwimlanes) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Candidates</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={cn("grid gap-4", expanded ? "grid-cols-1 md:grid-cols-3" : "grid-cols-1")}>
          {candidates.map((candidate, index) => {
            const colors = candidateColors[candidate.candidate_id as keyof typeof candidateColors] || candidateColors.A;
            const isSelected = candidate.candidate_id === selectedCandidate;
            const ComplianceIcon = statusIcons[candidate.compliance_status];
            const RedTeamIcon = statusIcons[candidate.redteam_status];

            return (
              <motion.div
                key={candidate.candidate_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className={cn(
                  "relative rounded-lg border-2 p-4 transition-all",
                  colors.border,
                  colors.bg,
                  isSelected && "ring-2 ring-gold ring-offset-2 ring-offset-background"
                )}
              >
                {/* Winner Badge */}
                {isSelected && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="absolute -top-3 -right-3"
                  >
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center shadow-lg">
                      <Trophy className="h-4 w-4 text-white" />
                    </div>
                  </motion.div>
                )}

                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      "w-8 h-8 rounded-full flex items-center justify-center font-bold text-white bg-gradient-to-br",
                      colors.gradient
                    )}>
                      {candidate.candidate_id}
                    </div>
                    <span className="font-medium">Candidate {candidate.candidate_id}</span>
                  </div>
                  {candidate.repair_attempts > 0 && (
                    <Badge variant="warning" className="gap-1 text-xs">
                      <Wrench className="h-3 w-3" />
                      {candidate.repair_attempts}
                    </Badge>
                  )}
                </div>

                {/* Checks */}
                <div className="space-y-3">
                  {/* Compliance */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm">
                      <Shield className="h-4 w-4 text-muted-foreground" />
                      <span>Compliance</span>
                    </div>
                    <CandidateStatusBadge
                      status={candidate.compliance_status}
                      passed={candidate.compliance_passed}
                    />
                  </div>

                  {/* Red Team */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm">
                      <Swords className="h-4 w-4 text-muted-foreground" />
                      <span>Red Team</span>
                    </div>
                    <CandidateStatusBadge
                      status={candidate.redteam_status}
                      passed={candidate.redteam_passed}
                    />
                  </div>
                </div>

                {/* Rejection Reason */}
                {candidate.rejection_reason && (
                  <div className="mt-3 pt-3 border-t border-border/50">
                    <p className="text-xs text-destructive">{candidate.rejection_reason}</p>
                  </div>
                )}

                {/* Winner Status */}
                {isSelected && (
                  <div className="mt-3 pt-3 border-t border-border/50">
                    <Badge variant="gold" className="w-full justify-center gap-1">
                      <Trophy className="h-3 w-3" />
                      Selected Winner
                    </Badge>
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function CandidateStatusBadge({
  status,
  passed,
}: {
  status: StageStatus;
  passed?: boolean;
}) {
  const Icon = statusIcons[status];

  if (status === "pending") {
    return (
      <Badge variant="pending" className="gap-1">
        <Icon className="h-3 w-3" />
        Pending
      </Badge>
    );
  }

  if (status === "running") {
    return (
      <Badge variant="running" className="gap-1">
        <Icon className="h-3 w-3 animate-spin" />
        Running
      </Badge>
    );
  }

  if (status === "succeeded" || passed === true) {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        Passed
      </Badge>
    );
  }

  if (status === "failed" || passed === false) {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="h-3 w-3" />
        Failed
      </Badge>
    );
  }

  if (status === "repaired") {
    return (
      <Badge variant="warning" className="gap-1">
        <Wrench className="h-3 w-3" />
        Repaired
      </Badge>
    );
  }

  return (
    <Badge variant="secondary" className="gap-1">
      <Icon className="h-3 w-3" />
      {status}
    </Badge>
  );
}
