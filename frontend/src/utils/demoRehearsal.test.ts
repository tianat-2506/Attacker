import { describe, expect, it } from "vitest";
import runbook from "../../../docs/21-competition-demo-runbook.md?raw";
import rehearsalHtml from "../../public/demo-rehearsal.html?raw";
import { getDemoAccountById } from "./demoAccounts";
import { demoStoryReadyCount, demoStorySteps } from "./demoStory";
import {
  BUYER_REHEARSAL_ROUTE,
  BUYER_REHEARSAL_URL,
  OFFICIAL_DEMO_FLOW,
  OFFICIAL_DEMO_FLOW_LABELS,
  OFFICIAL_DEMO_ROUTE,
  OFFICIAL_DEMO_URL
} from "./demoRehearsal";
import { readWorkspaceUrlState } from "./workspaceUrlState";
import type { AppView, ShockState } from "../types";

const validAccountIds = new Set(["demo-operator", "buyer-admin", "sme-submit"]);
const validViews = new Set<AppView>(["overview", "map", "companies", "intake", "onboarding", "risk", "matching", "finance", "invoice", "audit"]);
const rehearsalShock: ShockState = {
  active: false,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009"],
  affectedEdgeIds: ["EDGE-055"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 78000,
  revenueAtRisk: 1870000000,
  avgStockoutDays: 3.4
};

describe("competition demo rehearsal contract", () => {
  it("keeps official and buyer rehearsal URLs parseable by workspace URL state", () => {
    const official = readWorkspaceUrlState(new URL(OFFICIAL_DEMO_URL).search, validAccountIds, validViews);
    const buyer = readWorkspaceUrlState(new URL(BUYER_REHEARSAL_URL).search, validAccountIds, validViews);

    expect(official).toEqual(OFFICIAL_DEMO_ROUTE);
    expect(buyer).toEqual(BUYER_REHEARSAL_ROUTE);
  });

  it("keeps demo operator fully rehearsable and buyer admin intentionally scoped", () => {
    const operator = getDemoAccountById(OFFICIAL_DEMO_ROUTE.accountId);
    const buyer = getDemoAccountById(BUYER_REHEARSAL_ROUTE.accountId);
    const operatorSteps = demoStorySteps({
      shock: rehearsalShock,
      canOpenIntake: operator.allowedViews.includes("intake"),
      canOpenRisk: operator.allowedViews.includes("risk"),
      canOpenMatching: operator.allowedViews.includes("matching"),
      canOpenAudit: operator.allowedViews.includes("audit")
    });
    const buyerSteps = demoStorySteps({
      shock: rehearsalShock,
      canOpenIntake: buyer.allowedViews.includes("intake"),
      canOpenRisk: buyer.allowedViews.includes("risk"),
      canOpenMatching: buyer.allowedViews.includes("matching"),
      canOpenAudit: buyer.allowedViews.includes("audit")
    });

    expect(operatorSteps.map((step) => step.id)).toEqual(OFFICIAL_DEMO_FLOW);
    expect(demoStoryReadyCount(operatorSteps)).toBe(5);
    expect(buyerSteps.filter((step) => step.status === "blocked").map((step) => step.id)).toEqual(["intake", "audit"]);
  });

  it("keeps the Markdown runbook aligned with official route and flow labels", () => {
    expect(runbook).toContain(OFFICIAL_DEMO_URL);
    expect(runbook).toContain(BUYER_REHEARSAL_URL);
    expect(runbook).toContain("Main persona: `demo-operator`");
    for (const label of OFFICIAL_DEMO_FLOW_LABELS) {
      expect(runbook).toContain(label);
    }
  });

  it("keeps a rendered browser rehearsal page aligned with the official runbook", () => {
    expect(rehearsalHtml).toContain(OFFICIAL_DEMO_URL);
    expect(rehearsalHtml).toContain(BUYER_REHEARSAL_URL);
    expect(rehearsalHtml).toContain("Main persona: demo-operator");
    expect(rehearsalHtml).toContain("Decision-support only");
    for (const label of OFFICIAL_DEMO_FLOW_LABELS) {
      expect(rehearsalHtml).toContain(label);
    }
  });
});
