import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/ic/runs/[runId]
 *
 * Get run details from backend, or return mock data in demo mode.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId } = await params;
  const backendUrl = process.env.BACKEND_URL;

  // Try to get from backend if configured
  if (backendUrl) {
    try {
      const backendResponse = await fetch(`${backendUrl}/api/ic/runs/${runId}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });

      if (backendResponse.ok) {
        const data = await backendResponse.json();
        return NextResponse.json(data);
      }

      // If 404, return run not found
      if (backendResponse.status === 404) {
        return NextResponse.json(
          { error: "Run not found" },
          { status: 404 }
        );
      }

      console.warn(`[Run] Backend error: ${backendResponse.status}`);
    } catch (error) {
      console.warn("[Run] Backend connection failed:", error);
    }
  }

  // Demo mode - return mock run data
  return NextResponse.json({
    run_id: runId,
    status: "running",
    mandate_id: "demo-mandate",
    created_at: new Date().toISOString(),
    progress_pct: 0,
    current_stage: "initializing",
    policy: {},
    mode: "demo",
  });
}
