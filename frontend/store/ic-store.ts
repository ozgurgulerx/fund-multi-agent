"use client";

import { create } from "zustand";

// Types matching backend schemas
export type StageStatus = "pending" | "running" | "succeeded" | "failed" | "skipped" | "repaired";
export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface Stage {
  stage_id: string;
  stage_name: string;
  stage_order: number;
  status: StageStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  progress_pct: number;
  artifacts: string[];
  error_message?: string;
  repair_attempts: number;
}

export interface CandidateProgress {
  candidate_id: string;
  compliance_status: StageStatus;
  redteam_status: StageStatus;
  compliance_passed?: boolean;
  redteam_passed?: boolean;
  repair_attempts: number;
  is_selected: boolean;
  rejection_reason?: string;
}

export interface RunMetadata {
  run_id: string;
  status: RunStatus;
  mandate_id: string;
  seed: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  current_stage?: string;
  stages_completed: number;
  total_stages: number;
  progress_pct: number;
  stages: Stage[];
  candidates: CandidateProgress[];
  selected_candidate?: string;
  error_message?: string;
  error_stage?: string;
  event_count: number;
  artifact_count: number;
}

export interface WorkflowEvent {
  event_id: string;
  run_id: string;
  ts: string;
  sequence: number;
  level: "info" | "warn" | "error";
  kind: string;
  stage_id?: string;
  stage_name?: string;
  candidate_id?: string;
  agent_name?: string;
  executor_name?: string;
  tool_name?: string;
  message: string;
  payload: Record<string, unknown>;
  duration_ms?: number;
}

interface ICStore {
  // Current run state
  currentRun: RunMetadata | null;
  events: WorkflowEvent[];
  isConnected: boolean;
  lastEventId: string | null;

  // Actions
  setCurrentRun: (run: RunMetadata | null) => void;
  updateRunFromEvent: (event: WorkflowEvent) => void;
  addEvent: (event: WorkflowEvent) => void;
  clearEvents: () => void;
  setConnected: (connected: boolean) => void;
  setLastEventId: (id: string) => void;

  // Computed
  getStageByName: (name: string) => Stage | undefined;
  getCandidateProgress: (id: string) => CandidateProgress | undefined;
}

export const useICStore = create<ICStore>((set, get) => ({
  currentRun: null,
  events: [],
  isConnected: false,
  lastEventId: null,

  setCurrentRun: (run) => set({ currentRun: run }),

  updateRunFromEvent: (event) => {
    const state = get();
    if (!state.currentRun) return;

    const run = { ...state.currentRun };

    // Update based on event kind
    switch (event.kind) {
      case "stage_started":
        if (event.stage_id) {
          run.current_stage = event.stage_id;
          const stage = run.stages.find(s => s.stage_id === event.stage_id);
          if (stage) {
            stage.status = "running";
            stage.started_at = event.ts;
          }
        }
        break;

      case "stage_completed":
        if (event.stage_id) {
          const stage = run.stages.find(s => s.stage_id === event.stage_id);
          if (stage) {
            stage.status = "succeeded";
            stage.completed_at = event.ts;
            stage.duration_ms = event.duration_ms;
          }
          run.stages_completed = run.stages.filter(s =>
            s.status === "succeeded" || s.status === "skipped"
          ).length;
          run.progress_pct = (run.stages_completed / run.total_stages) * 100;
        }
        break;

      case "stage_failed":
        if (event.stage_id) {
          const stage = run.stages.find(s => s.stage_id === event.stage_id);
          if (stage) {
            stage.status = "failed";
            stage.error_message = event.message;
          }
        }
        break;

      case "candidate_created":
        if (event.candidate_id) {
          const candidate = run.candidates.find(c => c.candidate_id === event.candidate_id);
          if (candidate) {
            candidate.compliance_status = "pending";
            candidate.redteam_status = "pending";
          }
        }
        break;

      case "candidate_passed":
      case "candidate_failed":
        if (event.candidate_id) {
          const candidate = run.candidates.find(c => c.candidate_id === event.candidate_id);
          if (candidate) {
            if (event.message.includes("compliance")) {
              candidate.compliance_status = event.kind === "candidate_passed" ? "succeeded" : "failed";
              candidate.compliance_passed = event.kind === "candidate_passed";
            }
            if (event.message.includes("red-team")) {
              candidate.redteam_status = event.kind === "candidate_passed" ? "succeeded" : "failed";
              candidate.redteam_passed = event.kind === "candidate_passed";
            }
          }
        }
        break;

      case "decision_made":
        if (event.payload?.winner) {
          run.selected_candidate = event.payload.winner as string;
          const candidate = run.candidates.find(c => c.candidate_id === run.selected_candidate);
          if (candidate) {
            candidate.is_selected = true;
          }
        }
        break;

      case "run_completed":
        run.status = "completed";
        run.completed_at = event.ts;
        break;

      case "run_failed":
        run.status = "failed";
        run.error_message = event.message;
        break;
    }

    run.event_count = state.events.length + 1;

    set({ currentRun: run });
  },

  addEvent: (event) => {
    set((state) => ({
      events: [...state.events, event],
      lastEventId: event.event_id,
    }));
    get().updateRunFromEvent(event);
  },

  clearEvents: () => set({ events: [] }),

  setConnected: (connected) => set({ isConnected: connected }),

  setLastEventId: (id) => set({ lastEventId: id }),

  getStageByName: (name) => {
    const state = get();
    return state.currentRun?.stages.find(s => s.stage_name === name);
  },

  getCandidateProgress: (id) => {
    const state = get();
    return state.currentRun?.candidates.find(c => c.candidate_id === id);
  },
}));
