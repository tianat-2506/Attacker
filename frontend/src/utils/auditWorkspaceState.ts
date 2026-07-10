export function auditWorkspaceState(resolved: boolean, hasAudit: boolean, hasAdminOps: boolean) {
  return {
    loading: !resolved,
    auditUnavailable: resolved && !hasAudit,
    opsUnavailable: resolved && !hasAdminOps
  };
}

export function auditWorkspaceContextMatches(
  loadedContextKey: string | null,
  activeAccountId: string,
  businessId: string,
  canReadOps = true
) {
  return canReadOps && loadedContextKey === `${activeAccountId}:${businessId}`;
}
