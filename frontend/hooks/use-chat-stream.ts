"use client";

import { useCallback, useRef, useState } from "react";
import type { ChatStreamPayload, Message, Product } from "@/types/product";

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastUserMessage, setLastUserMessage] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (text: string) => {
    const userMsg = text.trim();
    if (!userMsg) return;

    setLastUserMessage(userMsg);
    const assistantId = uid();

    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", text: userMsg, timestamp: Date.now() },
      { id: assistantId, role: "assistant", text: "", timestamp: Date.now() },
    ]);
    setLoading(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: "anonymous",
          message: userMsg,
          stream: true,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const details = await res.text();
        throw new Error(
          `Chat API returned HTTP ${res.status}: ${details || res.statusText}`
        );
      }
      if (!res.body) throw new Error("Chat API response has no stream body.");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let receivedText = false;
      let collectedProducts: Product[] = [];

      const processEvent = (event: string) => {
        const data = event
          .split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!data) return;

        let payload: ChatStreamPayload;
        try {
          payload = JSON.parse(data);
        } catch {
          return;
        }

        if (typeof payload.error === "string") {
          throw new Error(payload.error);
        }

        if (payload.products && Array.isArray(payload.products)) {
          collectedProducts = payload.products;
        }

        if (typeof payload.text === "string") {
          receivedText = true;
          setMessages((prev) => {
            const updated = [...prev];
            const idx = updated.findIndex((m) => m.id === assistantId);
            if (idx >= 0) {
              updated[idx] = {
                ...updated[idx],
                text: updated[idx].text + payload.text,
                products:
                  collectedProducts.length > 0
                    ? collectedProducts
                    : updated[idx].products,
              };
            }
            return updated;
          });
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0) {
          processEvent(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          boundary = buffer.indexOf("\n\n");
        }
        if (done) break;
      }
      if (buffer.trim()) processEvent(buffer);

      if (collectedProducts.length > 0) {
        setMessages((prev) => {
          const updated = [...prev];
          const idx = updated.findIndex((m) => m.id === assistantId);
          if (idx >= 0) {
            updated[idx] = { ...updated[idx], products: collectedProducts };
          }
          return updated;
        });
      }

      if (!receivedText) throw new Error("Chat API stream returned no answer.");
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      console.error(e);
      const errorText =
        e instanceof Error ? e.message : "Lỗi khi gọi API.";
      setMessages((prev) => {
        const updated = [...prev];
        const idx = updated.findIndex((m) => m.id === assistantId);
        if (idx >= 0) {
          const current = updated[idx].text;
          updated[idx] = {
            ...updated[idx],
            isError: true,
            text: current
              ? `${current}\n\n[Phản hồi bị gián đoạn: ${errorText}]`
              : `Lỗi khi gọi API: ${errorText}`,
          };
        }
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const clearChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setLastUserMessage("");
    setLoading(false);
  }, []);

  const retryLast = useCallback(() => {
    if (lastUserMessage && !loading) void sendMessage(lastUserMessage);
  }, [lastUserMessage, loading, sendMessage]);

  return {
    messages,
    loading,
    lastUserMessage,
    sendMessage,
    clearChat,
    retryLast,
  };
}
