"use client";

import { useState } from "react";
import { SidebarLeft } from "@/components/sidebar-left";
import { SidebarRight } from "@/components/sidebar-right";
import { ChatHeader } from "@/components/chat-header";
import { ChatMessages } from "@/components/chat-messages";
import { ChatInput } from "@/components/chat-input";
import { useChatStream } from "@/hooks/use-chat-stream";

export default function ChatPage() {
  const {
    messages,
    loading,
    sendMessage,
    clearChat,
    retryLast,
    sessionId,
    sessionReady,
    sessionStatus,
    endResult,
    endError,
    endSession,
    startNewSession,
  } = useChatStream();
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

  const handleEndSession = async () => {
    if (!window.confirm("Kết thúc phiên và lưu lịch sử tư vấn?")) return;
    const result = await endSession();
    if (result) {
      showToast(
        result.already_finalized
          ? "Phiên đã được lưu trước đó."
          : `Đã lưu phiên: ${result.working_events} sự kiện.`
      );
    } else {
      showToast("Kết thúc phiên thất bại, vui lòng thử lại.");
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
            <ChatHeader
              sessionStatus={sessionStatus}
              sessionReady={sessionReady}
              onEndSession={handleEndSession}
            />
          </div>
          <div className="mx-auto w-full max-w-3xl px-4 pt-2 text-[12px] text-[var(--text-secondary)]">
            Phiên: {!sessionReady || !sessionId ? "Đang khởi tạo phiên..." : `${sessionId.slice(0, 8)}…`} · Trạng thái:{" "}
            {sessionStatus === "active" && "Đang tư vấn"}
            {sessionStatus === "ending" && "Đang lưu phiên..."}
            {sessionStatus === "ended" && "Đã kết thúc và lưu memory"}
            {sessionStatus === "error" && `Lỗi: ${endError || "không lưu được"}`}
          </div>
          {sessionStatus === "ended" && endResult && (
            <div className="mx-auto mt-2 w-full max-w-3xl rounded-xl bg-white/80 px-4 py-2 text-[12.5px] shadow">
              Đã lưu {endResult.working_events} sự kiện
              {endResult.episode_outcome ? ` · Kết quả: ${endResult.episode_outcome}` : ""}
              {endResult.profile_facts_written.length > 0
                ? ` · Profile: ${endResult.profile_facts_written.join(", ")}`
                : ""}
              {endResult.persistence_warning
                ? ` · Cảnh báo: ${endResult.persistence_warning}`
                : ""}
              <button
                type="button"
                onClick={startNewSession}
                className="ml-3 rounded-full bg-[var(--accent-caramel)] px-3 py-1 text-white"
              >
                Bắt đầu phiên mới
              </button>
            </div>
          )}
          <ChatMessages
            messages={messages}
            loading={loading}
            onCopy={handleCopy}
            onRetry={retryLast}
          />
          <ChatInput
            onSend={sendMessage}
            loading={!sessionReady || loading || sessionStatus === "ending" || sessionStatus === "ended"}
          />
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
