// ─── Channel & Status ────────────────────────────────────────────────────────

export type Channel = 'Phone' | 'Zalo' | 'Facebook';
export type InteractionStatus = 'Open' | 'Pending' | 'Resolved' | 'Handoff';
export type Priority = 'High' | 'Normal' | 'Low';

// ─── Interaction ──────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  from: 'customer' | 'agent' | 'note';
  text: string;
  time: string;
}

export interface Interaction {
  id: string;
  customerId: string;
  customerName: string;
  agentId: string;
  channel: Channel;
  timeAgo: string;
  preview: string;
  status: InteractionStatus;
  priority: Priority;
  identityVerified: boolean;
  messages: Message[];
  linkedCase?: string;
  suggestedReply?: string;
}

// ─── Customer ─────────────────────────────────────────────────────────────────

export type CustomerType = 'New customer' | 'Returning customer';

export interface CustomerJourneyEvent {
  date: string;
  label: string;
  type: 'interaction' | 'purchase' | 'support' | 'note';
}

export interface Customer {
  id: string;
  name: string;
  initials: string;
  phone: string;
  email?: string;
  type: CustomerType;
  verified: boolean;
  interactionCount: number;
  totalSpend?: string;
  joinDate?: string;
  tags?: string[];
  journey: CustomerJourneyEvent[];
}

// ─── Product ─────────────────────────────────────────────────────────────────

export type StockStatus = 'In stock' | 'Low stock' | 'Out of stock';

export interface Product {
  id: string;
  sku: string;
  name: string;
  category: string;
  price: number;
  stockStatus: StockStatus;
  stockQty: number;
  warranty?: string;
  description?: string;
  specs?: Record<string, string>;
  tags?: string[];
}

// ─── Promotion ────────────────────────────────────────────────────────────────

export type PromoStatus = 'Active' | 'Upcoming' | 'Expired';
export type PromoType = 'Percentage' | 'Bundle' | 'Free gift';

export interface Promotion {
  id: string;
  name: string;
  code: string;
  status: PromoStatus;
  type: PromoType;
  discount: string;
  startDate: string;
  endDate: string;
  minOrder?: string;
  applicableSkus?: string[];
  description?: string;
  terms?: string[];
}

// ─── Policy ───────────────────────────────────────────────────────────────────

export type PolicyStatus = 'Current' | 'Archived';

export interface PolicyVersion {
  version: string;
  effectiveFrom: string;
  effectiveTo?: string;
  changes?: string;
}

export interface Policy {
  id: string;
  title: string;
  category: string;
  version: string;
  status: PolicyStatus;
  effectiveFrom: string;
  effectiveTo?: string;
  summary?: string;
  content?: string[];
  versions?: PolicyVersion[];
}

// ─── Evaluation ───────────────────────────────────────────────────────────────

export type ScenarioResult = 'Pass' | 'Needs review' | 'Fail';

export interface ScenarioEvidence {
  step: string;
  observation: string;
  pass: boolean;
}

export interface EvalScenario {
  id: string;
  name: string;
  result: ScenarioResult;
  score: number;
  runDate: string;
  duration: string;
  evidence: ScenarioEvidence[];
}

// ─── Improvement ─────────────────────────────────────────────────────────────

export interface ImprovementProposal {
  id: string;
  title: string;
  description: string;
  count?: number;
  status: 'Pending review' | 'Applied' | 'Rejected';
}

// ─── Store ────────────────────────────────────────────────────────────────────

export interface WorkspaceState {
  activeInteractionId: string;
  contextTab: 'overview' | 'journey' | 'case';
  channelFilter: string;
  statusFilter: string;
  customerVerifiedOverrides: Record<string, boolean>;
  sessionMessages: Record<string, Array<{ from: 'agent'; text: string; time: string }>>;
}
