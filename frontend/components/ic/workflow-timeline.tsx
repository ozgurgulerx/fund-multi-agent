"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  AlertTriangle,
  Wrench,
} from "lucide-react";
import { Stage, StageStatus } from "@/store/ic-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDuration } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface WorkflowTimelineProps {
  stages: Stage[];
  currentStage?: string;
}

const statusConfig: Record<StageStatus, {
  icon: typeof CheckCircle2;
  color: string;
  bgColor: string;
  borderColor: string;
}> = {
  pending: {
    icon: Clock,
    color: "text-muted-foreground",
    bgColor: "bg-surface-2",
    borderColor: "border-border",
  },
  running: {
    icon: Loader2,
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/50",
  },
  succeeded: {
    icon: CheckCircle2,
    color: "text-success",
    bgColor: "bg-success/10",
    borderColor: "border-success/50",
  },
  failed: {
    icon: XCircle,
    color: "text-destructive",
    bgColor: "bg-destructive/10",
    borderColor: "border-destructive/50",
  },
  skipped: {
    icon: Clock,
    color: "text-muted-foreground",
    bgColor: "bg-surface-2",
    borderColor: "border-border",
  },
  repaired: {
    icon: Wrench,
    color: "text-warning",
    bgColor: "bg-warning/10",
    borderColor: "border-warning/50",
  },
};

export function WorkflowTimeline({ stages, currentStage }: WorkflowTimelineProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Workflow Progress</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative">
          {/* Connection Line */}
          <div className="absolute left-5 top-0 bottom-0 w-0.5 bg-border" />

          {/* Stages */}
          <div className="space-y-1">
            {stages.map((stage, index) => {
              const config = statusConfig[stage.status];
              const StatusIcon = config.icon;
              const isActive = stage.stage_id === currentStage;
              const isCompleted = stage.status === "succeeded" || stage.status === "repaired";

              return (
                <motion.div
                  key={stage.stage_id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="relative"
                >
                  <div
                    className={cn(
                      "flex items-start gap-4 p-3 rounded-lg transition-colors",
                      isActive && "bg-surface-2"
                    )}
                  >
                    {/* Status Icon */}
                    <div className="relative z-10">
                      <motion.div
                        className={cn(
                          "w-10 h-10 rounded-full flex items-center justify-center border-2",
                          config.bgColor,
                          config.borderColor
                        )}
                        animate={isActive ? {
                          scale: [1, 1.1, 1],
                          boxShadow: [
                            "0 0 0 0 rgba(245, 158, 11, 0)",
                            "0 0 0 8px rgba(245, 158, 11, 0.1)",
                            "0 0 0 0 rgba(245, 158, 11, 0)",
                          ],
                        } : {}}
                        transition={{ duration: 1.5, repeat: isActive ? Infinity : 0 }}
                      >
                        <StatusIcon
                          className={cn(
                            "h-5 w-5",
                            config.color,
                            stage.status === "running" && "animate-spin"
                          )}
                        />
                      </motion.div>
                    </div>

                    {/* Stage Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{stage.stage_name}</span>
                          {stage.repair_attempts > 0 && (
                            <Badge variant="warning" className="gap-1 text-xs">
                              <Wrench className="h-3 w-3" />
                              {stage.repair_attempts} repairs
                            </Badge>
                          )}
                        </div>
                        {stage.duration_ms && (
                          <span className="text-xs text-muted-foreground">
                            {formatDuration(stage.duration_ms)}
                          </span>
                        )}
                      </div>

                      {/* Progress for running stage */}
                      {stage.status === "running" && stage.progress_pct > 0 && (
                        <div className="mt-2">
                          <div className="h-1 bg-surface-3 rounded-full overflow-hidden">
                            <motion.div
                              className="h-full bg-amber-500 rounded-full"
                              initial={{ width: 0 }}
                              animate={{ width: `${stage.progress_pct}%` }}
                            />
                          </div>
                        </div>
                      )}

                      {/* Error message */}
                      {stage.error_message && (
                        <div className="mt-1 text-sm text-destructive flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3" />
                          {stage.error_message}
                        </div>
                      )}

                      {/* Artifacts */}
                      {stage.artifacts.length > 0 && isCompleted && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {stage.artifacts.map((artifact) => (
                            <Badge key={artifact} variant="secondary" className="text-xs">
                              {artifact}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
