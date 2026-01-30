import { NextRequest } from "next/server";

/**
 * SSE Proxy endpoint - forwards events from backend to frontend
 *
 * The frontend connects to this endpoint, which proxies SSE events
 * from the backend orchestrator running in AKS.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId } = await params;
  const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
  const sseUrl = `${backendUrl}/api/ic/runs/${runId}/events`;

  console.log(`[SSE Proxy] Connecting to backend: ${sseUrl}`);

  try {
    // Connect to backend SSE endpoint
    const backendResponse = await fetch(sseUrl, {
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
      },
      // Important: Don't buffer the response
      cache: "no-store",
    });

    if (!backendResponse.ok) {
      console.error(`[SSE Proxy] Backend error: ${backendResponse.status}`);
      return new Response(
        JSON.stringify({ error: "Backend connection failed", status: backendResponse.status }),
        { status: backendResponse.status, headers: { "Content-Type": "application/json" } }
      );
    }

    if (!backendResponse.body) {
      console.error("[SSE Proxy] No response body from backend");
      return new Response(
        JSON.stringify({ error: "No response body" }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }

    // Create a TransformStream to forward SSE events
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const reader = backendResponse.body.getReader();
    const decoder = new TextDecoder();

    // Forward events from backend to client
    (async () => {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            console.log("[SSE Proxy] Backend stream ended");
            break;
          }

          const chunk = decoder.decode(value, { stream: true });
          await writer.write(new TextEncoder().encode(chunk));
        }
      } catch (error) {
        console.error("[SSE Proxy] Stream error:", error);
      } finally {
        try {
          await writer.close();
        } catch {
          // Writer might already be closed
        }
      }
    })();

    // Return SSE response
    return new Response(readable, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no", // Disable nginx buffering
      },
    });
  } catch (error) {
    console.error("[SSE Proxy] Connection error:", error);

    // Return error as SSE event so frontend can handle gracefully
    return new Response(
      JSON.stringify({
        error: "Backend connection failed",
        message: error instanceof Error ? error.message : "Unknown error",
        backendUrl: sseUrl
      }),
      {
        status: 503,
        headers: { "Content-Type": "application/json" }
      }
    );
  }
}

// Disable body parsing for streaming
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
