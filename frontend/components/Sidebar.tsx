"use client";

import React from "react";
import { Menu, Moon, Plus, Sun, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { formatDateGroup } from "@/lib/utils";

const HISTORY = [
  { id: "1", title: "Chat với TechStore AI", date: new Date() },
  { id: "2", title: "Sản phẩm Samsung", date: new Date(Date.now() - 2 * 86400000) },
  { id: "3", title: "Chính sách trả góp", date: new Date(Date.now() - 10 * 86400000) },
];

export function Sidebar() {
  const [open, setOpen] = React.useState(false);
  const [dark, setDark] = React.useState(false);

  const toggleDark = (value: boolean) => {
    setDark(value);
    document.documentElement.classList.toggle("dark", value);
  };

  const content = (
    <div className="flex h-full flex-col">
      <div className="mb-5 flex items-center justify-between">
        <span className="text-lg font-bold">SUDO AI</span>
        <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setOpen(false)} aria-label="Đóng menu">
          <X size={18} />
        </Button>
      </div>
      <Button variant="outline" className="mb-5 w-full justify-start" onClick={() => setOpen(false)}>
        <Plus className="mr-2 h-4 w-4" /> Cuộc trò chuyện mới
      </Button>
      <nav className="flex-1 space-y-4 overflow-y-auto">
        {Object.entries(HISTORY.reduce<Record<string, typeof HISTORY>>((groups, chat) => {
          const group = formatDateGroup(chat.date);
          (groups[group] ??= []).push(chat);
          return groups;
        }, {})).map(([group, chats]) => (
          <div key={group}>
            <p className="mb-1 px-2 text-xs font-semibold uppercase text-slate-400">{group}</p>
            {chats.map((chat) => (
              <button key={chat.id} className="block w-full truncate rounded-lg px-2 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => setOpen(false)}>
                {chat.title}
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="flex items-center justify-between gap-3 border-t border-slate-200 pt-4 text-sm dark:border-slate-800">
        <span className="min-w-0 flex-1 truncate">Chế độ tối</span>
        <span className="flex shrink-0 items-center gap-2">
          {dark ? <Moon size={16} /> : <Sun size={16} />}
          <Switch checked={dark} onCheckedChange={toggleDark} />
        </span>
      </div>
    </div>
  );

  return (
    <>
      <Button variant="ghost" size="icon" className="fixed left-3 top-3 z-30 md:hidden" onClick={() => setOpen(true)} aria-label="Mở menu">
        <Menu size={20} />
      </Button>
      <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950 md:block">{content}</aside>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setOpen(false)}>
          <aside className="h-full w-72 bg-white p-4 dark:bg-slate-950" onClick={(event) => event.stopPropagation()}>{content}</aside>
        </div>
      )}
    </>
  );
}
