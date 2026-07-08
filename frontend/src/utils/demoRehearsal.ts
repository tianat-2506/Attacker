import type { AppView } from "../types";
import type { DemoStoryStepId } from "./demoStory";

export const OFFICIAL_DEMO_ROUTE = {
  accountId: "demo-operator",
  businessId: "BIZ-005",
  period: "2026-07",
  view: "overview" as AppView
};

export const BUYER_REHEARSAL_ROUTE = {
  accountId: "buyer-admin",
  businessId: "BIZ-005",
  period: "2026-07",
  view: "overview" as AppView
};

export const OFFICIAL_DEMO_URL = routeUrl(OFFICIAL_DEMO_ROUTE);
export const BUYER_REHEARSAL_URL = routeUrl(BUYER_REHEARSAL_ROUTE);

export const OFFICIAL_DEMO_FLOW: DemoStoryStepId[] = [
  "intake",
  "map_risk",
  "shock",
  "matching",
  "audit"
];

export const OFFICIAL_DEMO_FLOW_LABELS = [
  "Data Intake",
  "Supply Map + Risk",
  "Shock Simulation",
  "Recovery Matching",
  "Consent + Audit"
];

export function routeUrl(route: typeof OFFICIAL_DEMO_ROUTE) {
  const params = new URLSearchParams({
    view: route.view,
    account: route.accountId,
    business: route.businessId,
    period: route.period
  });
  return `http://127.0.0.1:5173/?${params.toString()}`;
}
