import type { AppView } from "../types";

function viewIs(activeView: AppView, allowedViews: readonly AppView[]) {
  return allowedViews.includes(activeView);
}

export function canLoadBusinessDetailForView(activeView: AppView, canReadBusiness: boolean, canReadSelectedBusiness: boolean) {
  return viewIs(activeView, ["map", "companies"]) && canReadBusiness && canReadSelectedBusiness;
}

export function canLoadGraphForView(activeView: AppView, canReadGraph: boolean) {
  return viewIs(activeView, ["overview", "map", "companies", "matching"]) && canReadGraph;
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

export function canLoadReviewQueueForView(activeView: AppView, canApproveDraft: boolean) {
  return activeView === "intake" && canApproveDraft;
}

export function canLoadRecommendationsForView(
  activeView: AppView,
  canReadRecommendations: boolean,
  shockActive = false,
  shockPeriodKey?: string | null,
  selectedPeriod?: string
) {
  if (!canReadRecommendations) return false;
  if (activeView === "matching") return true;
  return activeView === "overview"
    && shockActive
    && Boolean(shockPeriodKey && selectedPeriod && shockPeriodKey === selectedPeriod);
}

export function canLoadConnectionRequestsForView(activeView: AppView, canReadConnectionRequests: boolean) {
  return activeView === "onboarding" && canReadConnectionRequests;
}

export function canLoadSupplyMapRegistrationsForView(activeView: AppView, canCreateOnboarding: boolean, canReviewOnboarding: boolean) {
  return activeView === "onboarding" && (canCreateOnboarding || canReviewOnboarding);
}

export function canLoadAuditWorkspaceForView(activeView: AppView, canReadOps: boolean) {
  return activeView === "audit" && canReadOps;
}
