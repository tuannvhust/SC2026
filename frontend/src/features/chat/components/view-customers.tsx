"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useWorkspace } from "@/features/chat/components/workspace-provider";
import { INITIAL_CUSTOMERS } from "@/lib/mock-customers";
import { DataSourceNotice, useReferenceData } from "@/lib/reference-data";

type DirectoryCustomer = { id: string; name: string; initials: string; phone: string; email: string; segment: string; verified: boolean; caseCount: number; latestActivity?: string | null };

export function CustomersView() {
  const w = useWorkspace();
  const [q, setQ] = useState(w.customerSearch);
  const [page, setPage] = useState(1);
  const demoItems = useMemo(() => Object.entries(INITIAL_CUSTOMERS).map(([id, c]) => ({ ...c, id, latestActivity: c.history[0]?.time })), []);
  const data = useReferenceData<DirectoryCustomer>(`/api/reference/customers?q=${encodeURIComponent(q)}&page=${page}&page_size=12`, demoItems, `${q}:${page}`);
	const list = data.loading ? [] : data.source === "demo" ? data.items.filter((c) => [c.id, c.name, c.phone, c.email].join(" ").toLowerCase().includes(q.toLowerCase())) : data.items;
  useEffect(() => { setPage(1); }, [q]);
  return (
    <div>
      <div className="mb-4 flex flex-col items-start justify-between gap-3 sm:flex-row">
        <div><div className="text-[11px] font-extrabold uppercase text-[#3859d7]">Customer directory</div>
        <h1 className="text-[25px] font-bold">Customers</h1>
        <p className="text-[13px] text-[#6b7788]">Customer profiles from the connected directory.</p></div>
        <button type="button" onClick={() => w.setView("workspace")} className="rounded-[10px] border bg-white px-3 py-2 font-semibold">← Back to workspace</button>
      </div>
      <DataSourceNotice source={data.source} loading={data.loading} backendError={data.backendError} empty={!list.length} />
      <div className="mb-4 rounded-2xl border bg-white p-3">
        <input value={q} onChange={(e) => { setQ(e.target.value); w.setCustomerSearch(e.target.value); }}
          placeholder="Search customer name, ID, or contact…" className="w-full rounded-[9px] border bg-[#fbfcfe] p-2.5 outline-none" />
      </div>
      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 xl:grid-cols-3">
        {list.map((c) => {
          const id = c.id;
          return (
            <div key={id} className="rounded-[15px] border bg-white p-4">
              <div className="mb-3 flex items-center gap-2.5">
                <div className="grid h-[34px] w-[34px] place-items-center rounded-full bg-[#e6eaff] font-bold text-[#334ab5]">{c.initials}</div>
                <div><strong className="block text-[13px]">{c.name}</strong><small className="text-[10px] text-[#6b7788]">{id} · {c.segment}</small></div>
              </div>
              <p className="mb-3 text-[11px] text-[#6b7788]">{c.phone}<br />{c.email}</p>
              <div className="mb-3 flex gap-1.5">
                <span className={`rounded-md px-2 py-1 text-[10px] font-bold ${c.verified ? "bg-[#e7f7ee] text-[#148052]" : "bg-[#fff3dc] text-[#a56809]"}`}>{c.verified ? "Verified" : "Unverified"}</span>
                <span className="rounded-md bg-[#f1f4f8] px-2 py-1 text-[10px] font-bold">{c.caseCount} interactions</span>
              </div>
              <div className="flex items-center justify-between border-t pt-3">
                <small className="text-[#6b7788]">Latest: {c.latestActivity ?? "—"}</small>
                <Link href={`/chat?customer_id=${encodeURIComponent(id)}`} className="rounded-lg border px-2 py-1.5 text-xs font-semibold">
                  Start AI chat ↗
                </Link>
              </div>
            </div>
          );
        })}
      </div>
      {data.source !== "demo" && data.total && data.total > 12 && <div className="mt-4 flex items-center justify-end gap-2 text-sm"><button disabled={page <= 1} onClick={() => setPage((v) => Math.max(1, v - 1))} className="rounded-lg border px-3 py-1.5 disabled:opacity-40">Previous</button><span>Page {page} of {Math.ceil(data.total / 12)}</span><button disabled={page >= Math.ceil(data.total / 12)} onClick={() => setPage((v) => v + 1)} className="rounded-lg border px-3 py-1.5 disabled:opacity-40">Next</button></div>}
    </div>
  );
}
