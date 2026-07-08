import { describe, expect, it } from "vitest";
import { demoEvidenceFilePayload } from "./demoEvidenceFile";

describe("demoEvidenceFilePayload", () => {
  it("creates a clean demo certification payload tied to the selected period", () => {
    const payload = demoEvidenceFilePayload({
      businessId: "BIZ-005",
      periodKey: "2026-09",
      documentType: "CERTIFICATION",
      classification: "confidential"
    });

    expect(payload.fileName).toBe("BIZ-005-2026-09-certification-demo-evidence.txt");
    expect(payload.contentType).toBe("text/plain");
    expect(payload.documentType).toBe("CERTIFICATION");
    expect(payload.classification).toBe("confidential");
    expect(payload.content).toContain("period=2026-09");
    expect(payload.content).toContain("document_type=CERTIFICATION");
    expect(payload.content).not.toContain("EICAR");
  });

  it("keeps financial evidence restricted and avoids legal authenticity wording", () => {
    const payload = demoEvidenceFilePayload({
      businessId: "BIZ-009",
      periodKey: "2026-10",
      documentType: "GUARANTEE",
      classification: "confidential"
    });

    expect(payload.classification).toBe("restricted_financial");
    expect(payload.content.toLowerCase()).not.toContain("verified supplier");
    expect(payload.content.toLowerCase()).not.toContain("loan approved");
    expect(payload.content.toLowerCase()).not.toContain("authenticity verified");
  });
});
