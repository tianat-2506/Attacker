import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import { riskShockBridgeModel, shockResultMatchesContext } from "./riskShockBridge";

const shock: ShockState = {
  active: false,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-055", "EDGE-056"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 199060,
  revenueAtRisk: 4800000000,
  avgStockoutDays: 3.8,
  periodKey: "2026-07",
  scenarioRunId: "SCN-001",
  rulesetVersion: "shock-rules-v1.0",
  modelVersion: "deterministic-adjacency-v1.0",
  policyDecisionId: "POL-SHOCK-001",
  auditEventId: "AUD-SHOCK-001",
  resultSource: "current_demo_graph"
};

function model(overrides: Partial<Parameters<typeof riskShockBridgeModel>[0]> = {}) {
  return riskShockBridgeModel({
    signalBusinessId: "BIZ-005",
    subjectName: "Dai Tin Distribution",
    periodKey: "2026-07",
    canReadGraph: true,
    canRunShock: true,
    shock,
    ...overrides
  });
}

describe("riskShockBridgeModel", () => {
  it("scopes reusable shock results to complete provenance for the selected period", () => {
    expect(shockResultMatchesContext({ ...shock, active: true }, "2026-07")).toBe(true);
    expect(shockResultMatchesContext({ ...shock, active: true }, "2026-08")).toBe(false);
    expect(shockResultMatchesContext({ ...shock, active: true, auditEventId: null }, "2026-07")).toBe(false);
  });

  it("keeps seeded impact values hidden before a scenario runs", () => {
    const bridge = model();

    expect(bridge.state).toBe("ready");
    expect(bridge.action).toBe("run");
    expect(bridge.metrics.map((metric) => metric.value)).toEqual(["Trace", "Map", "Calculate", "Estimate"]);
    expect(JSON.stringify(bridge)).not.toContain("199");
  });

  it("shows only returned impact values for a provenance-matched scenario result", () => {
    const bridge = model({ shock: { ...shock, active: true } });

    expect(bridge.state).toBe("result");
    expect(bridge.action).toBe("open");
    expect(bridge.actionLabel).toBe("View scenario results");
    expect(bridge.metrics.map((metric) => metric.value)).toEqual(["2", "12", "199.1K units/mo", "3.8 days"]);
    expect(bridge.provenance).toContain("SCN-001");
    expect(bridge.provenance).toContain("POL-SHOCK-001");
  });

  it("does not reuse a result after the reporting period changes", () => {
    const bridge = model({ periodKey: "2026-08", shock: { ...shock, active: true } });

    expect(bridge.state).toBe("ready");
    expect(bridge.action).toBe("run");
    expect(JSON.stringify(bridge)).not.toContain("199.1K");
  });

  it("does not expose an API result with incomplete policy provenance", () => {
    const bridge = model({ shock: { ...shock, active: true, policyDecisionId: null } });

    expect(bridge.state).toBe("ready");
    expect(bridge.action).toBe("run");
  });

  it("separates graph access, shock execution permission and unsupported subjects", () => {
    expect(model({ canReadGraph: false }).unavailableReason).toBe("graph_access_denied");
    expect(model({ canRunShock: false }).unavailableReason).toBe("shock_execution_denied");
    expect(model({ signalBusinessId: "BIZ-013" }).unavailableReason).toBe("subject_not_supported");
  });

  it("labels a complete demo fallback result instead of presenting it as an API result", () => {
    const bridge = model({
      shock: {
        ...shock,
        active: true,
        policyDecisionId: null,
        auditEventId: null,
        resultSource: "demo_fallback"
      }
    });

    expect(bridge.state).toBe("result");
    expect(bridge.eyebrow).toBe("Synthetic fallback scenario result");
    expect(bridge.detail).toContain("backend result was unavailable");
  });

  it("keeps the scenario wording inside product and legal boundaries", () => {
    const bridge = model();

    expect(bridge.guardrail).toBe("Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.");
    expect(bridge.riskNotice).toBe("Advisory risk signal. Not a credit assessment or legal/compliance breach determination. No supplier is selected or replaced automatically.");
    expect(`${bridge.headline} ${bridge.detail}`.toLowerCase()).not.toContain("probability");
  });
});
