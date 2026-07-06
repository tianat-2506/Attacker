import type { AppView } from "../types";

export interface WorkspaceUrlState {
  accountId?: string;
  businessId?: string;
  period?: string;
  view?: AppView;
}

export function isPeriodKey(value: string | null | undefined): value is string {
  return Boolean(value && /^\d{4}-\d{2}$/.test(value));
}

export function readWorkspaceUrlState(search: string, validAccountIds: Set<string>, validViews: Set<AppView>): WorkspaceUrlState {
  const params = new URLSearchParams(search);
  const accountId = params.get("account") ?? undefined;
  const businessId = params.get("business") ?? undefined;
  const period = params.get("period");
  const view = params.get("view") as AppView | null;
  return {
    accountId: accountId && validAccountIds.has(accountId) ? accountId : undefined,
    businessId: businessId || undefined,
    period: isPeriodKey(period) ? period : undefined,
    view: view && validViews.has(view) ? view : undefined
  };
}

export function workspaceSearchWithState(search: string, state: Required<WorkspaceUrlState>): string {
  const params = new URLSearchParams(search);
  params.set("account", state.accountId);
  params.set("business", state.businessId);
  params.set("period", state.period);
  params.set("view", state.view);
  return `?${params.toString()}`;
}
