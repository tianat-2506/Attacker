import { describe, expect, it } from "vitest";
import type { ShockState } from "../types";
import {
  isShockPhaseVisible,
  phaseAtElapsedMs,
  shockEdgeVisualClass,
  shockNodeVisualClass,
  shockPhaseCopy
} from "./shockPresentation";

const shock: ShockState = {
  active: true,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-1"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 199100,
  revenueAtRisk: 4800000000,
  avgStockoutDays: 0.9
};

describe("shock presentation", () => {
  it("advances through the deterministic phases", () => {
    expect(phaseAtElapsedMs(false, 9999)).toBe("baseline");
    expect(phaseAtElapsedMs(true, 0)).toBe("origin");
    expect(phaseAtElapsedMs(true, 549)).toBe("origin");
    expect(phaseAtElapsedMs(true, 550)).toBe("propagation");
    expect(phaseAtElapsedMs(true, 1400)).toBe("impact");
    expect(phaseAtElapsedMs(true, 2200)).toBe("recovery");
    expect(phaseAtElapsedMs(true, 0, true)).toBe("recovery");
  });

  it("gates impact and recovery until their phases", () => {
    expect(isShockPhaseVisible("propagation", "impact")).toBe(false);
    expect(isShockPhaseVisible("impact", "impact")).toBe(true);
    expect(isShockPhaseVisible("impact", "recovery")).toBe(false);
    expect(isShockPhaseVisible("recovery", "recovery")).toBe(true);
  });

  it("assigns semantic map classes only when their phase is visible", () => {
    expect(shockNodeVisualClass("BIZ-005", shock, "origin")).toContain("shock-node-origin");
    expect(shockNodeVisualClass("BIZ-009", shock, "origin")).toBe("");
    expect(shockNodeVisualClass("BIZ-009", shock, "propagation")).toContain("shock-node-affected");
    expect(shockEdgeVisualClass("EDGE-1", 2, shock, "propagation")).toBe("shock-edge-impacted shock-edge-delay-2");
    expect(shockEdgeVisualClass("EDGE-2", 0, shock, "recovery")).toBe("");
  });

  it("turns returned facts into concise phase copy", () => {
    expect(shockPhaseCopy("origin", shock).metric).toContain("BIZ-005");
    expect(shockPhaseCopy("propagation", shock).metric).toContain("1 routes");
    expect(shockPhaseCopy("impact", shock).metric).toContain("12 SMEs");
    expect(shockPhaseCopy("recovery", shock).label).toBe("Recovery ready");
  });
});
