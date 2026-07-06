import type { AppView, BusinessNode, DemoAccount } from "../types";

export const demoAccounts: DemoAccount[] = [
  {
    id: "demo-operator",
    personName: "Nguyen Minh",
    label: "Demo operator",
    stakeholder: "Platform demo operator",
    organizationId: "org-demo",
    organizationName: "VietSupply Demo Ops",
    actorId: "demo-user",
    actorRole: "demo_operator",
    purpose: "demo_view",
    scopes: ["demo:read"],
    defaultBusinessId: "BIZ-005",
    allowedViews: ["overview", "map", "companies", "intake", "onboarding", "risk", "matching", "finance", "invoice", "audit"],
    description: "Full synthetic demo navigation with masked-by-default data controls."
  },
  {
    id: "sme-submit",
    personName: "Tran Lan",
    label: "SME submitter",
    stakeholder: "Retail SME",
    organizationId: "BIZ-009",
    organizationName: "Thu Duc Retail Mart",
    actorId: "sme-biz-009",
    actorRole: "sme_submitter",
    purpose: "periodic_intake",
    scopes: ["demo:read", "intake:write"],
    defaultBusinessId: "BIZ-009",
    allowedViews: ["intake", "companies", "onboarding", "risk"],
    description: "Own-organization profile, monthly intake, draft/submit and evidence preparation."
  },
  {
    id: "buyer-admin",
    personName: "Pham Anh",
    label: "Buyer admin",
    stakeholder: "Anchor buyer",
    organizationId: "BIZ-009",
    organizationName: "Thu Duc Retail Mart",
    actorId: "buyer-admin-009",
    actorRole: "buyer_admin",
    purpose: "supplier_risk_review",
    scopes: ["demo:read", "buyer:intro"],
    defaultBusinessId: "BIZ-009",
    allowedViews: ["overview", "map", "companies", "onboarding", "risk", "matching"],
    description: "Buyer-side supplier map, consented supplier view and human-reviewed shortlist."
  },
  {
    id: "supplier-admin",
    personName: "Le Quang",
    label: "Supplier admin",
    stakeholder: "Distributor supplier",
    organizationId: "BIZ-005",
    organizationName: "Dai Tin Distribution",
    actorId: "supplier-admin-005",
    actorRole: "supplier_admin",
    purpose: "evidence_management",
    scopes: ["demo:read", "intake:write", "evidence:write"],
    defaultBusinessId: "BIZ-005",
    allowedViews: ["intake", "companies", "onboarding", "risk"],
    description: "Supplier-side profile, product capability and evidence maintenance."
  },
  {
    id: "supplier-admin-007",
    personName: "Vo Ngan",
    label: "Target supplier",
    stakeholder: "Alternative supplier",
    organizationId: "BIZ-007",
    organizationName: "An Phu FMCG Hub",
    actorId: "supplier-admin-007",
    actorRole: "supplier_admin",
    purpose: "supplier_introduction_review",
    scopes: ["demo:read", "intake:write", "evidence:write"],
    defaultBusinessId: "BIZ-007",
    allowedViews: ["intake", "companies", "onboarding", "risk"],
    description: "Supplier persona for incoming connection consent requests."
  },
  {
    id: "reviewer",
    personName: "Do Khoa",
    label: "Verifier",
    stakeholder: "Submission reviewer",
    organizationId: "BIZ-009",
    organizationName: "Review Desk",
    actorId: "reviewer-001",
    actorRole: "reviewer",
    purpose: "submission_review",
    scopes: ["demo:read"],
    defaultBusinessId: "BIZ-009",
    allowedViews: ["intake", "onboarding", "companies", "risk"],
    description: "Review submissions, evidence completeness and approval workflow."
  },
  {
    id: "network-analyst",
    personName: "Hoang Vy",
    label: "Network analyst",
    stakeholder: "Supply network analyst",
    organizationId: "BIZ-009",
    organizationName: "Network Analysis Team",
    actorId: "network-analyst-001",
    actorRole: "network_analyst",
    purpose: "supplier_shortlist_review",
    scopes: ["demo:read", "commercial_graph:read"],
    defaultBusinessId: "BIZ-009",
    allowedViews: ["overview", "map", "onboarding", "risk", "matching"],
    description: "Masked supply map analysis and consent-gated network exploration."
  },
  {
    id: "lender",
    personName: "Mai Linh",
    label: "Lender",
    stakeholder: "Invoice finance partner",
    organizationId: "BIZ-062",
    organizationName: "Saigon Invoice Finance",
    actorId: "lender-062",
    actorRole: "lender",
    purpose: "invoice_financing_review",
    scopes: ["demo:read", "invoice:read"],
    defaultBusinessId: "BIZ-062",
    allowedViews: ["finance", "invoice", "onboarding", "risk"],
    description: "Finance review workspace; decisions remain human-reviewed and non-automatic."
  },
  {
    id: "system-admin",
    personName: "Admin Ops",
    label: "System admin",
    stakeholder: "Platform operations",
    organizationId: "org-demo",
    organizationName: "VietSupply Platform",
    actorId: "system-admin",
    actorRole: "system_admin",
    purpose: "ops_governance_review",
    scopes: ["demo:read", "policy:override", "ops:read"],
    defaultBusinessId: "BIZ-009",
    allowedViews: ["overview", "onboarding", "audit"],
    description: "Operational health, audit and registry visibility without pilot-ready claims."
  }
];

export const defaultDemoAccount = demoAccounts[0];

export function getDemoAccountById(accountId: string | null | undefined): DemoAccount {
  return demoAccounts.find((account) => account.id === accountId) ?? defaultDemoAccount;
}

export function demoAccountHeaders(account: DemoAccount): Record<string, string> {
  return {
    "X-Tenant-Id": "tenant-demo",
    "X-Organization-Id": account.organizationId,
    "X-Actor-Id": account.actorId,
    "X-Actor-Role": account.actorRole,
    "X-Purpose": account.purpose,
    "X-Demo-Scopes": account.scopes.join(" ")
  };
}

export function firstAllowedView(account: DemoAccount, fallback: AppView = "overview"): AppView {
  return account.allowedViews[0] ?? fallback;
}

export function accountHasAnyRole(account: DemoAccount, roles: string[]) {
  return roles.includes(account.actorRole);
}

export function accountCanBrowseNetwork(account: DemoAccount) {
  return accountHasAnyRole(account, ["demo_operator", "system_admin", "buyer_admin", "network_analyst", "org_admin"]);
}

export function accountCanReadOwnBusiness(account: DemoAccount, businessId: string) {
  return accountHasAnyRole(account, ["demo_operator", "system_admin"]) || businessId === account.defaultBusinessId || businessId === account.organizationId;
}

export function scopedBusinessNodesForAccount(account: DemoAccount, nodes: BusinessNode[]) {
  if (accountCanBrowseNetwork(account)) return nodes;
  return nodes.filter((node) => accountCanReadOwnBusiness(account, node.id));
}
