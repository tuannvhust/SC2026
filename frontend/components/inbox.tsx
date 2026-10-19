"use client";
import { useMemo, useState } from "react";
import { useWorkspace } from "./workspace-provider";

function chClass(ch: string) {
  return ch === "Phone" ? "bg-[#e7f7ef] text-[#17835c]" : ch === "Zalo" ? "bg-[#e9f1ff] text-[#2563c8]" : "bg-[#edf0ff] text-[#4b58bc]";
}
function chLetter(ch: string) {
  return ch === "Phone" ? "☎" : ch === "Zalo" ? "Z" : "f";
}
function stClass(s: string) {
  if (s === "Pending") return "bg-[#fff3dc] text-[#a56809]";
  if (s === "Resolved") return "bg-[#e7f7ee] text-[#148052]";
  if (s === "Handoff") return "bg-[#f4eaff] text-[#8651b6]";
  return "bg-[#edf1ff] text-[#435bc8]";
}

export function Inbox() {
  const { interactions, activeId, setActiveId, setContextTab, channelFilter, setChannelFilter, statusFilter, setStatusFilter } = useWorkspace();
  const [q, setQ] = useState("");
  const filtered = useMemo(() => interactions.filter((x) =>
    (channelFilter === "All" || x.channel === channelFilter) &&
    (statusFilter === "All" || x.status === statusFilter) &&
    [x.name, x.id, x.preview, x.caseTitle].join(" ").toLowerCase().includes(q.toLowerCase())),
    [interactions, channelFilter, statusFilter, q]);
  return (
    <section className="overflow-hidden rounded-2xl border border-[#e7ebf1] bg-white">
      <div className="flex items-center justify-between border-b px-4 py-4">
        <div><h2 className="text-[15px] font-semibold">Interaction inbox</h2><div className="mt-1 text-[11px] text-[#6b7788]">Prioritize what needs attention</div></div>
        <span className="rounded-[7px] bg-[#f1f3f7] px-2 py-1 text-[11px] font-bold text-[#667085]">{filtered.length} items</span>
      </div>
      <div className="border-b px-3 pb-2 pt-3">
        <div className="relative">
          <span className="absolute left-3 top-1.5 text-xl text-[#8994a6]">⌕</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customer or message…"
            className="w-full rounded-[9px] border bg-[#fbfcfe] py-2.5 pl-9 pr-3 outline-none" />
        </div>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {["All", "Phone", "Zalo", "Facebook"].map((c) => (
            <button key={c} type="button" onClick={() => setChannelFilter(c)}
              className={`rounded-[7px] px-2 py-1.5 text-[11px] font-bold ${channelFilter === c ? "border border-[#dce3ff] bg-[#edf1ff] text-[#3859d7]" : "bg-[#f4f6fa] text-[#667085]"}`}>{c}</button>
          ))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {["All", "Open", "Pending", "Handoff"].map((s) => (
            <button key={s} type="button" onClick={() => setStatusFilter(s)}
              className={`rounded-[7px] px-2 py-1.5 text-[11px] font-bold ${statusFilter === s ? "border border-[#dce3ff] bg-[#edf1ff] text-[#3859d7]" : "bg-[#f4f6fa] text-[#667085]"}`}>{s === "All" ? "All status" : s}</button>
          ))}
        </div>
      </div>
      <div className="max-h-[610px] overflow-auto">
        {filtered.length === 0 && <div className="px-4 py-9 text-center text-xs text-[#6b7788]">No interactions match.</div>}
        {filtered.map((x) => (
          <div key={x.id} onClick={() => { setActiveId(x.id); setContextTab("overview"); }}
            className={`cursor-pointer border-b border-l-[3px] px-3.5 py-3.5 hover:bg-[#fafbff] ${x.id === activeId ? "border-l-[#3859d7] bg-[#f0f3ff]" : "border-l-transparent"}`}>
            <div className="flex items-center gap-2.5">
              <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-[10px] font-extrabold ${chClass(x.channel)}`}>{chLetter(x.channel)}</div>
              <div className="min-w-0 flex-1"><strong className="block truncate text-xs">{x.name}</strong><small className="mt-0.5 block text-[10px] text-[#6b7788]">{x.channel} · {x.id}</small></div>
              <span className="text-[10px] text-[#8a94a4]">{x.time}</span>
            </div>
            <div className="mb-2 ml-[41px] mt-2 truncate text-[11px] text-[#687487]">{x.preview}</div>
            <div className="ml-[41px] flex items-center justify-between">
              <span className={`rounded-md px-2 py-1 text-[10px] font-bold ${stClass(x.status)}`}>{x.status}</span>
              <span className="text-[10px] text-[#a9660a]">{x.priority === "High" ? "▲ High" : ""}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
