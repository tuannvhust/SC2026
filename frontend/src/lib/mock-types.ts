export type Channel = "Phone" | "Zalo" | "Facebook";
export type InteractionStatus = "Open" | "Pending" | "Resolved" | "Handoff";
export type Priority = "High" | "Normal" | "Low";

export interface ChatMessage {
  from: "customer" | "agent" | "note";
  text: string;
  time: string;
}

export interface Interaction {
  id: string;
  customerId: string;
  name: string;
  channel: Channel;
  time: string;
  preview: string;
  status: InteractionStatus;
  priority: Priority;
  caseId: string;
  caseTitle: string;
  suggestion?: string;
  messages: ChatMessage[];
}

export interface JourneyEvent {
  title: string;
  detail: string;
  time: string;
  id: string;
}

export interface Customer {
  id: string;
  name: string;
  initials: string;
  phone: string;
  email: string;
  segment: string;
  verified: boolean;
  caseCount: number;
  history: JourneyEvent[];
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  category: string;
  price: number;
  availability: "In stock" | "Low stock" | "Out of stock";
  stock: number;
  description: string;
  features: string[];
  warranty: string;
  tags: string[];
  icon: string;
}

export interface Promotion {
  id: string;
  code: string;
  name: string;
  type: string;
  status: "Active" | "Upcoming" | "Expired";
  value: string;
  start: string;
  end: string;
  minimum: number;
  products: string[];
  description: string;
  terms: string[];
  icon: string;
}

export interface Policy {
  id: string;
  topic: string;
  category: string;
  version: string;
  status: "Current" | "Archived";
  effective: string;
  effectiveTo?: string;
  published: string;
  owner: string;
  approvedBy: string;
  summary: string;
  keywords: string[];
  content: string;
  changeNote: string;
  previous?: string;
  supersededBy?: string;
}

export interface EvalScenario {
  id: string;
  focus: string;
  mode: string;
  outcome: "Pass" | "Needs review" | "Fail";
}
