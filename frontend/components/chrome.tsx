"use client";
import { usePathname } from "next/navigation";
import { useWorkspace } from "./workspace-provider";

const TITLES = {
  workspace: "Workspace", customers: "Customers", products: "Products",
  promotions: "Promotions", policies: "Store policies", evaluation: "Evaluation", improvement: "Improvement",
} as const;

export function Topbar() {
  const pathname = usePathname();
  const section = pathname.split("/")[1] || "workspace";
  const view = section in TITLES ? (section as keyof typeof TITLES) : "workspace";
  return (
    <header className="flex h-14 items-center justify-between gap-3 border-b border-[#e7ebf1] bg-white px-4 sm:h-[72px] sm:gap-5 sm:px-7">
      <div className="text-xs text-[#6b7788]">SC2026 <strong className="ml-2 text-sm text-[#182230]">/ {TITLES[view]}</strong></div>
      <div className="flex items-center gap-3">
        <span className="rounded-full border border-[#f4dfad] bg-[#fff4dc] px-2.5 py-1.5 text-[11px] font-bold text-[#8d5a0b]">● DEMO · MOCK DATA</span>
        <div className="grid h-8 w-8 place-items-center rounded-full bg-[#e6eaff] text-[11px] font-bold text-[#334ab5]">LT</div>
      </div>
    </header>
  );
}

export function Overlays() {
  const { toast, modal, closeModal } = useWorkspace();
  return (
    <>
      {modal && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-[rgba(18,27,46,0.38)] p-5" onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}>
          <div className="w-full max-w-[480px] overflow-hidden rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true">
            <div className="flex items-center justify-between border-b border-[#e7ebf1] px-5 py-4">
              <h2 className="text-[15px] font-semibold">{modal.title}</h2>
              <button type="button" onClick={closeModal} className="grid h-9 w-9 place-items-center rounded-[10px] border border-[#e7ebf1]">×</button>
            </div>
            <div className="p-5">{modal.body}</div>
            <div className="flex justify-end gap-2 border-t border-[#e7ebf1] px-5 py-3.5">
              <button type="button" onClick={closeModal} className="rounded-[10px] border px-3 py-2 font-semibold text-[#344054]">Cancel</button>
              <button type="button" onClick={closeModal} className="rounded-[10px] bg-[#3859d7] px-3 py-2 font-semibold text-white">{modal.confirmText ?? "Close"}</button>
            </div>
          </div>
        </div>
      )}
      {toast && (
        <div role="status" className="animate-toast-in fixed bottom-6 right-6 z-30 max-w-[340px] rounded-[11px] bg-[#17243a] px-4 py-3 text-xs text-white shadow-xl">{toast}</div>
      )}
    </>
  );
}
