"use client";
import { useWorkspace } from "./workspace-provider";
import { briefForCustomer } from "@/lib/mock-customers";

export function Timeline({ items }: { items: { title: string; detail: string; time: string; id: string }[] }) {
  return (
    <div className="relative pl-4">
      <span className="absolute bottom-2 left-1 top-2 w-px bg-[#e2e7f0]" />
      {items.map((h, i) => (
        <div key={i} className="relative pb-4 pl-2">
          <span className="absolute -left-[13px] top-1 h-[7px] w-[7px] rounded-full bg-[#9caaf2]" />
          <strong className="block text-[10px]">{h.title}</strong>
          <p className="mt-1 text-[10px] text-[#6f7a8c]">{h.detail}</p>
          <small className="mt-1 block text-[9px] text-[#a0a8b4]">{h.time} · {h.id}</small>
        </div>
      ))}
    </div>
  );
}

export function ContextPanel() {
  const w = useWorkspace();
  const x = w.interactions.find((i) => i.id === w.activeId) ?? w.interactions[0];
  const c = x ? w.customers[x.customerId] : undefined;
  if (!x || !c) return null;
  return (
    <aside className="flex flex-col overflow-hidden rounded-2xl border bg-white">
      <div className="flex items-center justify-between border-b px-4 py-4">
        <div><h2 className="text-[15px] font-semibold">Customer context</h2></div>
        <button type="button" onClick={() => { w.setCustomerSearch(x.customerId); w.setView("customers"); }} className="rounded-lg border px-2 py-1.5 text-xs font-semibold">View profile ↗</button>
      </div>
      <div className="flex border-b px-3">
        {(["overview", "journey", "case"] as const).map((t) => (
          <button key={t} type="button" onClick={() => w.setContextTab(t)}
            className={`border-b-2 px-2.5 py-2.5 text-[11px] font-bold ${w.contextTab === t ? "border-[#3859d7] text-[#3859d7]" : "border-transparent text-[#7a8494]"}`}>
            {t === "overview" ? "Overview" : t === "journey" ? "Journey" : "Case details"}</button>
        ))}
      </div>
      <div className="max-h-[690px] overflow-auto p-4">
        <div className="mb-4 flex items-center gap-2.5">
          <div className="grid h-[42px] w-[42px] place-items-center rounded-full bg-[#e6eaff] font-bold text-[#334ab5]">{c.initials}</div>
          <div><strong className="block text-[13px]">{c.name}</strong><small className="text-[10px] text-[#6b7788]">{x.customerId} · {c.segment}</small></div>
        </div>
        {w.contextTab !== "overview" && <Timeline items={c.history} />}
        {w.contextTab === "overview" && (
          <div>
            <div className={`mb-4 rounded-[10px] border p-2.5 ${c.verified ? "bg-[#e9f7f0]" : "bg-[#fff4dc]"}`}>
              <div className="text-[11px] font-extrabold">{c.verified ? "✓ Identity verified" : "! Not verified"}</div>
              {!c.verified && <button type="button" onClick={() => { w.verifyCustomer(x.customerId); w.showToast("Demo identity verified."); }} className="mt-2 rounded-lg border bg-white px-2 py-1.5 text-xs font-semibold">Simulate verification</button>}
            </div>
            <strong className="text-[11px]">Call Brief</strong>
            <p className="mt-1.5 rounded-[11px] border bg-[#fbfcff] p-3 text-[11px] text-[#4b586b]">{briefForCustomer(x.customerId)}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 text-[11px]">
              <div><label className="text-[10px] text-[#8a94a4]">Phone</label><strong className="block">{c.phone}</strong></div>
              <div><label className="text-[10px] text-[#8a94a4]">Email</label><strong className="block break-all">{c.email}</strong></div>
            </div>
            <div className="mt-4"><strong className="text-[11px]">Recent journey</strong></div>
            <div className="mt-2"><Timeline items={c.history.slice(0, 2)} /></div>
          </div>
        )}
        {w.contextTab === "case" && (
          <p className="mt-3 text-[11px] text-[#4b586b]">{x.caseId} · {x.caseTitle} · linked to {x.id}.</p>
        )}
      </div>
    </aside>
  );
}
