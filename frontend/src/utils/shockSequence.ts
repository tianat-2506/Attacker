import type { ShockState } from "../types";

export type ShockSequenceStepId = "baseline" | "disruption" | "recovery";
export type ShockSequenceStatus = "complete" | "active" | "ready" | "blocked";

export interface ShockSequenceStep {
  id: ShockSequenceStepId;
  label: string;
  metric: string;
  detail: string;
  status: ShockSequenceStatus;
}

const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

export function shockSequenceSteps({
  shock,
  canOpenMatching,
  shockTargetName
}: {
  shock: ShockState;
  canOpenMatching: boolean;
  shockTargetName: string;
}): ShockSequenceStep[] {
  if (!shock.active) {
    return [
      {
        id: "baseline",
        label: "Before",
        metric: "Baseline graph",
        detail: "Normal directed supply routes are visible before disruption.",
        status: "active"
      },
      {
        id: "disruption",
        label: "After",
        metric: shockTargetName,
        detail: "Run the shock to reveal exposed SMEs, units and route stress.",
        status: "ready"
      },
      {
        id: "recovery",
        label: "Recovery",
        metric: "Waiting",
        detail: "Recovery matching opens after the disruption is live.",
        status: "blocked"
      }
    ];
  }

  return [
    {
      id: "baseline",
      label: "Before",
      metric: "Baseline saved",
      detail: "Pre-shock network stays available for comparison.",
      status: "complete"
    },
    {
      id: "disruption",
      label: "After",
      metric: `${shock.affectedSmeCount} SMEs`,
      detail: `${compactNumber.format(shock.monthlyVolumeAtRisk)} units/month exposed through ${shockTargetName}.`,
      status: "active"
    },
    {
      id: "recovery",
      label: "Recovery",
      metric: canOpenMatching ? "Shortlist ready" : "Policy gated",
      detail: canOpenMatching
        ? "Open matching to compare consent-gated alternatives."
        : "This account cannot open recovery matching.",
      status: canOpenMatching ? "ready" : "blocked"
    }
  ];
}
