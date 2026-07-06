import type { FinanceData, Recommendation } from "../types";

export function financePeriodState(finance: FinanceData) {
  const hasSelectedPeriodData = finance.health.level !== "no_period_data" && Boolean(finance.latest);
  return {
    hasSelectedPeriodData,
    statusLabel: hasSelectedPeriodData ? "selected period data" : "no selected period row",
    kpiNote: hasSelectedPeriodData ? `Selected month ${finance.latest?.month ?? "available"}` : "No exact row for selected month",
    chartNote: hasSelectedPeriodData
      ? "Trend rows are scoped to the selected organization."
      : "Trend rows remain historical context only; do not treat them as the selected month's snapshot.",
    notice: hasSelectedPeriodData
      ? finance.advisoryNotice
      : `${finance.advisoryNotice} No exact financial row exists for the selected month; the register below is historical context only and the app does not silently use another month as the current snapshot.`
  };
}

export function matchingPeriodNotice(recommendations: Recommendation[], selectedPeriod: string) {
  return recommendations[0]?.advisoryNotice
    ?? `No supplier shortlist is available for selected period ${selectedPeriod}; no supplier replacement, contact release or order commitment is triggered.`;
}

export function recommendationPeriodLabel(recommendation: Recommendation, selectedPeriod: string) {
  return recommendation.periodKey ?? selectedPeriod;
}
