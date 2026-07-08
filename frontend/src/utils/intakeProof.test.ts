import { describe, expect, it } from "vitest";
import { intakeProofChecklist } from "./intakeProof";

describe("intakeProofChecklist", () => {
  it("starts with an action-oriented proof checklist before any draft exists", () => {
    const checklist = intakeProofChecklist({});

    expect(checklist.map((item) => `${item.id}:${item.status}`)).toEqual([
      "draft:active",
      "csv:idle",
      "evidence:idle",
      "snapshot:blocked"
    ]);
    expect(checklist[0].metric).toBe("create draft");
    expect(checklist[3].detail).toContain("No approved snapshot");
  });

  it("flags quarantined CSV rows and blocked evidence before review approval", () => {
    const checklist = intakeProofChecklist({
      submission: { source: "csv", status: "draft", version: 1, validationSummary: { errors: 2, warnings: 1, infos: 0 } },
      importBatch: { rowCount: 20, status: "quarantined", idempotentReplay: false },
      selectedReviewTask: {
        evidenceReview: {
          clean: 0,
          pending: 1,
          rejected: 0,
          required: true,
          approvalBlocked: true
        }
      }
    });

    expect(checklist.map((item) => `${item.id}:${item.status}`)).toEqual([
      "draft:active",
      "csv:blocked",
      "evidence:blocked",
      "snapshot:blocked"
    ]);
    expect(checklist[1].metric).toBe("2 errors / 20 rows");
    expect(checklist[1].detail).toContain("quarantined");
    expect(checklist[2].detail).toContain("scan-clear");
  });

  it("shows replayed CSV, clean evidence and approved source-linked snapshot as complete", () => {
    const checklist = intakeProofChecklist({
      submission: { source: "csv", status: "approved", version: 3, validationSummary: { errors: 0, warnings: 0, infos: 0 } },
      importBatch: { rowCount: 42, status: "parsed", idempotentReplay: true },
      selectedReviewTask: {
        evidenceReview: {
          clean: 2,
          pending: 0,
          rejected: 0,
          required: true,
          approvalBlocked: false
        }
      },
      snapshot: {
        approvedVersion: 3,
        sourceSubmissionIds: ["SUB-1", "BATCH-1", "UPLOAD-1"],
        financials: [{ id: 1 }],
        products: [{ id: 2 }],
        evidence: [{ id: 3 }]
      }
    });

    expect(checklist.map((item) => `${item.id}:${item.status}`)).toEqual([
      "draft:complete",
      "csv:complete",
      "evidence:complete",
      "snapshot:complete"
    ]);
    expect(checklist[1].detail).toContain("idempotent replay");
    expect(checklist[3].metric).toBe("approved v3");
    expect(checklist[3].detail).toContain("3 canonical rows");
    expect(checklist[3].detail).toContain("3 source refs");
  });

  it("guides the evidence scan, submit and reviewer approval next actions", () => {
    const pendingScan = intakeProofChecklist({
      submission: { source: "manual", status: "draft", version: 1, validationSummary: { errors: 0, warnings: 0, infos: 0 } },
      pendingEvidenceUploads: [{ malwareScanStatus: "pending_scan" }]
    });

    expect(pendingScan[2].status).toBe("active");
    expect(pendingScan[2].nextAction).toBe("Run demo scan");

    const scanClean = intakeProofChecklist({
      submission: { source: "manual", status: "draft", version: 1, validationSummary: { errors: 0, warnings: 0, infos: 0 } },
      pendingEvidenceUploads: [{ malwareScanStatus: "clean" }]
    });

    expect(scanClean[2].status).toBe("complete");
    expect(scanClean[2].nextAction).toBe("Submit for review");

    const reviewReady = intakeProofChecklist({
      submission: { source: "manual", status: "in_review", version: 2, validationSummary: { errors: 0, warnings: 0, infos: 0 } },
      selectedReviewTask: {
        evidenceReview: {
          clean: 1,
          pending: 0,
          rejected: 0,
          required: true,
          approvalBlocked: false
        }
      }
    });

    expect(reviewReady[3].status).toBe("active");
    expect(reviewReady[3].nextAction).toBe("Approve snapshot");
  });

  it("counts scan-cleared vault documents as evidence proof after upload tickets leave the pending queue", () => {
    const checklist = intakeProofChecklist({
      submission: { source: "manual", status: "draft", version: 1, validationSummary: { errors: 0, warnings: 0, infos: 0 } },
      evidenceDocuments: [{ verificationStatus: "MALWARE_SCAN_CLEAN", evidenceVersionId: "EVV-1" }]
    });

    expect(checklist[2].status).toBe("complete");
    expect(checklist[2].metric).toBe("1 clean / 0 pending");
    expect(checklist[2].nextAction).toBe("Submit for review");
  });

  it("guides back to draft creation when clean evidence exists before a submission", () => {
    const checklist = intakeProofChecklist({
      evidenceDocuments: [{ verificationStatus: "MALWARE_SCAN_CLEAN", evidenceVersionId: "EVV-1" }]
    });

    expect(checklist[2].status).toBe("complete");
    expect(checklist[2].nextAction).toBe("Create draft");
  });
});
