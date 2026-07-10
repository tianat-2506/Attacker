import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import { riskShockBridgeModel } from "./riskShockBridge";

const shock: ShockState = {
  active: false,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-055", "EDGE-056"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 199060,
  revenueAtRisk: 4800000000,
  avgStockoutDays: 3.8
};

function model(overrides: Partial<Parameters<typeof riskShockBridgeModel>[0]> = {}) {
  return riskShockBridgeModel({
    signalBusinessId: "BIZ-005",
    subjectName: "Dai Tin Distribution",
    periodKey: "2026-07",
    canRunScenario: true,
    shock,
    ...overrides
  });
}

describe("riskShockBridgeModel", () => {
  it("keeps seeded impact values hidden before a scenario runs", () => {
    const bridge = model();

    expect(bridge.state).toBe("ready");
    expect(bridge.action).toBe("run");
    expect(bridge.metrics.map((metric) => metric.value)).toEqual(["Trace", "Map", "Calculate", "Estimate"]);
    expect(JSON.stringify(bridge)).not.toContain("199");
  });

  it("shows only returned impact values for a live matching scenario", () => {
    const bridge = model({ shock: { ...shock, active: true } });

    expect(bridge.state).toBe("live");
    expect(bridge.action).toBe("open");
    expect(bridge.metrics.map((metric) => metric.value)).toEqual(["2", "12", "199.1K units/mo", "3.8 days"]);
  });

  it("blocks mismatched subjects and denied graph access", () => {
    expect(model({ signalBusinessId: "BIZ-013" }).action).toBe("none");
    expect(model({ canRunScenario: false }).disabled).toBe(true);
  });

  it("keeps the scenario wording inside product and legal boundaries", () => {
    const bridge = model();

    expect(bridge.guardrail).toBe("Hypothetical decision-support scenario. Not a forecast, legal finding, or supplier replacement instruction.");
    expect(`${bridge.headline} ${bridge.detail}`.toLowerCase()).not.toContain("probability");
  });
});
