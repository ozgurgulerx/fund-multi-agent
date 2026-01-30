import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/ic/policy
 *
 * Accepts an InvestorPolicyStatement and starts a portfolio optimization run.
 * Tries to forward to the backend first, falls back to demo mode if unavailable.
 */
export async function POST(request: NextRequest) {
  try {
    const policy = await request.json();
    const backendUrl = process.env.BACKEND_URL;

    // Try to forward to backend if configured
    if (backendUrl) {
      console.log(`[Policy] Forwarding to backend: ${backendUrl}/api/ic/policy`);

      try {
        const backendResponse = await fetch(`${backendUrl}/api/ic/policy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(policy),
        });

        if (backendResponse.ok) {
          const data = await backendResponse.json();
          console.log("[Policy] Backend response:", data);
          return NextResponse.json({
            ...data,
            mode: "backend",
          });
        } else {
          console.warn(`[Policy] Backend error: ${backendResponse.status}, falling back to demo mode`);
        }
      } catch (backendError) {
        console.warn("[Policy] Backend connection failed, falling back to demo mode:", backendError);
      }
    }

    // Demo mode fallback - generate a local run ID
    const runId = `run-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;

    console.log("[Policy] Starting in demo mode:", runId);
    console.log("[Policy] Policy:", JSON.stringify(policy, null, 2));

    return NextResponse.json({
      run_id: runId,
      status: "started",
      message: "Portfolio optimization started (demo mode)",
      mode: "demo",
    });
  } catch (error) {
    console.error("[Policy] Error starting run:", error);
    return NextResponse.json(
      { error: "Failed to start run" },
      { status: 500 }
    );
  }
}

/**
 * GET /api/ic/policy/templates
 *
 * Returns available policy templates.
 */
export async function GET() {
  return NextResponse.json({
    templates: [
      {
        id: "conservative",
        name: "Conservative",
        description: "Lower risk, stable income focus",
      },
      {
        id: "balanced",
        name: "Balanced",
        description: "Moderate risk, growth and income",
      },
      {
        id: "aggressive",
        name: "Aggressive",
        description: "Higher risk, growth focus",
      },
    ],
  });
}
