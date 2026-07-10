import { describe, expect, it } from "vitest";
import type { Recommendation } from "../types";
import type { ShockState } from "../types";
import { recoveryPlaybook, shockSequenceSteps } from "./shockSequence";

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

const recoveryRecommendations: Recommendation[] = [
  {
    supplierId: "BIZ-007",
    supplierName: "An Phu FMCG Hub",
    score: 86,
    leadTimeDays: 2,
    reasons: ["capacity headroom"],
    components: { capacityFit: 92, reliability: 93 }
  },
  {
    supplierId: "BIZ-013",
    supplierName: "Gia Dinh Beverage Supply",
    score: 82,
    leadTimeDays: 1,
    reasons: ["near buyer"],
    components: { capacityFit: 88, reliability: 92 }
  },
  {
    supplierId: "BIZ-019",
    supplierName: "Trang Bom Beverage Link",
    score: 76,
    leadTimeDays: 2,
    reasons: ["split order"],
    components: { capacityFit: 73, reliability: 90 }
  }
];

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

  it("keeps recovery blocked until the cinematic recovery phase", () => {
    const propagating = shockSequenceSteps({
      shock: { ...baseShock, active: true },
      canOpenMatching: true,
      shockTargetName: "Dai Tin Distribution",
      presentationPhase: "propagation"
    });
    const recovered = shockSequenceSteps({
      shock: { ...baseShock, active: true },
      canOpenMatching: true,
      shockTargetName: "Dai Tin Distribution",
      presentationPhase: "recovery"
    });

    expect(propagating.find((step) => step.id === "disruption")?.metric).toBe("Tracing routes");
    expect(propagating.find((step) => step.id === "disruption")?.detail).not.toContain("78K units/month");
    expect(propagating.find((step) => step.id === "recovery")?.status).toBe("blocked");
    expect(recovered.find((step) => step.id === "recovery")?.status).toBe("ready");
  });

  it("turns live shock recommendations into a guarded recovery playbook", () => {
    const playbook = recoveryPlaybook({
      shock: { ...baseShock, active: true },
      recommendations: recoveryRecommendations
    });

    expect(playbook.status).toBe("ready");
    expect(playbook.primarySupplierName).toBe("An Phu FMCG Hub");
    expect(playbook.routeCount).toBe(3);
    expect(playbook.coveragePercent).toBe(81);
    expect(playbook.recoverableVolume).toBe(63440);
    expect(playbook.residualVolume).toBe(14560);
    expect(playbook.weightedLeadTimeDays).toBe(1.66);
    expect(playbook.guardrail).toContain("not an automatic supplier replacement");
  });

  it("keeps recovery playbook blocked until the shock and shortlist are both present", () => {
    const playbook = recoveryPlaybook({
      shock: baseShock,
      recommendations: recoveryRecommendations
    });

    expect(playbook.status).toBe("blocked");
    expect(playbook.routeCount).toBe(0);
    expect(playbook.recoverableVolume).toBe(0);
    expect(playbook.guardrail).toContain("Run shock simulation first");
  });
});
