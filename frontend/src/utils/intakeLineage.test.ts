import { describe, expect, it } from "vitest";
import { intakeLineageSteps } from "./intakeLineage";

describe("intakeLineageSteps", () => {
  it("starts with raw input active and downstream lineage blocked", () => {
    const steps = intakeLineageSteps({});

    expect(steps.map((step) => `${step.id}:${step.status}`)).toEqual([
      "raw:active",
      "staging:blocked",
      "review:blocked",
      "canonical:blocked"
    ]);
  });

  it("shows CSV quarantine before review", () => {
    const steps = intakeLineageSteps({
      submission: { source: "csv", status: "draft", version: 1, validationSummary: { errors: 2, warnings: 1 } },
      importBatch: { rowCount: 20, status: "quarantined", fileName: "products.csv" }
    });

    expect(steps[0].metric).toBe("20 CSV rows");
    expect(steps[1].status).toBe("active");
    expect(steps[1].metric).toBe("quarantined");
    expect(steps[2].status).toBe("ready");
    expect(steps[3].status).toBe("blocked");
  });

  it("tracks submitted review state and approved canonical source lineage", () => {
    const submitted = intakeLineageSteps({
      submission: { source: "manual", status: "in_review", version: 2, validationSummary: { errors: 0, warnings: 1 }, reviewTask: { assignedTo: "reviewer-001" } }
    });

    expect(submitted.map((step) => `${step.id}:${step.status}`)).toEqual([
      "raw:complete",
      "staging:complete",
      "review:active",
      "canonical:ready"
    ]);
    expect(submitted[2].metric).toBe("reviewer-001");

    const approved = intakeLineageSteps({
      submission: { source: "manual", status: "approved", version: 2, validationSummary: { errors: 0, warnings: 0 } },
      snapshot: {
        approvedVersion: 2,
        sourceSubmissionIds: ["SUB-1", "UPLOAD-EVD-1"],
        financials: [{ id: 1 }],
        products: [{ id: 2 }],
        evidence: [{ id: 3 }]
      }
    });

    expect(approved[2].status).toBe("complete");
    expect(approved[3].status).toBe("complete");
    expect(approved[3].detail).toContain("3 canonical rows");
    expect(approved[3].detail).toContain("2 source references");
  });
});
