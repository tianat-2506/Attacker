import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  Bell,
  Building2,
  CalendarDays,
  ChevronDown,
  FileCheck2,
  FileSearch,
  Handshake,
  Home,
  Landmark,
  Map,
  Network,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  UserRoundCheck,
  UserRoundPlus
} from "lucide-react";
import {
  completeEvidenceUploadTicket,
  createConnectionRequest,
  createDataSubmission,
  createEvidenceDownloadTicket,
  createEvidenceUploadTicket,
  createImportBatch,
  createSupplyMapRegistration,
  decideConnectionRequest,
  decideSupplyMapRegistration,
  decideReviewTask,
  getAdminOps,
  getAudit,
  getAuthMe,
  getBusinessDetail,
  getConnectionRequests,
  getDashboard,
  getDataSubmission,
  getDataSubmissionErrorReport,
  getEvidence,
  getFinance,
  getGraph,
  getInvoiceVerification,
  getPendingEvidenceUploads,
  getPeriodSnapshot,
  getPeriods,
  getRecommendations,
  getReviewQueue,
  getRiskSignal,
  getScenario,
  getSupplyMapRegistrations,
  runEvidenceScanJob,
  setDemoAccountContext,
  simulateShock,
  submitDataSubmission,
  updateDataSubmission,
  validateDataSubmission
} from "./api/client";
import {
  AuditWorkspace,
  CompaniesWorkspace,
  DataIntakeWorkspace,
  FinanceWorkspace,
  InvoiceWorkspace,
  MapWorkspace,
  MatchingWorkspace,
  OnboardingWorkspace,
  OverviewWorkspace,
  RiskWorkspace
} from "./components/WorkspaceViews";
import { businesses as fallbackBusinesses, defaultShock, edges as fallbackEdges, recommendations as fallbackRecommendations } from "./utils/demoData";
import { accountCanBrowseNetwork, accountCanReadOwnBusiness, accountHasAnyRole, defaultDemoAccount, demoAccounts, firstAllowedView, getDemoAccountById, scopedBusinessNodesForAccount } from "./utils/demoAccounts";
import { canLoadInvoiceWorkspace, invoiceIdForWorkspace } from "./utils/invoiceSelection";
import { canRequestRiskSignal } from "./utils/accessDecision";
import { mergePendingEvidenceUploadsForPeriod } from "./utils/pendingEvidenceUploads";
import { readWorkspaceUrlState, workspaceSearchWithState } from "./utils/workspaceUrlState";
import {
  canLoadAuditWorkspaceForView,
  canLoadBusinessDetailForView,
  canLoadConnectionRequestsForView,
  canLoadEvidenceVaultForView,
  canLoadFinanceForView,
  canLoadGraphForView,
  canLoadIntakePeriodContextForView,
  canLoadRecommendationsForView,
  canLoadReviewQueueForView,
  canLoadRiskSignalForView,
  canLoadSupplyMapRegistrationsForView
} from "./utils/workspaceDataLoading";
import type {
  AppView,
  AdminOpsData,
  AuditData,
  AuthMe,
  BusinessDetail,
  BusinessNode,
  ConnectionRequest,
  CsvImportBatch,
  DashboardData,
  DataSubmission,
  DemoAccessDecision,
  EvidenceDocument,
  EvidenceDownloadTicket,
  EvidenceScanJobResult,
  EvidenceVault,
  FinanceData,
  IntakeErrorReport,
  InvoiceVerificationData,
  PendingEvidenceUpload,
  PeriodKey,
  PeriodSnapshot,
  Recommendation,
  ReviewQueueItem,
  RiskSignal,
  ScenarioData,
  ShockState,
  SupplyMapRegistration,
  SupplyEdge
} from "./types";

const navItems: Array<{ id: AppView; label: string; icon: ReactNode }> = [
  { id: "overview", label: "Overview", icon: <Home size={18} /> },
  { id: "map", label: "Supply Map", icon: <Map size={18} /> },
  { id: "companies", label: "Companies & Evidence", icon: <Building2 size={18} /> },
  { id: "intake", label: "Data Intake", icon: <FileCheck2 size={18} /> },
  { id: "onboarding", label: "Onboarding", icon: <UserRoundPlus size={18} /> },
  { id: "risk", label: "Risk Analysis", icon: <ShieldCheck size={18} /> },
  { id: "matching", label: "Matching", icon: <Handshake size={18} /> },
  { id: "finance", label: "Finance", icon: <Landmark size={18} /> },
  { id: "invoice", label: "Invoice Review", icon: <FileCheck2 size={18} /> },
  { id: "audit", label: "Audit Trail", icon: <FileSearch size={18} /> }
];

const validAccountIds = new Set(demoAccounts.map((account) => account.id));
const validViewIds = new Set(navItems.map((item) => item.id));
const initialWorkspaceUrlState = typeof window === "undefined"
  ? {}
  : readWorkspaceUrlState(window.location.search, validAccountIds, validViewIds);

function initialPeriodKey() {
  return initialWorkspaceUrlState.period ?? "2026-06";
}

function initialDemoAccountId() {
  if (typeof window === "undefined") return defaultDemoAccount.id;
  return initialWorkspaceUrlState.accountId ?? window.localStorage.getItem("vietsupply.demoAccountId") ?? defaultDemoAccount.id;
}

function initialSelectedBusinessId() {
  return initialWorkspaceUrlState.businessId ?? getDemoAccountById(initialDemoAccountId()).defaultBusinessId;
}

function initialViewId() {
  const account = getDemoAccountById(initialDemoAccountId());
  return initialWorkspaceUrlState.view && account.allowedViews.includes(initialWorkspaceUrlState.view)
    ? initialWorkspaceUrlState.view
    : firstAllowedView(account);
}

const frontendAppMode = import.meta.env.VITE_APP_MODE ?? "demo";
const DEMO_DISRUPTED_SUPPLIER_ID = "BIZ-005";

async function evidenceUploadPayload(file: File) {
  const buffer = await file.arrayBuffer();
  const documentHash = typeof crypto === "undefined" || !crypto.subtle
    ? null
    : Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer))).map((byte) => byte.toString(16).padStart(2, "0")).join("");
  if (typeof btoa === "undefined") return { documentHash, contentBase64: null };
  const bytes = new Uint8Array(buffer);
  const chunks: string[] = [];
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    chunks.push(String.fromCharCode(...bytes.subarray(index, index + chunkSize)));
  }
  return { documentHash, contentBase64: btoa(chunks.join("")) };
}

const initialSupplyMapRegistrations: SupplyMapRegistration[] = [
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

function demoCoordinatesForProvince(province: string) {
  if (province === "Binh Duong") return { lat: 10.9804, lng: 106.6519 };
  if (province === "Dong Nai") return { lat: 10.9453, lng: 106.8246 };
  if (province === "Lam Dong") return { lat: 11.5753, lng: 108.1429 };
  return { lat: 10.7769, lng: 106.7009 };
}

function demoAccessDecisionFor(account: ReturnType<typeof getDemoAccountById>, businessId: string, request: ConnectionRequest | null): DemoAccessDecision {
  const now = new Date().toISOString();
  const isOwnOrganization = account.organizationId === businessId || account.defaultBusinessId === businessId;
  if (isOwnOrganization) {
    return {
      businessId,
      status: "owner",
      visibility: "own_data",
      purpose: account.purpose,
      reason: "Own-organization workspace.",
      allowedFields: ["profile", "products", "own evidence", "own period submissions"],
      blockedFields: ["counterparty confidential financials", "unconsented contacts"],
      updatedAt: now
    };
  }
  if (["demo_operator", "reviewer", "system_admin"].includes(account.actorRole)) {
    return {
      businessId,
      status: "ops_review",
      visibility: "review_queue",
      purpose: account.purpose,
      reason: "Operational/reviewer demo visibility; production access still requires policy decision and audit.",
      allowedFields: ["masked profile", "review status", "audit correlation"],
      blockedFields: ["raw financials", "object storage paths", "commercial terms"],
      updatedAt: now
    };
  }
  if (request?.targetSupplierId === businessId && request.consentStatus.includes("awaiting")) {
    return {
      businessId,
      status: "pending_consent",
      visibility: "masked_summary",
      purpose: "supplier_introduction_review",
      reason: `Connection request ${request.requestId} is waiting for supplier consent.`,
      allowedFields: ["masked profile", "shortlist rationale", "request status"],
      blockedFields: ["contact details", "commercial graph", "financials", "documents"],
      updatedAt: request.requestedAt
    };
  }
  if (account.actorRole === "network_analyst" || account.actorRole === "lender" || account.actorRole === "org_admin" || account.actorRole === "buyer_admin" || account.actorRole === "supplier_admin") {
    return {
      businessId,
      status: "masked",
      visibility: "masked_summary",
      purpose: account.purpose,
      reason: "Cross-organization data is masked until relationship, consent and purpose checks pass.",
      allowedFields: ["masked profile", "high-level risk signal", "non-sensitive category"],
      blockedFields: ["legal name if masked", "financials", "evidence documents", "relationship volumes", "contact details"],
      updatedAt: now
    };
  }
  return {
    businessId,
    status: "masked",
    visibility: "masked_summary",
    purpose: account.purpose,
    reason: "Default masked view.",
    allowedFields: ["masked profile"],
    blockedFields: ["sensitive commercial data"],
    updatedAt: now
  };
}

export default function App() {
  const previousAccountId = useRef<string | null>(null);
  const [activeView, setActiveView] = useState<AppView>(initialViewId);
  const [activeAccountId, setActiveAccountId] = useState(initialDemoAccountId);
  const [allNodes, setAllNodes] = useState<BusinessNode[]>(fallbackBusinesses);
  const [allEdges, setAllEdges] = useState<SupplyEdge[]>(fallbackEdges);
  const [scenario, setScenario] = useState<ScenarioData | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [selectedId, setSelectedId] = useState(initialSelectedBusinessId);
  const [detail, setDetail] = useState<BusinessDetail | null>(null);
  const [evidence, setEvidence] = useState<EvidenceVault | null>(null);
  const [riskSignal, setRiskSignal] = useState<RiskSignal | null>(null);
  const [riskAccessNotice, setRiskAccessNotice] = useState<string | null>(null);
  const [finance, setFinance] = useState<FinanceData | null>(null);
  const [financeAccessNotice, setFinanceAccessNotice] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>(fallbackRecommendations);
  const [invoice, setInvoice] = useState<InvoiceVerificationData | null>(null);
  const [invoiceAccessNotice, setInvoiceAccessNotice] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditData | null>(null);
  const [adminOps, setAdminOps] = useState<AdminOpsData | null>(null);
  const [authContext, setAuthContext] = useState<AuthMe | null>(null);
  const [authContextStatus, setAuthContextStatus] = useState<"loading" | "verified" | "mismatch" | "unavailable">("loading");
  const [shock, setShock] = useState<ShockState>(defaultShock);
  const [disruptedSupplierId, setDisruptedSupplierId] = useState(DEMO_DISRUPTED_SUPPLIER_ID);
  const [connectionRequest, setConnectionRequest] = useState<ConnectionRequest | null>(null);
  const [connectionRequests, setConnectionRequests] = useState<ConnectionRequest[]>([]);
  const [focusedNetwork, setFocusedNetwork] = useState(true);
  const [apiMode, setApiMode] = useState<"loading" | "database" | "fallback">("loading");
  const [selectedPeriod, setSelectedPeriod] = useState(initialPeriodKey);
  const [periods, setPeriods] = useState<PeriodKey[]>([]);
  const [periodSnapshot, setPeriodSnapshot] = useState<PeriodSnapshot | null>(null);
  const [intakeSubmission, setIntakeSubmission] = useState<DataSubmission | null>(null);
  const [importBatch, setImportBatch] = useState<CsvImportBatch | null>(null);
  const [intakeErrorReport, setIntakeErrorReport] = useState<IntakeErrorReport | null>(null);
  const [pendingEvidenceUploads, setPendingEvidenceUploads] = useState<PendingEvidenceUpload[]>([]);
  const [evidenceScanJob, setEvidenceScanJob] = useState<EvidenceScanJobResult | null>(null);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueItem[]>([]);
  const [reviewQueueNotice, setReviewQueueNotice] = useState<string | null>(null);
  const [evidenceDownloadTicket, setEvidenceDownloadTicket] = useState<EvidenceDownloadTicket | null>(null);
  const [evidenceViewError, setEvidenceViewError] = useState<string | null>(null);
  const [viewingEvidenceVersionId, setViewingEvidenceVersionId] = useState<string | null>(null);
  const [supplyMapRegistrations, setSupplyMapRegistrations] = useState<SupplyMapRegistration[]>(initialSupplyMapRegistrations);
  const [intakeBusy, setIntakeBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [region, setRegion] = useState("ALL");
  const [category, setCategory] = useState("ALL");
  const activeAccount = useMemo(() => getDemoAccountById(activeAccountId), [activeAccountId]);
  const verifiedCapabilities = useMemo(() => {
    if (!authContext || authContextStatus !== "verified") return null;
    const mismatch = authContext.actorId !== activeAccount.actorId
      || authContext.organizationId !== activeAccount.organizationId
      || !authContext.roles.includes(activeAccount.actorRole);
    return mismatch ? null : authContext.capabilities;
  }, [activeAccount, authContext, authContextStatus]);
  const verifiedWorkspaceAccess = useMemo(() => {
    if (!authContext || authContextStatus !== "verified") return null;
    const mismatch = authContext.actorId !== activeAccount.actorId
      || authContext.organizationId !== activeAccount.organizationId
      || !authContext.roles.includes(activeAccount.actorRole);
    return mismatch ? null : authContext.workspaceAccess;
  }, [activeAccount, authContext, authContextStatus]);
  const allowedViewIds = useMemo(() => {
    const knownViewIds = new Set(navItems.map((item) => item.id));
    const verifiedViews = verifiedWorkspaceAccess?.allowedViews.filter((view) => knownViewIds.has(view)) ?? [];
    return verifiedViews.length ? verifiedViews : activeAccount.allowedViews;
  }, [activeAccount, verifiedWorkspaceAccess]);
  const defaultViewId = useMemo(() => {
    const verifiedDefault = verifiedWorkspaceAccess?.defaultView;
    if (verifiedDefault && allowedViewIds.includes(verifiedDefault)) return verifiedDefault;
    return allowedViewIds[0] ?? firstAllowedView(activeAccount);
  }, [activeAccount, allowedViewIds, verifiedWorkspaceAccess]);
  const accessibleNavItems = useMemo(() => navItems.filter((item) => allowedViewIds.includes(item.id)), [allowedViewIds]);
  const dataPermissions = useMemo(() => {
    const elevated = accountHasAnyRole(activeAccount, ["demo_operator", "system_admin"]);
    return {
      elevated,
      canReadGraph: verifiedCapabilities?.canReadGraph ?? accountCanBrowseNetwork(activeAccount),
      canReadBusiness: verifiedCapabilities?.canReadBusiness ?? accountHasAnyRole(activeAccount, ["demo_operator", "system_admin", "sme_submitter", "supplier_admin", "buyer_admin", "reviewer", "org_admin"]),
      canReadEvidence: verifiedCapabilities?.canReadEvidence ?? accountHasAnyRole(activeAccount, ["demo_operator", "system_admin", "sme_submitter", "supplier_admin", "reviewer", "lender", "org_admin"]),
      canReadFinance: verifiedCapabilities?.canReadFinancials ?? accountHasAnyRole(activeAccount, ["demo_operator", "system_admin", "sme_submitter", "supplier_admin", "reviewer", "lender", "org_admin"]),
      canReadInvoice: verifiedCapabilities?.canReadInvoice ?? accountHasAnyRole(activeAccount, ["demo_operator", "system_admin", "sme_submitter", "supplier_admin", "lender", "org_admin"]),
      canReadRiskRun: verifiedCapabilities?.canReadRiskRun ?? activeAccount.allowedViews.includes("risk"),
      canReadConnectionRequests: verifiedCapabilities?.canReadConnectionRequest ?? accountHasAnyRole(activeAccount, ["demo_operator", "system_admin", "reviewer", "buyer_admin", "supplier_admin", "org_admin"]),
      canDecideConnectionRequest: verifiedCapabilities?.canDecideConnectionRequest ?? accountHasAnyRole(activeAccount, ["demo_operator", "system_admin", "reviewer", "supplier_admin", "org_admin"]),
      canReadRecommendations: (verifiedCapabilities?.canReadMatchRun ?? activeAccount.allowedViews.includes("matching")) || Boolean(verifiedCapabilities?.canReadGraph)
    };
  }, [activeAccount, verifiedCapabilities]);
  const selectedInvoiceId = useMemo(() => invoiceIdForWorkspace(activeAccount, selectedId), [activeAccount, selectedId]);
  const canRequestInvoiceWorkspace = canLoadInvoiceWorkspace(activeView, allowedViewIds, dataPermissions.canReadInvoice);
  const scopedCompanyNodes = useMemo(() => scopedBusinessNodesForAccount(activeAccount, allNodes), [activeAccount, allNodes]);
  const canReadSelectedBusiness = useMemo(() => accountCanReadOwnBusiness(activeAccount, selectedId), [activeAccount, selectedId]);
  const accessByBusinessId = useMemo(() => Object.fromEntries(allNodes.map((node) => [node.id, demoAccessDecisionFor(activeAccount, node.id, connectionRequest)])), [activeAccount, allNodes, connectionRequest]);
  const selectedAccessDecision = accessByBusinessId[selectedId] ?? demoAccessDecisionFor(activeAccount, selectedId, connectionRequest);
  const canReadSelectedRisk = useMemo(() => canRequestRiskSignal(selectedAccessDecision), [selectedAccessDecision]);
  const canReviewOnboarding = useMemo(() => verifiedCapabilities?.canReviewSupplyMapRegistration ?? ["demo_operator", "reviewer", "system_admin"].includes(activeAccount.actorRole), [activeAccount, verifiedCapabilities]);
  const canCreateOnboarding = useMemo(() => verifiedCapabilities?.canCreateSupplyMapRegistration ?? ["demo_operator", "sme_submitter", "buyer_admin", "supplier_admin", "org_admin", "lender"].includes(activeAccount.actorRole), [activeAccount, verifiedCapabilities]);
  const canRequestIntroduction = useMemo(() => verifiedCapabilities?.canCreateConnectionRequest ?? ["demo_operator", "buyer_admin", "org_admin"].includes(activeAccount.actorRole), [activeAccount, verifiedCapabilities]);
  const visibleSupplyMapRegistrations = useMemo(() => {
    if (canReviewOnboarding) return supplyMapRegistrations;
    return supplyMapRegistrations.filter((item) => item.organizationId === activeAccount.organizationId || item.linkedBusinessId === activeAccount.defaultBusinessId);
  }, [activeAccount, canReviewOnboarding, supplyMapRegistrations]);
  const intakePermissions = useMemo(() => {
    const canSubmit = verifiedCapabilities
      ? verifiedCapabilities.canCreateSubmission || verifiedCapabilities.canUpdateSubmission || verifiedCapabilities.canSubmitSubmission
      : ["demo_operator", "sme_submitter", "supplier_admin", "org_admin"].includes(activeAccount.actorRole);
    const canReview = verifiedCapabilities?.canReviewSubmission ?? ["demo_operator", "reviewer"].includes(activeAccount.actorRole);
    return {
      canCreateDraft: verifiedCapabilities?.canCreateSubmission ?? canSubmit,
      canSaveDraft: verifiedCapabilities?.canUpdateSubmission ?? canSubmit,
      canValidateDraft: verifiedCapabilities?.canValidateSubmission ?? canSubmit,
      canSubmitDraft: verifiedCapabilities?.canSubmitSubmission ?? canSubmit,
      canApproveDraft: canReview,
      canUploadEvidence: verifiedCapabilities?.canCreateEvidenceUpload ?? canSubmit,
      canScanEvidence: verifiedCapabilities?.canRecordEvidenceScanResult ?? ["demo_operator", "system_admin"].includes(activeAccount.actorRole)
    };
  }, [activeAccount, verifiedCapabilities]);
  const permittedIntakeBusinessIds = useMemo(() => {
    if (activeAccount.actorRole === "demo_operator") return allNodes.map((node) => node.id);
    if (intakePermissions.canApproveDraft) {
      const queueOrgIds = reviewQueue.map((item) => item.organizationId);
      return Array.from(new Set([activeAccount.defaultBusinessId, ...queueOrgIds]));
    }
    return [activeAccount.defaultBusinessId];
  }, [activeAccount, allNodes, intakePermissions.canApproveDraft, reviewQueue]);
  const canReadOps = verifiedCapabilities?.canReadAudit ?? activeAccount.allowedViews.includes("audit");
  const authContextMismatch = Boolean(
    authContext
    && (
      authContext.actorId !== activeAccount.actorId
      || authContext.organizationId !== activeAccount.organizationId
      || !authContext.roles.includes(activeAccount.actorRole)
    )
  );

  useEffect(() => {
    const accountChanged = previousAccountId.current !== null && previousAccountId.current !== activeAccount.id;
    previousAccountId.current = activeAccount.id;
    setDemoAccountContext(activeAccount);
    window.localStorage.setItem("vietsupply.demoAccountId", activeAccount.id);
    if (accountChanged) {
      setSelectedId(activeAccount.defaultBusinessId);
      setActiveView(firstAllowedView(activeAccount));
      setDisruptedSupplierId(DEMO_DISRUPTED_SUPPLIER_ID);
    }
    setDetail(null);
    setEvidence(null);
    setRiskSignal(null);
    setRiskAccessNotice(null);
    setFinance(null);
    setFinanceAccessNotice(null);
    setInvoiceAccessNotice(null);
    setPeriods([]);
    setPeriodSnapshot(null);
    setIntakeSubmission(null);
    setImportBatch(null);
    setIntakeErrorReport(null);
    setPendingEvidenceUploads([]);
    setReviewQueue([]);
    setReviewQueueNotice(null);
    setEvidenceDownloadTicket(null);
    setEvidenceViewError(null);
    setViewingEvidenceVersionId(null);
    setConnectionRequest(null);
    setConnectionRequests([]);
  }, [activeAccount]);

  useEffect(() => {
    let mounted = true;
    setAuthContext(null);
    setAuthContextStatus("loading");
    getAuthMe()
      .then((context) => {
        if (!mounted) return;
        const mismatch = context.actorId !== activeAccount.actorId
          || context.organizationId !== activeAccount.organizationId
          || !context.roles.includes(activeAccount.actorRole);
        setAuthContext(context);
        setAuthContextStatus(mismatch ? "mismatch" : "verified");
      })
      .catch(() => {
        if (!mounted) return;
        setAuthContext(null);
        setAuthContextStatus("unavailable");
      });
    return () => { mounted = false; };
  }, [activeAccount]);

  useEffect(() => {
    let mounted = true;
    if (!canLoadSupplyMapRegistrationsForView(activeView, canCreateOnboarding, canReviewOnboarding)) {
      setSupplyMapRegistrations([]);
      return () => { mounted = false; };
    }
    getSupplyMapRegistrations()
      .then((registrations) => {
        if (mounted) setSupplyMapRegistrations(registrations);
      })
      .catch(() => {
        if (mounted && frontendAppMode === "demo") setSupplyMapRegistrations(initialSupplyMapRegistrations);
      });
    return () => { mounted = false; };
  }, [activeAccount.id, activeView, canCreateOnboarding, canReviewOnboarding]);

  useEffect(() => {
    if (!allowedViewIds.includes(activeView)) {
      setActiveView(defaultViewId);
    }
  }, [activeView, allowedViewIds, defaultViewId]);

  useEffect(() => {
    if (authContextStatus !== "verified" || !verifiedWorkspaceAccess?.defaultView) return;
    if (!allowedViewIds.includes(activeView) && allowedViewIds.includes(verifiedWorkspaceAccess.defaultView)) {
      setActiveView(verifiedWorkspaceAccess.defaultView);
    }
  }, [activeAccount.id, activeView, allowedViewIds, authContextStatus, verifiedWorkspaceAccess?.defaultView]);

  useEffect(() => {
    let mounted = true;
    if (!canLoadReviewQueueForView(activeView, intakePermissions.canApproveDraft)) {
      setReviewQueue([]);
      setReviewQueueNotice(null);
      return () => { mounted = false; };
    }
    getReviewQueue("open", 25)
      .then((queue) => {
        if (!mounted) return;
        setReviewQueue(queue.reviewTasks);
        setReviewQueueNotice(queue.advisoryNotice);
      })
      .catch(() => {
        if (!mounted) return;
        setReviewQueue([]);
        setReviewQueueNotice("Review queue is unavailable for this account or backend mode.");
      });
    return () => { mounted = false; };
  }, [activeAccount.id, activeView, intakePermissions.canApproveDraft]);

  useEffect(() => {
    if (activeView === "intake" && !permittedIntakeBusinessIds.includes(selectedId)) {
      setSelectedId(activeAccount.defaultBusinessId);
    }
  }, [activeAccount, activeView, permittedIntakeBusinessIds, selectedId]);

  useEffect(() => {
    let mounted = true;
    if (!canRequestInvoiceWorkspace) {
      setInvoice(null);
      setInvoiceAccessNotice(null);
      return () => { mounted = false; };
    }
    if (!selectedInvoiceId) {
      setInvoice(null);
      setInvoiceAccessNotice("No invoice register item is mapped to the selected organization. Choose a seller or buyer with invoice records.");
      return () => { mounted = false; };
    }
    setInvoice(null);
    setInvoiceAccessNotice(null);
    getInvoiceVerification(selectedInvoiceId)
      .then((invoiceData) => {
        if (!mounted) return;
        setInvoice(invoiceData);
        setInvoiceAccessNotice(null);
      })
      .catch(() => {
        if (!mounted) return;
        setInvoice(null);
        setInvoiceAccessNotice(`Invoice ${selectedInvoiceId} requires seller/buyer party membership or explicit invoice-claim consent.`);
      });
    return () => { mounted = false; };
  }, [activeAccount.id, canRequestInvoiceWorkspace, selectedInvoiceId]);

  useEffect(() => {
    let mounted = true;
    setApiMode("loading");
    async function loadApplication() {
      const [graph, scenarioData, dashboardData] = await Promise.all([
        canLoadGraphForView(activeView, dataPermissions.canReadGraph) ? getGraph() : Promise.resolve({ nodes: fallbackBusinesses, edges: fallbackEdges, fallback: false }),
        getScenario(),
        getDashboard()
      ]);
      if (!mounted) return;
      setAllNodes(graph.nodes);
      setAllEdges(graph.edges);
      setScenario(scenarioData);
      setDashboard(dashboardData);
      setApiMode(graph.fallback ? "fallback" : "database");
    }
    loadApplication();
    return () => { mounted = false; };
  }, [activeAccount.id, activeView, dataPermissions.canReadGraph]);

  useEffect(() => {
    let mounted = true;
    if (!canLoadRecommendationsForView(activeView, dataPermissions.canReadRecommendations)) {
      setRecommendations([]);
      return () => { mounted = false; };
    }
    getRecommendations(activeAccount.defaultBusinessId, selectedPeriod, disruptedSupplierId)
      .then((shortlist) => {
        if (mounted) setRecommendations(shortlist);
      })
      .catch(() => {
        if (mounted) setRecommendations([]);
      });
    return () => { mounted = false; };
  }, [activeAccount.defaultBusinessId, activeAccount.id, activeView, dataPermissions.canReadRecommendations, disruptedSupplierId, selectedPeriod]);

  useEffect(() => {
    let mounted = true;
    if (!canLoadConnectionRequestsForView(activeView, dataPermissions.canReadConnectionRequests)) {
      setConnectionRequests([]);
      return () => { mounted = false; };
    }
    getConnectionRequests()
      .then((items) => {
        if (!mounted) return;
        setConnectionRequests(items);
      })
      .catch(() => undefined);
    return () => { mounted = false; };
  }, [activeAccount.id, activeView, dataPermissions.canReadConnectionRequests]);

  useEffect(() => {
    const nextSearch = workspaceSearchWithState(window.location.search, {
      accountId: activeAccount.id,
      businessId: selectedId,
      period: selectedPeriod,
      view: activeView
    });
    window.history.replaceState(null, "", `${window.location.pathname}${nextSearch}${window.location.hash}`);
  }, [activeAccount.id, activeView, selectedId, selectedPeriod]);

  useEffect(() => {
    let mounted = true;
    setDetail(null);
    setEvidence(null);
    setEvidenceDownloadTicket(null);
    setEvidenceViewError(null);
    setViewingEvidenceVersionId(null);
    setRiskSignal(null);
    setRiskAccessNotice(null);
    setFinance(null);
    setFinanceAccessNotice(null);
    const shouldLoadBusiness = canLoadBusinessDetailForView(activeView, dataPermissions.canReadBusiness, canReadSelectedBusiness);
    const shouldLoadEvidence = canLoadEvidenceVaultForView(activeView, dataPermissions.canReadEvidence, canReadSelectedBusiness);
    const shouldLoadRisk = canLoadRiskSignalForView(activeView, dataPermissions.canReadRiskRun, canReadSelectedRisk);
    const shouldLoadFinance = canLoadFinanceForView(activeView, dataPermissions.canReadFinance, canReadSelectedBusiness);
    let riskNotice: string | null = null;
    let financeNotice: string | null = null;
    if (activeView === "risk" && dataPermissions.canReadRiskRun && !canReadSelectedRisk) {
      riskNotice = "Risk signal is restricted to own organization, a visible high-level risk scope, or active relationship/consent.";
    }
    if (activeView === "finance" && dataPermissions.canReadFinance && !canReadSelectedBusiness) {
      financeNotice = "Financial data is restricted to own organization or active financial-summary consent.";
    }
    Promise.all([
      shouldLoadBusiness ? getBusinessDetail(selectedId, selectedPeriod).catch(() => null) : Promise.resolve(null),
      shouldLoadEvidence ? getEvidence(selectedId, selectedPeriod).catch(() => null) : Promise.resolve(null),
      shouldLoadRisk ? getRiskSignal(selectedId, selectedPeriod).catch(() => {
        riskNotice = "Risk signal access was denied or unavailable for this account scope.";
        return null;
      }) : Promise.resolve(null),
      shouldLoadFinance ? getFinance(selectedId, selectedPeriod).catch(() => {
        financeNotice = "Financial data is restricted to own organization or active financial-summary consent.";
        return null;
      }) : Promise.resolve(null)
    ])
      .then(([detailData, evidenceData, riskData, financeData]) => {
        if (!mounted) return;
        setDetail(detailData);
        setEvidence(evidenceData);
        setRiskSignal(riskData);
        setRiskAccessNotice(riskNotice);
        setFinance(financeData);
        setFinanceAccessNotice(financeNotice);
      });
    return () => { mounted = false; };
  }, [activeView, selectedId, selectedPeriod, activeAccount.id, canReadSelectedBusiness, canReadSelectedRisk, dataPermissions]);

  useEffect(() => {
    let mounted = true;
    if (!canLoadEvidenceVaultForView(activeView, dataPermissions.canReadEvidence, canReadSelectedBusiness)) {
      setPendingEvidenceUploads((current) => current.filter((item) => item.businessId !== selectedId));
      return () => { mounted = false; };
    }
    getPendingEvidenceUploads(selectedId, selectedPeriod)
      .then((tickets) => {
        if (!mounted) return;
        setPendingEvidenceUploads((current) => mergePendingEvidenceUploadsForPeriod(current, tickets, selectedId, selectedPeriod));
      })
      .catch(() => undefined);
    return () => { mounted = false; };
  }, [activeView, selectedId, selectedPeriod, activeAccount.id, canReadSelectedBusiness, dataPermissions]);

  useEffect(() => {
    let mounted = true;
    setIntakeSubmission(null);
    setImportBatch(null);
    setIntakeErrorReport(null);
    async function loadPeriodContext() {
      if (!canLoadIntakePeriodContextForView(activeView, dataPermissions.canReadFinance, canReadSelectedBusiness)) {
        if (!mounted) return;
        setPeriods([]);
        setPeriodSnapshot(null);
        return;
      }
      try {
        const [periodData, snapshotData] = await Promise.all([getPeriods(selectedId), getPeriodSnapshot(selectedId, selectedPeriod)]);
        if (!mounted) return;
        setPeriods(periodData);
        setPeriodSnapshot(snapshotData);
      } catch {
        if (!mounted) return;
        setPeriods([]);
        setPeriodSnapshot(null);
      }
    }
    loadPeriodContext();
    return () => { mounted = false; };
  }, [activeView, selectedId, selectedPeriod, activeAccount.id, canReadSelectedBusiness, dataPermissions]);

  useEffect(() => {
    let mounted = true;
    if (!canLoadAuditWorkspaceForView(activeView, canReadOps)) {
      setAudit(null);
      setAdminOps(null);
      return () => { mounted = false; };
    }
    Promise.all([getAudit().catch(() => null), getAdminOps(selectedId).catch(() => null)])
      .then(([auditData, opsData]) => {
        if (!mounted) return;
        setAudit(auditData);
        setAdminOps(opsData);
      });
    return () => { mounted = false; };
  }, [activeView, selectedId, activeAccount.id, canReadOps]);

  const selected = useMemo(() => allNodes.find((node) => node.id === selectedId) ?? scenario?.nodes.find((node) => node.id === selectedId), [allNodes, scenario, selectedId]);
  const disruptedSupplier = useMemo(() => allNodes.find((node) => node.id === disruptedSupplierId) ?? scenario?.nodes.find((node) => node.id === disruptedSupplierId), [allNodes, disruptedSupplierId, scenario]);
  const matchingBuyer = useMemo(() => allNodes.find((node) => node.id === activeAccount.defaultBusinessId) ?? scenario?.nodes.find((node) => node.id === activeAccount.defaultBusinessId), [activeAccount.defaultBusinessId, allNodes, scenario]);
  const filteredNodes = useMemo(() => allNodes.filter((node) => (region === "ALL" || node.province === region) && (category === "ALL" || node.category === category)), [allNodes, region, category]);
  const filteredIds = useMemo(() => new Set(filteredNodes.map((node) => node.id)), [filteredNodes]);
  const filteredEdges = useMemo(() => allEdges.filter((edge) => filteredIds.has(edge.sourceId) && filteredIds.has(edge.targetId)), [allEdges, filteredIds]);

  async function handleSimulate() {
    setDisruptedSupplierId(DEMO_DISRUPTED_SUPPLIER_ID);
    setSelectedId(DEMO_DISRUPTED_SUPPLIER_ID);
    const [result, shortlist] = await Promise.all([
      simulateShock(),
      dataPermissions.canReadRecommendations ? getRecommendations(activeAccount.defaultBusinessId, selectedPeriod, DEMO_DISRUPTED_SUPPLIER_ID) : Promise.resolve([])
    ]);
    setShock(result);
    setRecommendations(shortlist);
  }

  function openView(view: AppView) {
    setActiveView(allowedViewIds.includes(view) ? view : defaultViewId);
  }

  function handleOpenRisk(businessId?: string | null) {
    if (businessId) {
      setSelectedId(businessId);
      setDisruptedSupplierId(businessId);
    }
    openView("risk");
  }

  async function handleConnectionRequest(supplierId: string) {
    if (!canRequestIntroduction) return;
    try {
      const request = await createConnectionRequest({
        buyerId: activeAccount.defaultBusinessId,
        targetSupplierId: supplierId,
        disruptedSupplierId: disruptedSupplierId !== supplierId ? disruptedSupplierId : undefined
      });
      setConnectionRequest(request);
      setConnectionRequests((current) => [request, ...current.filter((item) => item.requestId !== request.requestId)]);
      if (canLoadAuditWorkspaceForView(activeView, canReadOps)) setAudit(await getAudit());
    } catch (error) {
      if (frontendAppMode !== "demo") throw error;
      const localRequest: ConnectionRequest = { requestId: "REQ-OFFLINE", buyerId: activeAccount.defaultBusinessId, targetSupplierId: supplierId, disruptedSupplierId: disruptedSupplierId !== supplierId ? disruptedSupplierId : undefined, status: "pending", consentStatus: "awaiting_supplier_consent", requestedAt: new Date().toISOString(), nextStep: "Queued locally; start the backend to persist the audit event." };
      setConnectionRequest(localRequest);
      setConnectionRequests((current) => [localRequest, ...current.filter((item) => item.requestId !== localRequest.requestId)]);
    }
  }

  async function handleConnectionRequestDecision(requestId: string, decision: "grant_consent" | "reject" | "request_changes" | "activate_relationship") {
    if (!dataPermissions.canDecideConnectionRequest) return;
    const decided = await decideConnectionRequest({
      requestId,
      decision,
      note: decision === "activate_relationship"
        ? "Contract evidence reviewed before demo relationship activation."
        : "Connection request reviewed from audit queue.",
      contractEvidenceId: decision === "activate_relationship" ? `EVD-CONTRACT-${requestId}` : null
    });
    setConnectionRequest((current) => current?.requestId === requestId ? decided : current);
    setConnectionRequests((current) => current.map((item) => item.requestId === requestId ? decided : item));
    if (canLoadAuditWorkspaceForView(activeView, canReadOps)) setAudit(await getAudit());
    const refreshedConnectionRequests = dataPermissions.canReadConnectionRequests ? await getConnectionRequests().catch(() => null) : null;
    if (refreshedConnectionRequests) setConnectionRequests(refreshedConnectionRequests);
    if (decision === "activate_relationship" && dataPermissions.canReadGraph) {
      const graph = await getGraph().catch(() => null);
      if (graph) {
        setAllNodes(graph.nodes);
        setAllEdges(graph.edges);
      }
    }
  }

  async function handleCreateSupplyMapRegistration(draft: {
    organizationName: string;
    stakeholderRole: SupplyMapRegistration["stakeholderRole"];
    province: string;
    category: string;
    scale: string;
    contactEmail: string;
    intendedRelationships: string[];
    dataBoundary: string;
  }) {
    if (!canCreateOnboarding) return;
    const registration = await createSupplyMapRegistration(draft);
    setSupplyMapRegistrations((current) => [registration, ...current.filter((item) => item.id !== registration.id)]);
  }

  async function handleSupplyMapRegistrationDecision(registrationId: string, decision: "approve" | "request_changes" | "reject", note: string) {
    if (!canReviewOnboarding) return;
    const registration = supplyMapRegistrations.find((item) => item.id === registrationId);
    if (!registration) return;
    const localStatus: SupplyMapRegistration["status"] = decision === "approve" ? "approved" : decision === "reject" ? "rejected" : "changes_requested";
    let reviewedRegistration: SupplyMapRegistration | null = null;
    try {
      reviewedRegistration = await decideSupplyMapRegistration(registrationId, decision, note);
    } catch (error) {
      if (frontendAppMode !== "demo") throw error;
    }
    const fallbackLinkedBusinessId = decision === "approve" && !registration.linkedBusinessId
      ? `BIZ-ONB-${registration.id.replace(/\D/g, "").slice(-6) || Date.now().toString().slice(-6)}`
      : registration.linkedBusinessId ?? null;
    const effectiveRegistration: SupplyMapRegistration = reviewedRegistration ?? {
      ...registration,
      status: localStatus,
      reviewStatus: localStatus === "approved" ? "approved" : localStatus === "rejected" ? "rejected" : "changes_requested",
      mapVisibility: localStatus === "approved" ? "visible_demo_node" : "masked_pending_consent",
      linkedBusinessId: fallbackLinkedBusinessId,
      reviewedAt: new Date().toISOString(),
      reviewerNote: note,
      advisoryNotice: localStatus === "approved" ? "Approved for demo map visibility; unmasked commercial data still requires consent." : "Review decision recorded; membership is not active until requirements are satisfied."
    };
    const linkedBusinessId = effectiveRegistration.linkedBusinessId ?? null;
    const addOptimisticOnboardingNode = () => {
      if (!linkedBusinessId) return;
      const coordinates = demoCoordinatesForProvince(registration.province);
      const newNode: BusinessNode = {
        id: linkedBusinessId,
        name: effectiveRegistration.organizationName,
        type: effectiveRegistration.stakeholderRole,
        province: effectiveRegistration.province,
        category: effectiveRegistration.category,
        lat: coordinates.lat,
        lng: coordinates.lng,
        revenue: 0.8,
        capacity: 18000,
        health: 68,
        risk: 38,
        scale: effectiveRegistration.scale
      };
      setAllNodes((current) => current.some((node) => node.id === linkedBusinessId) ? current : [newNode, ...current]);
    };
    if (decision === "approve" && linkedBusinessId) {
      if (reviewedRegistration && dataPermissions.canReadGraph) {
        try {
          const graph = await getGraph();
          setAllNodes(graph.nodes);
          setAllEdges(graph.edges);
        } catch {
          addOptimisticOnboardingNode();
        }
      } else {
        addOptimisticOnboardingNode();
      }
    }
    setSupplyMapRegistrations((current) => current.map((item) => {
      if (item.id !== registrationId) return item;
      return effectiveRegistration;
    }));
    if (linkedBusinessId && decision === "approve") {
      setSelectedId(linkedBusinessId);
      setFocusedNetwork(false);
      setActiveView(allowedViewIds.includes("map") ? "map" : allowedViewIds.includes("companies") ? "companies" : defaultViewId);
    }
  }

  async function refreshPeriodContext(submission?: DataSubmission | null) {
    const [periodData, snapshotData] = await Promise.all([getPeriods(selectedId), getPeriodSnapshot(selectedId, selectedPeriod)]);
    setPeriods(periodData);
    setPeriodSnapshot(snapshotData);
    if (submission) setIntakeSubmission(submission);
  }

  async function loadPeriodContextFor(organizationId: string, periodKey: string, submission?: DataSubmission | null) {
    const [periodData, snapshotData] = await Promise.all([getPeriods(organizationId), getPeriodSnapshot(organizationId, periodKey)]);
    setPeriods(periodData);
    setPeriodSnapshot(snapshotData);
    if (submission) setIntakeSubmission(submission);
  }

  async function refreshReviewQueue() {
    if (!canLoadReviewQueueForView(activeView, intakePermissions.canApproveDraft)) return;
    const queue = await getReviewQueue("open", 25);
    setReviewQueue(queue.reviewTasks);
    setReviewQueueNotice(queue.advisoryNotice);
  }

  async function loadIntakeErrorReport(submissionId: string, format: "json" | "csv" = "json") {
    const report = await getDataSubmissionErrorReport(submissionId, format);
    setIntakeErrorReport(report);
    if (format === "csv" && report.csv && typeof document !== "undefined") {
      const blob = new Blob([report.csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `intake-errors-${submissionId}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }
    return report;
  }

  async function handleLoadErrorReport(format: "json" | "csv" = "json") {
    if (!intakeSubmission) return;
    await loadIntakeErrorReport(intakeSubmission.id, format);
  }

  async function handleCreateDraft(sections: Record<string, unknown>) {
    if (!intakePermissions.canCreateDraft || !permittedIntakeBusinessIds.includes(selectedId)) return;
    setIntakeBusy(true);
    try {
      const submission = await createDataSubmission(selectedId, selectedPeriod, sections, "manual");
      setImportBatch(null);
      setIntakeErrorReport(null);
      await refreshPeriodContext(submission);
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleSaveDraft(sections: Record<string, unknown>) {
    if (!intakePermissions.canSaveDraft || !permittedIntakeBusinessIds.includes(selectedId)) return;
    if (!intakeSubmission) {
      await handleCreateDraft(sections);
      return;
    }
    setIntakeBusy(true);
    try {
      const submission = await updateDataSubmission(intakeSubmission.id, sections);
      setIntakeErrorReport(null);
      await refreshPeriodContext(submission);
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleValidateDraft() {
    if (!intakePermissions.canValidateDraft || !intakeSubmission) return;
    setIntakeBusy(true);
    try {
      const submission = await validateDataSubmission(intakeSubmission.id);
      setIntakeSubmission(submission);
      if (submission.validationSummary.errors || submission.validationSummary.warnings) {
        await loadIntakeErrorReport(submission.id);
      } else {
        setIntakeErrorReport(null);
      }
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleSubmitDraft() {
    if (!intakePermissions.canSubmitDraft || !intakeSubmission) return;
    setIntakeBusy(true);
    try {
      const submission = await submitDataSubmission(intakeSubmission.id);
      setIntakeErrorReport(null);
      await refreshPeriodContext(submission);
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleReviewQueueSelect(item: ReviewQueueItem) {
    if (!intakePermissions.canApproveDraft) return;
    setIntakeBusy(true);
    try {
      setSelectedId(item.organizationId);
      setSelectedPeriod(item.periodKey);
      setImportBatch(null);
      setIntakeErrorReport(null);
      const submission = await getDataSubmission(item.submissionId);
      await loadPeriodContextFor(item.organizationId, item.periodKey, submission);
      if (submission.validationSummary.errors || submission.validationSummary.warnings) {
        await loadIntakeErrorReport(submission.id);
      }
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleReviewDecision(decision: "approve" | "reject" | "request_changes", note: string) {
    if (!intakePermissions.canApproveDraft || !intakeSubmission?.reviewTask) return;
    setIntakeBusy(true);
    try {
      const submission = await decideReviewTask(intakeSubmission.reviewTask.id, decision, note || "Reviewed from demo Data Intake workspace.");
      setIntakeErrorReport(null);
      await refreshPeriodContext(submission);
      await refreshReviewQueue().catch(() => undefined);
      setAdminOps(canLoadAuditWorkspaceForView(activeView, canReadOps) ? await getAdminOps(selectedId).catch(() => null) : null);
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleImportCsv(dataset: string, fileName: string, csvText: string) {
    if (!intakePermissions.canSaveDraft || !permittedIntakeBusinessIds.includes(selectedId)) return;
    setIntakeBusy(true);
    try {
      const batch = await createImportBatch({ businessId: selectedId, periodKey: selectedPeriod, dataset, fileName, csvText, submissionId: intakeSubmission?.id });
      setImportBatch(batch);
      const submission = await getDataSubmission(batch.submissionId);
      await refreshPeriodContext(submission);
      if (batch.status === "quarantined" || submission.validationSummary.errors || submission.validationSummary.warnings) {
        await loadIntakeErrorReport(submission.id);
      } else {
        setIntakeErrorReport(null);
      }
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleEvidenceUpload(file: File, documentType: string, classification: string) {
    if (!intakePermissions.canUploadEvidence || !permittedIntakeBusinessIds.includes(selectedId)) return;
    setIntakeBusy(true);
    try {
      const ticket = await createEvidenceUploadTicket({
        organizationId: selectedId,
        fileName: file.name,
        contentType: file.type || "application/octet-stream",
        byteSize: file.size,
        documentType,
        periodKey: selectedPeriod,
        classification,
        purpose: "evidence_intake"
      });
      setPendingEvidenceUploads((current) => [
        {
          id: ticket.evidenceVersionId,
          businessId: selectedId,
          periodKey: ticket.periodKey ?? selectedPeriod,
          documentType: (ticket.documentType ?? documentType) as PendingEvidenceUpload["documentType"],
          fileName: ticket.fileName ?? file.name,
          contentType: ticket.contentType ?? (file.type || "application/octet-stream"),
          byteSize: ticket.byteSize ?? file.size,
          classification: ticket.classification ?? classification,
          status: "upload_ticket_created",
          malwareScanStatus: ticket.malwareScanStatus,
          evidenceVersionId: ticket.evidenceVersionId,
          policyDecisionId: ticket.policyDecisionId,
          auditEventId: ticket.auditEventId,
          advisoryNotice: ticket.advisoryNotice,
          uploadedAt: new Date().toISOString()
        },
        ...current
      ]);
      const { documentHash, contentBase64 } = await evidenceUploadPayload(file);
      if (documentHash) {
        await completeEvidenceUploadTicket(ticket.evidenceVersionId, {
          organizationId: selectedId,
          documentHash,
          malwareScanStatus: "pending_scan",
          title: file.name,
          contentBase64
        });
      }
      const [vaultData, pendingTickets] = await Promise.all([
        getEvidence(selectedId, selectedPeriod).catch(() => evidence),
        getPendingEvidenceUploads(selectedId, selectedPeriod).catch(() => null)
      ]);
      setEvidence(vaultData);
      if (pendingTickets) {
        setPendingEvidenceUploads((current) => mergePendingEvidenceUploadsForPeriod(current, pendingTickets, selectedId, selectedPeriod));
      }
    } catch {
      setPendingEvidenceUploads((current) => [
        {
          id: `LOCAL-EVID-${Date.now()}`,
          businessId: selectedId,
          periodKey: selectedPeriod,
          documentType: documentType as PendingEvidenceUpload["documentType"],
          fileName: file.name,
          contentType: file.type || "application/octet-stream",
          byteSize: file.size,
          classification,
          status: "local_pending",
          malwareScanStatus: "pending_backend",
          uploadedAt: new Date().toISOString(),
          advisoryNotice: "Queued in the demo UI only. Start the backend with evidence storage to persist and scan this file."
        },
        ...current
      ]);
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleRunEvidenceScan() {
    if (!intakePermissions.canScanEvidence || !permittedIntakeBusinessIds.includes(selectedId)) return;
    setIntakeBusy(true);
    try {
      const result = await runEvidenceScanJob({
        organizationId: selectedId,
        periodKey: selectedPeriod,
        limit: 20,
        scanner: "local_demo",
        dryRun: false
      });
      setEvidenceScanJob(result);
      const [vaultData, pendingTickets] = await Promise.all([
        getEvidence(selectedId, selectedPeriod).catch(() => evidence),
        getPendingEvidenceUploads(selectedId, selectedPeriod).catch(() => null)
      ]);
      setEvidence(vaultData);
      if (pendingTickets) {
        setPendingEvidenceUploads((current) => mergePendingEvidenceUploadsForPeriod(current, pendingTickets, selectedId, selectedPeriod));
      }
      await refreshPeriodContext(intakeSubmission ?? undefined).catch(() => undefined);
      await refreshReviewQueue().catch(() => undefined);
      setAdminOps(canLoadAuditWorkspaceForView(activeView, canReadOps) ? await getAdminOps(selectedId).catch(() => null) : null);
    } finally {
      setIntakeBusy(false);
    }
  }

  async function handleViewEvidenceDocument(document: EvidenceDocument) {
    setEvidenceViewError(null);
    setEvidenceDownloadTicket(null);
    if (!dataPermissions.canReadEvidence || !canReadSelectedBusiness) {
      setEvidenceViewError("Evidence file access requires policy-scoped access to this organization.");
      return;
    }
    if (!document.evidenceVersionId) {
      setEvidenceViewError("This demo record has provenance metadata only; no scan-cleared file version is attached.");
      return;
    }
    setViewingEvidenceVersionId(document.evidenceVersionId);
    try {
      const ticket = await createEvidenceDownloadTicket(document.evidenceVersionId);
      setEvidenceDownloadTicket(ticket);
    } catch {
      setEvidenceViewError("File access was denied or the malware scan is not clean yet.");
    } finally {
      setViewingEvidenceVersionId(null);
    }
  }

  function handleSearchKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    const match = allNodes.find((node) => `${node.name} ${node.province} ${node.category}`.toLowerCase().includes(search.toLowerCase()));
    if (match) {
      setSelectedId(match.id);
      openView("companies");
      setSearch(match.name);
    }
  }

  if (!dashboard || !scenario) {
    return <div className="app-loading"><Network size={34} /><strong>VietSupply Radar</strong><span>Loading evidence-backed demo...</span></div>;
  }

  const networkProps = {
    allNodes: filteredNodes,
    allEdges: filteredEdges,
    scenario,
    focused: focusedNetwork,
    selectedId,
    shock,
    onFocusedChange: setFocusedNetwork,
    onSelect: setSelectedId
  };
  const isFallbackMode = apiMode === "fallback";
  const isLocalPermissionFallback = authContextStatus === "unavailable" || authContextMismatch;
  const boundaryBanner = isFallbackMode
    ? {
        title: "Synthetic fallback dataset active",
        message: isLocalPermissionFallback
          ? "Backend data and actor context are unavailable or mismatched. Navigation is using local synthetic demo rules only."
          : "Backend is offline or returned a server error. Authorization failures are not replaced with fallback data."
      }
    : isLocalPermissionFallback
      ? {
          title: "Local synthetic permissions active",
          message: "Backend actor context is unavailable or mismatched. Role navigation is demo-only and must not be treated as verified authorization."
        }
      : null;
  const authContextLabel = authContextStatus === "loading"
    ? "Checking backend actor context"
    : authContextStatus === "unavailable"
      ? "Local synthetic permissions only"
      : authContextMismatch
        ? `Local synthetic permissions only: backend actor ${authContext?.actorId ?? "unknown"}`
        : `${authContext?.authAssurance ?? "demo-header"} / ${authContext?.actorId ?? activeAccount.actorId}`;

  return (
    <main className="app-shell">
      <nav className="nav-rail" aria-label="Primary navigation">
        <div className="brand-lockup"><span className="radar-mark"><i /><i /><i /></span><div><strong>VietSupply</strong><b>Radar</b></div></div>
        <div className="nav-links">
          {accessibleNavItems.map((item) => <button key={item.id} type="button" className={activeView === item.id ? "nav-item active" : "nav-item"} onClick={() => openView(item.id)}>{item.icon}<span>{item.label}</span></button>)}
        </div>
        <div className="nav-status">
          <div><ShieldCheck size={16} /><span>Supply Health</span></div><strong>{dashboard.overview.supplyHealthScore}<small>/100</small></strong><p><i className={apiMode === "database" ? "online" : "offline"} />{apiMode === "database" ? "SQLite API connected" : apiMode === "loading" ? "Connecting API" : "Fallback data active"}</p>
        </div>
      </nav>

      <section className={boundaryBanner ? "main-shell has-boundary-banner" : "main-shell"}>
        <header className="topbar">
          <label className="global-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={handleSearchKey} placeholder="Search companies, products, or provinces..." aria-label="Search companies" /><kbd>Enter</kbd></label>
          <label className="filter-control"><CalendarDays size={16} /><input type="month" value={selectedPeriod} onChange={(event) => setSelectedPeriod(event.target.value)} aria-label="Selected reporting period" /></label>
          <label className="filter-control"><Map size={16} /><select value={region} onChange={(event) => setRegion(event.target.value)} aria-label="Filter by region"><option value="ALL">All regions</option><option value="Binh Duong">Binh Duong</option><option value="TP.HCM">TP.HCM</option><option value="Dong Nai">Dong Nai</option><option value="Lam Dong">Lam Dong</option></select><ChevronDown size={15} /></label>
          <label className="filter-control"><SlidersHorizontal size={16} /><select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter by industry"><option value="ALL">All industries</option><option value="beverage">Beverage</option><option value="packaged_food">Packaged food</option><option value="processed_agri">Processed agri</option><option value="cold_chain_food">Cold chain</option><option value="finance">Finance</option></select><ChevronDown size={15} /></label>
          <button className="notification-button" type="button" title="Notifications"><Bell size={19} /><span>3</span></button>
          <label className="account-menu">
            <span><UserRoundCheck size={20} /></span>
            <div>
              <select value={activeAccount.id} onChange={(event) => setActiveAccountId(event.target.value)} aria-label="Demo stakeholder account">
                {demoAccounts.map((account) => <option key={account.id} value={account.id}>{account.label}</option>)}
              </select>
              <small>{activeAccount.personName} · {activeAccount.organizationName}</small>
              <small className={`auth-context-line ${authContextStatus}`}>{authContextLabel}</small>
            </div>
            <ChevronDown size={15} />
          </label>
        </header>

        {boundaryBanner ? (
          <div className="demo-boundary-banner" role="status" aria-live="polite">
            <ShieldCheck size={16} />
            <div>
              <strong>{boundaryBanner.title}</strong>
              <span>{boundaryBanner.message}</span>
            </div>
          </div>
        ) : null}

        <div className="view-heading-mobile"><span>{accessibleNavItems.find((item) => item.id === activeView)?.label}</span><i>{activeAccount.label}</i></div>

        <div className="view-content">
          {activeView === "overview" ? <OverviewWorkspace {...networkProps} dashboard={dashboard} onSimulate={handleSimulate} onReset={() => setShock(defaultShock)} canOpenIntake={allowedViewIds.includes("intake")} onOpenIntake={() => openView("intake")} canOpenRisk={allowedViewIds.includes("risk")} onOpenRisk={handleOpenRisk} canOpenMatching={allowedViewIds.includes("matching")} onOpenMatching={() => openView("matching")} canOpenAudit={allowedViewIds.includes("audit")} onOpenAudit={() => openView("audit")} /> : null}
          {activeView === "map" ? <MapWorkspace {...networkProps} selected={selected} detail={detail} accessDecision={selectedAccessDecision} /> : null}
          {activeView === "companies" ? <CompaniesWorkspace nodes={scopedCompanyNodes} selectedId={selectedId} onSelect={setSelectedId} detail={detail} evidence={evidence} pendingEvidenceUploads={dataPermissions.canReadEvidence && canReadSelectedBusiness ? pendingEvidenceUploads.filter((item) => item.businessId === selectedId) : []} accessDecision={selectedAccessDecision} downloadTicket={evidenceDownloadTicket} viewError={evidenceViewError} viewingEvidenceVersionId={viewingEvidenceVersionId} onViewEvidence={handleViewEvidenceDocument} onCloseDownloadTicket={() => { setEvidenceDownloadTicket(null); setEvidenceViewError(null); }} /> : null}
          {activeView === "intake" ? <DataIntakeWorkspace nodes={intakePermissions.canApproveDraft ? allNodes : scopedCompanyNodes} selectedId={selectedId} selectedPeriod={selectedPeriod} periods={periods} submission={intakeSubmission} snapshot={periodSnapshot} importBatch={importBatch} errorReport={intakeErrorReport} pendingEvidenceUploads={dataPermissions.canReadEvidence && canReadSelectedBusiness ? pendingEvidenceUploads.filter((item) => item.businessId === selectedId && item.periodKey === selectedPeriod) : []} vaultDocuments={dataPermissions.canReadEvidence && canReadSelectedBusiness ? evidence?.documents ?? [] : []} evidenceScanJob={evidenceScanJob} permittedBusinessIds={permittedIntakeBusinessIds} actionPermissions={intakePermissions} reviewQueue={reviewQueue} reviewQueueNotice={reviewQueueNotice} busy={intakeBusy} onSelect={setSelectedId} onPeriodChange={setSelectedPeriod} onCreateDraft={handleCreateDraft} onSaveDraft={handleSaveDraft} onValidate={handleValidateDraft} onSubmit={handleSubmitDraft} onReviewDecision={handleReviewDecision} onReviewQueueSelect={handleReviewQueueSelect} onImportCsv={handleImportCsv} onEvidenceUpload={handleEvidenceUpload} onRunEvidenceScan={handleRunEvidenceScan} onLoadErrorReport={handleLoadErrorReport} /> : null}
          {activeView === "onboarding" ? <OnboardingWorkspace account={activeAccount} registrations={visibleSupplyMapRegistrations} connectionRequests={connectionRequests} canCreate={canCreateOnboarding} canReview={canReviewOnboarding} canDecideConnectionRequest={dataPermissions.canDecideConnectionRequest} onCreate={handleCreateSupplyMapRegistration} onDecision={handleSupplyMapRegistrationDecision} onConnectionDecision={handleConnectionRequestDecision} /> : null}
          {activeView === "risk" ? <RiskWorkspace signal={riskSignal} subjectName={selected?.name ?? riskSignal?.businessId ?? selectedId} accessNotice={riskAccessNotice} canOpenMatching={allowedViewIds.includes("matching")} onOpenMatching={() => openView("matching")} /> : null}
          {activeView === "matching" ? <MatchingWorkspace recommendations={recommendations} request={connectionRequest} buyerName={matchingBuyer?.name ?? activeAccount.organizationName} disruptedSupplierName={disruptedSupplier?.name ?? disruptedSupplierId} selectedPeriod={selectedPeriod} accessByBusinessId={accessByBusinessId} canConnect={canRequestIntroduction} onConnect={handleConnectionRequest} /> : null}
          {activeView === "finance" ? <FinanceWorkspace finance={finance} account={activeAccount} accessNotice={financeAccessNotice} /> : null}
          {activeView === "invoice" ? <InvoiceWorkspace invoice={invoice} account={activeAccount} accessNotice={invoiceAccessNotice} /> : null}
          {activeView === "audit" ? <AuditWorkspace audit={audit} adminOps={adminOps} accounts={demoAccounts} activeAccount={activeAccount} canDecideConnectionRequest={dataPermissions.canDecideConnectionRequest} onConnectionDecision={handleConnectionRequestDecision} /> : null}
        </div>
      </section>
    </main>
  );
}
