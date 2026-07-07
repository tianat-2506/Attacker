import { describe, expect, it } from "vitest";
import type { PendingEvidenceUpload } from "../types";
import { mergePendingEvidenceUploadsForPeriod } from "./pendingEvidenceUploads";

function upload(id: string, businessId: string, periodKey: string, status = "upload_ticket_created"): PendingEvidenceUpload {
  return {
    id,
    businessId,
    periodKey,
    documentType: "CERTIFICATION",
    fileName: `${id}.pdf`,
    contentType: "application/pdf",
    byteSize: 100,
    classification: "confidential",
    status,
    malwareScanStatus: "pending_upload",
    uploadedAt: "2026-07-01T00:00:00Z"
  };
}

describe("mergePendingEvidenceUploadsForPeriod", () => {
  it("replaces only the selected business period and preserves other periods", () => {
    const merged = mergePendingEvidenceUploadsForPeriod(
      [
        upload("old-july", "BIZ-009", "2026-07"),
        upload("old-june", "BIZ-009", "2026-06"),
        upload("other-org", "BIZ-005", "2026-07")
      ],
      [upload("new-july", "BIZ-009", "2026-07")],
      "BIZ-009",
      "2026-07"
    );

    expect(merged.map((item) => item.id)).toEqual(["old-june", "other-org", "new-july"]);
  });

  it("keeps local pending uploads for the selected period after backend refresh", () => {
    const merged = mergePendingEvidenceUploadsForPeriod(
      [
        upload("local-july", "BIZ-009", "2026-07", "local_pending"),
        upload("local-june", "BIZ-009", "2026-06", "local_pending")
      ],
      [upload("server-july", "BIZ-009", "2026-07")],
      "BIZ-009",
      "2026-07"
    );

    expect(merged.map((item) => item.id)).toEqual(["local-june", "server-july", "local-july"]);
  });

  it("deduplicates incoming and local rows by id within the selected period", () => {
    const merged = mergePendingEvidenceUploadsForPeriod(
      [upload("same", "BIZ-009", "2026-07", "local_pending")],
      [upload("same", "BIZ-009", "2026-07")],
      "BIZ-009",
      "2026-07"
    );

    expect(merged.map((item) => item.id)).toEqual(["same"]);
    expect(merged[0].status).toBe("upload_ticket_created");
  });
});
