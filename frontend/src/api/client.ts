import { businesses, defaultShock, edges, recommendations, riskDrivers } from "../utils/demoData";
import { defaultDemoAccount, demoAccountHeaders } from "../utils/demoAccounts";
import type {
  AdminOpsData,
  AppView,
  AlertItem,
  AuditData,
  AuditEvent,
  AuthMe,
  BusinessDetail,
  BusinessNode,
  ConnectionRequest,
  ConsentRecord,
  CsvImportBatch,
  DashboardData,
  DataSubmission,
  DemoAccount,
  EvidenceDocument,
  EvidenceDownloadTicket,
  EvidenceScanJobResult,
  EvidenceUploadTicket,
  EvidenceVersionRecord,
  EvidenceVault,
  FinanceData,
  FinancePoint,
  IntakeErrorReport,
  IntakeErrorReportRow,
  InvoiceClaim,
  InvoiceVerificationData,
  MatchRunsData,
  OverviewMetrics,
  PendingEvidenceUpload,
  PeriodKey,
  PeriodSnapshot,
  Recommendation,
  ReviewQueueData,
  ReviewQueueItem,
  ReviewTask,
  RiskDriver,
  RiskRunsData,
  RiskSignal,
  ScenarioData,
  ShockState,
  SupplyEdge,
  SupplyMapRegistration
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const APP_MODE = import.meta.env.VITE_APP_MODE ?? "demo";
const APP_VIEW_IDS = new Set<AppView>(["overview", "map", "companies", "intake", "onboarding", "risk", "matching", "finance", "invoice", "audit"]);
let activeDemoAccount = defaultDemoAccount;

export function setDemoAccountContext(account: DemoAccount) {
  activeDemoAccount = account;
}

class ApiError extends Error {
  status: number;

  constructor(path: string, status: number) {
    super(`${path} returned ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

function bearerToken() {
  const envToken = import.meta.env.VITE_AUTH_TOKEN;
  if (envToken) return envToken;
  if (typeof globalThis.localStorage === "undefined") return null;
  return globalThis.localStorage.getItem("vietsupply.authToken");
}

function trustHeaders() {
  const headers = new Headers();
  if (APP_MODE === "demo") {
    Object.entries(demoAccountHeaders(activeDemoAccount)).forEach(([key, value]) => headers.set(key, value));
    return headers;
  }
  const token = bearerToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

function demoAdminOpsInit(): RequestInit | undefined {
  if (APP_MODE !== "demo") return undefined;
  return {
    headers: {
      "X-Tenant-Id": "tenant-demo",
      "X-Organization-Id": "org-demo",
      "X-Actor-Id": "demo-admin",
      "X-Actor-Role": "demo_admin",
      "X-Purpose": "ops_governance_review",
      "X-Demo-Scopes": "demo:read policy:override"
    }
  };
}

async function requestJson(path: string, init?: RequestInit) {
  const headers = trustHeaders();
  new Headers(init?.headers).forEach((value, key) => headers.set(key, value));
  if (!headers.has("X-Request-Id")) headers.set("X-Request-Id", `web-${Date.now().toString(36)}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) throw new ApiError(path, response.status);
  return response.json();
}

function demoFallback<T>(error: unknown, fallback: () => T): T {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    throw error;
  }
  if (APP_MODE !== "demo") {
    if (error instanceof Error) throw error;
    throw new Error("API fallback is disabled outside demo mode.");
  }
  return fallback();
}

function apiNodeToBusiness(node: any): BusinessNode {
  return {
    id: node.id ?? node.business_id,
    name: node.name ?? node.label,
    type: node.type,
    province: node.province,
    category: node.category ?? node.product_category,
    lat: Number(node.lat),
    lng: Number(node.lng),
    revenue: Number(node.revenue ?? Number(node.monthly_revenue ?? 0) / 1_000_000_000),
    capacity: Number(node.capacity ?? 0),
    health: Number(node.health ?? node.financial_health_score ?? 0),
    risk: Number(node.risk ?? node.supply_risk_score ?? 0),
    scale: node.scale
  };
}

function apiEdgeToSupplyEdge(edge: any): SupplyEdge {
  return {
    id: edge.id ?? edge.edge_id,
    sourceId: edge.sourceId ?? edge.source_id,
    targetId: edge.targetId ?? edge.target_id,
    category: edge.category ?? edge.product_category,
    volume: Number(edge.volume ?? edge.monthly_volume ?? 0),
    leadTimeDays: Number(edge.leadTimeDays ?? edge.lead_time_days ?? 0),
    reliability: Number(edge.reliability ?? 0),
    relationType: edge.relation_type ?? "supply"
  };
}

function apiShockToState(data: any): ShockState {
  return {
    active: true,
    shockNodeId: data.shock_node,
    affectedNodeIds: (data.affected_nodes ?? []).map((node: any) => node.business_id),
    affectedEdgeIds: data.affected_edges ?? [],
    affectedSmeCount: Number(data.impact?.affected_sme_count ?? 0),
    monthlyVolumeAtRisk: Number(data.impact?.monthly_volume_at_risk ?? 0),
    revenueAtRisk: Number(data.impact?.estimated_revenue_at_risk ?? 0),
    avgStockoutDays: Number(data.impact?.avg_stockout_days ?? 0),
    advisoryNotice: data.advisory_notice
  };
}

function apiRecommendationToCard(item: any): Recommendation {
  return {
    supplierId: item.supplier_id,
    supplierName: item.supplier_name,
    score: Number(item.match_score ?? 0),
    leadTimeDays: Number(item.new_edge_preview?.lead_time_days ?? 0),
    reasons: item.reason_codes ?? [],
    components: item.components ?? {},
    periodKey: item.period_key,
    advisoryNotice: item.advisory_notice
  };
}

function apiAlertItem(item: any): AlertItem {
  return {
    id: item.id,
    severity: item.severity,
    title: item.title,
    detail: item.detail,
    age: item.age,
    businessId: item.business_id ?? item.businessId ?? null
  };
}

function apiDriverToRiskDriver(driver: any): RiskDriver {
  const label = String(driver.feature ?? "risk_driver")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
  return {
    label,
    value: Math.round(Number(driver.value ?? 0)),
    note: driver.message ?? `${label} contributes ${driver.contribution ?? 0} points`
  };
}

function apiDocumentToEvidence(item: any): EvidenceDocument {
  return {
    id: item.id,
    type: item.type,
    title: item.title,
    status: item.status,
    verificationStatus: item.verification_status,
    effectiveDate: item.effective_date,
    expiryDate: item.expiry_date,
    source: item.source,
    hash: item.hash,
    facts: item.facts ?? [],
    evidenceVersionId: item.evidenceVersionId ?? item.evidence_version_id ?? item.latest_evidence_version_id ?? null,
    downloadable: Boolean(item.downloadable ?? item.usable ?? false)
  };
}

function periodPath(path: string, periodKey?: string | null): string {
  if (!periodKey) return path;
  const search = new URLSearchParams({ period: periodKey });
  return `${path}?${search.toString()}`;
}

function apiSupplyMapRegistration(item: any): SupplyMapRegistration {
  return {
    id: item.id ?? item.registration_id,
    organizationId: item.organizationId ?? item.organization_id,
    organizationName: item.organizationName ?? item.organization_name,
    requestedBy: item.requestedBy ?? item.requested_by,
    stakeholderRole: item.stakeholderRole ?? item.stakeholder_role,
    province: item.province,
    category: item.category,
    scale: item.scale,
    contactEmail: item.contactEmail ?? item.contact_email,
    intendedRelationships: item.intendedRelationships ?? item.intended_relationships ?? [],
    dataBoundary: item.dataBoundary ?? item.data_boundary,
    status: item.status,
    reviewStatus: item.reviewStatus ?? item.review_status,
    mapVisibility: item.mapVisibility ?? item.map_visibility,
    linkedBusinessId: item.linkedBusinessId ?? item.linked_business_id ?? null,
    submittedAt: item.submittedAt ?? item.submitted_at,
    reviewedAt: item.reviewedAt ?? item.reviewed_at ?? null,
    reviewerNote: item.reviewerNote ?? item.reviewer_note ?? null,
    advisoryNotice: item.advisoryNotice ?? item.advisory_notice ?? "Review-gated demo onboarding record."
  };
}

const fallbackOverview: OverviewMetrics = {
  activeCompanies: businesses.length,
  atRiskNodes: businesses.filter((business) => business.risk >= 70).length,
  affectedSmes: 0,
  supplyHealthScore: 72,
  monthlyNetworkVolume: edges.reduce((sum, edge) => sum + edge.volume, 0),
  advisoryNotice: "Fallback synthetic data is active. Human review is required for all actions."
};

const fallbackEvidenceDocuments: EvidenceDocument[] = [
  { id: "PO-260501", type: "PURCHASE_ORDER", title: "Purchase order PO-260501", status: "DELIVERED_LATE", verificationStatus: "VERIFIED", effectiveDate: "2026-05-01", expiryDate: "2026-05-04", source: "Synthetic procurement register", hash: "98c5b0f4410b7ce31ad54d9ce39b9e5b", facts: ["Quantity 4,200", "Value VND 126,000,000", "Expected 2026-05-04"] },
  { id: "PO-260515", type: "PURCHASE_ORDER", title: "Purchase order PO-260515", status: "DELIVERED_LATE", verificationStatus: "VERIFIED", effectiveDate: "2026-05-15", expiryDate: "2026-05-18", source: "Synthetic procurement register", hash: "9b61f24d8c1779c695b41234fbf77e55", facts: ["Quantity 3,900", "Value VND 117,000,000", "Expected 2026-05-18"] },
  { id: "PO-260601", type: "PURCHASE_ORDER", title: "Purchase order PO-260601", status: "DELIVERED_LATE", verificationStatus: "VERIFIED", effectiveDate: "2026-06-01", expiryDate: "2026-06-04", source: "Synthetic procurement register", hash: "355ea48d58129933bd10013a1b3f2789", facts: ["Quantity 4,600", "Value VND 138,000,000", "Expected 2026-06-04"] },
  { id: "PO-260612", type: "PURCHASE_ORDER", title: "Purchase order PO-260612", status: "OVERDUE_IN_TRANSIT", verificationStatus: "PENDING_REVIEW", effectiveDate: "2026-06-12", expiryDate: "2026-06-16", source: "Synthetic procurement register", hash: "2a0d80d6d14ee5b2efc5d1e2a97c04ea", facts: ["Quantity 5,000", "Value VND 150,000,000", "Expected 2026-06-16"] },
  { id: "CERT-005-HACCP", type: "CERTIFICATION", title: "HACCP", status: "EXPIRING_SOON", verificationStatus: "VERIFIED", effectiveDate: "2025-07-06", expiryDate: "2026-07-05", source: "Demo Food Safety Board", hash: "819b84c77e2ce5fc57e593e9ec823581", facts: ["Issuer Demo Food Safety Board", "Expires 2026-07-05"] },
  { id: "GUA-001", type: "GUARANTEE", title: "Performance Guarantee", status: "ACTIVE", verificationStatus: "VERIFIED", effectiveDate: "2026-01-15", expiryDate: "2026-09-30", source: "Issuer BIZ-061", hash: "e4dc4101c561cf522e696a778d670395", facts: ["Amount VND 350,000,000", "Beneficiary BIZ-009"] }
];

const fallbackSupplyMapRegistrations: SupplyMapRegistration[] = [
  {
    id: "REG-BIZ-009",
    organizationId: "BIZ-009",
    organizationName: "Thu Duc Retail Mart",
    requestedBy: "sme-biz-009",
    stakeholderRole: "retailer",
    province: "TP.HCM",
    category: "beverage",
    scale: "SME",
    contactEmail: "sme-biz-009@demo.vietsupply.local",
    intendedRelationships: ["buyer_profile", "supplier_shortlist"],
    dataBoundary: "masked profile, product demand, evidence metadata",
    status: "approved",
    reviewStatus: "approved",
    mapVisibility: "visible_demo_node",
    linkedBusinessId: "BIZ-009",
    submittedAt: "2026-06-01T09:00:00.000Z",
    reviewedAt: "2026-06-01T11:00:00.000Z",
    reviewerNote: "Approved demo membership; commercial graph access remains consent-gated.",
    advisoryNotice: "Demo onboarding record; not KYB or legal verification."
  },
  {
    id: "REG-BIZ-005",
    organizationId: "BIZ-005",
    organizationName: "Dai Tin Distribution",
    requestedBy: "supplier-admin-005",
    stakeholderRole: "distributor",
    province: "Binh Duong",
    category: "beverage",
    scale: "Distributor",
    contactEmail: "supplier-admin-005@demo.vietsupply.local",
    intendedRelationships: ["supply_relationship", "evidence_sharing"],
    dataBoundary: "masked profile, product capability, certifications",
    status: "submitted",
    reviewStatus: "in_review",
    mapVisibility: "masked_pending_consent",
    linkedBusinessId: "BIZ-005",
    submittedAt: "2026-06-18T08:30:00.000Z",
    reviewedAt: null,
    reviewerNote: null,
    advisoryNotice: "Pending review; no unmasked relationship data is opened."
  },
  {
    id: "REG-BIZ-062",
    organizationId: "BIZ-062",
    organizationName: "Saigon Invoice Finance",
    requestedBy: "lender-062",
    stakeholderRole: "financial_partner",
    province: "TP.HCM",
    category: "finance",
    scale: "Finance partner",
    contactEmail: "lender-062@demo.vietsupply.local",
    intendedRelationships: ["invoice_review", "consented_finance_signals"],
    dataBoundary: "invoice registry signals, no automatic lending decision",
    status: "changes_requested",
    reviewStatus: "changes_requested",
    mapVisibility: "masked_pending_consent",
    linkedBusinessId: "BIZ-062",
    submittedAt: "2026-06-20T13:15:00.000Z",
    reviewedAt: "2026-06-21T10:20:00.000Z",
    reviewerNote: "Add consent scope and lender human-approval terms before enabling graph access.",
    advisoryNotice: "Finance partner onboarding remains review-gated."
  }
];

const fallbackScenarioNodes: BusinessNode[] = [
  ...businesses.filter((item) => ["BIZ-002", "BIZ-005", "BIZ-007", "BIZ-009", "BIZ-011", "BIZ-013", "BIZ-022"].includes(item.id)),
  { id: "BIZ-017", name: "Song Than Cold Logistics", type: "logistics_partner", province: "Binh Duong", category: "logistics", lat: 10.9041, lng: 106.745, revenue: 3.2, capacity: 95000, health: 74, risk: 31 },
  { id: "BIZ-061", name: "VietWorking Capital Partner", type: "financial_partner", province: "TP.HCM", category: "finance", lat: 10.781, lng: 106.705, revenue: 0, capacity: 0, health: 88, risk: 18 },
  { id: "BIZ-062", name: "Saigon Invoice Finance", type: "financial_partner", province: "TP.HCM", category: "finance", lat: 10.786, lng: 106.704, revenue: 0, capacity: 0, health: 88, risk: 18 }
];

function fallbackFinanceSeries(): FinancePoint[] {
  const months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"];
  return months.map((month, index) => {
    const cashIn = [3_250, 3_180, 3_020, 2_930, 2_730, 2_470][index] * 1_000_000;
    const cashOut = [3_120, 3_210, 3_260, 3_280, 3_300, 3_320][index] * 1_000_000;
    return {
      month,
      cashIn,
      cashOut,
      netCashFlow: cashIn - cashOut,
      revenue: 3_400_000_000,
      debt: (1_800 + index * 45) * 1_000_000,
      accountsReceivable: (820 + index * 20) * 1_000_000,
      accountsPayable: 620_000_000,
      inventoryValue: (890 + index * 70) * 1_000_000,
      workingCapital: (1090 + index * 90) * 1_000_000,
      cashflowMargin: Number((((cashIn - cashOut) / 3_400_000_000) * 100).toFixed(1)),
      receivableDaysProxy: 8.2,
      inventoryDaysProxy: 9.8,
      debtToMonthlyRevenue: 0.58,
      latePaymentRate: 0.24,
      deliveryDelayRate: 0.16
    };
  });
}

export async function getGraph() {
  try {
    const payload = await requestJson("/api/v1/graph");
    return { nodes: (payload.data.nodes ?? []).map(apiNodeToBusiness), edges: (payload.data.edges ?? []).map(apiEdgeToSupplyEdge), fallback: false };
  } catch (error) {
    return demoFallback(error, () => ({ nodes: businesses, edges, fallback: true }));
  }
}

export async function getScenario(): Promise<ScenarioData> {
  try {
    const payload = await requestJson("/api/v1/demo/scenario");
    const data = payload.data;
    return {
      id: data.scenario_id,
      name: data.name,
      nodes: (data.nodes ?? []).map(apiNodeToBusiness),
      edges: (data.edges ?? []).map(apiEdgeToSupplyEdge),
      roleCoverage: data.role_coverage ?? {},
      dataScope: data.data_scope
    };
  } catch (error) {
    return demoFallback(error, () => ({
      id: "DEMO-BEVERAGE-BD-01",
      name: "Binh Duong beverage disruption",
      nodes: fallbackScenarioNodes,
      edges: edges.filter((edge) => fallbackScenarioNodes.some((node) => node.id === edge.sourceId) && fallbackScenarioNodes.some((node) => node.id === edge.targetId)),
      roleCoverage: { supplier: ["BIZ-002", "BIZ-007", "BIZ-013"], distributor: ["BIZ-005", "BIZ-022"], sme: ["BIZ-009", "BIZ-011"], logistics: ["BIZ-017"], finance: ["BIZ-061", "BIZ-062"] },
      dataScope: "Synthetic fallback scenario."
    }));
  }
}

export async function getDashboard(): Promise<DashboardData> {
  try {
    const payload = await requestJson("/api/v1/dashboard");
    const data = payload.data;
    return {
      overview: {
        activeCompanies: Number(data.overview.active_companies),
        atRiskNodes: Number(data.overview.at_risk_nodes),
        affectedSmes: Number(data.overview.affected_smes),
        supplyHealthScore: Number(data.overview.supply_health_score),
        monthlyNetworkVolume: Number(data.overview.monthly_network_volume),
        advisoryNotice: data.overview.advisory_notice
      },
      disruptionTrend: (data.disruption_trend ?? []).map((item: any) => ({ month: item.month, total: Number(item.total), highCritical: Number(item.high_critical) })),
      regionalFlow: (data.regional_flow ?? []).map((item: any) => ({ region: item.region, volume: Number(item.volume), share: Number(item.share) })),
      recentAlerts: (data.recent_alerts ?? []).map(apiAlertItem),
      riskyBusinesses: (data.risky_businesses ?? []).map(apiNodeToBusiness),
      dataScope: data.data_scope
    };
  } catch (error) {
    return demoFallback(error, () => ({
      overview: fallbackOverview,
      disruptionTrend: [{ month: "Dec", total: 18, highCritical: 4 }, { month: "Jan", total: 23, highCritical: 6 }, { month: "Feb", total: 21, highCritical: 5 }, { month: "Mar", total: 31, highCritical: 8 }, { month: "Apr", total: 27, highCritical: 6 }, { month: "May", total: 24, highCritical: 7 }],
      regionalFlow: [{ region: "TP.HCM", volume: 210000, share: 38.4 }, { region: "Binh Duong", volume: 156000, share: 28.5 }, { region: "Dong Nai", volume: 108000, share: 19.7 }, { region: "Lam Dong", volume: 73000, share: 13.4 }],
      recentAlerts: [{ id: "ALT-001", severity: "high", title: "Delivery risk signal at Dai Tin Distribution", detail: "3 reviewed purchase-order records exceeded the contracted delivery SLA.", age: "27 min", businessId: "BIZ-005" }, { id: "ALT-002", severity: "medium", title: "Certificate expiry window", detail: "HACCP evidence enters the 30-day review window.", age: "1 hr", businessId: "BIZ-005" }, { id: "ALT-003", severity: "info", title: "Alternative supplier pilot signal", detail: "An Phu FMCG Hub completed one on-time sample delivery.", age: "5 hr", businessId: "BIZ-007" }],
      riskyBusinesses: [...businesses].sort((a, b) => b.risk - a.risk).slice(0, 5),
      dataScope: "Synthetic fallback dataset."
    }));
  }
}

export async function getOverview(): Promise<OverviewMetrics> {
  return (await getDashboard()).overview;
}

export async function simulateShock(): Promise<ShockState> {
  try {
    const payload = await requestJson("/api/v1/simulation/shock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shock_business_id: "BIZ-005", product_category: "beverage", inventory_coverage_days: 5 })
    });
    return apiShockToState(payload.data);
  } catch (error) {
    return demoFallback(error, () => ({ ...defaultShock, active: true }));
  }
}

export async function getBusinessDetail(businessId: string, periodKey?: string | null): Promise<BusinessDetail> {
  try {
    const payload = await requestJson(periodPath(`/api/v1/businesses/${businessId}`, periodKey));
    const data = payload.data;
    return {
      business: apiNodeToBusiness(data.business),
      products: data.products ?? [],
      risk: {
        score: Number(data.risk.score),
        level: data.risk.level,
        formulaVersion: data.risk.formula_version,
        drivers: (data.risk.drivers ?? []).map(apiDriverToRiskDriver),
        explanation: data.risk.explanation,
        advisoryNotice: data.risk.advisory_notice
      },
      financialSummary: data.financial_summary,
      dependencySummary: { downstreamBusinessCount: Number(data.dependency_summary.downstream_business_count), monthlyVolumeSupplied: Number(data.dependency_summary.monthly_volume_supplied) },
      evidenceSummary: { total: Number(data.evidence_summary.total), verified: Number(data.evidence_summary.verified), byType: data.evidence_summary.by_type ?? {} }
    };
  } catch (error) {
    const business = businesses.find((item) => item.id === businessId) ?? businesses[0];
    return demoFallback(error, () => ({ business, products: [{ sku: "SKU-BEV-1L", product_name: "UHT beverage 1L", specification: "UHT, 1L, no sugar", certifications: "HACCP; ISO 22000" }], risk: { score: business.risk, level: business.risk >= 70 ? "red" : "yellow", formulaVersion: "risk-v1-fallback", drivers: riskDrivers, explanation: "Rule-based signal from synthetic operating data.", advisoryNotice: fallbackOverview.advisoryNotice }, financialSummary: null, dependencySummary: { downstreamBusinessCount: 12, monthlyVolumeSupplied: 78000 }, evidenceSummary: { total: fallbackEvidenceDocuments.length, verified: 5, byType: { purchase_orders: 4, certifications: 1, guarantees: 1 } } }));
  }
}

export async function getBusinessRiskDrivers(businessId: string): Promise<RiskDriver[]> {
  return (await getBusinessDetail(businessId)).risk.drivers;
}

export async function getEvidence(businessId: string, periodKey?: string | null): Promise<EvidenceVault> {
  try {
    const payload = await requestJson(periodPath(`/api/v1/businesses/${businessId}/evidence`, periodKey));
    const data = payload.data;
    return { businessId: data.business_id, documents: (data.documents ?? []).map(apiDocumentToEvidence), summary: { total: Number(data.summary.total), verified: Number(data.summary.verified), needsReview: Number(data.summary.needs_review) }, dataScope: data.data_scope };
  } catch (error) {
    return demoFallback(error, () => ({ businessId, documents: fallbackEvidenceDocuments, summary: { total: fallbackEvidenceDocuments.length, verified: 5, needsReview: 1 }, dataScope: "Synthetic fallback evidence." }));
  }
}

export async function getRiskSignal(businessId: string, periodKey?: string | null): Promise<RiskSignal> {
  try {
    const payload = await requestJson(periodPath(`/api/v1/businesses/${businessId}/risk-signal`, periodKey));
    const data = payload.data;
    return { id: data.signal_id, businessId: data.business_id, riskType: data.risk_type, level: data.level, confidence: Number(data.confidence), summary: data.summary, triggers: data.triggers ?? [], evidenceIds: data.evidence_ids ?? [], evidence: (data.evidence ?? []).map(apiDocumentToEvidence), suggestedActions: data.suggested_actions ?? [], formulaVersion: data.formula_version, evidenceScope: data.evidence_scope ?? null, policyDecisionId: data.policy_decision_id ?? null, auditEventId: data.audit_event_id ?? null, disclaimer: data.disclaimer };
  } catch (error) {
    return demoFallback(error, () => ({ id: "RISK-BIZ-005-DELIVERY", businessId, riskType: "DELIVERY_AND_COMPLIANCE", level: "HIGH", confidence: 86, summary: "3 delivered orders exceeded SLA; 1 order remains overdue and 1 certificate needs review.", triggers: [{ rule: "Late PO in rolling review window", observed: 3, threshold: 3, result: "triggered" }, { rule: "Overdue in-transit PO", observed: 1, threshold: 1, result: "triggered" }], evidenceIds: fallbackEvidenceDocuments.slice(0, 5).map((item) => item.id), evidence: fallbackEvidenceDocuments.slice(0, 5), suggestedActions: ["Request updated delivery evidence.", "Review qualified supplier alternatives.", "Require human approval before commercial action."], formulaVersion: "risk-signal-rules-v1.1", evidenceScope: "linked_evidence_visible", policyDecisionId: null, auditEventId: null, disclaimer: "Advisory signal based on synthetic evidence; not a legal breach finding or credit decision." }));
  }
}

function apiFinancePoint(row: any): FinancePoint {
  return { month: row.month, cashIn: Number(row.cash_in), cashOut: Number(row.cash_out), netCashFlow: Number(row.net_cash_flow), revenue: Number(row.revenue), debt: Number(row.debt), accountsReceivable: Number(row.accounts_receivable), accountsPayable: Number(row.accounts_payable), inventoryValue: Number(row.inventory_value), workingCapital: Number(row.working_capital), cashflowMargin: Number(row.cashflow_margin), receivableDaysProxy: Number(row.receivable_days_proxy), inventoryDaysProxy: Number(row.inventory_days_proxy), debtToMonthlyRevenue: Number(row.debt_to_monthly_revenue), latePaymentRate: Number(row.late_payment_rate), deliveryDelayRate: Number(row.delivery_delay_rate) };
}

export async function getFinance(businessId: string, periodKey?: string | null): Promise<FinanceData> {
  try {
    const payload = await requestJson(periodPath(`/api/v1/businesses/${businessId}/finance`, periodKey));
    const data = payload.data;
    return { business: apiNodeToBusiness(data.business), health: { score: Number(data.health.score), level: data.health.level, components: data.health.components ?? {}, formulaVersion: data.health.formula_version, explanation: data.health.explanation }, latest: data.latest ? apiFinancePoint(data.latest) : null, previous: data.previous ? apiFinancePoint(data.previous) : null, series: (data.series ?? []).map(apiFinancePoint), accessScope: data.access_scope, dataScope: data.data_scope, policyDecisionId: data.policy_decision_id, advisoryNotice: data.advisory_notice };
  } catch (error) {
    const series = fallbackFinanceSeries();
    return demoFallback(error, () => ({ business: businesses.find((item) => item.id === businessId) ?? businesses[0], health: { score: 43, level: "watch", components: { operating_cashflow: 18, payment_discipline: 47, delivery_reliability: 60, leverage_pressure: 48 }, formulaVersion: "financial-health-v1.0-demo", explanation: "Operational indicator only; not a regulated credit score." }, latest: series[series.length - 1] ?? null, previous: series[series.length - 2] ?? null, series, accessScope: "synthetic_fallback", dataScope: "restricted_financial", advisoryNotice: "Synthetic management indicators only. Independent review is required." }));
  }
}

function fallbackRecommendationsForRequest(buyerId: string, disruptedSupplierId: string, periodKey?: string | null): Recommendation[] {
  return recommendations
    .filter((item) => item.supplierId !== buyerId && item.supplierId !== disruptedSupplierId)
    .map((item) => ({
      ...item,
      periodKey: periodKey ?? item.periodKey ?? null,
      advisoryNotice: `Synthetic fallback shortlist for selected period ${periodKey ?? "demo"}; excludes the selected disrupted supplier and still requires consent and human review.`
    }));
}

export async function getRecommendations(buyerId = "BIZ-009", periodKey?: string | null, disruptedSupplierId = "BIZ-005"): Promise<Recommendation[]> {
  try {
    const payload = await requestJson("/api/v1/recommendations/suppliers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ buyer_id: buyerId, disrupted_supplier_id: disruptedSupplierId, period_key: periodKey, product_category: "beverage", product_specification: "UHT, 1L, khong duong", required_monthly_volume: 12000, preferred_payment_term_days: 30, top_k: 3 }) });
    return (payload.data ?? []).map(apiRecommendationToCard);
  } catch (error) {
    return demoFallback(error, () => fallbackRecommendationsForRequest(buyerId, disruptedSupplierId, periodKey));
  }
}

export async function getInvoiceVerification(invoiceId = "INV-0242"): Promise<InvoiceVerificationData> {
  try {
    const payload = await requestJson(`/api/v1/invoices/${invoiceId}/verification`);
    const data = payload.data;
    return { invoiceId: data.invoice_id, sellerId: data.seller_id, buyerId: data.buyer_id, amount: Number(data.amount), issueDate: data.issue_date, dueDate: data.due_date, storedHash: data.invoice_hash, computedHash: data.computed_hash, fundingStatus: data.funding_status, confirmedBy: String(data.confirmed_by).split(";"), doubleFinancingAlert: Boolean(data.double_financing_alert), accessScope: data.access_scope, dataScope: data.data_scope, policyDecisionId: data.policy_decision_id, advisoryNotice: data.advisory_notice };
  } catch (error) {
    return demoFallback(error, () => ({ invoiceId, sellerId: "BIZ-005", buyerId: "BIZ-009", amount: 68_000_000, issueDate: "2026-06-08", dueDate: "2026-07-08", storedHash: "7b42ef8490a3d869c0ca0e8ec8d95c87", computedHash: "7b42ef8490a3d869c0ca0e8ec8d95c87", fundingStatus: "unfunded", confirmedBy: ["buyer", "seller"], doubleFinancingAlert: false, accessScope: "synthetic_fallback", dataScope: "restricted_financial", advisoryNotice: "Hash match is a signal; partner review remains required." }));
  }
}

function apiConnectionRequest(item: any): ConnectionRequest {
  return {
    requestId: item.requestId ?? item.request_id,
    requesterId: item.requesterId ?? item.requester_id,
    buyerId: item.buyerId ?? item.buyer_id,
    targetSupplierId: item.targetSupplierId ?? item.target_supplier_id,
    disruptedSupplierId: item.disruptedSupplierId ?? item.disrupted_supplier_id,
    status: item.status,
    consentStatus: item.consentStatus ?? item.consent_status,
    requestedAt: item.requestedAt ?? item.requested_at,
    decidedAt: item.decidedAt ?? item.decided_at,
    decidedBy: item.decidedBy ?? item.decided_by,
    decisionNote: item.decisionNote ?? item.decision_note,
    contractEvidenceId: item.contractEvidenceId ?? item.contract_evidence_id,
    relationshipId: item.relationshipId ?? item.relationship_id,
    relationshipEdgeId: item.relationshipEdgeId ?? item.relationship_edge_id,
    policyDecisionId: item.policyDecisionId ?? item.policy_decision_id,
    auditEventId: item.auditEventId ?? item.audit_event_id,
    nextStep: item.nextStep ?? item.next_step,
    advisoryNotice: item.advisoryNotice ?? item.advisory_notice
  };
}

function apiPeriod(item: any): PeriodKey {
  return {
    id: item.id,
    periodType: item.period_type,
    periodKey: item.period_key,
    periodStart: item.period_start,
    periodEnd: item.period_end,
    status: item.status,
    latestSubmissionStatus: item.latest_submission_status
  };
}

function apiReviewTask(item: any): ReviewTask {
  return {
    id: item.id,
    status: item.status,
    assignedRole: item.assigned_role,
    assignedTo: item.assigned_to,
    assignmentReason: item.assignment_reason,
    assignedAt: item.assigned_at,
    decision: item.decision,
    decisionNote: item.decision_note
  };
}

function apiSubmission(item: any): DataSubmission {
  return {
    id: item.id,
    businessId: item.business_id,
    organizationId: item.organization_id,
    period: apiPeriod(item.period),
    source: item.source,
    status: item.status,
    version: Number(item.version),
    sections: Object.fromEntries(Object.entries(item.sections ?? {}).map(([key, value]: [string, any]) => [key, { status: value.status, payload: value.payload, updatedAt: value.updated_at }])),
    issues: (item.issues ?? []).map((issue: any) => ({ id: issue.id, section: issue.section, path: issue.path, row: issue.row, column: issue.column, code: issue.code, severity: issue.severity, message: issue.message, suggestion: issue.suggestion })),
    validationSummary: { errors: Number(item.validation_summary?.errors ?? 0), warnings: Number(item.validation_summary?.warnings ?? 0), infos: Number(item.validation_summary?.infos ?? 0) },
    reviewTask: item.review_task ? apiReviewTask(item.review_task) : null,
    advisoryNotice: item.advisory_notice
  };
}

function apiReviewQueueItem(item: any): ReviewQueueItem {
  const evidenceReview = item.evidence_review ?? {};
  return {
    reviewTaskId: item.review_task_id,
    submissionId: item.submission_id,
    organizationId: item.organization_id,
    organizationName: item.organization_name,
    periodKey: item.period_key,
    periodStart: item.period_start,
    periodEnd: item.period_end,
    reviewStatus: item.review_status,
    assignedRole: item.assigned_role,
    assignedTo: item.assigned_to,
    assignmentReason: item.assignment_reason,
    assignedAt: item.assigned_at,
    submissionStatus: item.submission_status,
    source: item.source,
    version: Number(item.version ?? 0),
    submittedBy: item.submitted_by,
    submittedAt: item.submitted_at,
    updatedAt: item.updated_at,
    validationSummary: {
      errors: Number(item.validation_summary?.errors ?? 0),
      warnings: Number(item.validation_summary?.warnings ?? 0),
      infos: Number(item.validation_summary?.infos ?? 0)
    },
    evidenceReview: {
      total: Number(evidenceReview.total ?? 0),
      clean: Number(evidenceReview.clean ?? 0),
      pending: Number(evidenceReview.pending ?? 0),
      rejected: Number(evidenceReview.rejected ?? 0),
      required: Boolean(evidenceReview.required ?? false),
      approvalBlocked: Boolean(evidenceReview.approval_blocked ?? false),
      advisory: evidenceReview.advisory ?? "Evidence gate has not reported status for this task.",
      requirements: (evidenceReview.requirements ?? []).map((requirement: any) => ({
        documentType: requirement.document_type ?? requirement.documentType,
        title: requirement.title,
        section: requirement.section,
        total: Number(requirement.total ?? 0),
        clean: Number(requirement.clean ?? 0),
        pending: Number(requirement.pending ?? 0),
        rejected: Number(requirement.rejected ?? 0),
        status: requirement.status ?? "missing",
        satisfied: Boolean(requirement.satisfied)
      }))
    },
    sections: item.sections ?? []
  };
}

function apiReviewQueueData(item: any): ReviewQueueData {
  return {
    reviewTasks: (item.review_tasks ?? []).map(apiReviewQueueItem),
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiImportBatch(item: any): CsvImportBatch {
  return {
    id: item.id,
    submissionId: item.submission_id,
    dataset: item.dataset,
    fileName: item.file_name,
    rowCount: Number(item.row_count ?? 0),
    status: item.status,
    checksum: item.checksum,
    previewRows: item.preview_rows ?? [],
    idempotentReplay: Boolean(item.idempotent_replay)
  };
}

function apiIntakeErrorReportRow(item: any): IntakeErrorReportRow {
  return {
    source: item.source,
    batchId: item.batch_id,
    dataset: item.dataset,
    fileName: item.file_name,
    rawRecordId: item.raw_record_id,
    row: item.row,
    column: item.column,
    path: item.path,
    code: item.code,
    severity: item.severity,
    message: item.message,
    suggestion: item.suggestion,
    payload: item.payload
  };
}

function apiIntakeErrorReport(item: any): IntakeErrorReport {
  return {
    submissionId: item.submission_id,
    format: item.format,
    summary: {
      errors: Number(item.summary?.errors ?? 0),
      warnings: Number(item.summary?.warnings ?? 0),
      infos: Number(item.summary?.infos ?? 0),
      rows: Number(item.summary?.rows ?? 0)
    },
    rows: (item.rows ?? []).map(apiIntakeErrorReportRow),
    csv: item.csv,
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiPeriodSnapshot(item: any): PeriodSnapshot {
  return {
    businessId: item.business_id,
    organizationId: item.organization_id,
    period: item.period ? apiPeriod({ id: item.period.id ?? "", ...item.period }) : {},
    approvedVersion: item.approved_version,
    approvedAt: item.approved_at,
    latestSubmissionStatus: item.latest_submission_status,
    sections: item.sections ?? {},
    financials: item.financials ?? [],
    products: item.products ?? [],
    evidence: item.evidence ?? [],
    sourceSubmissionIds: item.source_submission_ids ?? [],
    advisoryNotice: item.advisory_notice
  };
}

function apiAuthMe(item: any): AuthMe {
  const capabilities = item.capabilities ?? {};
  const workspaceAccess = item.workspace_access ?? {};
  const allowedViews = Array.isArray(workspaceAccess.allowed_views)
    ? workspaceAccess.allowed_views.filter((view: unknown): view is AppView => typeof view === "string" && APP_VIEW_IDS.has(view as AppView))
    : [];
  const defaultView = typeof workspaceAccess.default_view === "string" && APP_VIEW_IDS.has(workspaceAccess.default_view as AppView)
    ? workspaceAccess.default_view as AppView
    : allowedViews[0] ?? null;
  return {
    tenantId: item.tenant_id,
    actorId: item.actor_id,
    organizationId: item.organization_id,
    organizationIds: item.organization_ids ?? [],
    roles: item.roles ?? [],
    scopes: item.scopes ?? [],
    purpose: item.purpose,
    requestId: item.request_id,
    authAssurance: item.auth_assurance,
    appMode: item.app_mode,
    capabilities: {
      canReadGraph: Boolean(capabilities.can_read_graph),
      canUnmaskGraph: Boolean(capabilities.can_unmask_graph),
      canReadBusiness: Boolean(capabilities.can_read_business),
      canReadFinancials: Boolean(capabilities.can_read_financials),
      canReadEvidence: Boolean(capabilities.can_read_evidence),
      canCreateSubmission: Boolean(capabilities.can_create_submission),
      canUpdateSubmission: Boolean(capabilities.can_update_submission),
      canValidateSubmission: Boolean(capabilities.can_validate_submission),
      canSubmitSubmission: Boolean(capabilities.can_submit_submission),
      canReviewSubmission: Boolean(capabilities.can_review_submission),
      canCreateImportBatch: Boolean(capabilities.can_create_import_batch),
      canReadSupplyMapRegistration: Boolean(capabilities.can_read_supply_map_registration),
      canCreateSupplyMapRegistration: Boolean(capabilities.can_create_supply_map_registration),
      canReviewSupplyMapRegistration: Boolean(capabilities.can_review_supply_map_registration),
      canReadConnectionRequest: Boolean(capabilities.can_read_connection_request),
      canCreateConnectionRequest: Boolean(capabilities.can_create_connection_request),
      canDecideConnectionRequest: Boolean(capabilities.can_decide_connection_request),
      canCreateConsent: Boolean(capabilities.can_create_consent),
      canCreateEvidenceUpload: Boolean(capabilities.can_create_evidence_upload),
      canCreateEvidenceVersion: Boolean(capabilities.can_create_evidence_version),
      canRecordEvidenceScanResult: Boolean(capabilities.can_record_evidence_scan_result),
      canReadInvoice: Boolean(capabilities.can_read_invoice),
      canRegisterInvoiceClaim: Boolean(capabilities.can_register_invoice_claim),
      canTransitionInvoiceClaim: Boolean(capabilities.can_transition_invoice_claim),
      canReadRiskRun: Boolean(capabilities.can_read_risk_run),
      canReadMatchRun: Boolean(capabilities.can_read_match_run),
      canReadScenarioRun: Boolean(capabilities.can_read_scenario_run),
      canReadAudit: Boolean(capabilities.can_read_audit),
      allowedActions: capabilities.allowed_actions ?? []
    },
    workspaceAccess: {
      views: workspaceAccess.views ?? {},
      allowedViews,
      defaultView
    },
    advisoryNotice: item.advisory_notice
  };
}

function apiConsent(item: any): ConsentRecord {
  return {
    consentId: item.consent_id,
    subjectId: item.subject_id,
    recipientId: item.recipient_id,
    scope: item.scope,
    purpose: item.purpose,
    legalBasis: item.legal_basis,
    status: item.status,
    expiresAt: item.expires_at,
    revokedAt: item.revoked_at,
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiEvidenceUploadTicket(item: any): EvidenceUploadTicket {
  return {
    evidenceVersionId: item.evidence_version_id,
    organizationId: item.organization_id,
    periodKey: item.period_key,
    documentType: item.document_type,
    fileName: item.file_name,
    contentType: item.content_type,
    byteSize: item.byte_size === undefined ? undefined : Number(item.byte_size),
    classification: item.classification,
    objectKey: item.object_key,
    uploadUrl: item.upload_url,
    expiresInSeconds: Number(item.expires_in_seconds),
    malwareScanStatus: item.malware_scan_status,
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiPendingEvidenceUpload(item: any): PendingEvidenceUpload {
  return {
    id: item.id ?? item.evidence_version_id,
    businessId: item.businessId ?? item.business_id ?? item.organization_id,
    periodKey: item.periodKey ?? item.period_key ?? "",
    documentType: item.documentType ?? item.document_type ?? "CERTIFICATION",
    fileName: item.fileName ?? item.file_name,
    contentType: item.contentType ?? item.content_type ?? "application/octet-stream",
    byteSize: Number(item.byteSize ?? item.byte_size ?? 0),
    classification: item.classification ?? "confidential",
    status: item.status ?? "upload_ticket_created",
    malwareScanStatus: item.malwareScanStatus ?? item.malware_scan_status ?? "pending_upload",
    evidenceVersionId: item.evidenceVersionId ?? item.evidence_version_id,
    policyDecisionId: item.policyDecisionId ?? item.policy_decision_id,
    auditEventId: item.auditEventId ?? item.audit_event_id,
    advisoryNotice: item.advisoryNotice ?? item.advisory_notice,
    uploadedAt: item.uploadedAt ?? item.uploaded_at ?? new Date().toISOString()
  };
}

function apiEvidenceVersion(item: any): EvidenceVersionRecord {
  return {
    evidenceVersionId: item.evidence_version_id,
    evidenceDocumentId: item.evidence_document_id,
    organizationId: item.organization_id,
    periodKey: item.period_key,
    documentType: item.document_type,
    title: item.title,
    objectKey: item.object_key,
    objectVersion: item.object_version,
    documentHash: item.document_hash,
    malwareScanStatus: item.malware_scan_status,
    objectStorageStatus: item.object_storage_status,
    usable: Boolean(item.usable),
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiEvidenceScanJobResult(item: any): EvidenceScanJobResult {
  return {
    mode: item.mode,
    dryRun: Boolean(item.dry_run),
    candidates: Number(item.candidates ?? 0),
    processed: Number(item.processed ?? 0),
    skipped: Number(item.skipped ?? 0),
    errors: item.errors ?? [],
    organizationId: item.organization_id,
    periodKey: item.period_key,
    scanner: item.scanner,
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiEvidenceDownloadTicket(item: any): EvidenceDownloadTicket {
  return {
    evidenceVersionId: item.evidence_version_id,
    evidenceDocumentId: item.evidence_document_id,
    organizationId: item.organization_id,
    downloadUrl: item.download_url,
    downloadMethod: item.download_method,
    expiresInSeconds: Number(item.expires_in_seconds),
    objectStorageStatus: item.object_storage_status,
    objectVersion: item.object_version,
    documentHash: item.document_hash,
    contentType: item.content_type,
    byteSize: Number(item.byte_size ?? 0),
    malwareScanStatus: item.malware_scan_status,
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    objectAccessId: item.object_access_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiInvoiceClaim(item: any): InvoiceClaim {
  return {
    claimId: item.claim_id,
    sellerId: item.seller_id,
    buyerId: item.buyer_id,
    financierId: item.financier_id,
    invoiceId: item.invoice_id,
    invoiceHash: item.invoice_hash,
    invoiceIdentityHash: item.invoice_identity_hash,
    amount: Number(item.amount),
    currency: item.currency,
    dueDate: item.due_date,
    status: item.status,
    reviewStatus: item.review_status,
    policyDecisionId: item.policy_decision_id,
    auditEventId: item.audit_event_id,
    advisoryNotice: item.advisory_notice
  };
}

function apiAdminOpsData(modelsPayload: any, rulesetsPayload: any, jobsPayload: any): AdminOpsData {
  const models = (modelsPayload.models ?? []).map((item: any) => ({
    id: item.model_registry_id ?? item.id,
    artifactType: item.artifact_type,
    modelVersion: item.model_version,
    name: item.name ?? item.model_version,
    status: item.status,
    config: item.config ?? {},
    createdAt: item.created_at
  }));
  const rulesets = (rulesetsPayload.rulesets ?? []).map((item: any) => ({
    id: item.ruleset_registry_id ?? item.id,
    artifactType: item.artifact_type,
    rulesetVersion: item.ruleset_version,
    name: item.name ?? item.ruleset_version,
    status: item.status,
    config: item.config ?? {},
    createdAt: item.created_at
  }));
  const recomputeJobs = (jobsPayload.jobs ?? []).map((item: any) => ({
    id: item.job_id ?? item.id,
    organizationId: item.organization_id,
    reportingPeriodId: item.reporting_period_id,
    sourceSubmissionId: item.source_submission_id,
    jobType: item.job_type,
    status: item.status,
    attempts: Number(item.attempts ?? 0),
    maxAttempts: Number(item.max_attempts ?? 0),
    lastError: item.last_error,
    payload: item.payload ?? {},
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    availableAt: item.available_at,
    completedAt: item.completed_at
  }));
  return {
    models,
    rulesets,
    recomputeJobs,
    policyDecisionIds: [modelsPayload.policy_decision_id, rulesetsPayload.policy_decision_id, jobsPayload.policy_decision_id].filter(Boolean),
    auditEventIds: [modelsPayload.audit_event_id, rulesetsPayload.audit_event_id, jobsPayload.audit_event_id].filter(Boolean),
    advisoryNotice: jobsPayload.advisory_notice ?? modelsPayload.advisory_notice ?? "Operational decision-support only.",
    access: "authorized"
  };
}

export async function createConnectionRequest(params: { buyerId: string; targetSupplierId: string; disruptedSupplierId?: string | null; purpose?: string }): Promise<ConnectionRequest> {
  const payload = await requestJson("/api/v1/connection-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      buyer_id: params.buyerId,
      target_supplier_id: params.targetSupplierId,
      disrupted_supplier_id: params.disruptedSupplierId ?? null,
      purpose: params.purpose ?? "alternative_supplier_review"
    })
  });
  return apiConnectionRequest(payload.data);
}

export async function getConnectionRequests(limit = 100): Promise<ConnectionRequest[]> {
  try {
    const payload = await requestJson(`/api/v1/connection-requests?limit=${encodeURIComponent(String(limit))}`);
    return (payload.data.connection_requests ?? []).map(apiConnectionRequest);
  } catch (error) {
    return demoFallback(error, () => []);
  }
}

export async function decideConnectionRequest(params: { requestId: string; decision: "grant_consent" | "reject" | "request_changes" | "activate_relationship"; note?: string; contractEvidenceId?: string | null }): Promise<ConnectionRequest> {
  const payload = await requestJson(`/api/v1/connection-requests/${params.requestId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision: params.decision, note: params.note, contract_evidence_id: params.contractEvidenceId ?? null })
  });
  return apiConnectionRequest(payload.data);
}

export async function getSupplyMapRegistrations(): Promise<SupplyMapRegistration[]> {
  try {
    const payload = await requestJson("/api/v1/supply-map-registrations");
    return (payload.data.registrations ?? []).map(apiSupplyMapRegistration);
  } catch (error) {
    return demoFallback(error, () => fallbackSupplyMapRegistrations);
  }
}

export async function createSupplyMapRegistration(params: {
  organizationName: string;
  stakeholderRole: SupplyMapRegistration["stakeholderRole"];
  province: string;
  category: string;
  scale: string;
  contactEmail: string;
  intendedRelationships: string[];
  dataBoundary: string;
}): Promise<SupplyMapRegistration> {
  try {
    const payload = await requestJson("/api/v1/supply-map-registrations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        organization_name: params.organizationName,
        stakeholder_role: params.stakeholderRole,
        province: params.province,
        category: params.category,
        scale: params.scale,
        contact_email: params.contactEmail,
        intended_relationships: params.intendedRelationships,
        data_boundary: params.dataBoundary
      })
    });
    return apiSupplyMapRegistration(payload.data);
  } catch (error) {
    return demoFallback(error, () => {
      const linkedBusinessId = activeDemoAccount.organizationId.startsWith("BIZ-") ? activeDemoAccount.defaultBusinessId : null;
      return {
        id: `REG-${Date.now()}`,
        organizationId: activeDemoAccount.organizationId,
        organizationName: params.organizationName,
        requestedBy: activeDemoAccount.actorId,
        stakeholderRole: params.stakeholderRole,
        province: params.province,
        category: params.category,
        scale: params.scale,
        contactEmail: params.contactEmail,
        intendedRelationships: params.intendedRelationships,
        dataBoundary: params.dataBoundary,
        status: "submitted",
        reviewStatus: "in_review",
        mapVisibility: linkedBusinessId ? "masked_pending_consent" : "not_on_map",
        linkedBusinessId,
        submittedAt: new Date().toISOString(),
        reviewedAt: null,
        reviewerNote: null,
        advisoryNotice: "Submitted for human review; no unmasked graph access is granted by submission alone."
      };
    });
  }
}

export async function decideSupplyMapRegistration(registrationId: string, decision: "approve" | "reject" | "request_changes", note?: string): Promise<SupplyMapRegistration> {
  const payload = await requestJson(`/api/v1/supply-map-registrations/${registrationId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note })
  });
  return apiSupplyMapRegistration(payload.data);
}

export async function getPeriods(businessId: string): Promise<PeriodKey[]> {
  const payload = await requestJson(`/api/v1/periods?business_id=${encodeURIComponent(businessId)}`);
  return (payload.data ?? []).map(apiPeriod);
}

export async function createDataSubmission(businessId: string, periodKey: string, sections: Record<string, unknown>, source: "manual" | "csv" = "manual"): Promise<DataSubmission> {
  const payload = await requestJson("/api/v1/data-submissions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_id: businessId, period_key: periodKey, source, sections })
  });
  return apiSubmission(payload.data);
}

export async function getDataSubmission(submissionId: string): Promise<DataSubmission> {
  const payload = await requestJson(`/api/v1/data-submissions/${submissionId}`);
  return apiSubmission(payload.data);
}

export async function updateDataSubmission(submissionId: string, sections: Record<string, unknown>): Promise<DataSubmission> {
  const payload = await requestJson(`/api/v1/data-submissions/${submissionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sections })
  });
  return apiSubmission(payload.data);
}

export async function createImportBatch(params: { businessId: string; periodKey: string; dataset: string; fileName: string; csvText: string; submissionId?: string | null }): Promise<CsvImportBatch> {
  const payload = await requestJson("/api/v1/import-batches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_id: params.businessId, period_key: params.periodKey, dataset: params.dataset, file_name: params.fileName, csv_text: params.csvText, submission_id: params.submissionId })
  });
  return apiImportBatch(payload.data);
}

export async function validateDataSubmission(submissionId: string): Promise<DataSubmission> {
  const payload = await requestJson(`/api/v1/data-submissions/${submissionId}/validate`, { method: "POST" });
  return apiSubmission(payload.data);
}

export async function getDataSubmissionErrorReport(submissionId: string, format: "json" | "csv" = "json"): Promise<IntakeErrorReport> {
  const payload = await requestJson(`/api/v1/data-submissions/${submissionId}/error-report?format=${encodeURIComponent(format)}`);
  return apiIntakeErrorReport(payload.data);
}

export async function submitDataSubmission(submissionId: string): Promise<DataSubmission> {
  const payload = await requestJson(`/api/v1/data-submissions/${submissionId}/submit`, { method: "POST" });
  return apiSubmission(payload.data);
}

export async function getReviewQueue(status: "open" | "closed" | "all" = "open", limit = 25): Promise<ReviewQueueData> {
  const search = new URLSearchParams({ status, limit: String(limit) });
  const payload = await requestJson(`/api/v1/review-tasks?${search.toString()}`);
  return apiReviewQueueData(payload.data);
}

export async function decideReviewTask(reviewTaskId: string, decision: "approve" | "reject" | "request_changes", note?: string): Promise<DataSubmission> {
  const payload = await requestJson(`/api/v1/review-tasks/${reviewTaskId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note })
  });
  return apiSubmission(payload.data);
}

export async function getPeriodSnapshot(businessId: string, periodKey: string): Promise<PeriodSnapshot> {
  const payload = await requestJson(`/api/v1/businesses/${businessId}/periods/${periodKey}/snapshot`);
  return apiPeriodSnapshot(payload.data);
}

export async function getAuthMe(): Promise<AuthMe> {
  const payload = await requestJson("/api/v1/auth/me");
  return apiAuthMe(payload.data);
}

export async function createConsent(params: { subjectId: string; recipientId: string; scope: string; purpose: string; legalBasis?: string; expiresAt?: string | null; evidenceReference?: string | null }): Promise<ConsentRecord> {
  const payload = await requestJson("/api/v1/consents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject_id: params.subjectId, recipient_id: params.recipientId, scope: params.scope, purpose: params.purpose, legal_basis: params.legalBasis ?? "contract_or_explicit_consent", expires_at: params.expiresAt, evidence_reference: params.evidenceReference })
  });
  return apiConsent(payload.data);
}

export async function revokeConsent(consentId: string): Promise<ConsentRecord> {
  const payload = await requestJson(`/api/v1/consents/${consentId}/revoke`, { method: "POST" });
  return apiConsent(payload.data);
}

export async function createEvidenceUploadTicket(params: { organizationId: string; fileName: string; contentType: string; byteSize: number; documentType?: string; periodKey?: string | null; classification?: string; purpose?: string }): Promise<EvidenceUploadTicket> {
  const payload = await requestJson("/api/v1/evidence/upload-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization_id: params.organizationId, file_name: params.fileName, document_type: params.documentType ?? "CERTIFICATION", period_key: params.periodKey, content_type: params.contentType, byte_size: params.byteSize, classification: params.classification ?? "confidential", purpose: params.purpose ?? "evidence_intake" })
  });
  return apiEvidenceUploadTicket(payload.data);
}

export async function getPendingEvidenceUploads(organizationId: string, periodKey?: string | null): Promise<PendingEvidenceUpload[]> {
  const search = new URLSearchParams({ organization_id: organizationId });
  if (periodKey) search.set("period_key", periodKey);
  const payload = await requestJson(`/api/v1/evidence/upload-tickets?${search.toString()}`);
  return (payload.data.tickets ?? []).map(apiPendingEvidenceUpload);
}

export async function completeEvidenceUploadTicket(evidenceVersionId: string, params: { organizationId: string; documentHash: string; malwareScanStatus?: "pending_scan" | "clean" | "infected" | "failed"; title?: string | null; contentBase64?: string | null }): Promise<EvidenceVersionRecord> {
  const payload = await requestJson(`/api/v1/evidence/upload-tickets/${evidenceVersionId}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization_id: params.organizationId, document_hash: params.documentHash, malware_scan_status: params.malwareScanStatus ?? "pending_scan", title: params.title, content_base64: params.contentBase64 })
  });
  return apiEvidenceVersion(payload.data);
}

export async function createEvidenceVersion(evidenceDocumentId: string, params: { organizationId: string; objectKey: string; documentHash: string; contentType: string; byteSize: number; malwareScanStatus?: string; supersedesVersionId?: string | null }): Promise<EvidenceVersionRecord> {
  const payload = await requestJson(`/api/v1/evidence/${evidenceDocumentId}/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization_id: params.organizationId, object_key: params.objectKey, document_hash: params.documentHash, content_type: params.contentType, byte_size: params.byteSize, malware_scan_status: params.malwareScanStatus ?? "pending_scan", supersedes_version_id: params.supersedesVersionId })
  });
  return apiEvidenceVersion(payload.data);
}

export async function runEvidenceScanJob(params: { organizationId: string; periodKey?: string | null; limit?: number; scanner?: "local_demo" | "fail_closed"; dryRun?: boolean }): Promise<EvidenceScanJobResult> {
  const payload = await requestJson("/api/v1/evidence/scan-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization_id: params.organizationId, period_key: params.periodKey, limit: params.limit ?? 20, scanner: params.scanner ?? "local_demo", dry_run: params.dryRun ?? false })
  });
  return apiEvidenceScanJobResult(payload.data);
}

export async function createEvidenceDownloadTicket(evidenceVersionId: string): Promise<EvidenceDownloadTicket> {
  const payload = await requestJson(`/api/v1/evidence/versions/${evidenceVersionId}/download-url`, { method: "POST" });
  return apiEvidenceDownloadTicket(payload.data);
}

export async function createInvoiceClaim(params: { sellerId: string; buyerId: string; financierId: string; invoiceHash: string; amount: number; dueDate: string; invoiceId?: string | null; issueDate?: string | null; currency?: string; idempotencyKey?: string | null; sourceEvidenceId?: string | null }): Promise<InvoiceClaim> {
  const payload = await requestJson("/api/v1/invoice-claims", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seller_id: params.sellerId, buyer_id: params.buyerId, financier_id: params.financierId, invoice_hash: params.invoiceHash, amount: params.amount, due_date: params.dueDate, invoice_id: params.invoiceId, issue_date: params.issueDate, currency: params.currency ?? "VND", idempotency_key: params.idempotencyKey, source_evidence_id: params.sourceEvidenceId })
  });
  return apiInvoiceClaim(payload.data);
}

export async function transitionInvoiceClaim(claimId: string, status: "verified" | "pledged" | "financed" | "released" | "disputed", note?: string): Promise<InvoiceClaim> {
  const payload = await requestJson(`/api/v1/invoice-claims/${claimId}/transition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, note })
  });
  return apiInvoiceClaim(payload.data);
}

export async function getRiskRuns(organizationId: string, periodKey?: string): Promise<RiskRunsData> {
  const search = new URLSearchParams({ organization_id: organizationId });
  if (periodKey) search.set("period", periodKey);
  const payload = await requestJson(`/api/v1/risk-runs?${search.toString()}`);
  return { organizationId: payload.data.organization_id, periodKey: payload.data.period_key, riskRuns: payload.data.risk_runs ?? [], policyDecisionId: payload.data.policy_decision_id, advisoryNotice: payload.data.advisory_notice };
}

export async function getMatchRuns(organizationId: string, periodKey?: string): Promise<MatchRunsData> {
  const search = new URLSearchParams({ organization_id: organizationId });
  if (periodKey) search.set("period", periodKey);
  const payload = await requestJson(`/api/v1/match-runs?${search.toString()}`);
  return { organizationId: payload.data.organization_id, periodKey: payload.data.period_key, matchRuns: payload.data.match_runs ?? [], policyDecisionId: payload.data.policy_decision_id, advisoryNotice: payload.data.advisory_notice };
}

export async function getAdminOps(organizationId?: string): Promise<AdminOpsData> {
  const init = demoAdminOpsInit();
  const jobsSearch = new URLSearchParams({ limit: "20" });
  if (organizationId) jobsSearch.set("organization_id", organizationId);
  try {
    const [models, rulesets, jobs] = await Promise.all([
      requestJson("/api/v1/admin/model-registry", init),
      requestJson("/api/v1/admin/ruleset-registry", init),
      requestJson(`/api/v1/admin/recompute-jobs?${jobsSearch.toString()}`, init)
    ]);
    return apiAdminOpsData(models.data, rulesets.data, jobs.data);
  } catch (error) {
    return demoFallback(error, () => ({
      models: [],
      rulesets: [],
      recomputeJobs: [],
      policyDecisionIds: [],
      auditEventIds: [],
      advisoryNotice: "Ops registry requires demo_admin/system_admin read_ops policy.",
      access: "fallback"
    }));
  }
}

export async function getAudit(): Promise<AuditData> {
  try {
    const payload = await requestJson("/api/v1/audit");
    const data = payload.data;
    return { events: (data.events ?? []).map((item: any): AuditEvent => ({ eventId: item.event_id, eventType: item.event_type, actorId: item.actor_id, actorRole: item.actor_role, subjectId: item.subject_id, purpose: item.purpose, timestamp: item.timestamp })), connectionRequests: (data.connection_requests ?? []).map(apiConnectionRequest), dataScope: data.data_scope };
  } catch (error) {
    return demoFallback(error, () => ({ events: [{ eventId: "AUD-DEMO", eventType: "EVIDENCE_VAULT_VIEWED", actorId: "demo-user", actorRole: "demo_operator", subjectId: "BIZ-005", purpose: "evidence_review", timestamp: new Date().toISOString() }], connectionRequests: [{ requestId: "REQ-DEMO-001", buyerId: "BIZ-009", targetSupplierId: "BIZ-007", disruptedSupplierId: "BIZ-005", status: "pending", consentStatus: "awaiting_supplier_consent", requestedAt: new Date().toISOString() }], dataScope: "Synthetic fallback audit trail." }));
  }
}
