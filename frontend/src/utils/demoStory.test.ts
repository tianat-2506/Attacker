import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import { getDemoAccountById } from "./demoAccounts";
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
  function stepsForAccount(accountId: string, shock: ShockState = baseShock) {
    const account = getDemoAccountById(accountId);
    return demoStorySteps({
      shock,
      canOpenIntake: account.allowedViews.includes("intake"),
      canOpenRisk: account.allowedViews.includes("risk"),
      canOpenMatching: account.allowedViews.includes("matching"),
      canOpenAudit: account.allowedViews.includes("audit")
    });
  }

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

  it("keeps the official demo operator path fully live for competition rehearsal", () => {
    const steps = stepsForAccount("demo-operator");

    expect(demoStoryReadyCount(steps)).toBe(5);
    expect(steps.every((step) => step.status !== "blocked")).toBe(true);
    expect(steps.map((step) => `${step.order}:${step.id}`)).toEqual([
      "0:00:intake",
      "0:45:map_risk",
      "1:45:shock",
      "2:30:matching",
      "3:30:audit"
    ]);
  });

  it("keeps the buyer admin path intentionally scoped so blocked steps prove RBAC", () => {
    const steps = stepsForAccount("buyer-admin");

    expect(steps.filter((step) => step.status === "blocked").map((step) => step.id)).toEqual([
      "intake",
      "audit"
    ]);
    expect(demoStoryReadyCount(steps)).toBe(3);
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
