import type { ShockState } from "../types";

export type RiskShockBridgeState = "ready" | "result" | "unavailable";
export type RiskShockBridgeAction = "run" | "open" | "none";
export type RiskShockUnavailableReason = "graph_access_denied" | "shock_execution_denied" | "subject_not_supported";

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
  riskNotice: string;
  provenance: string | null;
  unavailableReason: RiskShockUnavailableReason | null;
}

const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const guardrail = "Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.";
const riskNotice = "Advisory risk signal. Not a credit assessment or legal/compliance breach determination. No supplier is selected or replaced automatically.";

function resultHasRequiredProvenance(shock: ShockState) {
  const hasRunContext = Boolean(shock.periodKey && shock.scenarioRunId && shock.rulesetVersion && shock.modelVersion && shock.resultSource);
  if (!hasRunContext) return false;
  if (shock.resultSource === "demo_fallback") return true;
  return Boolean(shock.policyDecisionId && shock.auditEventId);
}

export function shockResultMatchesContext(shock: ShockState, periodKey: string) {
  return shock.active && shock.periodKey === periodKey && resultHasRequiredProvenance(shock);
}

function unavailableModel(reason: RiskShockUnavailableReason): RiskShockBridgeModel {
  const copy = reason === "graph_access_denied"
    ? {
        headline: "Graph access is required for this scenario",
        detail: "This account can review the risk signal but cannot trace the commercial network graph."
      }
    : reason === "shock_execution_denied"
      ? {
          headline: "Scenario execution is not permitted",
          detail: "This account can read the graph but its policy capability does not allow a shock simulation."
        }
      : {
          headline: "No scoped operational scenario for this signal",
          detail: "The selected risk subject is outside the configured competition scenario."
        };

  return {
    state: "unavailable",
    eyebrow: "Scenario access boundary",
    headline: copy.headline,
    detail: copy.detail,
    metrics: [],
    action: "none",
    actionLabel: "Scenario unavailable",
    disabled: true,
    guardrail,
    riskNotice,
    provenance: null,
    unavailableReason: reason
  };
}

export function riskShockBridgeModel({
  signalBusinessId,
  subjectName,
  periodKey,
  canReadGraph,
  canRunShock,
  shock
}: {
  signalBusinessId: string;
  subjectName: string;
  periodKey: string;
  canReadGraph: boolean;
  canRunShock: boolean;
  shock: ShockState;
}): RiskShockBridgeModel {
  if (!canReadGraph) return unavailableModel("graph_access_denied");
  if (!canRunShock) return unavailableModel("shock_execution_denied");
  if (signalBusinessId !== shock.shockNodeId) return unavailableModel("subject_not_supported");

  const resultMatchesContext = shockResultMatchesContext(shock, periodKey);
  if (!resultMatchesContext) {
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
      guardrail,
      riskNotice,
      provenance: null,
      unavailableReason: null
    };
  }

  const isFallback = shock.resultSource === "demo_fallback";
  const provenance = [
    `run ${shock.scenarioRunId}`,
    `period ${shock.periodKey}`,
    `ruleset ${shock.rulesetVersion}`,
    `model ${shock.modelVersion}`,
    shock.policyDecisionId ? `policy ${shock.policyDecisionId}` : "policy demo fallback",
    shock.auditEventId ? `audit ${shock.auditEventId}` : "audit demo fallback"
  ].join(" / ");

  return {
    state: "result",
    eyebrow: isFallback ? "Synthetic fallback scenario result" : "Hypothetical scenario result",
    headline: `Scenario exposure traced from ${subjectName}`,
    detail: isFallback
      ? `A synthetic ${periodKey} fallback is shown because the backend result was unavailable.`
      : `The hypothetical ${periodKey} result follows visible downstream routes from the selected disruption point.`,
    metrics: [
      { label: "Affected routes", value: String(shock.affectedEdgeIds.length) },
      { label: "Downstream SMEs", value: String(shock.affectedSmeCount) },
      { label: "Exposed volume", value: `${compactNumber.format(shock.monthlyVolumeAtRisk)} units/mo` },
      { label: "Stockout window", value: `${shock.avgStockoutDays.toFixed(1)} days` }
    ],
    action: "open",
    actionLabel: "View scenario results",
    disabled: false,
    guardrail,
    riskNotice,
    provenance,
    unavailableReason: null
  };
}
