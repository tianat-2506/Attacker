import type { ConnectionRequest, DemoAccount } from "../types";

export type ConnectionRequestFilter = "all" | "open" | "needs_action" | "active" | "rejected";

export const CONNECTION_REQUEST_FILTERS: ConnectionRequestFilter[] = ["all", "open", "needs_action", "active", "rejected"];

export function connectionRequestFilterLabel(filter: ConnectionRequestFilter): string {
  if (filter === "needs_action") return "action needed";
  return filter.replace(/_/g, " ");
}

export function connectionRequestTone(status: string): string {
  if (status === "relationship_active") return "healthy";
  if (status === "rejected") return "critical";
  return "watch";
}

export function isPlatformOpsRole(role: string): boolean {
  return ["demo_admin", "demo_operator", "system_admin"].includes(role);
}

export function isReviewerOrOpsRole(role: string): boolean {
  return ["reviewer", "demo_admin", "demo_operator", "system_admin"].includes(role);
}

export function connectionRequestIsClosed(request: ConnectionRequest): boolean {
  return request.status === "relationship_active" || request.status === "rejected";
}

export function canGrantConnectionConsent(account: DemoAccount, request: ConnectionRequest): boolean {
  return account.organizationId === request.targetSupplierId || isPlatformOpsRole(account.actorRole);
}

export function canRequestConnectionChanges(account: DemoAccount, request: ConnectionRequest): boolean {
  return account.organizationId === request.targetSupplierId || isReviewerOrOpsRole(account.actorRole);
}

export function canRejectConnection(account: DemoAccount, request: ConnectionRequest): boolean {
  return account.organizationId === request.targetSupplierId || isPlatformOpsRole(account.actorRole);
}

export function canActivateConnection(account: DemoAccount): boolean {
  return isReviewerOrOpsRole(account.actorRole);
}

export function connectionRequestIsActionable(account: DemoAccount, request: ConnectionRequest, canDecideConnectionRequest: boolean): boolean {
  if (!canDecideConnectionRequest || connectionRequestIsClosed(request)) return false;
  if (request.consentStatus !== "supplier_consented" && canGrantConnectionConsent(account, request)) return true;
  if (request.consentStatus === "supplier_consented" && canActivateConnection(account)) return true;
  return canRequestConnectionChanges(account, request) || canRejectConnection(account, request);
}

export function connectionRequestMatchesFilter(
  filter: ConnectionRequestFilter,
  request: ConnectionRequest,
  account: DemoAccount,
  canDecideConnectionRequest: boolean
): boolean {
  if (filter === "all") return true;
  if (filter === "open") return !connectionRequestIsClosed(request);
  if (filter === "needs_action") return connectionRequestIsActionable(account, request, canDecideConnectionRequest);
  if (filter === "active") return request.status === "relationship_active";
  if (filter === "rejected") return request.status === "rejected";
  return true;
}

export function connectionRequestPerspectiveLabel(account: DemoAccount, request: ConnectionRequest): string {
  if (account.organizationId === request.buyerId) return "buyer request";
  if (account.organizationId === request.targetSupplierId) return "supplier action";
  if (isReviewerOrOpsRole(account.actorRole)) return "review queue";
  return "visible history";
}
