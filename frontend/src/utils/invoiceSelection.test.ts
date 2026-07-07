import { describe, expect, it } from "vitest";
import { demoAccounts } from "./demoAccounts";
import { demoInvoiceCandidates, demoInvoiceRecords } from "./demoInvoices";
import { invoiceIdForWorkspace } from "./invoiceSelection";

describe("invoiceIdForWorkspace", () => {
  it("uses the same demo invoice records for selection and fallback", () => {
    expect(demoInvoiceCandidates.map((item) => item.invoiceId).sort()).toEqual(demoInvoiceRecords.map((item) => item.invoiceId).sort());
  });

  it("uses the selected organization invoice instead of a fixed invoice id", () => {
    const demoOperator = demoAccounts.find((account) => account.id === "demo-operator")!;

    expect(invoiceIdForWorkspace(demoOperator, "BIZ-009")).toBe("INV-0242");
    expect(invoiceIdForWorkspace(demoOperator, "BIZ-002")).toBe("INV-0241");
  });

  it("prefers the selected outgoing invoice when one organization has multiple records", () => {
    const demoOperator = demoAccounts.find((account) => account.id === "demo-operator")!;

    expect(invoiceIdForWorkspace(demoOperator, "BIZ-005")).toBe("INV-0242");
  });

  it("falls back to the account party invoice when the selected business has no invoice", () => {
    const supplier = demoAccounts.find((account) => account.id === "supplier-admin")!;

    expect(invoiceIdForWorkspace(supplier, "BIZ-007")).toBe("INV-0242");
  });

  it("returns null when neither the account nor selected business maps to an invoice", () => {
    const lender = demoAccounts.find((account) => account.id === "lender")!;

    expect(invoiceIdForWorkspace(lender, "BIZ-007")).toBeNull();
  });
});
