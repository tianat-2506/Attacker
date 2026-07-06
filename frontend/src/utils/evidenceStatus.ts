export type EvidenceVerificationBucket = "VERIFIED" | "PENDING" | "REJECTED";
export type EvidenceWorkflowStatus = "verified" | "pending" | "rejected" | "missing";

export function evidenceVerificationBucket(status: string): EvidenceVerificationBucket {
  const normalized = status.toLowerCase().replace(/[\s-]+/g, "_");
  if (normalized.includes("unverified") || normalized.includes("not_verified")) return "PENDING";
  if (["verified", "clean", "approved"].some((token) => normalized === token || normalized.includes(`_${token}`) || normalized.includes(`${token}_`))) return "VERIFIED";
  if (normalized.includes("reject") || normalized.includes("fail") || normalized.includes("revoked")) return "REJECTED";
  return "PENDING";
}

export function evidenceWorkflowStatus(statuses: Array<string | null | undefined>): EvidenceWorkflowStatus {
  const normalized = statuses.filter((status): status is string => Boolean(status));
  if (!normalized.length) return "missing";
  const buckets = normalized.map(evidenceVerificationBucket);
  if (buckets.includes("VERIFIED")) return "verified";
  if (buckets.includes("REJECTED")) return "rejected";
  return "pending";
}

export function evidenceRecordStatus(row: Record<string, unknown>): string {
  const status = row.verification_status
    ?? row.verificationStatus
    ?? row.status
    ?? row.malware_scan_status
    ?? row.malwareScanStatus;
  return typeof status === "string" && status.trim() ? status : "pending_scan";
}

export function evidenceStatusLabel(status: string): string {
  const normalized = status.toLowerCase().replace(/[\s-]+/g, "_");
  const bucket = evidenceVerificationBucket(status);
  if (bucket === "REJECTED") {
    if (normalized.includes("infect")) return "scan flagged";
    if (normalized.includes("scan")) return "scan failed";
    return "rejected";
  }
  if (bucket === "PENDING") {
    if (normalized.includes("upload")) return "upload pending";
    if (normalized.includes("scan")) return "scan pending";
    if (normalized.includes("review")) return "review pending";
    return "pending";
  }
  if (normalized.includes("clean") || normalized.includes("malware_scan_clean")) return "scan-cleared";
  if (normalized.includes("approved")) return "review-cleared";
  return "reviewed";
}

export function evidenceWorkflowLabel(status: EvidenceWorkflowStatus): string {
  if (status === "verified") return "review-cleared";
  if (status === "pending") return "pending";
  if (status === "rejected") return "rejected";
  return "missing";
}
