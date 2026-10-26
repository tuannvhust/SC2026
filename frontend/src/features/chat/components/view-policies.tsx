"use client";
import { useMemo, useState } from "react";
import { POLICIES } from "@/lib/mock-policies";
import { useWorkspace } from "@/features/chat/components/workspace-provider";
import { DataSourceNotice, useReferenceData } from "@/lib/reference-data";
import type { Policy } from "@/lib/mock-types";

export function PoliciesView() {
	const w = useWorkspace();
	const [q, setQ] = useState("");
	const [cat, setCat] = useState("All");
	const data = useReferenceData<Policy>("/api/reference/policies", POLICIES);
	const cats = useMemo(() => [...new Set(data.items.map((p) => p.category))], [data.items]);
	const cur = (data.loading ? [] : data.items).filter(
		(p) =>
			p.status === "Current" &&
			(cat === "All" || p.category === cat) &&
			[p.id, p.topic, p.summary, p.content]
				.join(" ")
				.toLowerCase()
				.includes(q.toLowerCase()),
	);
	const arc = (data.loading ? [] : data.items).filter(
		(p) =>
			p.status === "Archived" &&
			(cat === "All" || p.category === cat) &&
			[p.id, p.topic, p.summary, p.content]
				.join(" ")
				.toLowerCase()
				.includes(q.toLowerCase()),
	);
	const card = (p: Policy, archived = false) => (
		<article
			key={p.id}
			className="flex flex-col gap-2.5 rounded-[15px] border bg-white p-4"
		>
			<div className="flex gap-2.5">
				<div
					className={`grid h-[42px] w-[42px] place-items-center rounded-xl text-xl ${archived ? "bg-[#fff3dc] text-[#a56809]" : "bg-[#edf1ff] text-[#3859d7]"}`}
				>
					{archived ? "◷" : "▤"}
				</div>
				<div>
					<h2 className="text-[15px] font-semibold">{p.topic}</h2>
					<div className="mt-1 text-[10px] text-[#8993a2]">
						{p.id} · v{p.version}
					</div>
					<div className="mt-2 flex gap-1.5">
						<span
							className={`rounded-md px-2 py-1 text-[10px] font-bold ${archived ? "bg-[#fff3dc] text-[#a56809]" : "bg-[#e7f7ee] text-[#148052]"}`}
						>
							{archived ? "Archived" : "Current"}
						</span>
						<span className="rounded-md bg-[#f1f4f8] px-2 py-1 text-[10px] font-bold">
							{p.category}
						</span>
					</div>
				</div>
			</div>
			<p className="text-xs text-[#667085]">{p.summary}</p>
			<div className="grid grid-cols-2 gap-2 rounded-[10px] border bg-[#fafbfe] p-2.5 text-[11px]">
				<div>
					<label className="text-[10px] text-[#8993a2]">Effective</label>
					<strong className="block">{p.effective}</strong>
				</div>
				<div>
					<label className="text-[10px] text-[#8993a2]">Owner</label>
					<strong className="block">{p.owner}</strong>
				</div>
			</div>
			<div className="mt-auto flex justify-between border-t pt-2.5">
				<small className="text-[#6b7788]">
					{archived ? "Historical lookup" : "Current reference"}
				</small>
				<button
					type="button"
					className="rounded-lg border px-2 py-1.5 text-xs font-semibold"
					onClick={() =>
						w.openModal({
							title: `${p.topic} · v${p.version}`,
							confirmText: "Close",
							body: (
								<div className="text-xs leading-relaxed">
									<p className="whitespace-pre-line text-[#475467]">
										{p.content}
									</p>
									<p className="mt-2 text-[10px] text-[#8993a2]">
										{p.changeNote}
									</p>
								</div>
							),
						})
					}
				>
					View ↗
				</button>
			</div>
		</article>
	);
	return (
		<div>
			<div className="mb-4 flex items-start justify-between">
				<div>
					<div className="text-[11px] font-extrabold uppercase text-[#3859d7]">
						Knowledge & governance
					</div>
					<h1 className="text-[25px] font-bold">Store policies</h1>
					<p className="text-[13px] text-[#6b7788]">
						Current rules separated from archived versions.
					</p>
				</div>
				<span className="rounded-full bg-[#fff4dc] px-2.5 py-1.5 text-[11px] font-bold text-[#8d5a0b]">
					{data.source === "backend" ? "POLICY CORPUS" : data.source === "repository" ? "REPOSITORY POLICIES" : "POLICY DEMO"}
				</span>
			</div>
			<div className="mb-5 grid grid-cols-1 gap-2.5 rounded-[13px] border bg-white p-3 sm:grid-cols-[minmax(0,1fr)_200px]">
				<input
					value={q}
					onChange={(e) => setQ(e.target.value)}
					placeholder="Search title, ID, keyword…"
					className="rounded-[9px] border bg-[#fbfcfe] p-2.5 outline-none"
				/>
				<select
					value={cat}
					onChange={(e) => setCat(e.target.value)}
					className="rounded-[9px] border bg-[#fbfcfe] p-2.5"
				>
					<option value="All">All categories</option>
					{cats.map((c) => (
						<option key={c}>{c}</option>
					))}
				</select>
			</div>
			<DataSourceNotice source={data.source} loading={data.loading} backendError={data.backendError} empty={!cur.length && !arc.length} />
			<div className="mb-3 flex items-end justify-between">
				<h2 className="text-[17px] font-bold">Current policies</h2>
				<span className="rounded-md bg-[#e7f7ee] px-2 py-1 text-[10px] font-bold text-[#148052]">
					{cur.length} current
				</span>
			</div>
			<div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 xl:grid-cols-3">
				{cur.map((p) => card(p))}
			</div>
			<div className="mb-3 mt-8 flex items-end justify-between border-t pt-6">
				<h2 className="text-[17px] font-bold">Archived policy versions</h2>
				<span className="rounded-md bg-[#fff3dc] px-2 py-1 text-[10px] font-bold text-[#a56809]">
					{arc.length} archived
				</span>
			</div>
			<div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 xl:grid-cols-3">
				{arc.map((p) => card(p, true))}
			</div>
		</div>
	);
}
