"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { useICStore, WorkflowEvent } from "@/store/ic-store";

interface UseSSEOptions {
  runId: string;
  onEvent?: (event: WorkflowEvent) => void;
  onError?: (error: Error) => void;
  enabled?: boolean;
}

export function useSSE({ runId, onEvent, onError, enabled = true }: UseSSEOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [reconnecting, setReconnecting] = useState(false);

  const { addEvent, setConnected, lastEventId } = useICStore();

  const connect = useCallback(() => {
    if (!enabled || !runId) return;

    // Build URL with resume support
    let url = `/api/ic/runs/${runId}/events`;
    if (lastEventId) {
      url += `?since=${lastEventId}`;
    }

    console.log("[SSE] Connecting to:", url);

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      console.log("[SSE] Connected");
      setConnected(true);
      setReconnecting(false);
    };

    eventSource.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WorkflowEvent;

        // Skip heartbeats in UI
        if (event.kind === "heartbeat") {
          console.log("[SSE] Heartbeat received");
          return;
        }

        console.log("[SSE] Event:", event.kind, event.message);
        addEvent(event);
        onEvent?.(event);

        // Close on terminal events
        if (event.kind === "run_completed" || event.kind === "run_failed") {
          console.log("[SSE] Run complete, closing connection");
          eventSource.close();
          setConnected(false);
        }
      } catch (err) {
        console.error("[SSE] Parse error:", err);
      }
    };

    eventSource.onerror = (e) => {
      console.error("[SSE] Error:", e);
      eventSource.close();
      setConnected(false);

      // Attempt reconnect after delay
      if (enabled) {
        setReconnecting(true);
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log("[SSE] Reconnecting...");
          connect();
        }, 3000);
      }

      onError?.(new Error("SSE connection error"));
    };
  }, [runId, enabled, lastEventId, addEvent, setConnected, onEvent, onError]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setConnected(false);
    setReconnecting(false);
  }, [setConnected]);

  useEffect(() => {
    if (enabled && runId) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, runId, connect, disconnect]);

  return {
    reconnecting,
    disconnect,
    reconnect: connect,
  };
}
