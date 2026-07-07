export type BusinessType =
  | "manufacturer"
  | "distributor"
  | "wholesaler"
  | "retailer"
  | "logistics_partner"
  | "financial_partner";
export type RiskLevel = "green" | "yellow" | "red";
export type AppView = "overview" | "map" | "companies" | "intake" | "onboarding" | "risk" | "matching" | "finance" | "invoice" | "audit";

export type DemoStakeholderRole =
  | "demo_operator"
  | "sme_submitter"
  | "buyer_admin"
  | "supplier_admin"
  | "org_admin"
  | "reviewer"
  | "network_analyst"
  | "lender"
  | "system_admin";

export interface DemoAccount {
  id: string;
  personName: string;
  label: string;
  stakeholder: string;
  organizationId: string;
  organizationName: string;
  actorId: string;
  actorRole: DemoStakeholderRole;
  purpose: string;
  scopes: string[];
  defaultBusinessId: string;
  allowedViews: AppView[];
  description: string;
}

export interface SupplyMapRegistration {
  id: string;
  organizationId: string;
  organizationName: string;
  requestedBy: string;
  stakeholderRole: BusinessType;
  province: string;
  category: string;
  scale: string;
  contactEmail: string;
  intendedRelationships: string[];
  dataBoundary: string;
  status: "draft" | "submitted" | "changes_requested" | "approved" | "rejected";
  reviewStatus: "not_started" | "in_review" | "approved" | "changes_requested" | "rejected";
  mapVisibility: "not_on_map" | "masked_pending_consent" | "visible_demo_node";
  linkedBusinessId?: string | null;
  submittedAt: string;
  reviewedAt?: string | null;
  reviewerNote?: string | null;
  advisoryNotice: string;
}

export type DemoAccessStatus = "owner" | "consented" | "pending_consent" | "masked" | "ops_review";

export interface DemoAccessDecision {
  businessId: string;
  status: DemoAccessStatus;
  visibility: "own_data" | "consented_partner" | "masked_summary" | "review_queue";
  purpose: string;
  reason: string;
  allowedFields: string[];
  blockedFields: string[];
  updatedAt: string;
}

export interface BusinessNode {
  id: string;
  name: string;
  type: BusinessType;
  province: string;
  category: string;
  lat: number;
  lng: number;
  revenue: number;
  capacity: number;
  health: number;
  risk: number;
  scale?: string;
}

export interface SupplyEdge {
  id: string;
  sourceId: string;
  targetId: string;
  category: string;
  volume: number;
  leadTimeDays: number;
  reliability: number;
  relationType?: "supply" | "logistics" | "guarantee" | "finance";
}

export interface RiskDriver {
  label: string;
  value: number;
  note: string;
}

export interface Recommendation {
  supplierId: string;
  supplierName: string;
  score: number;
  leadTimeDays: number;
  reasons: string[];
  components: Record<string, number>;
  periodKey?: string | null;
  advisoryNotice?: string;
}

export interface ShockState {
  active: boolean;
  shockNodeId: string;
  affectedNodeIds: string[];
  affectedEdgeIds: string[];
  affectedSmeCount: number;
  monthlyVolumeAtRisk: number;
  revenueAtRisk: number;
  avgStockoutDays: number;
  advisoryNotice?: string;
}

export interface OverviewMetrics {
  activeCompanies: number;
  atRiskNodes: number;
  affectedSmes: number;
  supplyHealthScore: number;
  monthlyNetworkVolume: number;
  advisoryNotice: string;
}

export interface AlertItem {
  id: string;
  severity: "high" | "medium" | "info";
  title: string;
  detail: string;
  age: string;
  businessId?: string | null;
}

export interface DashboardData {
  overview: OverviewMetrics;
  disruptionTrend: Array<{ month: string; total: number; highCritical: number }>;
  regionalFlow: Array<{ region: string; volume: number; share: number }>;
  recentAlerts: AlertItem[];
  riskyBusinesses: BusinessNode[];
  dataScope: string;
}

export interface ScenarioData {
  id: string;
  name: string;
  nodes: BusinessNode[];
  edges: SupplyEdge[];
  roleCoverage: Record<string, string[]>;
  dataScope: string;
}

export interface BusinessDetail {
  business: BusinessNode;
  products: Array<Record<string, string | number>>;
  risk: {
    score: number;
    level: string;
    formulaVersion: string;
    drivers: RiskDriver[];
    explanation: string;
    advisoryNotice: string;
  };
  financialSummary: Record<string, number | string> | null;
  dependencySummary: { downstreamBusinessCount: number; monthlyVolumeSupplied: number };
  evidenceSummary: { total: number; verified: number; byType: Record<string, number> };
}

export interface EvidenceDocument {
  id: string;
  type: "CONTRACT" | "PURCHASE_ORDER" | "DELIVERY_NOTE" | "CERTIFICATION" | "GUARANTEE" | "INVOICE";
  title: string;
  status: string;
  verificationStatus: string;
  effectiveDate: string;
  expiryDate: string | null;
  source: string;
  hash: string;
  facts: string[];
  evidenceVersionId?: string | null;
  downloadable?: boolean;
}

export interface EvidenceVault {
  businessId: string;
  documents: EvidenceDocument[];
  summary: { total: number; verified: number; needsReview: number };
  dataScope: string;
}

export interface PendingEvidenceUpload {
  id: string;
  businessId: string;
  periodKey: string;
  documentType: EvidenceDocument["type"];
  fileName: string;
  contentType: string;
  byteSize: number;
  classification: string;
  status: string;
  malwareScanStatus: string;
  evidenceVersionId?: string | null;
  policyDecisionId?: string | null;
  auditEventId?: string | null;
  advisoryNotice?: string | null;
  uploadedAt: string;
}

export interface RiskSignal {
  id: string;
  businessId: string;
  riskType: string;
  level: string;
  confidence: number;
  summary: string;
  triggers: Array<{ rule: string; observed: number; threshold: number; result: string }>;
  evidenceIds: string[];
  evidence: EvidenceDocument[];
  suggestedActions: string[];
  formulaVersion: string;
  evidenceScope?: "linked_evidence_visible" | "evidence_blocked_by_policy" | string | null;
  policyDecisionId?: string | null;
  auditEventId?: string | null;
  disclaimer: string;
}

export interface FinancePoint {
  month: string;
  cashIn: number;
  cashOut: number;
  netCashFlow: number;
  revenue: number;
  debt: number;
  accountsReceivable: number;
  accountsPayable: number;
  inventoryValue: number;
  workingCapital: number;
  cashflowMargin: number;
  receivableDaysProxy: number;
  inventoryDaysProxy: number;
  debtToMonthlyRevenue: number;
  latePaymentRate: number;
  deliveryDelayRate: number;
}

export interface FinanceData {
  business: BusinessNode;
  health: {
    score: number;
    level: string;
    components: Record<string, number>;
    formulaVersion: string;
    explanation: string;
  };
  latest: FinancePoint | null;
  previous: FinancePoint | null;
  series: FinancePoint[];
  accessScope?: string;
  dataScope?: string;
  policyDecisionId?: string;
  advisoryNotice: string;
}

export interface InvoiceVerificationData {
  invoiceId: string;
  sellerId: string;
  requesterId?: string;
  buyerId: string;
  amount: number;
  issueDate: string;
  dueDate: string;
  storedHash: string;
  computedHash: string;
  fundingStatus: string;
  confirmedBy: string[];
  doubleFinancingAlert: boolean;
  accessScope?: string;
  dataScope?: string;
  policyDecisionId?: string;
  advisoryNotice: string;
}

export interface AuditEvent {
  eventId: string;
  eventType: string;
  actorId: string;
  actorRole: string;
  subjectId: string;
  purpose: string;
  timestamp: string;
}

export interface ConnectionRequest {
  requestId: string;
  requesterId?: string | null;
  buyerId: string;
  targetSupplierId: string;
  disruptedSupplierId?: string;
  status: string;
  consentStatus: string;
  requestedAt: string;
  decidedAt?: string | null;
  decidedBy?: string | null;
  decisionNote?: string | null;
  contractEvidenceId?: string | null;
  relationshipId?: string | null;
  relationshipEdgeId?: string | null;
  policyDecisionId?: string | null;
  auditEventId?: string | null;
  nextStep?: string;
  advisoryNotice?: string;
}

export interface AuditData {
  events: AuditEvent[];
  connectionRequests: ConnectionRequest[];
  dataScope: string;
}

export type SubmissionStatus =
  | "draft"
  | "ready"
  | "submitted"
  | "in_review"
  | "changes_requested"
  | "approved"
  | "rejected"
  | "superseded";

export type IntakeSection =
  | "profile"
  | "financials"
  | "products"
  | "evidence"
  | "inventory"
  | "supply_edges"
  | "purchase_orders"
  | "delivery_notes"
  | "certifications"
  | "invoices"
  | "guarantees";

export interface PeriodKey {
  id: string;
  periodType: "month";
  periodKey: string;
  periodStart: string;
  periodEnd: string;
  status: string;
  latestSubmissionStatus?: string | null;
}

export interface ValidationIssue {
  id: string;
  section: string;
  path: string;
  row?: number | null;
  column?: string | null;
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  suggestion?: string | null;
}

export interface ReviewTask {
  id: string;
  status: string;
  assignedRole: string;
  assignedTo?: string | null;
  assignmentReason?: string | null;
  assignedAt?: string | null;
  decision?: string | null;
  decisionNote?: string | null;
}

export interface DataSubmission {
  id: string;
  businessId: string;
  organizationId: string;
  period: PeriodKey;
  source: "manual" | "csv" | "seed";
  status: SubmissionStatus;
  version: number;
  sections: Record<string, { status: string; payload: unknown; updatedAt: string }>;
  issues: ValidationIssue[];
  validationSummary: { errors: number; warnings: number; infos: number };
  reviewTask?: ReviewTask | null;
  advisoryNotice: string;
}

export interface ReviewQueueItem {
  reviewTaskId: string;
  submissionId: string;
  organizationId: string;
  organizationName: string;
  periodKey: string;
  periodStart: string;
  periodEnd: string;
  reviewStatus: string;
  assignedRole: string;
  assignedTo?: string | null;
  assignmentReason?: string | null;
  assignedAt?: string | null;
  submissionStatus: SubmissionStatus;
  source: "manual" | "csv" | "seed";
  version: number;
  submittedBy: string;
  submittedAt?: string | null;
  updatedAt: string;
  validationSummary: { errors: number; warnings: number; infos: number };
  evidenceReview: {
    total: number;
    clean: number;
    pending: number;
    rejected: number;
    required: boolean;
    approvalBlocked: boolean;
    advisory: string;
    requirements: Array<{
      documentType: EvidenceDocument["type"] | string;
      title: string;
      section: string;
      total: number;
      clean: number;
      pending: number;
      rejected: number;
      status: "verified" | "pending" | "rejected" | "missing" | string;
      satisfied: boolean;
    }>;
  };
  sections: Array<{ section: string; status: string }>;
}

export interface ReviewQueueData {
  reviewTasks: ReviewQueueItem[];
  policyDecisionId: string;
  auditEventId: string;
  advisoryNotice: string;
}

export interface CsvImportBatch {
  id: string;
  submissionId: string;
  dataset: string;
  fileName: string;
  rowCount: number;
  status: string;
  checksum: string;
  previewRows: Array<Record<string, string>>;
  idempotentReplay: boolean;
}

export interface IntakeErrorReportRow {
  source: string;
  batchId?: string | null;
  dataset?: string | null;
  fileName?: string | null;
  rawRecordId?: string | null;
  row?: number | null;
  column?: string | null;
  path?: string | null;
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  suggestion?: string | null;
  payload?: Record<string, unknown>;
}

export interface IntakeErrorReport {
  submissionId: string;
  format: "json" | "csv";
  summary: { errors: number; warnings: number; infos: number; rows: number };
  rows: IntakeErrorReportRow[];
  csv?: string | null;
  policyDecisionId: string;
  auditEventId: string;
  advisoryNotice: string;
}

export interface PeriodSnapshot {
  businessId: string;
  organizationId: string;
  period: Partial<PeriodKey> & { periodKey?: string };
  approvedVersion?: number | null;
  approvedAt?: string | null;
  reviewDecision?: {
    reviewTaskId: string;
    assignedTo?: string | null;
    assignmentReason?: string | null;
    decidedBy?: string | null;
    decision?: string | null;
    decisionNote?: string | null;
    decidedAt?: string | null;
  } | null;
  reviewHistory?: Array<{
    reviewTaskId: string;
    submissionId: string;
    reviewStatus?: string | null;
    assignedTo?: string | null;
    assignmentReason?: string | null;
    assignedAt?: string | null;
    decidedBy?: string | null;
    decision?: string | null;
    decisionNote?: string | null;
    decidedAt?: string | null;
    createdAt?: string | null;
    submissionStatus?: string | null;
    source?: string | null;
    version?: number | null;
    submittedAt?: string | null;
  }>;
  latestSubmissionStatus?: string | null;
  sections: Record<string, unknown>;
  financials: Array<Record<string, number | string | null>>;
  products: Array<Record<string, number | string | null>>;
  evidence: Array<Record<string, number | string | null>>;
  sourceSubmissionIds: string[];
  advisoryNotice: string;
}

export interface AuthCapabilities {
  canReadGraph: boolean;
  canUnmaskGraph: boolean;
  canReadBusiness: boolean;
  canReadFinancials: boolean;
  canReadEvidence: boolean;
  canCreateSubmission: boolean;
  canUpdateSubmission: boolean;
  canValidateSubmission: boolean;
  canSubmitSubmission: boolean;
  canReviewSubmission: boolean;
  canCreateImportBatch: boolean;
  canReadSupplyMapRegistration: boolean;
  canCreateSupplyMapRegistration: boolean;
  canReviewSupplyMapRegistration: boolean;
  canReadConnectionRequest: boolean;
  canCreateConnectionRequest: boolean;
  canDecideConnectionRequest: boolean;
  canCreateConsent: boolean;
  canCreateEvidenceUpload: boolean;
  canCreateEvidenceVersion: boolean;
  canRecordEvidenceScanResult: boolean;
  canReadInvoice: boolean;
  canRegisterInvoiceClaim: boolean;
  canTransitionInvoiceClaim: boolean;
  canReadRiskRun: boolean;
  canReadMatchRun: boolean;
  canReadScenarioRun: boolean;
  canReadAudit: boolean;
  allowedActions: string[];
}

export interface AuthWorkspaceAccess {
  views: Partial<Record<AppView, boolean>>;
  allowedViews: AppView[];
  defaultView?: AppView | null;
}

export interface AuthMe {
  tenantId: string;
  actorId: string;
  organizationId: string;
  organizationIds: string[];
  roles: string[];
  scopes: string[];
  purpose: string;
  requestId: string;
  authAssurance: string;
  appMode: string;
  capabilities: AuthCapabilities;
  workspaceAccess: AuthWorkspaceAccess;
  advisoryNotice: string;
}

export interface ConsentRecord {
  consentId: string;
  subjectId: string;
  recipientId: string;
  scope: string;
  purpose: string;
  legalBasis: string;
  status: string;
  expiresAt?: string | null;
  revokedAt?: string | null;
  policyDecisionId: string;
  auditEventId?: string | null;
  advisoryNotice: string;
}

export interface EvidenceUploadTicket {
  evidenceVersionId: string;
  organizationId: string;
  periodKey?: string | null;
  documentType?: EvidenceDocument["type"];
  fileName?: string;
  contentType?: string;
  byteSize?: number;
  classification?: string;
  objectKey?: string;
  uploadUrl: string;
  expiresInSeconds: number;
  malwareScanStatus: string;
  policyDecisionId: string;
  auditEventId: string;
  advisoryNotice: string;
}

export interface EvidenceVersionRecord {
  evidenceVersionId: string;
  evidenceDocumentId: string;
  organizationId: string;
  periodKey?: string | null;
  documentType?: EvidenceDocument["type"] | string;
  title?: string;
  objectKey?: string;
  objectVersion: string;
  documentHash: string;
  malwareScanStatus: string;
  objectStorageStatus?: string;
  usable: boolean;
  policyDecisionId: string;
  auditEventId: string;
  advisoryNotice: string;
}

export interface EvidenceScanJobResult {
  mode: string;
  dryRun: boolean;
  candidates: number;
  processed: number;
  skipped: number;
  errors: string[];
  organizationId: string;
  periodKey?: string | null;
  scanner: "local_demo" | "fail_closed" | string;
  policyDecisionId: string;
  auditEventId: string;
  advisoryNotice: string;
}

export interface EvidenceDownloadTicket {
  evidenceVersionId: string;
  evidenceDocumentId: string;
  organizationId: string;
  downloadUrl: string;
  downloadMethod: "GET";
  expiresInSeconds: number;
  objectStorageStatus: string;
  objectVersion: string;
  documentHash: string;
  contentType: string;
  byteSize: number;
  malwareScanStatus: string;
  policyDecisionId: string;
  auditEventId: string;
  objectAccessId: string;
  advisoryNotice: string;
}

export interface InvoiceClaim {
  claimId: string;
  sellerId: string;
  buyerId: string;
  financierId: string;
  invoiceId?: string | null;
  invoiceHash: string;
  invoiceIdentityHash: string;
  amount: number;
  currency: string;
  dueDate: string;
  status: string;
  reviewStatus: string;
  policyDecisionId: string;
  auditEventId?: string | null;
  advisoryNotice: string;
}

export interface RiskRunsData {
  organizationId: string;
  periodKey?: string | null;
  riskRuns: Array<Record<string, unknown>>;
  policyDecisionId: string;
  advisoryNotice: string;
}

export interface MatchRunsData {
  organizationId: string;
  periodKey?: string | null;
  matchRuns: Array<Record<string, unknown>>;
  policyDecisionId: string;
  advisoryNotice: string;
}

export interface ModelRegistryItem {
  id: string;
  artifactType: string;
  modelVersion: string;
  name: string;
  status: string;
  config: Record<string, unknown>;
  createdAt?: string | null;
}

export interface RulesetRegistryItem {
  id: string;
  artifactType: string;
  rulesetVersion: string;
  name: string;
  status: string;
  config: Record<string, unknown>;
  createdAt?: string | null;
}

export interface RecomputeJobItem {
  id: string;
  organizationId: string;
  reportingPeriodId?: string | null;
  sourceSubmissionId?: string | null;
  jobType: string;
  status: string;
  attempts: number;
  maxAttempts: number;
  lastError?: string | null;
  payload: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
  availableAt?: string | null;
  completedAt?: string | null;
}

export interface AdminOpsData {
  models: ModelRegistryItem[];
  rulesets: RulesetRegistryItem[];
  recomputeJobs: RecomputeJobItem[];
  policyDecisionIds: string[];
  auditEventIds: string[];
  advisoryNotice: string;
  access: "authorized" | "fallback";
}
