"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { Customer, Interaction, InteractionStatus } from "@/lib/mock-types";
import { INITIAL_CUSTOMERS } from "@/lib/mock-customers";
import { INITIAL_INTERACTIONS } from "@/lib/mock-interactions";

export type ViewKey = "workspace" | "customers" | "products" | "promotions" | "policies" | "evaluation" | "improvement";
export type ContextTab = "overview" | "journey" | "case";
export type ModalState = { title: string; body: React.ReactNode; confirmText?: string } | null;

interface WorkspaceCtx {
  view: ViewKey; setView: (v: ViewKey) => void;
  interactions: Interaction[]; setInteractions: React.Dispatch<React.SetStateAction<Interaction[]>>;
  customers: Record<string, Customer>; setCustomers: React.Dispatch<React.SetStateAction<Record<string, Customer>>>;
  activeId: string; setActiveId: (id: string) => void;
  channelFilter: string; setChannelFilter: (v: string) => void;
  statusFilter: string; setStatusFilter: (v: string) => void;
  contextTab: ContextTab; setContextTab: (v: ContextTab) => void;
  toast: string; showToast: (msg: string) => void;
  modal: ModalState; openModal: (m: Exclude<ModalState, null>) => void; closeModal: () => void;
  updateStatus: (id: string, s: InteractionStatus) => void;
  sendAgentMessage: (id: string, text: string) => boolean;
  verifyCustomer: (customerId: string) => void;
  customerSearch: string; setCustomerSearch: (v: string) => void;
}

const Ctx = createContext<WorkspaceCtx | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
	const pathname = usePathname();
	const router = useRouter();
	const routeView = pathname.split("/")[1] || "workspace";
	const view: ViewKey = ["customers", "products", "promotions", "policies", "evaluation", "improvement"].includes(routeView)
		? (routeView as ViewKey)
		: "workspace";
	const setView = useCallback((nextView: ViewKey) => {
		router.push(nextView === "workspace" ? "/" : `/${nextView}`);
	}, [router]);
  const [interactions, setInteractions] = useState(INITIAL_INTERACTIONS);
  const [customers, setCustomers] = useState(INITIAL_CUSTOMERS);
  const [activeId, setActiveId] = useState("IN-2048");
  const [channelFilter, setChannelFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [contextTab, setContextTab] = useState<ContextTab>("overview");
  const [toast, setToast] = useState("");
  const [modal, setModal] = useState<ModalState>(null);
  const [customerSearch, setCustomerSearch] = useState("");

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(""), 2600);
  }, []);

  const openModal = useCallback((m: Exclude<ModalState, null>) => setModal(m), []);
  const closeModal = useCallback(() => setModal(null), []);

  const updateStatus = useCallback((id: string, s: InteractionStatus) => {
    setInteractions((prev) => prev.map((x) => (x.id === id ? { ...x, status: s } : x)));
  }, []);

  const verifyCustomer = useCallback((customerId: string) => {
    setCustomers((prev) => ({ ...prev, [customerId]: { ...prev[customerId], verified: true } }));
  }, []);

  const sendAgentMessage = useCallback((id: string, raw: string) => {
    const text = raw.trim();
    if (!text) return false;
    const time = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    setInteractions((prev) =>
      prev.map((x) => (x.id === id ? { ...x, preview: text, time: "now", messages: [...x.messages, { from: "agent" as const, text, time }] } : x)),
    );
    return true;
  }, []);

  const value = useMemo(
    () => ({
      view, setView, interactions, setInteractions, customers, setCustomers,
      activeId, setActiveId, channelFilter, setChannelFilter, statusFilter, setStatusFilter,
      contextTab, setContextTab, toast, showToast, modal, openModal, closeModal,
      updateStatus, sendAgentMessage, verifyCustomer, customerSearch, setCustomerSearch,
    }),
		[view, setView, interactions, customers, activeId, channelFilter, statusFilter, contextTab, toast, modal, customerSearch, showToast, openModal, closeModal, updateStatus, sendAgentMessage, verifyCustomer],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return v;
}
