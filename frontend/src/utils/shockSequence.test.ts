import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import { shockSequenceSteps } from "./shockSequence";

const baseShock: ShockState = {
  active: false,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-055"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 78000,
  revenueAtRisk: 1870000000,
  avgStockoutDays: 3.4
};

describe("shockSequenceSteps", () => {
  it("shows before state and keeps recovery blocked before simulation", () => {
    const steps = shockSequenceSteps({
      shock: baseShock,
      canOpenMatching: true,
      shockTargetName: "Dai Tin Distribution"
    });

    expect(steps.map((step) => `${step.id}:${step.status}`)).toEqual([
      "baseline:active",
      "disruption:ready",
      "recovery:blocked"
    ]);
    expect(steps[1].detail).toContain("Run the shock");
  });

  it("switches to disruption impact and recovery readiness after shock runs", () => {
    const steps = shockSequenceSteps({
      shock: { ...baseShock, active: true },
      canOpenMatching: true,
      shockTargetName: "Dai Tin Distribution"
    });

    expect(steps.map((step) => `${step.id}:${step.status}`)).toEqual([
      "baseline:complete",
      "disruption:active",
      "recovery:ready"
    ]);
    expect(steps[1].metric).toBe("12 SMEs");
    expect(steps[1].detail).toContain("78K units/month");
    expect(steps[2].metric).toBe("Shortlist ready");
  });

  it("keeps recovery policy-gated when matching is unavailable", () => {
    const steps = shockSequenceSteps({
      shock: { ...baseShock, active: true },
      canOpenMatching: false,
      shockTargetName: "Dai Tin Distribution"
    });

    expect(steps[2].status).toBe("blocked");
    expect(steps[2].metric).toBe("Policy gated");
  });
});
