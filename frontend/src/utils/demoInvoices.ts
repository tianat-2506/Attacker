import type { InvoiceVerificationData } from "../types";

export type DemoInvoiceCandidate = Pick<InvoiceVerificationData, "invoiceId" | "sellerId" | "buyerId">;

export const demoInvoiceRecords: InvoiceVerificationData[] = [
  {
    invoiceId: "INV-0241",
    sellerId: "BIZ-002",
    buyerId: "BIZ-005",
    amount: 240_000_000,
    issueDate: "2026-06-05",
    dueDate: "2026-07-05",
    storedHash: "0f9323ce77ce8c5f3f3d807a59f5ab48",
    computedHash: "0f9323ce77ce8c5f3f3d807a59f5ab48",
    fundingStatus: "funded",
    confirmedBy: ["buyer", "seller"],
    doubleFinancingAlert: false,
    accessScope: "synthetic_fallback",
    dataScope: "restricted_financial",
    advisoryNotice: "Synthetic invoice registry signal; lender/human review remains required."
  },
  {
    invoiceId: "INV-0242",
    sellerId: "BIZ-005",
    buyerId: "BIZ-009",
    amount: 68_000_000,
    issueDate: "2026-06-08",
    dueDate: "2026-07-08",
    storedHash: "7b42ef8490a3d869c0ca0e8ec8d95c87",
    computedHash: "7b42ef8490a3d869c0ca0e8ec8d95c87",
    fundingStatus: "unfunded",
    confirmedBy: ["buyer", "seller"],
    doubleFinancingAlert: false,
    accessScope: "synthetic_fallback",
    dataScope: "restricted_financial",
    advisoryNotice: "Synthetic invoice registry signal; lender/human review remains required."
  }
];

export const demoInvoiceCandidates: DemoInvoiceCandidate[] = demoInvoiceRecords.map(({ invoiceId, sellerId, buyerId }) => ({
  invoiceId,
  sellerId,
  buyerId
}));

export function demoInvoiceFallbackById(invoiceId: string): InvoiceVerificationData | null {
  const record = demoInvoiceRecords.find((item) => item.invoiceId === invoiceId);
  return record ? { ...record, confirmedBy: [...record.confirmedBy] } : null;
}
