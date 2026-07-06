import { describe, expect, it } from "vitest";
import { readWorkspaceUrlState, workspaceSearchWithState } from "./workspaceUrlState";
import type { AppView } from "../types";

const validAccounts = new Set(["buyer-009", "supplier-007"]);
const validViews = new Set<AppView>(["overview", "companies", "intake", "onboarding"]);

describe("workspace URL state", () => {
  it("reads valid account, business, period and view from query params", () => {
    expect(readWorkspaceUrlState("?account=buyer-009&business=BIZ-009&period=2026-07&view=intake", validAccounts, validViews)).toEqual({
      accountId: "buyer-009",
      businessId: "BIZ-009",
      period: "2026-07",
      view: "intake"
    });
  });

  it("drops invalid account, period and view while keeping business context", () => {
    expect(readWorkspaceUrlState("?account=unknown&business=BIZ-007&period=202607&view=audit", validAccounts, validViews)).toEqual({
      accountId: undefined,
      businessId: "BIZ-007",
      period: undefined,
      view: undefined
    });
  });

  it("serializes workspace state without deleting unrelated query params", () => {
    expect(workspaceSearchWithState("?debug=true&period=2026-01", {
      accountId: "supplier-007",
      businessId: "BIZ-007",
      period: "2026-08",
      view: "onboarding"
    })).toBe("?debug=true&period=2026-08&account=supplier-007&business=BIZ-007&view=onboarding");
  });
});
