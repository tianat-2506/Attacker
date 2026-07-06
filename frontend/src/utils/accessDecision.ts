import type { DemoAccessDecision, Recommendation } from "../types";

export function canShowSensitiveCompanyData(decision: Pick<DemoAccessDecision, "status"> | null | undefined) {
  return Boolean(decision && ["owner", "consented", "ops_review"].includes(decision.status));
}

export function canRequestRiskSignal(decision: Pick<DemoAccessDecision, "status" | "allowedFields"> | null | undefined) {
  if (!decision) return false;
  if (["owner", "consented", "ops_review"].includes(decision.status)) return true;
  return decision.status === "masked" && decision.allowedFields.some((field) => field.toLowerCase().includes("risk"));
}

function publicRecommendationComponent(label: string) {
  const normalized = label.replace(/[^a-z]/gi, "").toLowerCase();
  return normalized.includes("product") || normalized.includes("distance");
}

export function recommendationComponentsForAccess(components: Recommendation["components"], decision: Pick<DemoAccessDecision, "status"> | null | undefined) {
  const entries = Object.entries(components);
  if (canShowSensitiveCompanyData(decision)) return entries;
  return entries.filter(([label]) => publicRecommendationComponent(label));
}

export function restrictedRecommendationComponentCount(components: Recommendation["components"], decision: Pick<DemoAccessDecision, "status"> | null | undefined) {
  return Math.max(0, Object.keys(components).length - recommendationComponentsForAccess(components, decision).length);
}

function sensitiveRecommendationReason(reason: string) {
  const normalized = reason.toLowerCase();
  return ["capacity", "reliability", "health", "payment", "term", "net-", "score", "risk", "financial", "gia"].some((token) => normalized.includes(token));
}

export function recommendationReasonsForAccess(reasons: Recommendation["reasons"], decision: Pick<DemoAccessDecision, "status"> | null | undefined) {
  if (canShowSensitiveCompanyData(decision)) return reasons;
  return reasons.filter((reason) => !sensitiveRecommendationReason(reason));
}

export function restrictedRecommendationReasonCount(reasons: Recommendation["reasons"], decision: Pick<DemoAccessDecision, "status"> | null | undefined) {
  return Math.max(0, reasons.length - recommendationReasonsForAccess(reasons, decision).length);
}

export function accessStatusLabel(status: DemoAccessDecision["status"]) {
  return status.replace(/_/g, " ");
}
