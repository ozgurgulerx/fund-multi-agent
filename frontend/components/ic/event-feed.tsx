"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  Play,
  Square,
  Wrench,
  Trophy,
  FileText,
  Filter,
} from "lucide-react";
import { WorkflowEvent } from "@/store/ic-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

interface EventFeedProps {
  events: WorkflowEvent[];
}

const eventConfig: Record<string, {
  icon: typeof Info;
  color: string;
  label: string;
}> = {
  run_started: { icon: Play, color: "text-blue-500", label: "Run Started" },
  run_completed: { icon: CheckCircle2, color: "text-success", label: "Run Completed" },
  run_failed: { icon: XCircle, color: "text-destructive", label: "Run Failed" },
  stage_started: { icon: Play, color: "text-amber-500", label: "Stage Started" },
  stage_completed: { icon: CheckCircle2, color: "text-success", label: "Stage Completed" },
  stage_failed: { icon: XCircle, color: "text-destructive", label: "Stage Failed" },
  candidate_created: { icon: FileText, color: "text-blue-500", label: "Candidate Created" },
  candidate_passed: { icon: CheckCircle2, color: "text-success", label: "Candidate Passed" },
  candidate_failed: { icon: XCircle, color: "text-destructive", label: "Candidate Failed" },
  candidate_repaired: { icon: Wrench, color: "text-warning", label: "Candidate Repaired" },
  compliance_check: { icon: Info, color: "text-blue-500", label: "Compliance Check" },
  redteam_check: { icon: AlertTriangle, color: "text-amber-500", label: "Red Team Check" },
  repair_iteration: { icon: Wrench, color: "text-warning", label: "Repair Iteration" },
  decision_made: { icon: Trophy, color: "text-gold", label: "Decision Made" },
  artifact_persisted: { icon: FileText, color: "text-muted-foreground", label: "Artifact Saved" },
  tool_called: { icon: Info, color: "text-muted-foreground", label: "Tool Called" },
  tool_completed: { icon: CheckCircle2, color: "text-muted-foreground", label: "Tool Completed" },
  progress_update: { icon: Info, color: "text-muted-foreground", label: "Progress" },
};

const eventFilters = [
  { id: "all", label: "All" },
  { id: "stages", label: "Stages" },
  { id: "candidates", label: "Candidates" },
  { id: "tools", label: "Tools" },
];

export function EventFeed({ events }: EventFeedProps) {
  const [filter, setFilter] = useState("all");

  const filteredEvents = useMemo(() => {
    if (filter === "all") return events;
    if (filter === "stages") {
      return events.filter(e =>
        e.kind.includes("stage") || e.kind.includes("run")
      );
    }
    if (filter === "candidates") {
      return events.filter(e =>
        e.kind.includes("candidate") || e.kind.includes("compliance") ||
        e.kind.includes("redteam") || e.kind.includes("repair") ||
        e.kind.includes("decision")
      );
    }
    if (filter === "tools") {
      return events.filter(e => e.kind.includes("tool"));
    }
    return events;
  }, [events, filter]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-lg">Event Log</CardTitle>
        <div className="flex gap-1">
          {eventFilters.map((f) => (
            <Button
              key={f.id}
              variant={filter === f.id ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[500px] pr-4">
          <div className="space-y-2">
            <AnimatePresence mode="popLayout">
              {filteredEvents.length === 0 ? (
                <div className="text-center py-10 text-muted-foreground">
                  No events yet
                </div>
              ) : (
                [...filteredEvents].reverse().map((event, index) => {
                  const config = eventConfig[event.kind] || {
                    icon: Info,
                    color: "text-muted-foreground",
                    label: event.kind,
                  };
                  const Icon = config.icon;

                  return (
                    <motion.div
                      key={event.event_id}
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, x: -10 }}
                      transition={{ duration: 0.2 }}
                      className={cn(
                        "flex items-start gap-3 p-3 rounded-lg bg-surface-1 border border-border/50",
                        event.level === "error" && "bg-destructive/5 border-destructive/20",
                        event.level === "warn" && "bg-warning/5 border-warning/20"
                      )}
                    >
                      <div className={cn("mt-0.5", config.color)}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm">
                            {config.label}
                          </span>
                          {event.stage_name && (
                            <Badge variant="secondary" className="text-xs">
                              {event.stage_name}
                            </Badge>
                          )}
                          {event.candidate_id && (
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-xs",
                                event.candidate_id === "A" && "border-blue-500/50 text-blue-500",
                                event.candidate_id === "B" && "border-purple-500/50 text-purple-500",
                                event.candidate_id === "C" && "border-emerald-500/50 text-emerald-500"
                              )}
                            >
                              Candidate {event.candidate_id}
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          {event.message}
                        </p>
                        {event.duration_ms && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Duration: {event.duration_ms}ms
                          </p>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatDistanceToNow(new Date(event.ts), { addSuffix: true })}
                      </div>
                    </motion.div>
                  );
                })
              )}
            </AnimatePresence>
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
