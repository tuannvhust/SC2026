"use client";

import { Share2, MoreHorizontal } from "lucide-react";

interface ChatHeaderProps {
  title?: string;
}

export function ChatHeader({
  title = "Tư Vấn Sản Phẩm & Báo Giá",
}: ChatHeaderProps) {
  return (
    <div className="mx-auto flex w-full max-w-3xl items-center justify-center px-2 pt-3">
      <div className="chat-header-pill flex items-center gap-1 rounded-full px-2 py-1.5">
        <div className="flex items-center gap-2 rounded-full px-4 py-1.5">
          <span className="text-[13px] font-semibold tracking-tight text-[var(--text-primary)]">
            {title}
          </span>
        </div>

        <div className="h-5 w-px bg-[var(--border-cream)]" />

        <button
          type="button"
          className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition hover:bg-white hover:text-[var(--text-primary)]"
        >
          <Share2 className="h-3.5 w-3.5" strokeWidth={1.75} />
          Share
        </button>

        <button
          type="button"
          className="rounded-full p-1.5 text-[var(--text-muted)] transition hover:bg-white hover:text-[var(--text-primary)]"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
