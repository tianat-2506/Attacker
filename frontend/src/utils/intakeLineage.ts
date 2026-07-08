export type IntakeLineageStepId = "raw" | "staging" | "review" | "canonical";
export type IntakeLineageStatus = "complete" | "active" | "ready" | "blocked";

export interface IntakeLineageStep {
  id: IntakeLineageStepId;
  label: string;
  metric: string;
  detail: string;
  status: IntakeLineageStatus;
}

interface IntakeLineageSubmission {
  source?: string | null;
  status?: string | null;
  version?: number | null;
  validationSummary?: { errors?: number; warnings?: number; infos?: number } | null;
  reviewTask?: { id?: string; assignedTo?: string | null } | null;
}

interface IntakeLineageBatch {
  rowCount?: number | null;
  status?: string | null;
  fileName?: string | null;
  idempotentReplay?: boolean | null;
}

interface IntakeLineageSnapshot {
  approvedVersion?: number | null;
  sourceSubmissionIds?: string[] | null;
  latestSubmissionStatus?: string | null;
  financials?: unknown[] | null;
  products?: unknown[] | null;
  evidence?: unknown[] | null;
}

interface IntakeLineageReviewTask {
  assignedTo?: string | null;
  evidenceReview?: {
    clean?: number;
    pending?: number;
    rejected?: number;
    approvalBlocked?: boolean;
  } | null;
}

export function intakeLineageSteps({
  submission,
  importBatch,
  pendingEvidenceUploads = [],
  snapshot,
  selectedReviewTask
}: {
  submission?: IntakeLineageSubmission | null;
  importBatch?: IntakeLineageBatch | null;
  pendingEvidenceUploads?: Array<{ id?: string; malwareScanStatus?: string | null }>;
  snapshot?: IntakeLineageSnapshot | null;
  selectedReviewTask?: IntakeLineageReviewTask | null;
}): IntakeLineageStep[] {
  const submissionStatus = submission?.status ?? snapshot?.latestSubmissionStatus ?? null;
  const hasSubmission = Boolean(submission);
  const hasCsv = Boolean(importBatch);
  const hasEvidenceTickets = pendingEvidenceUploads.length > 0;
  const hasRawInput = hasSubmission || hasCsv || hasEvidenceTickets;
  const validationErrors = submission?.validationSummary?.errors ?? 0;
  const validationWarnings = submission?.validationSummary?.warnings ?? 0;
  const approvedVersion = snapshot?.approvedVersion ?? null;
  const isApproved = Boolean(approvedVersion);
  const reviewTask = selectedReviewTask ?? submission?.reviewTask ?? null;
  const reviewActive = Boolean(reviewTask) || ["submitted", "in_review"].includes(submissionStatus ?? "");
  const sourceCount = snapshot?.sourceSubmissionIds?.length ?? 0;
  const canonicalRows = (snapshot?.financials?.length ?? 0) + (snapshot?.products?.length ?? 0) + (snapshot?.evidence?.length ?? 0);

  return [
    {
      id: "raw",
      label: "Raw input",
      metric: hasCsv
        ? `${importBatch?.rowCount ?? 0} CSV rows`
        : hasSubmission
          ? `${submission?.source ?? "manual"} v${submission?.version ?? 0}`
          : hasEvidenceTickets
            ? `${pendingEvidenceUploads.length} evidence tickets`
            : "waiting",
      detail: "Manual form, CSV rows and evidence tickets are captured before canonical use.",
      status: hasRawInput ? "complete" : "active"
    },
    {
      id: "staging",
      label: "Staging validation",
      metric: validationErrors > 0 || importBatch?.status === "quarantined"
        ? "quarantined"
        : hasSubmission
          ? `${validationErrors} errors / ${validationWarnings} warnings`
          : "not started",
      detail: validationErrors > 0 || importBatch?.status === "quarantined"
        ? "Fix validation issues before review or approved materialization."
        : "Typed payloads are validated before review and replay.",
      status: !hasRawInput ? "blocked" : validationErrors > 0 || importBatch?.status === "quarantined" ? "active" : hasSubmission ? "complete" : "ready"
    },
    {
      id: "review",
      label: "Human review",
      metric: isApproved
        ? "approved"
        : reviewActive
          ? reviewTask?.assignedTo ?? "review queue"
          : hasSubmission
            ? "submit draft"
            : "blocked",
      detail: "Reviewer approval is required before downstream risk, matching or finance use.",
      status: isApproved ? "complete" : reviewActive ? "active" : hasSubmission ? "ready" : "blocked"
    },
    {
      id: "canonical",
      label: "Approved snapshot",
      metric: isApproved ? `v${approvedVersion}` : reviewActive ? "awaiting approval" : "no snapshot",
      detail: isApproved
        ? `${canonicalRows} canonical rows linked to ${sourceCount} source reference${sourceCount === 1 ? "" : "s"}.`
        : "Canonical tables stay empty until a reviewer approves this period.",
      status: isApproved ? "complete" : reviewActive ? "ready" : "blocked"
    }
  ];
}
