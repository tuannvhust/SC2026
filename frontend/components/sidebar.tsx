"use client";
import { useWorkspace, type ViewKey } from "./workspace-provider";
import { BarChart3, LayoutGrid, Percent, ScrollText, Sparkles, Users, Box } from "lucide-react";

const NAV: { key: ViewKey; label: string; icon: typeof Box }[] = [
  { key: "workspace", label: "Workspace", icon: LayoutGrid },
  { key: "customers", label: "Customers", icon: Users },
  { key: "products", label: "Products", icon: Box },
  { key: "promotions", label: "Promotions", icon: Percent },
  { key: "policies", label: "Policies", icon: ScrollText },
  { key: "evaluation", label: "Evaluation", icon: BarChart3 },
  { key: "improvement", label: "Improvement", icon: Sparkles },
];

export function Sidebar() {
  const { view, setView } = useWorkspace();
  return (
    <aside className="flex flex-col gap-7 bg-[#111a2c] px-3.5 py-6 text-[#d6ddec]">
      <div className="flex items-center gap-2.5 px-2 text-base font-bold text-white">
        <div className="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#8195ff] to-[#5368e7]">S</div>
        <div>SC2026<small className="mt-0.5 block text-[10px] tracking-[1.5px] text-[#8f9bb3]">AGENT WORKSPACE</small></div>
      </div>
      <div>
        <div className="mb-2 px-2.5 text-[10px] font-bold tracking-[1.4px] text-[#8190aa]">WORKSPACE</div>
        <nav className="grid gap-1">
          {NAV.map(({ key, label, icon: Icon }) => (
            <button key={key} type="button" onClick={() => setView(key)}
              className={`flex items-center gap-3 rounded-[10px] px-3 py-2.5 text-left font-semibold ${view === key ? "bg-[#2b3c64] text-white shadow-[inset_3px_0_#8ea0ff]" : "text-[#aeb9ce] hover:bg-[#202c43] hover:text-white"}`}>
              <Icon className="h-[18px] w-[18px]" /><span>{label}</span>
            </button>
          ))}
        </nav>
      </div>
      <div className="mt-auto rounded-[13px] border border-[#2a3750] bg-[#1a263b] p-3">
        <div className="flex items-center gap-2.5">
          <div className="grid h-[34px] w-[34px] place-items-center rounded-full bg-[#e6eaff] font-bold text-[#334ab5]">LT</div>
          <div><strong className="block text-xs text-[#f3f5fb]">Linh Trần</strong><small className="text-[11px] text-[#8f9bb3]">Customer service agent</small></div>
        </div>
        <p className="mt-3 text-[10px] text-[#8190aa]">Workspace preview · Local mock data only</p>
      </div>
    </aside>
  );
}
