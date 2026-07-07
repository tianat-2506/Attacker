import type { AppView } from "../types";

function viewIs(activeView: AppView, allowedViews: readonly AppView[]) {
  return allowedViews.includes(activeView);
}

export function canLoadBusinessDetailForView(activeView: AppView, canReadBusiness: boolean, canReadSelectedBusiness: boolean) {
  return viewIs(activeView, ["map", "companies"]) && canReadBusiness && canReadSelectedBusiness;
}

export function canLoadEvidenceVaultForView(activeView: AppView, canReadEvidence: boolean, canReadSelectedBusiness: boolean) {
  return viewIs(activeView, ["companies", "intake"]) && canReadEvidence && canReadSelectedBusiness;
}

export function canLoadRiskSignalForView(activeView: AppView, canReadRiskRun: boolean, canReadSelectedRisk: boolean) {
  return activeView === "risk" && canReadRiskRun && canReadSelectedRisk;
}

export function canLoadFinanceForView(activeView: AppView, canReadFinance: boolean, canReadSelectedBusiness: boolean) {
  return activeView === "finance" && canReadFinance && canReadSelectedBusiness;
}

export function canLoadIntakePeriodContextForView(activeView: AppView, canReadFinance: boolean, canReadSelectedBusiness: boolean) {
  return activeView === "intake" && canReadFinance && canReadSelectedBusiness;
}

export function canLoadRecommendationsForView(activeView: AppView, canReadRecommendations: boolean) {
  return activeView === "matching" && canReadRecommendations;
}

export function canLoadConnectionRequestsForView(activeView: AppView, canReadConnectionRequests: boolean) {
  return activeView === "onboarding" && canReadConnectionRequests;
}

export function canLoadAuditWorkspaceForView(activeView: AppView, canReadOps: boolean) {
  return activeView === "audit" && canReadOps;
}
