"use client";
import { useState } from "react";
import { useWorkspace } from "./workspace-provider";
import type { InteractionStatus } from "@/lib/mock-types";

export function Conversation() {
	const w = useWorkspace();
	const [draft, setDraft] = useState("");
	const x =
		w.interactions.find((i) => i.id === w.activeId) ?? w.interactions[0];
	const c = x ? w.customers[x.customerId] : undefined;
	if (!x || !c) return null;
	const send = () => {
		if (!c.verified) {
			w.showToast("Identity unverified: sending restricted.");
			return;
		}
		if (!draft.trim()) {
			w.showToast("Write a message first.");
			return;
		}
		w.sendAgentMessage(x.id, draft);
		setDraft("");
		w.showToast("Demo message added locally.");
	};
	return (
		<section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border bg-white">
			<div className="flex items-center justify-between gap-3 border-b px-5 py-4">
				<div className="min-w-0">
					<h2 className="text-[15px] font-semibold">{x.name}</h2>
					<p className="mt-1 text-[11px] text-[#6b7788]">
						{x.channel} · {x.id}
					</p>
				</div>
				<select
					value={x.status}
					aria-label="Status"
					onChange={(e) => {
						const n = e.target.value as InteractionStatus;
						if (!c.verified && n === "Resolved") {
							w.showToast("Verify identity first.");
							return;
						}
						w.updateStatus(x.id, n);
						w.showToast(`Status: ${n}.`);
					}}
					className="rounded-lg border bg-white px-2 py-2 text-[11px]"
				>
					<option>Open</option>
					<option>Pending</option>
					<option>Resolved</option>
					<option>Handoff</option>
				</select>
			</div>
			<div className="flex flex-wrap gap-2 border-b bg-[#fbfcff] px-4 py-2.5 text-[11px]">
				<span>
					Linked{" "}
					<strong>
						{x.caseId} · {x.caseTitle}
					</strong>
				</span>
				<span className="rounded-md bg-[#edf1ff] px-2 py-1 text-[10px] font-bold text-[#455bca]">
					{x.priority}
				</span>
				<span
					className={`rounded-md px-2 py-1 text-[10px] font-bold ${c.verified ? "bg-[#e7f7ee] text-[#148052]" : "bg-[#fff3dc] text-[#a56809]"}`}
				>
					{c.verified ? "Verified" : "Unverified"}
				</span>
			</div>
			<div className="m min-h-[250px] flex-1 overflow-auto px-5 py-5">
				{x.messages.map((m, i) =>
					m.from === "note" ? (
						<div
							key={i}
							className="mx-auto mb-3 max-w-[90%] rounded-[9px] border bg-[#fff8e9] px-3 py-2 text-center text-[10px] text-[#926316]"
						>
							ⓘ {m.text}
						</div>
					) : (
						<div
							key={i}
							className={`mb-3 flex items-end gap-2 ${m.from === "agent" ? "justify-end" : ""}`}
						>
							<div
								className={`max-w-[82%] rounded-[13px] px-3 py-2.5 text-xs ${m.from === "agent" ? "rounded-br bg-[#405bd3] text-white" : "rounded-bl bg-[#f1f3f7]"}`}
							>
								{m.text}
								<span className="mt-1 block text-[9px] opacity-70">
									{m.time}
								</span>
							</div>
						</div>
					),
				)}
			</div>
			<div className="border-t px-4 pb-4 pt-3">
				<div className="mb-2 rounded-[10px] border bg-[#f7f8ff] px-3 py-2.5">
					<div className="mb-1 flex justify-between">
						<strong className="text-[11px] text-[#4357bc]">
							✧ Suggested · demo
						</strong>
						<button
							type="button"
							className="text-[11px] font-bold text-[#3859d7]"
							onClick={() => setDraft(x.suggestion ?? "Dạ, em đã ghi nhận ạ.")}
						>
							Use reply ↗
						</button>
					</div>
					<p className="text-[11px] text-[#596579]">{x.suggestion}</p>
				</div>
				<textarea
					value={draft}
					onChange={(e) => setDraft(e.target.value)}
					placeholder="Type a reply… (demo)"
					className="min-h-[65px] w-full rounded-[10px] border p-3 outline-none"
				/>
				<div className="mt-2 flex justify-end gap-2">
					<button
						type="button"
						onClick={() => setDraft("")}
						className="rounded-[10px] border px-2.5 py-1.5 text-xs font-semibold"
					>
						Clear
					</button>
					<button
						type="button"
						onClick={send}
						disabled={!c.verified}
						className="rounded-[10px] bg-[#3859d7] px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
					>
						Send ↗
					</button>
				</div>
			</div>
		</section>
	);
}
