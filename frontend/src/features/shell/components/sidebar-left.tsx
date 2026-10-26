"use client";

import {
  Compass,
  LayoutGrid,
  Wrench,
  Settings,
  User,
  LogOut,
  Plus,
  Sparkles,
} from "lucide-react";

const NAV_ITEMS = [
  { icon: Compass, label: "Discover", active: false },
  { icon: LayoutGrid, label: "Workspace", active: true },
  { icon: Wrench, label: "Tools", active: false },
  { icon: Settings, label: "System", active: false },
  { icon: User, label: "Profile", active: false },
];

interface SidebarLeftProps {
  onNewChat?: () => void;
}

export function SidebarLeft({ onNewChat }: SidebarLeftProps) {
  return (
    <aside className="sidebar-left flex h-full min-h-0 w-[220px] shrink-0 flex-col gap-3 overflow-y-auto p-3">
      {/* Brand card */}
      <div className="glass-card rounded-[20px] p-4">
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--bg-charcoal)]">
            <Sparkles className="h-4.5 w-4.5 text-[var(--accent-gold)]" strokeWidth={2} />
          </div>
          <div>
            <p className="text-[13px] font-semibold tracking-tight text-[var(--text-primary)]">
              SUDOTECH
            </p>
            <p className="text-[11px] font-medium text-[var(--text-muted)]">
              Sales AI
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[var(--accent-caramel)] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[var(--accent-gold)] active:scale-[0.98]"
        >
          <Plus className="h-4 w-4" strokeWidth={2.5} />
          New chat
        </button>
      </div>

      {/* Navigation */}
      <nav className="glass-card flex flex-1 flex-col gap-1 rounded-[20px] p-2">
        {NAV_ITEMS.map(({ icon: Icon, label, active }) => (
          <button
            key={label}
            type="button"
            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[13px] font-medium transition ${
              active
                ? "bg-white text-[var(--text-primary)] shadow-sm"
                : "text-[var(--text-secondary)] hover:bg-white/60 hover:text-[var(--text-primary)]"
            }`}
          >
            <Icon className="h-4 w-4 shrink-0 opacity-80" strokeWidth={1.75} />
            {label}
          </button>
        ))}

        <div className="mt-auto border-t border-[var(--border-cream)] pt-2">
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[13px] font-medium text-[var(--text-muted)] transition hover:bg-white/60 hover:text-[var(--text-primary)]"
          >
            <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.75} />
            Log out
          </button>
        </div>
      </nav>
    </aside>
  );
}
