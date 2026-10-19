import type { NextRequest } from "next/server";

const backendUrl = (
  process.env.BACKEND_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const correlationId = request.headers.get("x-request-id") || crypto.randomUUID();
  console.log(`[SESSION][id=${correlationId}] END_SESSION_REQUESTED path=/api/chat/end-session method=POST`);

  let bodyText = "";
  let payload: Record<string, unknown> = {};
  try {
    bodyText = await request.text();
    payload = bodyText ? JSON.parse(bodyText) : {};
  } catch (err) {
    console.error(`[SESSION][id=${correlationId}] Invalid JSON payload:`, err);
    return Response.json(
      { error: "Invalid JSON request body." },
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const sessionId = typeof payload.session_id === "string" ? payload.session_id.trim() : "";
  if (!sessionId) {
    console.warn(`[SESSION][id=${correlationId}] Missing session_id in end-session request`);
    return Response.json(
      { error: "session_id is required to finalize a session." },
      { status: 422, headers: { "Content-Type": "application/json" } }
    );
  }

  console.log(`[SESSION][id=${correlationId}] FINALIZE_START forwarding to backend=${backendUrl}/api/chat/end-session session=${sessionId}`);
  const startTime = Date.now();

  try {
    const upstream = await fetch(`${backendUrl}/api/chat/end-session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": correlationId,
      },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(35000),
    });


    const durationMs = Date.now() - startTime;
    const responseText = await upstream.text();
    let responseJson: Record<string, unknown> | null = null;
    try {
      responseJson = JSON.parse(responseText);
    } catch {
      // Upstream returned non-JSON
    }

    if (upstream.ok && responseJson) {
      console.log(
        `[SESSION][id=${correlationId}] FINALIZE_END status=success duration_ms=${durationMs} ` +
        `working_events=${responseJson.working_events ?? 0} ` +
        `finalized=${responseJson.finalized} already_finalized=${responseJson.already_finalized}`
      );
      if (Array.isArray(responseJson.profile_facts_written) || responseJson.episode) {
        console.log(
          `[SESSION][id=${correlationId}] PERSISTENCE ` +
          `episode=${responseJson.episode ? "yes" : "no"} ` +
          `profile_facts_written=${Array.isArray(responseJson.profile_facts_written) ? responseJson.profile_facts_written.length : 0}`
        );
      }
    } else {
      console.warn(
        `[SESSION][id=${correlationId}] FINALIZE_END status=failed duration_ms=${durationMs} http_status=${upstream.status}`
      );
    }

    return new Response(responseText, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    const durationMs = Date.now() - startTime;
    console.error(`[SESSION][id=${correlationId}] FINALIZE_END status=error duration_ms=${durationMs}:`, error);
    return Response.json(
      { error: "Could not connect to the chat backend." },
      { status: 502, headers: { "Content-Type": "application/json" } }
    );
  }
}

