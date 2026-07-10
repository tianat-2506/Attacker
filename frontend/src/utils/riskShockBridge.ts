import type { ShockState } from "../types";

export type RiskShockBridgeState = "ready" | "live" | "unavailable";
export type RiskShockBridgeAction = "run" | "open" | "none";

export interface RiskShockBridgeMetric {
  label: string;
  value: string;
}

export interface RiskShockBridgeModel {
  state: RiskShockBridgeState;
  eyebrow: string;
  headline: string;
  detail: string;
  metrics: RiskShockBridgeMetric[];
  action: RiskShockBridgeAction;
  actionLabel: string;
  disabled: boolean;
  guardrail: string;
}

const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const guardrail = "Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.";

export function riskShockBridgeModel({
  signalBusinessId,
  subjectName,
  periodKey,
  canRunScenario,
  shock
}: {
  signalBusinessId: string;
  subjectName: string;
  periodKey: string;
  canRunScenario: boolean;
  shock: ShockState;
}): RiskShockBridgeModel {
  if (!canRunScenario || signalBusinessId !== shock.shockNodeId) {
    return {
      state: "unavailable",
      eyebrow: "Scenario access boundary",
      headline: "No scoped operational scenario for this signal",
      detail: "The selected account or risk subject does not have an available graph scenario for this period.",
      metrics: [],
      action: "none",
      actionLabel: "Scenario unavailable",
      disabled: true,
      guardrail
    };
  }

  if (!shock.active) {
    return {
      state: "ready",
      eyebrow: "Observed signal to hypothetical scenario",
      headline: "Test the network consequence of this signal",
      detail: `Run a hypothetical disruption at ${subjectName} for ${periodKey}. The model traces visible network relationships and calculates operational exposure.`,
      metrics: [
        { label: "Affected routes", value: "Trace" },
        { label: "Downstream SMEs", value: "Map" },
        { label: "Exposed volume", value: "Calculate" },
        { label: "Stockout window", value: "Estimate" }
      ],
      action: "run",
      actionLabel: "Run operational scenario",
      disabled: false,
      guardrail
    };
  }

  return {
    state: "live",
    eyebrow: "Operational scenario calculated",
    headline: `Exposure traced from ${subjectName}`,
    detail: `The ${periodKey} scenario follows visible downstream routes from the selected disruption point.`,
    metrics: [
      { label: "Affected routes", value: String(shock.affectedEdgeIds.length) },
      { label: "Downstream SMEs", value: String(shock.affectedSmeCount) },
      { label: "Exposed volume", value: `${compactNumber.format(shock.monthlyVolumeAtRisk)} units/mo` },
      { label: "Stockout window", value: `${shock.avgStockoutDays.toFixed(1)} days` }
    ],
    action: "open",
    actionLabel: "View live scenario",
    disabled: false,
    guardrail
  };
}
