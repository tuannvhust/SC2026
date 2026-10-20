import { proxyReference } from "@/lib/proxy-reference";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export function GET(request: Request) { return proxyReference(request, "customers"); }
