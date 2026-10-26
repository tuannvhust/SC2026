import type { EvalScenario } from "./mock-types";

export const EVAL_SCENARIOS: EvalScenario[] = [
  { id: "SC-01", focus: "Cross-session continuity", mode: "Memory-enabled", outcome: "Pass" },
  { id: "SC-04", focus: "Identity resolution", mode: "Baseline", outcome: "Needs review" },
  { id: "SC-07", focus: "Grounded response", mode: "Memory-enabled", outcome: "Pass" },
  { id: "SC-12", focus: "Human handoff", mode: "Baseline", outcome: "Pass" },
];
