import { describe, expect, it } from "vitest";
import { auditWorkspaceContextMatches, auditWorkspaceState } from "./auditWorkspaceState";

describe("auditWorkspaceState", () => {
  it("keeps ops registry visible when the audit event source is unavailable", () => {
    expect(auditWorkspaceState(true, false, true)).toEqual({
      loading: false,
      auditUnavailable: true,
      opsUnavailable: false
    });
  });

  it("loads only before the workspace request has resolved", () => {
    expect(auditWorkspaceState(false, false, false)).toEqual({
      loading: true,
      auditUnavailable: false,
      opsUnavailable: false
    });
  });

  it("shows both sources as unavailable after a fully failed request", () => {
    expect(auditWorkspaceState(true, false, false)).toEqual({
      loading: false,
      auditUnavailable: true,
      opsUnavailable: true
    });
  });

  it("rejects payload resolved for a previous actor or business context", () => {
    expect(auditWorkspaceContextMatches("demo-operator:BIZ-005", "buyer-admin", "BIZ-005")).toBe(false);
    expect(auditWorkspaceContextMatches("demo-operator:BIZ-005", "demo-operator", "BIZ-009")).toBe(false);
    expect(auditWorkspaceContextMatches("demo-operator:BIZ-005", "demo-operator", "BIZ-005")).toBe(true);
  });

  it("rejects cached payload when the current actor loses ops permission", () => {
    expect(auditWorkspaceContextMatches("demo-operator:BIZ-005", "demo-operator", "BIZ-005", false)).toBe(false);
  });
});
