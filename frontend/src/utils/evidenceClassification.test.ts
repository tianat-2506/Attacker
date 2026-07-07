import { describe, expect, it } from "vitest";
import {
  evidenceClassificationIsAllowed,
  normalizeEvidenceUploadClassification,
  recommendedEvidenceClassification
} from "./evidenceClassification";

describe("evidence classification helpers", () => {
  it("requires restricted financial classification for finance evidence", () => {
    expect(recommendedEvidenceClassification("GUARANTEE")).toBe("restricted_financial");
    expect(recommendedEvidenceClassification("INVOICE")).toBe("restricted_financial");
    expect(normalizeEvidenceUploadClassification("GUARANTEE", "confidential")).toBe("restricted_financial");
    expect(normalizeEvidenceUploadClassification("INVOICE", "partner_visible")).toBe("restricted_financial");
    expect(evidenceClassificationIsAllowed("GUARANTEE", "confidential")).toBe(false);
  });

  it("preserves valid non-financial classifications and falls back safely", () => {
    expect(recommendedEvidenceClassification("CERTIFICATION")).toBe("confidential");
    expect(normalizeEvidenceUploadClassification("CERTIFICATION", "public")).toBe("public");
    expect(normalizeEvidenceUploadClassification("CONTRACT", "restricted_financial")).toBe("restricted_financial");
    expect(normalizeEvidenceUploadClassification("DELIVERY_NOTE", "unexpected")).toBe("confidential");
    expect(evidenceClassificationIsAllowed("CERTIFICATION", "public")).toBe(true);
  });
});
