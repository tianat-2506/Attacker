import { describe, expect, it } from "vitest";
import type { FinanceData, Recommendation } from "../types";
import { financePeriodState, matchingPeriodNotice, recommendationPeriodLabel } from "./periodUi";

const business = {
  id: "BIZ-009",
  name: "Thu Duc Retail Mart",
  type: "retailer",
  province: "TP.HCM",
  category: "grocery",
  lat: 10.8,
  lng: 106.7,
  revenue: 1,
  capacity: 1,
  health: 80,
  risk: 20
} satisfies FinanceData["business"];

describe("period UI guardrails", () => {
  it("marks finance as missing selected-month data without treating history as the current snapshot", () => {
    const finance: FinanceData = {
      business,
      health: {
        score: 0,
        level: "no_period_data",
        components: {},
        formulaVersion: "demo",
        explanation: "No exact row."
      },
      latest: null,
      previous: null,
      series: [],
      advisoryNotice: "Financial indicators are management review signals only."
    };

    const state = financePeriodState(finance);

    expect(state.hasSelectedPeriodData).toBe(false);
    expect(state.statusLabel).toBe("no selected period row");
    expect(state.notice).toContain("does not silently use another month");
  });

  it("keeps matching empty-state wording review gated and period specific", () => {
    expect(matchingPeriodNotice([], "2026-09")).toContain("selected period 2026-09");
    expect(matchingPeriodNotice([], "2026-09")).toContain("no supplier replacement");
  });

  it("labels recommendation period from the API when available", () => {
    const recommendation = { supplierId: "BIZ-007", supplierName: "Supplier", score: 78, leadTimeDays: 3, reasons: [], components: {}, periodKey: "2026-07" } satisfies Recommendation;
    expect(recommendationPeriodLabel(recommendation, "2026-09")).toBe("2026-07");
  });
});
