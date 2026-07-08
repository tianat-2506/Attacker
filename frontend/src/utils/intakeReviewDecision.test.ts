import { describe, expect, it } from "vitest";
import { intakeReviewDecisionState } from "./intakeReviewDecision";
import type { DataSubmission, ReviewQueueItem } from "../types";

const submission = {
  reviewTask: { id: "review-1" }
} as DataSubmission;

function queueItem(approvalBlocked: boolean, advisory = "Evidence must be scan-cleared.") {
  return {
    reviewTaskId: "review-1",
    evidenceReview: {
      approvalBlocked,
      advisory
    }
  } as ReviewQueueItem;
}

describe("intakeReviewDecisionState", () => {
  it("fails closed while the submitted review task is missing from the hydrated queue", () => {
    expect(intakeReviewDecisionState(submission, null, "approve")).toEqual({
      enabled: false,
      notice: "Review gate is syncing. Wait for the submitted task to appear in the reviewer queue."
    });
  });

  it("fails closed when the queue entry does not match the submission review task", () => {
    const staleQueueItem = {
      ...queueItem(false),
      reviewTaskId: "review-stale"
    } as ReviewQueueItem;

    expect(intakeReviewDecisionState(submission, staleQueueItem, "approve").enabled).toBe(false);
  });

  it("blocks approval when the hydrated evidence gate is blocked", () => {
    expect(intakeReviewDecisionState(submission, queueItem(true), "approve")).toEqual({
      enabled: false,
      notice: "Evidence must be scan-cleared."
    });
  });

  it("allows a review decision after the matching queue task is hydrated", () => {
    expect(intakeReviewDecisionState(submission, queueItem(false), "approve")).toEqual({
      enabled: true,
      notice: null
    });
  });

  it("allows request changes despite an approval-only evidence block", () => {
    expect(intakeReviewDecisionState(submission, queueItem(true), "request_changes")).toEqual({
      enabled: true,
      notice: null
    });
  });
});
