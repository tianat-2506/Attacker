import type { DataSubmission, ReviewQueueItem } from "../types";

export type IntakeReviewDecision = "approve" | "reject" | "request_changes";

export function intakeReviewDecisionState(
  submission: Pick<DataSubmission, "reviewTask"> | null | undefined,
  selectedReviewTask: Pick<ReviewQueueItem, "reviewTaskId" | "evidenceReview"> | null | undefined,
  decision: IntakeReviewDecision
) {
  if (!submission?.reviewTask) {
    return {
      enabled: false,
      notice: "Select an open review task before recording a decision."
    };
  }

  if (!selectedReviewTask || selectedReviewTask.reviewTaskId !== submission.reviewTask.id) {
    return {
      enabled: false,
      notice: "Review gate is syncing. Wait for the submitted task to appear in the reviewer queue."
    };
  }

  if (decision === "approve" && selectedReviewTask.evidenceReview.approvalBlocked) {
    return {
      enabled: false,
      notice: selectedReviewTask.evidenceReview.advisory
    };
  }

  return {
    enabled: true,
    notice: null
  };
}
