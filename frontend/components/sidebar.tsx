"use client";
import { useWorkspace, type ViewKey } from "./workspace-provider";
import Link from "next/link";
import { BarChart3, ChevronLeft, LayoutGrid, Percent, ScrollText, Sparkles, Users, Box } from "lucide-react";

const NAV: { key: ViewKey; label: string; icon: typeof Box }[] = [
  { key: "workspace", label: "Workspace", icon: LayoutGrid },
  { key: "customers", label: "Customers", icon: Users },
  { key: "products", label: "Products", icon: Box },
  { key: "promotions", label: "Promotions", icon: Percent },
  { key: "policies", label: "Policies", icon: ScrollText },
  { key: "evaluation", label: "Evaluation", icon: BarChart3 },
  { key: "improvement", label: "Improvement", icon: Sparkles },
];

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { view } = useWorkspace();
  return (
    <aside className={`flex min-w-0 flex-col gap-4 bg-[#111a2c] px-3.5 py-4 text-[#d6ddec] sm:gap-7 sm:py-6 lg:min-h-screen ${collapsed ? "lg:px-2" : ""}`}>
      <div className={`flex items-center gap-2.5 px-2 text-base font-bold text-white ${collapsed ? "lg:justify-center lg:px-0" : "justify-between"}`}>
        <div className="flex min-w-0 items-center gap-2.5">
        <div className="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#8195ff] to-[#5368e7]">S</div>
        <div className={collapsed ? "lg:hidden" : ""}>SC2026<small className="mt-0.5 block text-[10px] tracking-[1.5px] text-[#8f9bb3]">AGENT WORKSPACE</small></div>
        </div>
        <button type="button" onClick={onToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}
          className="hidden h-8 w-8 shrink-0 place-items-center rounded-lg text-[#aeb9ce] hover:bg-[#202c43] hover:text-white lg:grid">
          <ChevronLeft className={`h-4 w-4 transition-transform ${collapsed ? "rotate-180" : ""}`} />
        </button>
      </div>
      <div className={collapsed ? "lg:w-full" : ""}>
        <div className={`mb-2 px-2.5 text-[10px] font-bold tracking-[1.4px] text-[#8190aa] ${collapsed ? "lg:hidden" : ""}`}>WORKSPACE</div>
        <nav className="flex gap-1 overflow-x-auto pb-1 lg:grid lg:overflow-visible lg:pb-0" aria-label="Workspace">
          {NAV.map(({ key, label, icon: Icon }) => (
            <Link key={key} href={key === "workspace" ? "/" : `/${key}`} title={collapsed ? label : undefined} aria-current={view === key ? "page" : undefined}
              className={`flex shrink-0 items-center gap-2 rounded-[10px] px-3 py-2.5 text-left text-sm font-semibold lg:gap-3 ${collapsed ? "lg:justify-center lg:px-0" : ""} ${view === key ? "bg-[#2b3c64] text-white shadow-[inset_3px_0_#8ea0ff]" : "text-[#aeb9ce] hover:bg-[#202c43] hover:text-white"}`}>
              <Icon className="h-[18px] w-[18px] shrink-0" /><span className={collapsed ? "lg:hidden" : ""}>{label}</span>
            </Link>
          ))}
        </nav>
      </div>
      <div className={`mt-auto hidden rounded-[13px] border border-[#2a3750] bg-[#1a263b] p-3 lg:block ${collapsed ? "lg:hidden" : ""}`}>
        <div className="flex items-center gap-2.5">
          <div className="grid h-[34px] w-[34px] place-items-center rounded-full bg-[#e6eaff] font-bold text-[#334ab5]">LT</div>
          <div><strong className="block text-xs text-[#f3f5fb]">Linh Trần</strong><small className="text-[11px] text-[#8f9bb3]">Customer service agent</small></div>
        </div>
        <p className="mt-3 text-[10px] text-[#8190aa]">Workspace preview · Local mock data only</p>
      </div>
    </aside>
  );
}
