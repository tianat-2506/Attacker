import type { PendingEvidenceUpload } from "../types";

export function mergePendingEvidenceUploadsForPeriod(
  current: PendingEvidenceUpload[],
  incoming: PendingEvidenceUpload[],
  businessId: string,
  periodKey: string
) {
  const outsideSelectedPeriod = current.filter((item) => item.businessId !== businessId || item.periodKey !== periodKey);
  const localPendingForPeriod = current.filter(
    (item) => item.businessId === businessId && item.periodKey === periodKey && item.status === "local_pending"
  );
  const seen = new Set<string>();
  return [
    ...outsideSelectedPeriod,
    ...[...incoming, ...localPendingForPeriod].filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    })
  ];
}
