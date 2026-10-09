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
  text?: string;
  error?: string;
  done?: boolean;
  products?: Product[];
}
