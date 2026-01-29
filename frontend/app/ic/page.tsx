"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Plus,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDistanceToNow } from "date-fns";

interface RunSummary {
  run_id: string;
  status: string;
  mandate_id: string;
  created_at: string;
  progress_pct: number;
  current_stage?: string;
  selected_candidate?: string;
}

const statusIcons = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: XCircle,
};

const statusBadgeVariant = {
  pending: "pending" as const,
  running: "running" as const,
  completed: "success" as const,
  failed: "destructive" as const,
  cancelled: "secondary" as const,
};

export default function ICDashboardPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  const fetchRuns = async () => {
    try {
      const res = await fetch("/api/ic/runs");
      const data = await res.json();
      setRuns(data.runs || []);
    } catch (error) {
      console.error("Failed to fetch runs:", error);
    } finally {
      setLoading(false);
    }
  };

  const startNewRun = async () => {
    setStarting(true);
    try {
      const res = await fetch("/api/ic/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mandate_id: "balanced_growth",
          seed: Math.floor(Math.random() * 10000),
        }),
      });
      const data = await res.json();
      if (data.run_id) {
        router.push(`/ic/runs/${data.run_id}`);
      }
    } catch (error) {
      console.error("Failed to start run:", error);
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    fetchRuns();
    const interval = setInterval(fetchRuns, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border/50 sticky top-0 bg-background/95 backdrop-blur z-10">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={() => router.push("/")}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center">
                <span className="text-white font-bold text-sm">IC</span>
              </div>
              <span className="font-semibold text-lg">IC Runs</span>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchRuns}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button size="sm" onClick={startNewRun} disabled={starting}>
              {starting ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Plus className="h-4 w-4 mr-2" />
              )}
              New Run
            </Button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-6 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : runs.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-20"
          >
            <div className="w-16 h-16 rounded-full bg-surface-2 flex items-center justify-center mx-auto mb-4">
              <Plus className="h-8 w-8 text-muted-foreground" />
            </div>
            <h2 className="text-xl font-semibold mb-2">No runs yet</h2>
            <p className="text-muted-foreground mb-6">
              Start your first IC Autopilot run to see it here
            </p>
            <Button onClick={startNewRun} disabled={starting}>
              {starting ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Plus className="h-4 w-4 mr-2" />
              )}
              Start First Run
            </Button>
          </motion.div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {runs.map((run, index) => {
              const StatusIcon = statusIcons[run.status as keyof typeof statusIcons] || Clock;

              return (
                <motion.div
                  key={run.run_id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                >
                  <Card
                    className="cursor-pointer hover:border-border transition-colors"
                    onClick={() => router.push(`/ic/runs/${run.run_id}`)}
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-sm font-mono">
                          {run.run_id.slice(0, 8)}...
                        </CardTitle>
                        <Badge variant={statusBadgeVariant[run.status as keyof typeof statusBadgeVariant]}>
                          <StatusIcon className={`h-3 w-3 mr-1 ${run.status === "running" ? "animate-spin" : ""}`} />
                          {run.status}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div>
                          <div className="text-sm text-muted-foreground">Mandate</div>
                          <div className="text-sm font-medium">{run.mandate_id}</div>
                        </div>

                        {run.status === "running" && (
                          <div>
                            <div className="flex justify-between text-xs mb-1">
                              <span className="text-muted-foreground">Progress</span>
                              <span>{run.progress_pct.toFixed(0)}%</span>
                            </div>
                            <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden">
                              <motion.div
                                className="h-full bg-amber-500 rounded-full"
                                initial={{ width: 0 }}
                                animate={{ width: `${run.progress_pct}%` }}
                                transition={{ duration: 0.3 }}
                              />
                            </div>
                            {run.current_stage && (
                              <div className="text-xs text-muted-foreground mt-1">
                                {run.current_stage}
                              </div>
                            )}
                          </div>
                        )}

                        {run.selected_candidate && (
                          <div>
                            <div className="text-sm text-muted-foreground">Winner</div>
                            <Badge variant="gold">Candidate {run.selected_candidate}</Badge>
                          </div>
                        )}

                        <div className="text-xs text-muted-foreground pt-2 border-t border-border/50">
                          {formatDistanceToNow(new Date(run.created_at), { addSuffix: true })}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
