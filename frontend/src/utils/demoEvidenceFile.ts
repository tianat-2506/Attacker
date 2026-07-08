import type { EvidenceDocument } from "../types";
import { normalizeEvidenceUploadClassification } from "./evidenceClassification";

export interface DemoEvidenceFilePayload {
  fileName: string;
  contentType: string;
  content: string;
  documentType: EvidenceDocument["type"];
  classification: string;
}

export function demoEvidenceFilePayload({
  businessId,
  periodKey,
  documentType,
  classification
}: {
  businessId: string;
  periodKey: string;
  documentType: EvidenceDocument["type"];
  classification: string;
}): DemoEvidenceFilePayload {
  const normalizedClassification = normalizeEvidenceUploadClassification(documentType, classification);
  const slug = documentType.toLowerCase().replace(/_/g, "-");
  const content = [
    "VietSupply Radar demo evidence file",
    `business_id=${businessId}`,
    `period=${periodKey}`,
    `document_type=${documentType}`,
    `classification=${normalizedClassification}`,
    "purpose=evidence_intake_demo",
    "note=synthetic supporting document for checksum, upload-ticket and malware-scan workflow only",
    "boundary=no legal authenticity conclusion, no supplier verification, no financing approval"
  ].join("\n");

  return {
    fileName: `${businessId}-${periodKey}-${slug}-demo-evidence.txt`,
    contentType: "text/plain",
    content,
    documentType,
    classification: normalizedClassification
  };
}
