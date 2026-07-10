export function opsProvenanceLabel(item: {
  approvalStatus?: string;
  checksum?: string;
  createdBy?: string;
}) {
  if (!item.approvalStatus || !item.checksum || !item.createdBy) {
    return "registry metadata unavailable";
  }
  return `internal registry ${item.approvalStatus} - manifest sha256 ${item.checksum.slice(0, 8)} - ${item.createdBy}`;
}
