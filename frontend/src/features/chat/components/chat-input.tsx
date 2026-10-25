"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Send, Paperclip, Mic } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string) => void;
  loading?: boolean;
}

export function ChatInput({ onSend, loading }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text || loading) return;
    onSend(text);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const onInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  return (
    <div className="relative z-20 flex w-full shrink-0 justify-center px-4 pb-4 pt-2">
      <div className="flex w-full max-w-2xl items-end gap-2 rounded-full border border-white/70 bg-[rgba(255,255,255,0.78)] px-2 py-1.5 shadow-float backdrop-blur-2xl">
        <button
          type="button"
          className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--text-muted)] transition hover:bg-[var(--bg-cream)] hover:text-[var(--text-primary)]"
          title="Đính kèm"
          disabled={loading}
        >
          <Paperclip className="h-4 w-4" strokeWidth={1.75} />
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          onInput={onInput}
          disabled={loading}
          placeholder="Hỏi về sản phẩm, giá, tồn kho…"
          className="max-h-[140px] min-h-[36px] flex-1 resize-none bg-transparent py-2 text-[13.5px] leading-snug text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] disabled:opacity-60"
        />

        <button
          type="button"
          className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--text-muted)] transition hover:bg-[var(--bg-cream)] hover:text-[var(--text-primary)]"
          title="Giọng nói"
          disabled={loading}
        >
          <Mic className="h-4 w-4" strokeWidth={1.75} />
        </button>

        <button
          type="button"
          onClick={submit}
          disabled={loading || !value.trim()}
          className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--accent-caramel)] text-white transition hover:bg-[var(--accent-gold)] disabled:opacity-40 disabled:hover:bg-[var(--accent-caramel)]"
          title="Gửi"
        >
          <Send className="h-4 w-4" strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}
