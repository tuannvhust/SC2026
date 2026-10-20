import { useEffect, useState } from "react";

export type DataSource = "backend" | "repository" | "demo";
export type ReferenceResult<T> = { items: T[]; source: DataSource; total?: number; page?: number; page_size?: number; reference_date?: string; backendError?: boolean };

export function useReferenceData<T>(url: string, demoItems: T[], fallbackKey = "") {
	const [result, setResult] = useState<ReferenceResult<T>>({ items: [], source: "demo", backendError: false });
	const [loading, setLoading] = useState(true);
	useEffect(() => {
		let active = true;
		setLoading(true);
		fetch(url, { cache: "no-store" }).then(async (response) => {
			if (!response.ok) throw new Error(`Reference API returned ${response.status}`);
			const payload = await response.json();
			if (!Array.isArray(payload.items) || !["backend", "repository", "demo"].includes(payload.source)) throw new Error("Invalid reference API response");
			if (active) setResult({ ...payload, backendError: Boolean(payload.backendError) });
		}).catch(() => { if (active) setResult({ items: demoItems, source: "demo", backendError: true }); })
			.finally(() => { if (active) setLoading(false); });
		return () => { active = false; };
	}, [url, fallbackKey]);
	return { ...result, loading };
}

export function DataSourceNotice({ source, loading, backendError, empty }: { source: DataSource; loading: boolean; backendError?: boolean; empty?: boolean }) {
	if (loading) return <p role="status" className="mb-3 text-xs text-[#6b7788]">Loading current data…</p>;
	const label = source === "backend" ? "Live backend data" : source === "repository" ? "Repository data" : "Demo data";
	return <p role="status" className="mb-3 text-xs text-[#6b7788]">{backendError ? "Backend unavailable; showing demo data. " : ""}{label}{empty ? " · No records match this view." : ""}</p>;
}
