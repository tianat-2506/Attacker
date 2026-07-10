import { describe, expect, it } from "vitest";
import { opsProvenanceLabel } from "./opsProvenance";

describe("opsProvenanceLabel", () => {
  it("labels registry approval and checksum without implying a business decision", () => {
    expect(opsProvenanceLabel({
      approvalStatus: "approved",
      checksum: "a".repeat(64),
      createdBy: "system-seed"
    })).toBe("internal registry approved - manifest sha256 aaaaaaaa - system-seed");
  });

  it("keeps incomplete fallback rows explicit", () => {
    expect(opsProvenanceLabel({})).toBe("registry metadata unavailable");
  });
});
