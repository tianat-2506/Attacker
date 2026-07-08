export type IntakeProofItemId = "draft" | "csv" | "evidence" | "snapshot";
export type IntakeProofStatus = "complete" | "active" | "blocked" | "idle";

export interface IntakeProofItem {
  id: IntakeProofItemId;
  label: string;
  metric: string;
  detail: string;
  status: IntakeProofStatus;
  nextAction: string;
}

interface IntakeProofSubmission {
  source?: string | null;
  status?: string | null;
  version?: number | null;
  validationSummary?: { errors?: number; warnings?: number; infos?: number } | null;
}

interface IntakeProofBatch {
  rowCount?: number | null;
  status?: string | null;
  idempotentReplay?: boolean | null;
}

interface IntakeProofReviewTask {
  evidenceReview?: {
    clean?: number | null;
    pending?: number | null;
    rejected?: number | null;
    required?: boolean | null;
    approvalBlocked?: boolean | null;
  } | null;
}

interface IntakeProofSnapshot {
  approvedVersion?: number | null;
  sourceSubmissionIds?: string[] | null;
  financials?: unknown[] | null;
  products?: unknown[] | null;
  evidence?: unknown[] | null;
}

function scanBucket(status?: string | null) {
  const normalized = String(status ?? "").toLowerCase();
  if (["clean", "malware_scan_clean", "approved_for_use", "verified"].includes(normalized)) return "clean";
  if (["infected", "failed", "scan_failed", "rejected", "revoked"].includes(normalized)) return "rejected";
  if (normalized) return "pending";
  return "missing";
}

export function intakeProofChecklist({
  submission,
  importBatch,
  pendingEvidenceUploads = [],
  snapshot,
  selectedReviewTask
}: {
  submission?: IntakeProofSubmission | null;
  importBatch?: IntakeProofBatch | null;
  pendingEvidenceUploads?: Array<{ malwareScanStatus?: string | null }>;
  snapshot?: IntakeProofSnapshot | null;
  selectedReviewTask?: IntakeProofReviewTask | null;
}): IntakeProofItem[] {
  const validationErrors = submission?.validationSummary?.errors ?? 0;
  const rowCount = importBatch?.rowCount ?? 0;
  const csvBlocked = Boolean(importBatch) && (importBatch?.status === "quarantined" || validationErrors > 0);
  const evidenceReview = selectedReviewTask?.evidenceReview;
  const uploadBuckets = pendingEvidenceUploads.map((item) => scanBucket(item.malwareScanStatus));
  const cleanEvidence = evidenceReview?.clean ?? uploadBuckets.filter((status) => status === "clean").length;
  const rejectedEvidence = evidenceReview?.rejected ?? uploadBuckets.filter((status) => status === "rejected").length;
  const pendingEvidence = evidenceReview?.pending ?? uploadBuckets.filter((status) => status === "pending" || status === "missing").length;
  const evidenceRequired = Boolean(evidenceReview?.required || pendingEvidenceUploads.length);
  const evidenceBlocked = Boolean(evidenceReview?.approvalBlocked || rejectedEvidence > 0 || (evidenceRequired && pendingEvidence > 0 && submission?.status === "in_review"));
  const approvedVersion = snapshot?.approvedVersion ?? null;
  const canonicalRows = (snapshot?.financials?.length ?? 0) + (snapshot?.products?.length ?? 0) + (snapshot?.evidence?.length ?? 0);
  const sourceRefs = snapshot?.sourceSubmissionIds?.length ?? 0;
  const isApproved = Boolean(approvedVersion);
  const submissionStatus = submission?.status ?? "";
  const inReview = ["submitted", "in_review"].includes(submissionStatus);
  const draftEditable = ["draft", "ready", "changes_requested"].includes(submissionStatus);
  const evidenceNextAction = !evidenceRequired
    ? "Upload evidence"
    : evidenceBlocked
      ? "Clear evidence gate"
      : pendingEvidence > 0
        ? "Run demo scan"
        : cleanEvidence > 0 && draftEditable
          ? "Submit for review"
          : cleanEvidence > 0 && inReview
            ? "Await reviewer"
            : "Evidence ready";
  const snapshotNextAction = isApproved
    ? "Use approved snapshot"
    : inReview && !evidenceBlocked && validationErrors === 0
      ? "Approve snapshot"
      : inReview
        ? "Resolve review gate"
        : submission
          ? "Submit for review"
          : "Create draft";

  return [
    {
      id: "draft",
      label: "Draft package",
      metric: submission ? `${submission.source ?? "manual"} v${submission.version ?? 0}` : "create draft",
      detail: submission
        ? `Current intake status is ${submission.status ?? "draft"} with ${validationErrors} validation error${validationErrors === 1 ? "" : "s"}.`
        : "Start by creating a monthly draft for form, CSV and evidence inputs.",
      status: isApproved ? "complete" : submission ? "active" : "active",
      nextAction: submission ? validationErrors > 0 ? "Fix validation" : "Validate draft" : "Create draft"
    },
    {
      id: "csv",
      label: "CSV proof",
      metric: importBatch ? (csvBlocked ? `${validationErrors} errors / ${rowCount} rows` : `${rowCount} rows`) : "optional",
      detail: importBatch
        ? csvBlocked
          ? "CSV batch is quarantined until validation issues are fixed."
          : `CSV preview and checksum captured as ${importBatch.idempotentReplay ? "idempotent replay" : "new batch"}.`
        : "Manual form can proceed, but CSV import demonstrates replayable raw rows.",
      status: importBatch ? (csvBlocked ? "blocked" : "complete") : "idle",
      nextAction: importBatch ? (csvBlocked ? "Export errors" : "Preview accepted") : "Parse CSV"
    },
    {
      id: "evidence",
      label: "Evidence gate",
      metric: evidenceRequired ? `${cleanEvidence} clean / ${pendingEvidence} pending` : "no ticket",
      detail: evidenceRequired
        ? evidenceBlocked
          ? "Approval waits for scan-clear evidence status; this is not document authenticity or finance approval."
          : `${cleanEvidence} evidence item${cleanEvidence === 1 ? "" : "s"} are scan-clear for review-gated use.`
        : "Upload ticket and malware scan prove supporting documents before approval.",
      status: evidenceRequired ? (evidenceBlocked ? "blocked" : cleanEvidence > 0 && pendingEvidence === 0 ? "complete" : "active") : "idle",
      nextAction: evidenceNextAction
    },
    {
      id: "snapshot",
      label: "Approved snapshot",
      metric: isApproved ? `approved v${approvedVersion}` : inReview ? "reviewing" : "not approved",
      detail: isApproved
        ? `${canonicalRows} canonical rows linked to ${sourceRefs} source ref${sourceRefs === 1 ? "" : "s"}.`
        : "No approved snapshot for this period until a reviewer records approval.",
      status: isApproved ? "complete" : inReview ? "active" : "blocked",
      nextAction: snapshotNextAction
    }
  ];
}
