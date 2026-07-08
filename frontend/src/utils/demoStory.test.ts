import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import { demoStoryReadyCount, demoStorySteps } from "./demoStory";

const baseShock: ShockState = {
  active: false,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-055"],
  affectedSmeCount: 1,
  monthlyVolumeAtRisk: 9200,
  revenueAtRisk: 220800000,
  avgStockoutDays: 3.2
};

describe("demoStorySteps", () => {
  it("keeps the 3-5 minute demo flow ordered and ready before shock", () => {
    const steps = demoStorySteps({
      shock: baseShock,
      canOpenIntake: true,
      canOpenRisk: true,
      canOpenMatching: true,
      canOpenAudit: true
    });

    expect(steps.map((step) => step.id)).toEqual(["intake", "map_risk", "shock", "matching", "audit"]);
    expect(steps.find((step) => step.id === "shock")?.status).toBe("ready");
    expect(demoStoryReadyCount(steps)).toBe(5);
  });

  it("marks shock and matching active after the simulation runs", () => {
    const steps = demoStorySteps({
      shock: { ...baseShock, active: true },
      canOpenIntake: true,
      canOpenRisk: true,
      canOpenMatching: true,
      canOpenAudit: true
    });

    expect(steps.find((step) => step.id === "shock")?.status).toBe("active");
    expect(steps.find((step) => step.id === "matching")?.status).toBe("active");
    expect(steps.find((step) => step.id === "shock")?.detail).toContain("highlighted");
  });

  it("shows blocked story steps for scoped stakeholder accounts", () => {
    const steps = demoStorySteps({
      shock: baseShock,
      canOpenIntake: false,
      canOpenRisk: true,
      canOpenMatching: false,
      canOpenAudit: false
    });

    expect(steps.filter((step) => step.status === "blocked").map((step) => step.id)).toEqual([
      "intake",
      "matching",
      "audit"
    ]);
    expect(demoStoryReadyCount(steps)).toBe(2);
  });
});
