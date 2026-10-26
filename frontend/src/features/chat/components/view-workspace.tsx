"use client";
import { useWorkspace } from "@/features/chat/components/workspace-provider";
import { Inbox } from "@/features/chat/components/inbox";
import { Conversation } from "@/features/chat/components/conversation";
import { ContextPanel } from "@/features/chat/components/context-panel";

export function WorkspaceView() {
	const w = useWorkspace();
	const open = w.interactions.filter((x) => x.status === "Open").length;
	const pend = w.interactions.filter((x) => x.status === "Pending").length;
	const hand = w.interactions.filter((x) => x.status === "Handoff").length;
	const res = w.interactions.filter((x) => x.status === "Resolved").length + 8;
	const kpis = [
		{
			l: "Open interactions",
			v: String(open).padStart(2, "0"),
			s: "Across all demo channels",
		},
		{
			l: "Waiting for reply",
			v: String(pend).padStart(2, "0"),
			s: "Customer or internal follow-up",
		},
		{
			l: "Handoffs today",
			v: String(hand).padStart(2, "0"),
			s: "Simulated handoff events",
		},
		{
			l: "Resolved today",
			v: String(res).padStart(2, "0"),
			s: "Illustrative demo count",
		},
	];
	return (
		<div>
			<div className="mb-5 flex items-center justify-between gap-4">
				<div>
					<div className="text-[11px] font-extrabold uppercase tracking-wider text-[#3859d7] ">
						Customer operations
					</div>
					<h1 className="mt-1 text-[25px] font-bold tracking-tight">
						Good morning, Linh ✦
					</h1>
					<p className="mt-1 text-[13px] text-[#6b7788]">
						Keep every conversation connected. Pick up where your customer left
						off.
					</p>
				</div>
				<button
					type="button"
					onClick={() =>
						w.openModal({
							title: "Create a demo interaction",
							confirmText: "Create",
							body: (
								<p className="text-xs text-[#6b7788]">
									Creates a new interaction in local state only. Use the inbox
									demo flow.
								</p>
							),
						})
					}
					className="rounded-[10px] bg-[#3859d7] px-3 py-2.5 font-650 text-white"
				>
					＋ New interaction
				</button>
			</div>
			<div className="mb-5 grid grid-cols-4 gap-3 max-[850px]:grid-cols-2">
				{kpis.map((k) => (
					<div key={k.l} className="rounded-[14px] border bg-white px-4 py-4">
						<div className="flex justify-between text-xs text-[#6b7788]">
							{k.l}
						</div>
						<strong className="mt-2 block text-[25px]">{k.v}</strong>
						<small className="text-[11px] text-[#6b7788]">{k.s}</small>
					</div>
				))}
			</div>
			<div className="grid min-h-[650px] grid-cols-[0.82fr_1.48fr_0.9fr] items-stretch gap-3.5 max-[1250px]:grid-cols-2 max-[850px]:grid-cols-1">
				<Inbox />
				<Conversation />
				<div className="max-[1250px]:col-span-2 max-[850px]:col-span-1">
					<ContextPanel />
				</div>
			</div>
		</div>
	);
}
