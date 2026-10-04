"use client";

import { useState } from "react";
import { SidebarLeft } from "@/components/sidebar-left";
import { SidebarRight } from "@/components/sidebar-right";
import { ChatHeader } from "@/components/chat-header";
import { ChatMessages } from "@/components/chat-messages";
import { ChatInput } from "@/components/chat-input";
import { useChatStream } from "@/hooks/use-chat-stream";

export default function ChatPage() {
  const { messages, loading, sendMessage, clearChat, retryLast } =
    useChatStream();
  const [toast, setToast] = useState("");

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(""), 2000);
  };

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast("Đã sao chép tin nhắn");
    } catch {
      showToast("Không thể sao chép");
    }
  };

  return (
    <div className="chat-app relative flex h-screen w-screen flex-row items-stretch overflow-hidden p-6">
      <div className="ambient-background" aria-hidden="true">
        <span className="ambient-orb ambient-orb-one" />
        <span className="ambient-orb ambient-orb-two" />
        <span className="ambient-orb ambient-orb-three" />
      </div>

      <div className="relative z-10 flex h-full min-h-0 w-full flex-row items-stretch">
        <SidebarLeft onNewChat={clearChat} />

        <main className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="shrink-0">
            <ChatHeader />
          </div>
          <ChatMessages
            messages={messages}
            loading={loading}
            onCopy={handleCopy}
            onRetry={retryLast}
          />
          <ChatInput onSend={sendMessage} loading={loading} />
        </main>

        <SidebarRight />
      </div>

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-[var(--bg-charcoal)] px-4 py-2 text-sm text-white shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
