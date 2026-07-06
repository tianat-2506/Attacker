import type { DemoAccessDecision } from "../types";

export function canShowSensitiveCompanyData(decision: Pick<DemoAccessDecision, "status"> | null | undefined) {
  return Boolean(decision && ["owner", "consented", "ops_review"].includes(decision.status));
}

export function canRequestRiskSignal(decision: Pick<DemoAccessDecision, "status" | "allowedFields"> | null | undefined) {
  if (!decision) return false;
  if (["owner", "consented", "ops_review"].includes(decision.status)) return true;
  return decision.status === "masked" && decision.allowedFields.some((field) => field.toLowerCase().includes("risk"));
}

export function accessStatusLabel(status: DemoAccessDecision["status"]) {
  return status.replace(/_/g, " ");
}
