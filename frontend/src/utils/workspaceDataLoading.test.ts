import { describe, expect, it } from "vitest";
import {
  canLoadBusinessDetailForView,
  canLoadConnectionRequestsForView,
  canLoadEvidenceVaultForView,
  canLoadFinanceForView,
  canLoadIntakePeriodContextForView,
  canLoadRecommendationsForView,
  canLoadRiskSignalForView
} from "./workspaceDataLoading";

describe("workspace data loading guardrails", () => {
  it("loads sensitive workspace data only for the active view that needs it", () => {
    expect(canLoadBusinessDetailForView("map", true, true)).toBe(true);
    expect(canLoadBusinessDetailForView("overview", true, true)).toBe(false);

    expect(canLoadEvidenceVaultForView("companies", true, true)).toBe(true);
    expect(canLoadEvidenceVaultForView("intake", true, true)).toBe(true);
    expect(canLoadEvidenceVaultForView("overview", true, true)).toBe(false);

    expect(canLoadRiskSignalForView("risk", true, true)).toBe(true);
    expect(canLoadRiskSignalForView("matching", true, true)).toBe(false);

    expect(canLoadFinanceForView("finance", true, true)).toBe(true);
    expect(canLoadFinanceForView("overview", true, true)).toBe(false);

    expect(canLoadIntakePeriodContextForView("intake", true, true)).toBe(true);
    expect(canLoadIntakePeriodContextForView("finance", true, true)).toBe(false);

    expect(canLoadRecommendationsForView("matching", true)).toBe(true);
    expect(canLoadRecommendationsForView("overview", true)).toBe(false);

    expect(canLoadConnectionRequestsForView("onboarding", true)).toBe(true);
    expect(canLoadConnectionRequestsForView("matching", true)).toBe(false);
  });

  it("keeps all loaders closed when role or subject scope is denied", () => {
    expect(canLoadBusinessDetailForView("companies", true, false)).toBe(false);
    expect(canLoadEvidenceVaultForView("companies", false, true)).toBe(false);
    expect(canLoadRiskSignalForView("risk", true, false)).toBe(false);
    expect(canLoadFinanceForView("finance", false, true)).toBe(false);
    expect(canLoadIntakePeriodContextForView("intake", true, false)).toBe(false);
    expect(canLoadRecommendationsForView("matching", false)).toBe(false);
    expect(canLoadConnectionRequestsForView("onboarding", false)).toBe(false);
  });
});
