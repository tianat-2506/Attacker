import { describe, expect, it } from "vitest";
import { accessStatusLabel, canRequestRiskSignal, canShowSensitiveCompanyData } from "../utils/accessDecision";
import {
  connectionRequestFilterLabel,
  connectionRequestIsActionable,
  connectionRequestMatchesFilter,
  connectionRequestPerspectiveLabel
} from "../utils/connectionRequests";
import { evidenceRecordStatus, evidenceStatusLabel, evidenceVerificationBucket, evidenceWorkflowLabel, evidenceWorkflowStatus } from "../utils/evidenceStatus";
import { invoiceFundingStateLabel, invoiceFundingStateNotice } from "../utils/invoiceStatus";
import type { ConnectionRequest, DemoAccount } from "../types";

describe("evidenceVerificationBucket", () => {
  it("does not treat unverified evidence as verified", () => {
    expect(evidenceVerificationBucket("UNVERIFIED")).toBe("PENDING");
    expect(evidenceVerificationBucket("NOT_VERIFIED")).toBe("PENDING");
    expect(evidenceVerificationBucket("PENDING_REVIEW")).toBe("PENDING");
  });

  it("groups clean/rejected scan statuses without legal overclaim", () => {
    expect(evidenceVerificationBucket("MALWARE_SCAN_CLEAN")).toBe("VERIFIED");
    expect(evidenceVerificationBucket("APPROVED_FOR_USE")).toBe("VERIFIED");
    expect(evidenceVerificationBucket("scan_failed")).toBe("REJECTED");
    expect(evidenceVerificationBucket("REVOKED")).toBe("REJECTED");
  });

  it("renders evidence labels as scan or review states instead of authenticity claims", () => {
    expect(evidenceStatusLabel("MALWARE_SCAN_CLEAN")).toBe("scan-cleared");
    expect(evidenceStatusLabel("APPROVED_FOR_USE")).toBe("review-cleared");
    expect(evidenceStatusLabel("VERIFIED")).toBe("reviewed");
    expect(evidenceWorkflowLabel("verified")).toBe("review-cleared");
  });

  it("summarizes evidence workflow status across vault and upload tickets", () => {
    expect(evidenceWorkflowStatus([])).toBe("missing");
    expect(evidenceWorkflowStatus(["pending_upload", "pending_scan"])).toBe("pending");
    expect(evidenceWorkflowStatus(["scan_failed", "pending_scan"])).toBe("rejected");
    expect(evidenceWorkflowStatus(["scan_failed", "clean"])).toBe("verified");
  });

  it("uses malware scan status for snapshot evidence and treats unknown status as pending", () => {
    expect(evidenceRecordStatus({ malware_scan_status: "clean" })).toBe("clean");
    expect(evidenceWorkflowStatus([evidenceRecordStatus({ malware_scan_status: "clean" })])).toBe("verified");
    expect(evidenceRecordStatus({ title: "Missing status" })).toBe("pending_scan");
    expect(evidenceWorkflowStatus([evidenceRecordStatus({ title: "Missing status" })])).toBe("pending");
  });
});

describe("access decision helpers", () => {
  it("keeps masked and pending-consent company data out of profile and vault detail", () => {
    expect(canShowSensitiveCompanyData({ status: "owner" })).toBe(true);
    expect(canShowSensitiveCompanyData({ status: "ops_review" })).toBe(true);
    expect(canShowSensitiveCompanyData({ status: "masked" })).toBe(false);
    expect(canShowSensitiveCompanyData({ status: "pending_consent" })).toBe(false);
  });

  it("allows masked high-level risk previews without opening sensitive company data", () => {
    expect(canRequestRiskSignal({ status: "masked", allowedFields: ["masked profile", "high-level risk signal"] })).toBe(true);
    expect(canRequestRiskSignal({ status: "masked", allowedFields: ["masked profile"] })).toBe(false);
    expect(canRequestRiskSignal({ status: "pending_consent", allowedFields: ["shortlist rationale"] })).toBe(false);
  });

  it("renders full access status labels instead of only the first underscore", () => {
    expect(accessStatusLabel("pending_consent")).toBe("pending consent");
    expect(accessStatusLabel("ops_review")).toBe("ops review");
  });
});

describe("invoice funding status labels", () => {
  it("describes financed states as lender-recorded workflow records", () => {
    expect(invoiceFundingStateLabel("financed")).toBe("lender-recorded financed");
    expect(invoiceFundingStateLabel("funded")).toBe("lender-recorded financed");
    expect(invoiceFundingStateNotice("financed")).toContain("not VietSupply financing approval");
  });

  it("keeps unfunded and reviewed states away from approval language", () => {
    expect(invoiceFundingStateLabel("unfunded")).toBe("no lender funding recorded");
    expect(invoiceFundingStateLabel("verified")).toBe("reviewed registry signal");
    expect(invoiceFundingStateNotice("verified")).toBe("Review signal only; no funding decision.");
  });
});

function demoAccount(role: DemoAccount["actorRole"], organizationId: string): DemoAccount {
  return {
    id: `${role}-${organizationId}`,
    personName: "Demo User",
    label: "Demo",
    stakeholder: role,
    organizationId,
    organizationName: organizationId,
    actorId: `${role}-actor`,
    actorRole: role,
    purpose: "demo",
    scopes: [],
    defaultBusinessId: organizationId,
    allowedViews: ["onboarding"],
    description: "test"
  };
}

function connectionRequest(status: string, consentStatus: string): ConnectionRequest {
  return {
    requestId: `REQ-${status}-${consentStatus}`,
    buyerId: "BIZ-009",
    targetSupplierId: "BIZ-007",
    disruptedSupplierId: "BIZ-005",
    status,
    consentStatus,
    requestedAt: "2026-07-01T00:00:00.000Z"
  };
}

describe("connection request filters", () => {
  it("marks supplier consent requests as actionable for the target supplier only", () => {
    const request = connectionRequest("pending", "awaiting_supplier_consent");
    expect(connectionRequestIsActionable(demoAccount("supplier_admin", "BIZ-007"), request, true)).toBe(true);
    expect(connectionRequestIsActionable(demoAccount("buyer_admin", "BIZ-009"), request, true)).toBe(false);
    expect(connectionRequestPerspectiveLabel(demoAccount("supplier_admin", "BIZ-007"), request)).toBe("supplier action");
  });

  it("marks supplier-consented requests as reviewer activation work", () => {
    const request = connectionRequest("pending", "supplier_consented");
    const reviewer = demoAccount("reviewer", "OPS");
    expect(connectionRequestIsActionable(reviewer, request, true)).toBe(true);
    expect(connectionRequestMatchesFilter("needs_action", request, reviewer, true)).toBe(true);
    expect(connectionRequestPerspectiveLabel(reviewer, request)).toBe("review queue");
  });

  it("separates open history from active and rejected connection outcomes", () => {
    const buyer = demoAccount("buyer_admin", "BIZ-009");
    expect(connectionRequestFilterLabel("needs_action")).toBe("action needed");
    expect(connectionRequestMatchesFilter("open", connectionRequest("pending", "awaiting_supplier_consent"), buyer, true)).toBe(true);
    expect(connectionRequestMatchesFilter("active", connectionRequest("relationship_active", "contract_evidence_recorded"), buyer, true)).toBe(true);
    expect(connectionRequestMatchesFilter("open", connectionRequest("relationship_active", "contract_evidence_recorded"), buyer, true)).toBe(false);
    expect(connectionRequestMatchesFilter("rejected", connectionRequest("rejected", "rejected"), buyer, true)).toBe(true);
  });
});
