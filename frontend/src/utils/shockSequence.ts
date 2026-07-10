import type { Recommendation, ShockState } from "../types";

export type ShockSequenceStepId = "baseline" | "disruption" | "recovery";
export type ShockSequenceStatus = "complete" | "active" | "ready" | "blocked";

export interface ShockSequenceStep {
  id: ShockSequenceStepId;
  label: string;
  metric: string;
  detail: string;
  status: ShockSequenceStatus;
}

export interface RecoveryPlaybook {
  status: "ready" | "blocked";
  primarySupplierName: string;
  routeCount: number;
  coveragePercent: number;
  recoverableVolume: number;
  residualVolume: number;
  weightedLeadTimeDays: number;
  guardrail: string;
}

const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const RECOVERY_COVERAGE_CAP = 92;

function roundTwo(value: number) {
  return Math.round(value * 100) / 100;
}

export function recoveryPlaybook({
  shock,
  recommendations
}: {
  shock: ShockState;
  recommendations: Recommendation[];
}): RecoveryPlaybook {
  const rankedRoutes = recommendations
    .filter((item) => item.supplierId !== shock.shockNodeId)
    .filter((item) => Number.isFinite(item.score) && item.score > 0)
    .slice(0, 3);

  if (!shock.active || !rankedRoutes.length) {
    return {
      status: "blocked",
      primarySupplierName: "No alternate route selected",
      routeCount: 0,
      coveragePercent: 0,
      recoverableVolume: 0,
      residualVolume: shock.monthlyVolumeAtRisk,
      weightedLeadTimeDays: 0,
      guardrail: "Run shock simulation first and load a consent-gated shortlist before proposing any recovery action."
    };
  }

  const scoreTotal = rankedRoutes.reduce((total, item) => total + item.score, 0);
  const coverageScore = Math.min(RECOVERY_COVERAGE_CAP, scoreTotal / rankedRoutes.length);
  const coveragePercent = Math.round(coverageScore);
  const recoverableVolume = Math.round(shock.monthlyVolumeAtRisk * (coverageScore / 100));
  const residualVolume = Math.max(0, shock.monthlyVolumeAtRisk - recoverableVolume);
  const weightedLeadTimeDays = scoreTotal
    ? roundTwo(rankedRoutes.reduce((total, item) => total + item.leadTimeDays * item.score, 0) / scoreTotal)
    : 0;

  return {
    status: "ready",
    primarySupplierName: rankedRoutes[0].supplierName,
    routeCount: rankedRoutes.length,
    coveragePercent,
    recoverableVolume,
    residualVolume,
    weightedLeadTimeDays,
    guardrail: "Decision-support only: this is not an automatic supplier replacement, credit approval or contract decision."
  };
}

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
