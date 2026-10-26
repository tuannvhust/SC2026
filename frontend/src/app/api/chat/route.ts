import type { NextRequest } from "next/server";

const backendUrl = (
  process.env.BACKEND_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxyJson(request: NextRequest, path: string) {
  try {
    const upstream = await fetch(`${backendUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Chat backend request failed:", error);
    return Response.json(
      { error: "Could not connect to the chat backend." },
      { status: 502 },
    );
  }
}

export async function POST(request: NextRequest) {
  const url = new URL(request.url);
  if (url.pathname.endsWith("/end-session")) {
    return proxyJson(request, "/api/chat/end-session");
  }
  let upstream: Response;

  try {
    upstream = await fetch(`${backendUrl}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type":
          request.headers.get("content-type") || "application/json",
        Accept: "text/event-stream",
      },
      body: await request.text(),
      cache: "no-store",
    });
  } catch (error) {
    console.error("Chat backend request failed:", error);
    return Response.json(
      { error: "Could not connect to the chat backend." },
      { status: 502 },
    );
  }

  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  headers.set("Cache-Control", "no-cache, no-transform");
  headers.set("X-Accel-Buffering", "no");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}
