export function invoiceFundingStateLabel(status: string): string {
  const normalized = status.toLowerCase().replace(/[\s-]+/g, "_");
  if (normalized === "financed" || normalized === "funded") return "lender-recorded financed";
  if (normalized === "pledged") return "lender-recorded pledge";
  if (normalized === "verified" || normalized === "reviewed") return "reviewed registry signal";
  if (normalized === "registered") return "registered claim";
  if (normalized === "released") return "released by lender";
  if (normalized === "disputed") return "disputed claim";
  if (normalized === "unfunded" || normalized === "not_funded") return "no lender funding recorded";
  return normalized.replace(/_/g, " ");
}

export function invoiceFundingStateNotice(status: string): string {
  const normalized = status.toLowerCase().replace(/[\s-]+/g, "_");
  if (normalized === "financed" || normalized === "funded") return "Recorded by lender workflow; not VietSupply financing approval.";
  if (normalized === "pledged") return "Registry hold recorded by lender workflow.";
  if (normalized === "verified" || normalized === "reviewed") return "Review signal only; no funding decision.";
  return "Registry workflow state; no automatic financing decision.";
}

export function invoiceAssuranceReviewNotice(accessScope?: string | null): { title: string; detail: string; stateLabel: string } {
  const normalized = String(accessScope ?? "").toLowerCase().replace(/[\s-]+/g, "_");
  const partyScope = normalized === "buyer_party" || normalized === "seller_party";
  return {
    title: "Financial assurance review gate",
    detail: partyScope
      ? "Guarantee or collateral links require scan-cleared evidence, consented access and human review before use."
      : "Guarantee or collateral details remain policy-gated; no financing approval or enforceability is implied.",
    stateLabel: "policy gated"
  };
}
