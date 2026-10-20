"use client";
import { useMemo, useState } from "react";
import { useWorkspace } from "@/components/workspace-provider";

export function CustomersView() {
  const w = useWorkspace();
  const [q, setQ] = useState(w.customerSearch);
  const list = useMemo(() => Object.entries(w.customers).filter(([id, c]) =>
    [id, c.name, c.phone, c.email].join(" ").toLowerCase().includes((q || w.customerSearch).toLowerCase())),
    [w.customers, q, w.customerSearch]);
  return (
    <div>
      <div className="mb-4 flex flex-col items-start justify-between gap-3 sm:flex-row">
        <div><div className="text-[11px] font-extrabold uppercase text-[#3859d7]">Customer directory</div>
        <h1 className="text-[25px] font-bold">Customers</h1>
        <p className="text-[13px] text-[#6b7788]">Profiles connected to demo interactions.</p></div>
        <button type="button" onClick={() => w.setView("workspace")} className="rounded-[10px] border bg-white px-3 py-2 font-semibold">← Back to workspace</button>
      </div>
      <div className="mb-4 rounded-2xl border bg-white p-3">
        <input value={q} onChange={(e) => { setQ(e.target.value); w.setCustomerSearch(e.target.value); }}
          placeholder="Search customer name, ID, or contact…" className="w-full rounded-[9px] border bg-[#fbfcfe] p-2.5 outline-none" />
      </div>
      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 2xl:grid-cols-3">
        {list.map(([id, c]) => {
          const recs = w.interactions.filter((x) => x.customerId === id);
          return (
            <div key={id} className="rounded-[15px] border bg-white p-4">
              <div className="mb-3 flex items-center gap-2.5">
                <div className="grid h-[34px] w-[34px] place-items-center rounded-full bg-[#e6eaff] font-bold text-[#334ab5]">{c.initials}</div>
                <div><strong className="block text-[13px]">{c.name}</strong><small className="text-[10px] text-[#6b7788]">{id} · {c.segment}</small></div>
              </div>
              <p className="mb-3 text-[11px] text-[#6b7788]">{c.phone}<br />{c.email}</p>
              <div className="mb-3 flex gap-1.5">
                <span className={`rounded-md px-2 py-1 text-[10px] font-bold ${c.verified ? "bg-[#e7f7ee] text-[#148052]" : "bg-[#fff3dc] text-[#a56809]"}`}>{c.verified ? "Verified" : "Unverified"}</span>
                <span className="rounded-md bg-[#f1f4f8] px-2 py-1 text-[10px] font-bold">{recs.length} interactions</span>
              </div>
              <div className="flex items-center justify-between border-t pt-3">
                <small className="text-[#6b7788]">Latest: {recs[0]?.id ?? "—"}</small>
                <button type="button" className="rounded-lg border px-2 py-1.5 text-xs font-semibold" onClick={() => {
                  const r = w.interactions.find((x) => x.customerId === id);
                  if (r) { w.setActiveId(r.id); w.setContextTab("journey"); w.setView("workspace"); }
                }}>Open workspace ↗</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
