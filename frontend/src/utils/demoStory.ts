import type { ShockState } from "../types";

export type DemoStoryStepId = "intake" | "map_risk" | "shock" | "matching" | "audit";
export type DemoStoryStepStatus = "ready" | "active" | "blocked";

export interface DemoStoryStep {
  id: DemoStoryStepId;
  order: string;
  label: string;
  detail: string;
  status: DemoStoryStepStatus;
}

export function demoStorySteps({
  shock,
  canOpenIntake,
  canOpenRisk,
  canOpenMatching,
  canOpenAudit
}: {
  shock: ShockState;
  canOpenIntake: boolean;
  canOpenRisk: boolean;
  canOpenMatching: boolean;
  canOpenAudit: boolean;
}): DemoStoryStep[] {
  return [
    {
      id: "intake",
      order: "0:00",
      label: "Data Intake",
      detail: "Show monthly SME input, evidence upload and review gate.",
      status: canOpenIntake ? "ready" : "blocked"
    },
    {
      id: "map_risk",
      order: "0:45",
      label: "Supply Map + Risk",
      detail: "Open the Binh Duong case and explain the policy-gated risk signal.",
      status: canOpenRisk ? "ready" : "blocked"
    },
    {
      id: "shock",
      order: "1:45",
      label: "Shock Simulation",
      detail: shock.active
        ? "Disruption is live; exposed routes and downstream SMEs are highlighted."
        : "Run the supplier disruption and reveal operational exposure.",
      status: shock.active ? "active" : "ready"
    },
    {
      id: "matching",
      order: "2:30",
      label: "Recovery Matching",
      detail: "Review the alternative supplier shortlist with consent still enforced.",
      status: canOpenMatching ? (shock.active ? "active" : "ready") : "blocked"
    },
    {
      id: "audit",
      order: "3:30",
      label: "Consent + Audit",
      detail: "Close by showing introduction consent, policy decisions and audit IDs.",
      status: canOpenAudit ? "ready" : "blocked"
    }
  ];
}

export function demoStoryReadyCount(steps: DemoStoryStep[]): number {
  return steps.filter((step) => step.status !== "blocked").length;
}
