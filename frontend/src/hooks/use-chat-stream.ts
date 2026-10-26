"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CallBriefSummary,
  ChatStreamPayload,
  Message,
  Product,
} from "@/types/product";

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export type SessionStatus = "active" | "ending" | "ended" | "error";

export interface EndSessionResult {
  session_id: string;
  finalized: boolean;
  already_finalized: boolean;
  empty_session: boolean;
  status: string;
  working_events: number;
  episode_outcome?: string | null;
  profile_facts_written: string[];
  persistence_warning?: string | null;
}

function newSessionId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

const SESSION_STORAGE_KEY = "sc2026-session-id";

export type ChatConnection = {
  scope?: string;
  channel?: string;
  metadata?: Record<string, string>;
};

export function chatSessionStorageKey(scope?: string, customerId?: string) {
  if (scope) return `${SESSION_STORAGE_KEY}:${scope}`;
  if (customerId) return `${SESSION_STORAGE_KEY}:${customerId}`;
  return SESSION_STORAGE_KEY;
}

function isValidSessionId(value: string | null): value is string {
  if (!value) return false;
  const trimmed = value.trim();
  if (trimmed.length < 8 || trimmed.length > 128) return false;
  return /^[A-Za-z0-9_-]+$/.test(trimmed);
}

export function useChatStream(connection?: ChatConnection) {
  const connectionRef = useRef(connection);
  connectionRef.current = connection;
  const scope = connection?.scope ?? "";
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [callBrief, setCallBrief] = useState<CallBriefSummary | null>(null);
  const [lastUserMessage, setLastUserMessage] = useState("");
  // Null on first render so server and client produce identical HTML.
  // The real ID is created/restored after mount (client-only).
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState("");
  const sessionReady = sessionId !== null;
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("active");
  const [endResult, setEndResult] = useState<EndSessionResult | null>(null);
  const [endError, setEndError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  // Client-only: restore the current session across refresh, otherwise
  // create exactly one ID. Never finalize or create extra sessions here.
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const selectedCustomerId = params.get("customer_id")?.trim() ?? "";
      setCustomerId(selectedCustomerId);
      const storageKey = chatSessionStorageKey(scope, selectedCustomerId);
      const stored = window.sessionStorage.getItem(storageKey);
      if (isValidSessionId(stored)) {
        setSessionId(stored);
        return;
      }
    } catch {
      // Storage unavailable: fall through to in-memory ID.
    }
    const nextId = newSessionId();
    setSessionId(nextId);
    try {
      const selectedCustomerId = new URLSearchParams(window.location.search)
        .get("customer_id")?.trim() ?? "";
      window.sessionStorage.setItem(
        chatSessionStorageKey(scope, selectedCustomerId),
        nextId,
      );
    } catch {
      // Ignore storage errors; session still works in memory.
    }
  }, [scope]);

  const sendMessage = useCallback(async (text: string) => {
    const userMsg = text.trim();
    if (!userMsg || !sessionId) return;
    if (sessionStatus === "ending" || sessionStatus === "ended") return;

    setLastUserMessage(userMsg);
    setCallBrief({
      status: "loading",
      has_history: false,
      current_need: userMsg,
      recent_sessions: [],
      open_blockers: [],
      open_questions: [],
      suggested_next_action: "",
    });
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
          customer_id: customerId,
          session_id: sessionId,
          message: userMsg,
          stream: true,
          ...(connectionRef.current?.channel
            ? { channel: connectionRef.current.channel }
            : {}),
          ...(connectionRef.current?.metadata
            ? { metadata: connectionRef.current.metadata }
            : {}),
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

        if (Object.prototype.hasOwnProperty.call(payload, "call_brief")) {
          setCallBrief(payload.call_brief ?? null);
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
        if (value) {
          buffer += decoder.decode(value, { stream: true });
        }
        if (done) {
          buffer += decoder.decode();
        }
        buffer = buffer.replace(/\r\n/g, "\n");
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
      setCallBrief((previous) =>
        previous
          ? { ...previous, status: "error" }
          : {
              status: "error",
              has_history: false,
              current_need: "",
              recent_sessions: [],
              open_blockers: [],
              open_questions: [],
              suggested_next_action: "",
            }
      );
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
  }, [sessionId, sessionStatus, customerId]);

  const endSession = useCallback(async () => {
    if (!sessionId || sessionStatus === "ending" || sessionStatus === "ended") return null;
    setSessionStatus("ending");
    setEndError("");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const res = await fetch("/api/chat/end-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          customer_id: customerId || "anonymous",
          ...(connectionRef.current?.metadata
            ? { metadata: connectionRef.current.metadata }
            : {}),
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        let errorDetail = "";
        try {
          const jsonError = await res.json();
          errorDetail =
            typeof jsonError.error === "string"
              ? jsonError.error
              : typeof jsonError.detail === "string"
              ? jsonError.detail
              : "";
        } catch {
          // Response is HTML or plain text, do not render raw HTML
        }
        if (errorDetail) {
          throw new Error(`Không thể kết thúc phiên: ${errorDetail} (HTTP ${res.status})`);
        }
        throw new Error(`Không thể kết thúc phiên: API trả về HTTP ${res.status}`);
      }
      const payload = (await res.json()) as EndSessionResult;
      // Only report success after backend confirms persistence.
      if (!payload.finalized && !payload.empty_session) {
        throw new Error("Backend chưa xác nhận lưu phiên.");
      }
      setEndResult(payload);
      setSessionStatus("ended");
      return payload;
    } catch (e) {
      const message = e instanceof Error ? e.message : "Lỗi khi kết thúc phiên.";
      setEndError(message);
      setSessionStatus("error");
      return null;
    } finally {
      window.clearTimeout(timeout);
    }
  }, [sessionId, sessionStatus, customerId]);

  const startNewSession = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setLastUserMessage("");
    setEndResult(null);
    setEndError("");
    setCallBrief(null);
    const nextId = newSessionId();
    setSessionId(nextId);
    try {
      window.sessionStorage.setItem(
        chatSessionStorageKey(connectionRef.current?.scope, customerId),
        nextId,
      );
    } catch {
      // Ignore storage errors; session still works in memory.
    }
    setSessionStatus("active");
    setLoading(false);
  }, [customerId]);

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
    sessionId,
    sessionReady,
    sessionStatus,
    endResult,
    endError,
    callBrief,
    sendMessage,
    endSession,
    startNewSession,
    clearChat,
    retryLast,
  };
}
