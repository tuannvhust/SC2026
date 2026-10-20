import { INITIAL_CUSTOMERS } from "@/lib/mock-customers";
import { POLICIES } from "@/lib/mock-policies";
import { PRODUCTS, PROMOTIONS } from "@/lib/mock-products";

const backendUrl = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

function demoResponse(resource: string, url: URL) {
	if (resource === "customers") {
		const query = (url.searchParams.get("q") || "").trim().toLowerCase();
		const page = Math.max(1, Number(url.searchParams.get("page") || 1));
		const pageSize = Math.min(100, Math.max(1, Number(url.searchParams.get("page_size") || 12)));
		const items = Object.entries(INITIAL_CUSTOMERS).map(([id, customer]) => ({
			...customer, id, latestActivity: customer.history[0]?.time || null,
		})).filter((customer) => !query || [customer.id, customer.name, customer.phone, customer.email].join(" ").toLowerCase().includes(query));
		return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, page_size: pageSize, source: "demo", backendError: true };
	}
	if (resource === "products") return { items: PRODUCTS, source: "demo", backendError: true };
	if (resource === "promotions") return { items: PROMOTIONS, source: "demo", backendError: true, reference_date: "2026-10-15" };
	if (resource === "policies") return { items: POLICIES, source: "demo", backendError: true };
	return { items: [], source: "demo", backendError: true };
}

export async function proxyReference(request: Request, resource: string) {
	const url = new URL(request.url);
	const query = url.search;
	try {
		const response = await fetch(`${backendUrl}/api/reference/${resource}${query}`, { cache: "no-store", signal: AbortSignal.timeout(12000) });
		if (!response.ok) {
			console.error(`Reference API upstream failed: resource=${resource} status=${response.status}`);
			return Response.json(demoResponse(resource, url));
		}
		return new Response(await response.text(), { status: response.status, headers: { "Content-Type": response.headers.get("content-type") || "application/json" } });
	} catch (error) {
		console.error(`Reference API backend unavailable: resource=${resource} error=${error instanceof Error ? error.name : "unknown"}`);
		return Response.json(demoResponse(resource, url));
	}
}
