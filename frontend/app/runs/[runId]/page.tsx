"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, ExternalLink, Pause, Play, RotateCcw, FastForward, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentGraph } from "@/components/mission-control/agent-graph";
import { OrchestratorTimeline } from "@/components/mission-control/orchestrator-timeline";
import { PortfolioCanvas } from "@/components/mission-control/portfolio-canvas";
import { AgentSelectionPanel } from "@/components/mission-control/agent-selection-panel";
import { CandidateTracker } from "@/components/mission-control/candidate-tracker";
import { useOrchestratorStore } from "@/store/orchestrator-store";
import { runMockOptimization, RunEvent, InvestorPolicy } from "@/lib/mock-events";

export default function MissionControlPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.runId as string;

  const { setRunId, processEvent, reset, status } = useOrchestratorStore();
  const [isPaused, setIsPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [useMock, setUseMock] = useState(false);
  const [policy, setPolicy] = useState<InvestorPolicy | undefined>(undefined);
  const abortRef = useRef<(() => void) | null>(null);
  const eventsRef = useRef<RunEvent[]>([]);

  // Load policy from sessionStorage
  useEffect(() => {
    if (typeof window !== "undefined" && runId) {
      const storedPolicy = sessionStorage.getItem(`policy-${runId}`);
      if (storedPolicy) {
        try {
          setPolicy(JSON.parse(storedPolicy));
        } catch (e) {
          console.error("Failed to parse policy:", e);
        }
      }
    }
  }, [runId]);

  // Start mock run if no real backend
  const startMockRun = useCallback(() => {
    reset();
    setRunId(runId);
    eventsRef.current = [];

    abortRef.current = runMockOptimization(
      runId,
      (event) => {
        eventsRef.current.push(event);
        processEvent({
          run_id: runId,
          kind: event.type,
          message: event.message || event.type,
          payload: event.payload,
          ts: event.ts,
        });
      },
      speed,
      policy // Pass the policy to the mock generator
    );
  }, [runId, speed, reset, setRunId, processEvent, policy]);

  // Set up SSE connection or use mock
  useEffect(() => {
    if (!runId) return;

    setRunId(runId);

    // Try real SSE first
    const eventSource = new EventSource(`/api/ic/runs/${runId}/events`);
    let sseWorking = false;

    const timeout = setTimeout(() => {
      if (!sseWorking) {
        console.log("SSE not available, using mock events");
        setUseMock(true);
        eventSource.close();
        startMockRun();
      }
    }, 2000);

    eventSource.onopen = () => {
      sseWorking = true;
      clearTimeout(timeout);
    };

    eventSource.onmessage = (event) => {
      sseWorking = true;
      try {
        const data = JSON.parse(event.data);
        processEvent(data);
      } catch (error) {
        console.error("Failed to parse event:", error);
      }
    };

    eventSource.onerror = () => {
      if (!useMock && !sseWorking) {
        clearTimeout(timeout);
        setUseMock(true);
        eventSource.close();
        startMockRun();
      }
    };

    return () => {
      clearTimeout(timeout);
      eventSource.close();
      if (abortRef.current) {
        abortRef.current();
      }
    };
  }, [runId, setRunId, processEvent, useMock, startMockRun]);

  const handleRestart = () => {
    if (abortRef.current) {
      abortRef.current();
    }
    startMockRun();
  };

  const handleViewResults = () => {
    router.push(`/runs/${runId}/results`);
  };

  const handleSpeedChange = () => {
    const speeds = [1, 2, 4];
    const currentIndex = speeds.indexOf(speed);
    const nextSpeed = speeds[(currentIndex + 1) % speeds.length];
    setSpeed(nextSpeed);
  };

  const handleExport = () => {
    const data = {
      runId,
      events: eventsRef.current,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `run-${runId}-events.json`;
    a.click();
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border/30 bg-background/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/")}
              className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Home
            </button>
            <div className="h-4 w-px bg-border" />
            <div>
              <span className="font-semibold text-sm">Mission Control</span>
              <span className="text-xs text-muted-foreground ml-2">
                {useMock && <span className="text-amber-500">[Demo Mode]</span>} Run: {runId.slice(0, 8)}...
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Speed Control */}
            {useMock && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleSpeedChange}
                className="gap-1"
              >
                <FastForward className="w-4 h-4" />
                {speed}x
              </Button>
            )}

            {/* Restart */}
            {useMock && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleRestart}
              >
                <RotateCcw className="w-4 h-4 mr-1" />
                Restart
              </Button>
            )}

            {/* Export */}
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
            >
              Export
            </Button>

            {status === "completed" && (
              <Button
                variant="default"
                size="sm"
                onClick={handleViewResults}
                className="bg-green-500 hover:bg-green-600"
              >
                View Results
                <ExternalLink className="w-4 h-4 ml-1" />
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Status Banner */}
      <div className="border-b border-border/30 bg-surface-1">
        <div className="container mx-auto px-6 py-2">
          <StatusBanner />
        </div>
      </div>

      {/* Main Content - 3 Column Layout */}
      <main className="container mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-180px)]">
          {/* Left Column: Agent Selection + Agent Graph */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-col gap-4 overflow-hidden"
          >
            {/* Agent Selection Panel */}
            <div className="flex-shrink-0 max-h-[40%] overflow-auto">
              <AgentSelectionPanel />
            </div>

            {/* Agent Graph */}
            <div className="flex-1 min-h-0 bg-card border border-border/30 rounded-xl p-4 relative overflow-hidden">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-amber-500" />
                Agent Network
              </h3>
              <div className="h-[calc(100%-40px)]">
                <AgentGraph />
              </div>
            </div>
          </motion.div>

          {/* Center: Orchestrator Timeline */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-card border border-border/30 rounded-xl p-4 overflow-hidden"
          >
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500" />
              Orchestrator Decisions
            </h3>
            <div className="h-[calc(100%-40px)]">
              <OrchestratorTimeline />
            </div>
          </motion.div>

          {/* Right Column: Candidate Tracker + Portfolio Canvas */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="flex flex-col gap-4 overflow-hidden"
          >
            {/* Candidate Tracker */}
            <div className="flex-shrink-0 max-h-[50%] overflow-auto">
              <CandidateTracker />
            </div>

            {/* Portfolio Canvas */}
            <div className="flex-1 min-h-0 bg-card border border-border/30 rounded-xl p-4 overflow-hidden">
              <PortfolioCanvas />
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}

function StatusBanner() {
  const { status, statusMessage, agents } = useOrchestratorStore();

  const runningAgents = Object.values(agents).filter((a) => a.status === "running");
  const completedAgents = Object.values(agents).filter((a) => a.status === "completed");

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-4">
        {/* Live indicator */}
        <div className="flex items-center gap-2">
          {status === "running" ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
              </span>
              <span className="text-sm font-medium text-amber-500">LIVE</span>
            </>
          ) : status === "completed" ? (
            <>
              <span className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-sm font-medium text-green-500">COMPLETED</span>
            </>
          ) : status === "failed" ? (
            <>
              <span className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-sm font-medium text-red-500">FAILED</span>
            </>
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-gray-500" />
              <span className="text-sm font-medium text-gray-500">IDLE</span>
            </>
          )}
        </div>

        {/* Current status message */}
        <span className="text-sm text-muted-foreground truncate max-w-md">
          {statusMessage}
        </span>
      </div>

      {/* Agent status summary */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        {runningAgents.length > 0 && (
          <span className="flex items-center gap-1">
            <Zap className="w-3 h-3 text-amber-500" />
            {runningAgents.length} working
          </span>
        )}
        <span>{completedAgents.length}/6 complete</span>
      </div>
    </div>
  );
}
