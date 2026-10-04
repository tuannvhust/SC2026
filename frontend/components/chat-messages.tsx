"use client";

import { useEffect, useRef } from "react";
import { Copy, RefreshCw, User, Bot } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "@/types/product";
import { ProductCard } from "./product-card";

interface ChatMessagesProps {
  messages: Message[];
  loading: boolean;
  onCopy?: (text: string) => void;
  onRetry?: () => void;
}

function TypingIndicator() {
  return (
    <div className="animate-msg mb-5 flex items-start gap-2.5">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--bg-charcoal)]">
        <Bot className="h-4 w-4 text-[var(--accent-gold)]" />
      </div>
      <div className="rounded-2xl rounded-tl-md bg-[var(--bg-charcoal)] px-4 py-3 shadow-soft">
        <div className="flex items-center gap-1.5">
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[var(--text-on-dark-muted)]" />
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[var(--text-on-dark-muted)]" />
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[var(--text-on-dark-muted)]" />
        </div>
      </div>
    </div>
  );
}

function UserBubble({ msg }: { msg: Message }) {
  return (
    <div className="animate-msg mb-5 flex items-start justify-end gap-2.5">
      <div className="max-w-[75%] rounded-2xl rounded-tr-md border border-white/70 bg-[rgba(242,238,229,0.88)] px-4 py-2.5 text-[13.5px] leading-relaxed text-[var(--text-primary)] shadow-soft backdrop-blur-xl">
        {msg.text}
      </div>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent-caramel)]">
        <User className="h-4 w-4 text-white" />
      </div>
    </div>
  );
}

function AssistantBubble({
  msg,
  onCopy,
  onRetry,
  isLast,
  isStreaming,
}: {
  msg: Message;
  onCopy?: (text: string) => void;
  onRetry?: () => void;
  isLast: boolean;
  isStreaming: boolean;
}) {
  if (!msg.text && !msg.products?.length) return null;

  return (
    <div className="animate-msg mb-5 flex items-start gap-2.5">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--bg-charcoal)]">
        <Bot className="h-4 w-4 text-[var(--accent-gold)]" />
      </div>

      <div className="flex max-w-[85%] flex-col gap-2">
        {msg.text && (
          <div
            className={`rounded-2xl rounded-tl-md px-4 py-3 text-[13.5px] leading-relaxed shadow-soft ${
              msg.isError
                ? "border border-red-500/30 bg-[var(--bg-charcoal)] text-red-200"
                : "bg-[var(--bg-charcoal)] text-[var(--text-on-dark)]"
            }`}
          >
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.text}
              </ReactMarkdown>
              {isStreaming && (
                <span
                  aria-hidden="true"
                  className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-[var(--accent-gold)] align-middle"
                />
              )}
            </div>

            {/* Action bar */}
            {msg.text && (
              <div className="mt-2.5 flex items-center gap-1 border-t border-white/10 pt-2">
                <button
                  type="button"
                  onClick={() => onCopy?.(msg.text)}
                  className="rounded-lg p-1.5 text-[var(--text-on-dark-muted)] transition hover:bg-white/10 hover:text-white"
                  title="Sao chép"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
                {isLast && onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="rounded-lg p-1.5 text-[var(--text-on-dark-muted)] transition hover:bg-white/10 hover:text-white"
                    title="Thử lại"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Product cards grid */}
        {msg.products && msg.products.length > 0 && (
          <div className="flex flex-wrap gap-2.5">
            {msg.products.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ChatMessages({
  messages,
  loading,
  onCopy,
  onRetry,
}: ChatMessagesProps) {
  const messagesRef = useRef<HTMLDivElement>(null);
  const shouldStickToBottomRef = useRef(true);

  useEffect(() => {
    const container = messagesRef.current;
    if (container && shouldStickToBottomRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages, loading]);

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div
      ref={messagesRef}
      aria-label="Chat messages"
      className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col overflow-x-hidden overflow-y-auto px-2 pb-6 pt-6"
      onScroll={(event) => {
        const container = event.currentTarget;
        shouldStickToBottomRef.current =
          container.scrollHeight - container.clientHeight - container.scrollTop < 80;
      }}
    >
      {isEmpty && (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--bg-cream)] shadow-soft">
            <Bot className="h-7 w-7 text-[var(--accent-caramel)]" />
          </div>
          <div>
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
              Xin chào! Tôi là SUDOTECH Sales AI
            </h2>
            <p className="mt-1 max-w-sm text-[13px] text-[var(--text-muted)]">
              Hỏi tôi về sản phẩm, giá cả, tồn kho hoặc chính sách bảo hành —
              tôi sẽ tư vấn ngay.
            </p>
          </div>
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            {[
              "Samsung A55 còn hàng không?",
              "So sánh S24 và S24 Ultra",
              "Chính sách trả góp?",
            ].map((q) => (
              <span
                key={q}
                className="rounded-full bg-[var(--bg-cream)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] shadow-sm"
              >
                {q}
              </span>
            ))}
          </div>
        </div>
      )}

      {messages.map((msg, idx) =>
        msg.role === "user" ? (
          <UserBubble key={msg.id} msg={msg} />
        ) : (
          <AssistantBubble
            key={msg.id}
            msg={msg}
            onCopy={onCopy}
            onRetry={onRetry}
            isLast={idx === messages.length - 1}
            isStreaming={loading && idx === messages.length - 1}
          />
        )
      )}

      {loading && <TypingIndicator />}
    </div>
  );
}
