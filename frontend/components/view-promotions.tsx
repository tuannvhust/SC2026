"use client";
import { useMemo, useState } from "react";
import { PROMOTIONS, PRODUCTS } from "@/lib/mock-products";
import { useWorkspace } from "@/components/workspace-provider";
import { fmtVND } from "@/components/view-products";

export function PromotionsView() {
  const w = useWorkspace();
  const [q, setQ] = useState("");
  const [st, setSt] = useState("All");
  const list = useMemo(() => PROMOTIONS.filter((p) =>
    (st === "All" || p.status === st) &&
    [p.id, p.code, p.name, p.description].join(" ").toLowerCase().includes(q.toLowerCase())), [q, st]);
  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <div><div className="text-[11px] font-extrabold uppercase text-[#3859d7]">Offers & eligibility</div>
        <h1 className="text-[25px] font-bold">Promotions</h1>
        <p className="text-[13px] text-[#6b7788]">Check conditions before mentioning a discount.</p></div>
        <span className="rounded-full bg-[#fff4dc] px-2.5 py-1.5 text-[11px] font-bold text-[#8d5a0b]">PROMOTION DEMO</span>
      </div>
      <div className="mb-4 grid grid-cols-[1fr_200px_200px] gap-2.5 rounded-[13px] border bg-white p-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, code, product…"
          className="rounded-[9px] border bg-[#fbfcfe] p-2.5 outline-none" />
        <select value={st} onChange={(e) => setSt(e.target.value)} className="rounded-[9px] border bg-[#fbfcfe] p-2.5">
          <option value="All">All statuses</option><option>Active</option><option>Upcoming</option><option>Expired</option>
        </select>
        <div className="rounded-[9px] border bg-[#fbfcfe] p-2.5 text-xs text-[#6b7788]">{list.length} offers</div>
      </div>
      <div className="grid grid-cols-3 gap-3.5 max-[850px]:grid-cols-1">
        {list.map((p) => (
          <article key={p.id} className="flex flex-col gap-3 rounded-[15px] border bg-white p-4">
            <div className="flex gap-3">
              <div className="grid h-[58px] w-[58px] place-items-center rounded-[14px] bg-[#fff8ee] text-[28px] text-[#a9660a]">{p.icon}</div>
              <div><h2 className="text-[15px] font-semibold">{p.name}</h2>
              <div className="mt-1 text-[10px] text-[#8993a2]">{p.id} · {p.code}</div>
              <div className="mt-2"><span className={`rounded-md px-2 py-1 text-[10px] font-bold ${p.status === "Active" ? "bg-[#e7f7ee] text-[#148052]" : p.status === "Upcoming" ? "bg-[#edf1ff] text-[#455bca]" : "bg-[#f1f4f8]"}`}>{p.status}</span></div></div>
            </div>
            <div className="text-[23px] font-extrabold text-[#a9660a]">{p.value}</div>
            <p className="text-xs text-[#667085]">{p.description}</p>
            <div className="mt-auto flex items-center justify-between border-t pt-2.5">
              <small className="text-[#6b7788]">{p.start} → {p.end}</small>
              <button type="button" className="rounded-lg border px-2 py-1.5 text-xs font-semibold" onClick={() => {
                const linked = PRODUCTS.filter((x) => p.products.includes(x.sku));
                w.openModal({ title: p.name, confirmText: "Close",
                  body: <div className="text-xs"><p>Min order: {p.minimum ? fmtVND(p.minimum) : "none"}</p><ul className="mt-2 list-disc pl-5">{p.terms.map((t) => <li key={t}>{t}</li>)}</ul><p className="mt-2">Products: {linked.map((x) => x.name).join(", ") || "—"}</p></div> });
              }}>View terms ↗</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
