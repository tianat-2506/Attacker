import type { DemoAccount } from "../types";

export interface DemoInvoiceCandidate {
  invoiceId: string;
  sellerId: string;
  buyerId: string;
}

export const demoInvoiceCandidates: DemoInvoiceCandidate[] = [
  { invoiceId: "INV-0242", sellerId: "BIZ-005", buyerId: "BIZ-009" },
  { invoiceId: "INV-0241", sellerId: "BIZ-002", buyerId: "BIZ-005" }
];

function isInvoiceParty(candidate: DemoInvoiceCandidate, organizationId: string) {
  return candidate.sellerId === organizationId || candidate.buyerId === organizationId;
}

export function invoiceIdForWorkspace(
  account: Pick<DemoAccount, "organizationId" | "actorRole" | "defaultBusinessId">,
  selectedBusinessId: string,
  candidates: DemoInvoiceCandidate[] = demoInvoiceCandidates
): string | null {
  const selectedMatches = candidates.filter((candidate) => isInvoiceParty(candidate, selectedBusinessId));
  const selectedAndOwned = selectedMatches.find((candidate) => isInvoiceParty(candidate, account.organizationId));
  if (selectedAndOwned) return selectedAndOwned.invoiceId;

  const selectedOutgoing = selectedMatches.find((candidate) => candidate.sellerId === selectedBusinessId);
  if (selectedOutgoing) return selectedOutgoing.invoiceId;
  if (selectedMatches[0]) return selectedMatches[0].invoiceId;

  const ownMatches = candidates.filter((candidate) => isInvoiceParty(candidate, account.organizationId));
  const ownOutgoing = ownMatches.find((candidate) => candidate.sellerId === account.organizationId);
  if (ownOutgoing) return ownOutgoing.invoiceId;
  return ownMatches[0]?.invoiceId ?? null;
}
