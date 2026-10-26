export interface Product {
  id: string;
  name: string;
  brand: string;
  series?: string;
  price: number;
  priceFormatted?: string;
  originalPrice?: number;
  stock: number;
  inStock: boolean;
  chipset?: string;
  ram?: string;
  rom?: string;
  display?: string;
  camera?: string;
  battery?: string;
  image?: string;
  category: string;
  tags?: string[];
}

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  text: string;
  products?: Product[];
  timestamp?: number;
  isError?: boolean;
}

export interface ChatStreamPayload {
  session_id?: string;
  turn_id?: string;
  type?: "call_brief" | "response" | "session" | "error";
  text?: string;
  error?: string;
  done?: boolean;
  products?: Product[];
  call_brief?: CallBriefSummary | null;
}

export interface CallBriefSummary {
  status: "loading" | "loaded" | "empty" | "partial" | "error";
  has_history: boolean;
  current_need: string;
  recent_sessions: Array<{
    date: string;
    summary: string;
    outcome: string;
  }>;
  open_blockers: string[];
  open_questions: string[];
  suggested_next_action: string;
}
