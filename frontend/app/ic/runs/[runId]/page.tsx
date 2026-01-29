"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  Play,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useICStore, RunMetadata } from "@/store/ic-store";
import { useSSE } from "@/hooks/use-sse";
import { WorkflowTimeline } from "@/components/ic/workflow-timeline";
import { CandidateSwimlanes } from "@/components/ic/candidate-swimlanes";
import { EventFeed } from "@/components/ic/event-feed";
import { formatDistanceToNow } from "date-fns";
import { formatDuration } from "@/lib/utils";

export default function RunDetailPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.runId as string;

  const { currentRun, setCurrentRun, events, clearEvents, isConnected } = useICStore();
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("workflow");

  // Fetch initial run data
  useEffect(() => {
    const fetchRun = async () => {
      try {
        const res = await fetch(`/api/ic/runs/${runId}`);
        if (res.ok) {
          const data = await res.json();
          setCurrentRun(data as RunMetadata);
        }
      } catch (error) {
        console.error("Failed to fetch run:", error);
      } finally {
        setLoading(false);
      }
    };

    clearEvents();
    fetchRun();

    return () => {
      setCurrentRun(null);
      clearEvents();
    };
  }, [runId, setCurrentRun, clearEvents]);

  // Connect to SSE for live updates
  const { reconnecting, reconnect } = useSSE({
    runId,
    enabled: currentRun?.status === "running" || currentRun?.status === "pending",
  });

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!currentRun) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <XCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
          <h2 className="text-xl font-semibold mb-2">Run not found</h2>
          <Button variant="outline" onClick={() => router.push("/ic")}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  const statusConfig = {
    pending: { icon: Clock, color: "text-muted-foreground", bg: "bg-surface-2" },
    running: { icon: Loader2, color: "text-amber-500", bg: "bg-amber-500/10" },
    completed: { icon: CheckCircle2, color: "text-success", bg: "bg-success/10" },
    failed: { icon: XCircle, color: "text-destructive", bg: "bg-destructive/10" },
    cancelled: { icon: XCircle, color: "text-muted-foreground", bg: "bg-surface-2" },
  };

  const status = statusConfig[currentRun.status] || statusConfig.pending;
  const StatusIcon = status.icon;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border/50 sticky top-0 bg-background/95 backdrop-blur z-10">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="icon" onClick={() => router.push("/ic")}>
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="font-semibold">IC Run</h1>
                  <code className="text-sm text-muted-foreground bg-surface-2 px-2 py-0.5 rounded">
                    {runId.slice(0, 8)}
                  </code>
                </div>
                <div className="text-sm text-muted-foreground">
                  {currentRun.mandate_id} • Seed {currentRun.seed}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {/* Connection Status */}
              {currentRun.status === "running" && (
                <div className="flex items-center gap-2 text-sm">
                  {isConnected ? (
                    <Badge variant="success" className="gap-1">
                      <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
                      Live
                    </Badge>
                  ) : reconnecting ? (
                    <Badge variant="warning" className="gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Reconnecting
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="gap-1">
                      <WifiOff className="h-3 w-3" />
                      Disconnected
                    </Badge>
                  )}
                </div>
              )}

              {/* Status Badge */}
              <Badge variant={currentRun.status === "running" ? "running" : currentRun.status === "completed" ? "success" : "secondary"}>
                <StatusIcon className={`h-3 w-3 mr-1 ${currentRun.status === "running" ? "animate-spin" : ""}`} />
                {currentRun.status}
              </Badge>

              {/* Elapsed Time */}
              <div className="text-sm text-muted-foreground">
                <Clock className="h-3 w-3 inline mr-1" />
                {currentRun.started_at
                  ? formatDistanceToNow(new Date(currentRun.started_at), { addSuffix: false })
                  : "Not started"}
              </div>
            </div>
          </div>

          {/* Progress Bar */}
          {currentRun.status === "running" && (
            <div className="mt-4">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">
                  Stage {currentRun.stages_completed + 1} of {currentRun.total_stages}
                </span>
                <span>{currentRun.progress_pct.toFixed(0)}%</span>
              </div>
              <div className="h-1 bg-surface-2 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${currentRun.progress_pct}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList>
            <TabsTrigger value="workflow">Workflow</TabsTrigger>
            <TabsTrigger value="candidates">Candidates</TabsTrigger>
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
          </TabsList>

          <TabsContent value="workflow" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Workflow Timeline */}
              <div className="lg:col-span-2">
                <WorkflowTimeline stages={currentRun.stages} currentStage={currentRun.current_stage} />
              </div>

              {/* Candidate Status */}
              <div>
                <CandidateSwimlanes
                  candidates={currentRun.candidates}
                  selectedCandidate={currentRun.selected_candidate}
                />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="candidates">
            <CandidateSwimlanes
              candidates={currentRun.candidates}
              selectedCandidate={currentRun.selected_candidate}
              expanded
            />
          </TabsContent>

          <TabsContent value="events">
            <EventFeed events={events} />
          </TabsContent>

          <TabsContent value="artifacts">
            <ArtifactsTab runId={runId} />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

// Artifacts Tab Component
function ArtifactsTab({ runId }: { runId: string }) {
  const [artifacts, setArtifacts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchArtifacts = async () => {
      try {
        const res = await fetch(`/api/ic/runs/${runId}/artifacts`);
        if (res.ok) {
          const data = await res.json();
          setArtifacts(data.artifacts || {});
        }
      } catch (error) {
        console.error("Failed to fetch artifacts:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchArtifacts();
  }, [runId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const artifactList = Object.entries(artifacts);

  if (artifactList.length === 0) {
    return (
      <div className="text-center py-10 text-muted-foreground">
        No artifacts yet
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {artifactList.map(([type, version]) => (
        <Card key={type}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono">{type}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <Badge variant="secondary">v{version}</Badge>
              <Button variant="ghost" size="sm">
                View
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
