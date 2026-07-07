import type { EvidenceDocument } from "../types";

export type EvidenceClassification = "public" | "partner_visible" | "confidential" | "restricted_financial";

const allowedClassifications = new Set<EvidenceClassification>([
  "public",
  "partner_visible",
  "confidential",
  "restricted_financial"
]);

const restrictedFinancialEvidenceTypes = new Set<string>(["GUARANTEE", "INVOICE"]);

export function recommendedEvidenceClassification(documentType: EvidenceDocument["type"] | string | null | undefined): EvidenceClassification {
  const normalizedType = String(documentType ?? "").toUpperCase();
  if (restrictedFinancialEvidenceTypes.has(normalizedType)) return "restricted_financial";
  return "confidential";
}

export function normalizeEvidenceUploadClassification(
  documentType: EvidenceDocument["type"] | string | null | undefined,
  classification: string | null | undefined
): EvidenceClassification {
  const recommended = recommendedEvidenceClassification(documentType);
  const requested = String(classification ?? "").trim() as EvidenceClassification;
  if (!allowedClassifications.has(requested)) return recommended;
  if (recommended === "restricted_financial") return "restricted_financial";
  return requested;
}

export function evidenceClassificationIsAllowed(
  documentType: EvidenceDocument["type"] | string | null | undefined,
  classification: string | null | undefined
) {
  return normalizeEvidenceUploadClassification(documentType, classification) === classification;
}
