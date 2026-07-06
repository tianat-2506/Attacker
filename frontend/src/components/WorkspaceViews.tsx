import { useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Banknote,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Database,
  Download,
  FileCheck2,
  FileKey2,
  FileText,
  Fingerprint,
  GitBranch,
  Handshake,
  Info,
  Landmark,
  ListFilter,
  MapPinned,
  PackageCheck,
  RefreshCw,
  Route,
  Send,
  ShieldAlert,
  ShieldCheck,
  Truck,
  Upload,
  UserRoundCheck,
  Users
} from "lucide-react";
import type {
  AdminOpsData,
  AuditData,
  BusinessDetail,
  BusinessNode,
  ConnectionRequest,
  CsvImportBatch,
  DashboardData,
  DataSubmission,
  DemoAccount,
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
} from "../types";
import { accessStatusLabel, canShowSensitiveCompanyData } from "../utils/accessDecision";
import {
  CONNECTION_REQUEST_FILTERS,
  canActivateConnection,
  canGrantConnectionConsent,
  canRejectConnection,
  canRequestConnectionChanges,
  connectionRequestFilterLabel,
  connectionRequestIsActionable,
  connectionRequestMatchesFilter,
  connectionRequestPerspectiveLabel,
  connectionRequestTone,
  type ConnectionRequestFilter
} from "../utils/connectionRequests";
import {
  evidenceRecordStatus,
  evidenceStatusLabel,
  evidenceVerificationBucket,
  evidenceWorkflowLabel,
  evidenceWorkflowStatus,
  type EvidenceWorkflowStatus
} from "../utils/evidenceStatus";
import { invoiceFundingStateLabel, invoiceFundingStateNotice } from "../utils/invoiceStatus";
import { financePeriodState, matchingPeriodNotice, recommendationPeriodLabel } from "../utils/periodUi";
import { MapView } from "./MapView";

const moneyCompact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const numberCompact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

function roleLabel(type: BusinessNode["type"]) {
  const labels: Record<BusinessNode["type"], string> = {
    manufacturer: "Supplier",
    distributor: "Distributor",
    wholesaler: "Wholesaler",
    retailer: "SME / Retailer",
    logistics_partner: "Logistics",
    financial_partner: "Finance"
  };
  return labels[type];
}

function riskTone(risk: number) {
  if (risk >= 70) return "critical";
  if (risk >= 45) return "watch";
  return "healthy";
}

function Sparkline({ values, color = "#22d3ee" }: { values: number[]; color?: string }) {
  const path = useMemo(() => {
    if (!values.length) return "";
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(1, max - min);
    return values.map((value, index) => {
      const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
      const y = 38 - ((value - min) / span) * 30;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");
  }, [values]);
  return (
    <svg className="sparkline" viewBox="0 0 100 42" preserveAspectRatio="none" aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function DataNotice({ children }: { children: string }) {
  return <div className="data-notice"><Info size={14} /><span>{children}</span></div>;
}

interface NetworkProps {
  allNodes: BusinessNode[];
  allEdges: SupplyEdge[];
  scenario: ScenarioData;
  focused: boolean;
  selectedId: string;
  shock: ShockState;
  onFocusedChange: (focused: boolean) => void;
  onSelect: (id: string) => void;
}

function NetworkToolbar({ focused, onFocusedChange, scenario }: Pick<NetworkProps, "focused" | "onFocusedChange" | "scenario">) {
  return (
    <div className="network-toolbar">
      <div>
        <div className="title-with-icon"><MapPinned size={18} /><h2>Supply Network Map</h2></div>
        <p>Southern Vietnam · Binh Duong focus · synthetic relationships</p>
      </div>
      <div className="segmented" aria-label="Network scope">
        <button type="button" className={focused ? "is-active" : ""} onClick={() => onFocusedChange(true)}>10-node case</button>
        <button type="button" className={!focused ? "is-active" : ""} onClick={() => onFocusedChange(false)}>All network</button>
      </div>
      <span className="scope-badge"><GitBranch size={14} />{focused ? `${scenario.nodes.length} roles` : `${scenario.nodes.length}+ case nodes`}</span>
    </div>
  );
}

function KpiCard({ icon, label, value, note, tone = "cyan" }: { icon: ReactNode; label: string; value: string; note: string; tone?: string }) {
  return (
    <article className={`kpi-card tone-${tone}`}>
      <div className="kpi-label">{icon}<span>{label}</span></div>
      <strong>{value}</strong>
      <p>{note}</p>
    </article>
  );
}

export function OverviewWorkspace({
  dashboard,
  allNodes,
  allEdges,
  scenario,
  focused,
  selectedId,
  shock,
  onFocusedChange,
  onSelect,
  onSimulate,
  onReset,
  canOpenRisk,
  onOpenRisk,
  canOpenMatching,
  onOpenMatching
}: NetworkProps & {
  dashboard: DashboardData;
  onSimulate: () => void;
  onReset: () => void;
  canOpenRisk: boolean;
  onOpenRisk: () => void;
  canOpenMatching: boolean;
  onOpenMatching: () => void;
}) {
  const nodes = focused ? scenario.nodes : allNodes;
  const edges = focused ? scenario.edges : allEdges;
  const trendTotals = dashboard.disruptionTrend.map((item) => item.total);
  const trendCritical = dashboard.disruptionTrend.map((item) => item.highCritical);

  return (
    <div className="page-stack overview-page">
      <div className="overview-grid">
        <section className="map-panel tool-panel">
          <NetworkToolbar focused={focused} onFocusedChange={onFocusedChange} scenario={scenario} />
          <MapView nodes={nodes} edges={edges} selectedId={selectedId} shock={shock} onSelect={onSelect} />
          <div className="map-footbar">
            <div className="legend-row">
              <span><i className="status-dot healthy" />Low</span>
              <span><i className="status-dot watch" />Watch</span>
              <span><i className="status-dot critical" />High</span>
              <span className="legend-divider" />
              <span><i className="role-ring supplier" />Supplier</span>
              <span><i className="role-ring logistics" />Logistics</span>
              <span><i className="role-ring finance" />Finance</span>
            </div>
            <span>Node size reflects role and scale</span>
          </div>
        </section>

        <aside className="insights-column">
          <div className="section-heading"><div><span className="eyebrow">Live demo</span><h2>Key insights</h2></div><Info size={15} /></div>
          <div className="kpi-grid">
            <KpiCard icon={<Users size={17} />} label="Active companies" value={dashboard.overview.activeCompanies.toLocaleString()} note="62 seeded business profiles" />
            <KpiCard icon={<ShieldAlert size={17} />} label="At-risk nodes" value={dashboard.overview.atRiskNodes.toString()} note="Rule-based signal threshold" tone="red" />
            <KpiCard icon={<Building2 size={17} />} label="Affected SMEs" value={(shock.active ? shock.affectedSmeCount : dashboard.overview.affectedSmes).toString()} note={shock.active ? "Current shock scenario" : "Run simulation to calculate"} tone="amber" />
            <KpiCard icon={<ShieldCheck size={17} />} label="Supply health" value={`${dashboard.overview.supplyHealthScore}/100`} note="Network operational indicator" tone="green" />
          </div>

          <div className="simulation-strip">
            <div><AlertTriangle size={18} /><span><strong>Dai Tin disruption</strong><small>{shock.active ? "Scenario active" : "Ready to simulate"}</small></span></div>
            <div className="button-row">
              <button className="primary-button" type="button" onClick={onSimulate} disabled={shock.active}><RefreshCw size={15} />Run</button>
              {shock.active ? <button className="icon-button" type="button" title="Reset scenario" onClick={onReset}><RefreshCw size={16} /></button> : null}
            </div>
          </div>

          <section className="alerts-list" aria-label="Recent alerts">
            <div className="list-title"><h3>Recent alerts</h3><button className="text-button" type="button" disabled={!canOpenRisk} onClick={onOpenRisk}>{canOpenRisk ? "Review risk" : "Risk unavailable"}</button></div>
            {dashboard.recentAlerts.map((alert) => (
              <button className="alert-row" key={alert.id} type="button" disabled={!canOpenRisk} onClick={onOpenRisk}>
                <span className={`alert-icon ${alert.severity}`}><AlertTriangle size={16} /></span>
                <span><strong>{alert.title}</strong><small>{alert.detail}</small></span>
                <time>{alert.age}</time>
                <ChevronRight size={15} />
              </button>
            ))}
          </section>

          {shock.active ? (
            <button className="recovery-cta" type="button" disabled={!canOpenMatching} onClick={onOpenMatching}>
              <span><Route size={18} /><span><strong>{canOpenMatching ? "Recovery plan ready" : "Matching unavailable"}</strong><small>{canOpenMatching ? `${numberCompact.format(shock.monthlyVolumeAtRisk)} units/month exposed` : "This account has no matching workspace access."}</small></span></span>
              <ArrowRight size={17} />
            </button>
          ) : null}
        </aside>
      </div>

      <div className="analytics-grid">
        <section className="analytics-panel health-score-panel">
          <div className="panel-heading"><span>Supply Health Score</span><Info size={14} /></div>
          <Sparkline values={[68, 71, 70, 74, 73, 72, 75, 72]} />
          <strong className="large-score">{dashboard.overview.supplyHealthScore}<small>/100</small></strong>
          <p className="positive-copy"><CheckCircle2 size={14} />Operationally stable</p>
        </section>

        <section className="analytics-panel trend-panel">
          <div className="panel-heading"><span>Monthly Disruptions Trend</span><Info size={14} /></div>
          <div className="chart-legend"><span><i className="line-key cyan" />Total signals</span><span><i className="line-key red" />High / critical</span></div>
          <div className="dual-spark"><Sparkline values={trendTotals} /><Sparkline values={trendCritical} color="#fb7185" /></div>
          <div className="month-axis">{dashboard.disruptionTrend.map((item) => <span key={item.month}>{item.month}</span>)}</div>
        </section>

        <section className="analytics-panel region-panel">
          <div className="panel-heading"><span>Supply Flow by Province</span><Info size={14} /></div>
          <div className="flow-layout">
            <div className="donut" style={{ background: "conic-gradient(#06b6d4 0 38%, #22c55e 38% 67%, #f59e0b 67% 86%, #a78bfa 86% 100%)" }}><span><small>Total flow</small><strong>{numberCompact.format(dashboard.overview.monthlyNetworkVolume)}</strong></span></div>
            <div className="flow-list">{dashboard.regionalFlow.slice(0, 4).map((item, index) => <div key={item.region}><i className={`flow-color f${index}`} /><span>{item.region}</span><strong>{item.share}%</strong></div>)}</div>
          </div>
        </section>

        <section className="analytics-panel risky-table-panel">
          <div className="panel-heading"><span>Top Risk Signals</span><Info size={14} /></div>
          <div className="compact-table">
            <div className="table-head"><span>Company</span><span>Region</span><span>Level</span><span>Score</span></div>
            {dashboard.riskyBusinesses.map((business) => (
              <button type="button" key={business.id} onClick={() => onSelect(business.id)}>
                <span>{business.name}</span><span>{business.province}</span><span><i className={`risk-pill ${riskTone(business.risk)}`}>{riskTone(business.risk)}</i></span><strong>{business.risk}</strong>
              </button>
            ))}
          </div>
        </section>
      </div>
      <DataNotice>{dashboard.dataScope}</DataNotice>
    </div>
  );
}

function accessTone(status: DemoAccessDecision["status"]) {
  if (status === "owner" || status === "consented") return "healthy";
  if (status === "masked" || status === "pending_consent") return "watch";
  return "critical";
}

function AccessDecisionPanel({ decision }: { decision: DemoAccessDecision }) {
  return (
    <div className="access-decision-panel">
      <div className="panel-heading"><span>Access status</span><ShieldCheck size={15} /></div>
      <span className={`access-badge ${accessTone(decision.status)}`}>{accessStatusLabel(decision.status)}</span>
      <p>{decision.reason}</p>
      <div className="access-lists">
        <div><strong>Visible</strong>{decision.allowedFields.slice(0, 4).map((field) => <span key={field}><CheckCircle2 size={12} />{field}</span>)}</div>
        <div><strong>Blocked</strong>{decision.blockedFields.slice(0, 4).map((field) => <span key={field}><ShieldAlert size={12} />{field}</span>)}</div>
      </div>
    </div>
  );
}

export function MapWorkspace(props: NetworkProps & { selected: BusinessNode | undefined; detail: BusinessDetail | null; accessDecision: DemoAccessDecision }) {
  const nodes = props.focused ? props.scenario.nodes : props.allNodes;
  const edges = props.focused ? props.scenario.edges : props.allEdges;
  const sensitiveVisible = canShowSensitiveCompanyData(props.accessDecision);
  return (
    <div className="page-stack map-page">
      <section className="map-panel tool-panel map-expanded">
        <NetworkToolbar focused={props.focused} onFocusedChange={props.onFocusedChange} scenario={props.scenario} />
        <MapView nodes={nodes} edges={edges} selectedId={props.selectedId} shock={props.shock} onSelect={props.onSelect} />
      </section>
      <aside className="selection-inspector tool-panel">
        {props.selected ? <>
          <span className={`risk-pill ${riskTone(props.selected.risk)}`}>{riskTone(props.selected.risk)}</span>
          <h2>{props.selected.name}</h2>
          <p>{roleLabel(props.selected.type)} · {props.selected.province}</p>
          <AccessDecisionPanel decision={props.accessDecision} />
          <div className="inspector-stats"><div><span>Risk signal</span><strong>{sensitiveVisible ? props.selected.risk : "signal"}</strong></div><div><span>Financial health</span><strong>{sensitiveVisible ? props.selected.health : "masked"}</strong></div><div><span>Downstream</span><strong>{sensitiveVisible ? props.detail?.dependencySummary.downstreamBusinessCount ?? 0 : "masked"}</strong></div><div><span>Evidence</span><strong>{sensitiveVisible ? props.detail?.evidenceSummary.total ?? 0 : "metadata"}</strong></div></div>
          <DataNotice>Map locations use real geographic coordinates; relationships and risk are synthetic.</DataNotice>
        </> : null}
      </aside>
    </div>
  );
}

function EvidenceIcon({ type }: { type: EvidenceDocument["type"] }) {
  if (type === "GUARANTEE") return <FileKey2 size={17} />;
  if (type === "CERTIFICATION") return <BadgeCheck size={17} />;
  if (type === "DELIVERY_NOTE") return <Truck size={17} />;
  if (type === "INVOICE") return <CircleDollarSign size={17} />;
  return <FileText size={17} />;
}

function EvidenceStatusPill({ status }: { status: string }) {
  const bucket = evidenceVerificationBucket(status);
  return <i className={bucket === "VERIFIED" ? "verified-state" : bucket === "REJECTED" ? "rejected-state" : "review-state"}>{evidenceStatusLabel(status)}</i>;
}

function evidenceFilterLabel(status: string) {
  if (status === "VERIFIED") return "reviewed";
  if (status === "PENDING") return "pending";
  if (status === "REJECTED") return "rejected";
  return status.toLowerCase();
}

const intakeEvidenceRequirements: Array<{
  documentType: EvidenceDocument["type"];
  title: string;
  classification: string;
  section: string;
}> = [
  { documentType: "CERTIFICATION", title: "Operating certification", classification: "confidential", section: "Profile" },
  { documentType: "GUARANTEE", title: "Guarantee document", classification: "restricted_financial", section: "Finance" },
  { documentType: "INVOICE", title: "Invoice evidence", classification: "restricted_financial", section: "Invoice" },
  { documentType: "CONTRACT", title: "Commercial contract", classification: "confidential", section: "Relationship" }
];

function workflowTone(status: EvidenceWorkflowStatus) {
  if (status === "verified") return "verified";
  if (status === "rejected") return "rejected";
  if (status === "pending") return "pending";
  return "missing";
}

function rowDocumentType(row: Record<string, number | string | null>): string {
  return String(row.document_type ?? row.type ?? row.documentType ?? "").toUpperCase();
}

export function CompaniesWorkspace({
  nodes,
  selectedId,
  onSelect,
  detail,
  evidence,
  pendingEvidenceUploads,
  accessDecision,
  downloadTicket,
  viewError,
  viewingEvidenceVersionId,
  onViewEvidence,
  onCloseDownloadTicket
}: {
  nodes: BusinessNode[];
  selectedId: string;
  onSelect: (id: string) => void;
  detail: BusinessDetail | null;
  evidence: EvidenceVault | null;
  pendingEvidenceUploads: PendingEvidenceUpload[];
  accessDecision: DemoAccessDecision;
  downloadTicket: EvidenceDownloadTicket | null;
  viewError: string | null;
  viewingEvidenceVersionId: string | null;
  onViewEvidence: (document: EvidenceDocument) => void;
  onCloseDownloadTicket: () => void;
}) {
  const [documentType, setDocumentType] = useState("ALL");
  const [documentStatus, setDocumentStatus] = useState("ALL");
  const [activeDocument, setActiveDocument] = useState<EvidenceDocument | null>(null);
  const selectedNode = nodes.find((node) => node.id === selectedId);
  const sensitiveVisible = canShowSensitiveCompanyData(accessDecision);
  const documents = evidence?.documents.filter((item) => {
    const typeMatch = documentType === "ALL" || item.type === documentType;
    const statusMatch = documentStatus === "ALL" || evidenceVerificationBucket(item.verificationStatus) === documentStatus;
    return typeMatch && statusMatch;
  }) ?? [];
  const visiblePendingUploads = pendingEvidenceUploads.filter((item) => {
    const typeMatch = documentType === "ALL" || item.documentType === documentType;
    const statusMatch = documentStatus === "ALL" || documentStatus === "PENDING";
    return typeMatch && statusMatch;
  });
  const pendingCount = pendingEvidenceUploads.length;
  const visibleBusinesses = nodes.filter((node) => ["BIZ-002", "BIZ-005", "BIZ-007", "BIZ-009", "BIZ-011", "BIZ-017", "BIZ-061"].includes(node.id));
  return (
    <div className="business-workspace">
      <section className="company-list tool-panel">
        <div className="panel-heading"><span>Business profiles</span><ListFilter size={15} /></div>
        {visibleBusinesses.map((node) => (
          <button key={node.id} type="button" className={node.id === selectedId ? "selected-company" : ""} onClick={() => onSelect(node.id)}>
            <span className={`company-avatar ${node.type}`}><Building2 size={18} /></span>
            <span><strong>{node.name}</strong><small>{roleLabel(node.type)} · {node.province}</small></span>
            <i className={`status-dot ${riskTone(node.risk)}`} />
          </button>
        ))}
      </section>

      <section className="company-profile">
        {detail ? <>
          <header className="profile-header">
            <div><span className="eyebrow">Business profile</span><h1>{detail.business.name}</h1><p>{roleLabel(detail.business.type)} · {detail.business.province} · {detail.business.category}</p></div>
            <span className="verified-badge"><BadgeCheck size={16} />Demo profile signal</span>
          </header>
          <div className="profile-kpis">
            <KpiCard icon={<ShieldAlert size={16} />} label="Risk signal" value={`${detail.risk.score}/100`} note={detail.risk.level.toUpperCase()} tone="red" />
            <KpiCard icon={<Banknote size={16} />} label="Financial health" value={`${detail.business.health}/100`} note="Management indicator" tone="amber" />
            <KpiCard icon={<GitBranch size={16} />} label="Downstream" value={detail.dependencySummary.downstreamBusinessCount.toString()} note={`${numberCompact.format(detail.dependencySummary.monthlyVolumeSupplied)} units/month`} />
            <KpiCard icon={<FileCheck2 size={16} />} label="Evidence" value={detail.evidenceSummary.total.toString()} note={`${detail.evidenceSummary.verified} reviewed`} tone="green" />
          </div>
          <div className="profile-sections">
            <section><h3>Product capability</h3>{detail.products.map((product, index) => <div className="fact-row" key={String(product.sku ?? index)}><span><PackageCheck size={15} />{String(product.product_name ?? "Product")}</span><strong>{String(product.specification ?? "")}</strong></div>)}</section>
            <section><h3>Risk explanation</h3><p>{detail.risk.explanation}</p><small>{detail.risk.formulaVersion}</small></section>
          </div>
          <DataNotice>{detail.risk.advisoryNotice}</DataNotice>
        </> : sensitiveVisible ? <div className="loading-state">Loading business profile...</div> : selectedNode ? (
          <div className="masked-profile-state">
            <header className="profile-header">
              <div><span className="eyebrow">Business profile</span><h1>{selectedNode.name}</h1><p>{roleLabel(selectedNode.type)} / {selectedNode.province} / {selectedNode.category}</p></div>
              <span className={`access-badge ${accessTone(accessDecision.status)}`}>{accessStatusLabel(accessDecision.status)}</span>
            </header>
            <AccessDecisionPanel decision={accessDecision} />
            <div className="profile-kpis">
              <KpiCard icon={<ShieldAlert size={16} />} label="Risk signal" value="signal" note="Masked summary" tone="amber" />
              <KpiCard icon={<Banknote size={16} />} label="Financial health" value="masked" note="Consent required" tone="amber" />
              <KpiCard icon={<GitBranch size={16} />} label="Relationships" value="masked" note="Policy gated" />
              <KpiCard icon={<FileCheck2 size={16} />} label="Evidence" value="metadata" note="Vault blocked" tone="green" />
            </div>
            <DataNotice>Cross-organization profile data is masked until relationship, consent, purpose and audit policy allow access.</DataNotice>
          </div>
        ) : <div className="empty-document-state">No visible business profile for this account.</div>}
      </section>

      <aside className="evidence-vault tool-panel">
        <div className="vault-heading"><div><span className="eyebrow">Evidence Vault</span><h2>Documents & provenance</h2></div><span>{evidence?.summary.verified ?? 0}/{evidence?.summary.total ?? 0} reviewed · {pendingCount} pending</span></div>
        {sensitiveVisible ? <>
        <div className="vault-status-tabs">{["ALL", "VERIFIED", "PENDING", "REJECTED"].map((status) => <button key={status} type="button" className={documentStatus === status ? "is-active" : ""} onClick={() => setDocumentStatus(status)}>{evidenceFilterLabel(status)}</button>)}</div>
        <div className="document-tabs">{["ALL", "PURCHASE_ORDER", "DELIVERY_NOTE", "CERTIFICATION", "GUARANTEE", "INVOICE", "CONTRACT"].map((type) => <button key={type} type="button" className={documentType === type ? "is-active" : ""} onClick={() => setDocumentType(type)}>{type === "ALL" ? "All" : type.replace("_", " ")}</button>)}</div>
        <div className="document-list">
          {documents.map((document) => (
            <button key={document.id} type="button" onClick={() => setActiveDocument(document)}>
              <span className="document-icon"><EvidenceIcon type={document.type} /></span>
              <span><strong>{document.title}</strong><small>{document.id} · {document.effectiveDate}</small></span>
              <EvidenceStatusPill status={document.verificationStatus} />
            </button>
          ))}
          {!documents.length && !visiblePendingUploads.length ? <div className="empty-document-state">No documents match the current vault filter.</div> : null}
        </div>
        {visiblePendingUploads.length ? (
          <div className="pending-vault-panel">
            <div className="panel-heading"><span>Pending upload tickets</span><Upload size={15} /></div>
            {visiblePendingUploads.map((item) => (
              <div className="pending-vault-row" key={item.id}>
                <span className="document-icon"><EvidenceIcon type={item.documentType} /></span>
                <span><strong>{item.fileName}</strong><small>{item.documentType.replace("_", " ")} / {item.classification}</small></span>
                <EvidenceStatusPill status={item.malwareScanStatus} />
                <p>{item.advisoryNotice ?? "Waiting for object storage persistence and malware scan before this can be used as approved evidence."}</p>
              </div>
            ))}
          </div>
        ) : null}
        </> : (
          <div className="vault-access-state">
            <ShieldAlert size={18} />
            <span><strong>Vault access blocked</strong><small>{accessDecision.reason}</small></span>
          </div>
        )}
        {activeDocument && sensitiveVisible ? (
          <div className="document-detail">
            <div className="panel-heading"><span>{activeDocument.id}</span><button className="icon-button small" type="button" title="Close document" onClick={() => setActiveDocument(null)}>×</button></div>
            <p>{activeDocument.facts.join(" · ")}</p>
            <div className="hash-box"><Fingerprint size={15} /><code>{activeDocument.hash}</code></div>
            <small>Source: {activeDocument.source}</small>
            <div className="document-action-row">
              <button
                className="icon-text-button"
                type="button"
                disabled={!activeDocument.downloadable || !activeDocument.evidenceVersionId || viewingEvidenceVersionId === activeDocument.evidenceVersionId}
                onClick={() => onViewEvidence(activeDocument)}
              >
                <Download size={14} />{viewingEvidenceVersionId === activeDocument.evidenceVersionId ? "Issuing ticket" : "View scan-cleared file"}
              </button>
              {!activeDocument.evidenceVersionId ? <small>Metadata-only demo record.</small> : !activeDocument.downloadable ? <small>Malware scan-clear status required before file access.</small> : null}
            </div>
            {viewError ? <div className="download-ticket-panel rejected"><ShieldAlert size={15} /><span>{viewError}</span></div> : null}
            {downloadTicket && downloadTicket.evidenceVersionId === activeDocument.evidenceVersionId ? (
              <div className="download-ticket-panel">
                <div className="panel-heading"><span>Read-only file access ticket</span><button className="icon-button small" type="button" title="Close ticket" onClick={onCloseDownloadTicket}>x</button></div>
                <span><strong>{downloadTicket.objectStorageStatus}</strong><small>{downloadTicket.downloadMethod} / expires in {downloadTicket.expiresInSeconds}s / {downloadTicket.contentType}</small></span>
                <code>{downloadTicket.downloadUrl}</code>
                <small>Policy {downloadTicket.policyDecisionId} / audit {downloadTicket.auditEventId} / object access {downloadTicket.objectAccessId}</small>
                {downloadTicket.downloadUrl.startsWith("http") ? <a className="icon-text-button" href={downloadTicket.downloadUrl} target="_blank" rel="noreferrer"><Download size={14} />Open signed URL</a> : null}
              </div>
            ) : null}
          </div>
        ) : null}
        {evidence && sensitiveVisible ? <DataNotice>{evidence.dataScope}</DataNotice> : null}
      </aside>
    </div>
  );
}

export function RiskWorkspace({ signal, canOpenMatching, onOpenMatching }: { signal: RiskSignal | null; canOpenMatching: boolean; onOpenMatching: () => void }) {
  if (!signal) return <div className="loading-state">Loading evidence-based risk signal...</div>;
  return (
    <div className="risk-workspace page-stack">
      <header className="workspace-heading"><div><span className="eyebrow">Evidence-based analysis</span><h1>Risk Signal Review</h1><p>Dai Tin Distribution · rule set {signal.formulaVersion}</p></div><span className="confidence-ring"><strong>{signal.confidence}%</strong><small>confidence</small></span></header>
      <section className="risk-summary-band">
        <div className="risk-severity"><AlertTriangle size={28} /><span><small>{signal.riskType.replace(/_/g, " ")}</small><strong>{signal.level}</strong></span></div>
        <p>{signal.summary}</p>
        <button className="primary-button" type="button" disabled={!canOpenMatching} onClick={onOpenMatching}>{canOpenMatching ? "Review alternatives" : "Matching unavailable"}<ArrowRight size={16} /></button>
      </section>
      <div className="risk-columns">
        <section className="rule-panel tool-panel">
          <div className="panel-heading"><span>Deterministic rule trace</span><ShieldCheck size={16} /></div>
          {signal.triggers.map((trigger) => (
            <div className="rule-row" key={trigger.rule}>
              <span className={trigger.result === "triggered" ? "rule-hit" : "rule-clear"}>{trigger.result === "triggered" ? <AlertTriangle size={15} /> : <Check size={15} />}</span>
              <span><strong>{trigger.rule}</strong><small>Observed {trigger.observed} · threshold {trigger.threshold}</small></span>
              <i>{trigger.result.replace("_", " ")}</i>
            </div>
          ))}
        </section>
        <section className="evidence-chain tool-panel">
          <div className="panel-heading"><span>Linked evidence chain</span><Database size={16} /></div>
          {signal.evidence.map((document, index) => (
            <div className="chain-row" key={document.id}>
              <span className="chain-index">{index + 1}</span>
              <EvidenceIcon type={document.type} />
              <span><strong>{document.title}</strong><small>{document.facts[document.facts.length - 1]}</small></span>
              <EvidenceStatusPill status={document.verificationStatus} />
            </div>
          ))}
        </section>
      </div>
      <section className="actions-panel tool-panel">
        <div className="panel-heading"><span>Suggested actions for human review</span><Users size={16} /></div>
        <div className="action-list">{signal.suggestedActions.map((action, index) => <div key={action}><span>{index + 1}</span><p>{action}</p></div>)}</div>
      </section>
      <DataNotice>{signal.disclaimer}</DataNotice>
    </div>
  );
}

export function MatchingWorkspace({ recommendations, request, selectedPeriod, accessByBusinessId, canConnect, onConnect }: { recommendations: Recommendation[]; request: ConnectionRequest | null; selectedPeriod: string; accessByBusinessId: Record<string, DemoAccessDecision>; canConnect: boolean; onConnect: (supplierId: string) => void }) {
  const periodNotice = matchingPeriodNotice(recommendations, selectedPeriod);
  return (
    <div className="page-stack matching-workspace">
      <header className="workspace-heading">
        <div>
          <span className="eyebrow">Human-reviewed recovery</span>
          <h1>Alternative Supplier Shortlist</h1>
          <p>Buyer: Thu Duc Retail Mart / disrupted supplier: Dai Tin Distribution / period {selectedPeriod}</p>
        </div>
        <span className="qualification-badge"><ShieldCheck size={16} />Qualified candidates only</span>
      </header>
      <section className="matching-criteria">
        {[["Product/spec", "25%"], ["Capacity", "20%"], ["Distance", "15%"], ["Financial health", "15%"], ["Reliability", "10%"], ["Payment term", "10%"]].map(([label, weight]) => <div key={label}><span>{label}</span><strong>{weight}</strong></div>)}
      </section>
      <div className="recommendation-grid">
        {!recommendations.length ? (
          <div className="empty-document-state empty-grid-state">
            No supplier shortlist is available for selected period {selectedPeriod}. Relationship, consent and review gates stay closed.
          </div>
        ) : null}
        {recommendations.map((recommendation, index) => {
          const access = accessByBusinessId[recommendation.supplierId];
          const periodLabel = recommendationPeriodLabel(recommendation, selectedPeriod);
          return (
            <article className={index === 0 ? "supplier-card best-match" : "supplier-card"} key={recommendation.supplierId}>
              <header><div>{index === 0 ? <span className="best-label">Best fit</span> : <span className="rank-label">#{index + 1}</span>}<h2>{recommendation.supplierName}</h2><p>{recommendation.leadTimeDays} day expected lead time / period {periodLabel}</p></div><span className="match-score"><strong>{recommendation.score}</strong><small>/100</small></span></header>
              <div className="supplier-access-strip"><span className={`access-badge ${accessTone(access?.status ?? "masked")}`}>{(access?.status ?? "masked").replace("_", " ")}</span><small>{access?.reason ?? "Cross-organization data is masked until consent is granted."}</small></div>
              <div className="component-bars">
                {Object.entries(recommendation.components).slice(0, 6).map(([label, value]) => <div key={label}><span>{label.replace(/_/g, " ")}</span><i><b style={{ width: `${Math.min(100, value)}%` }} /></i><strong>{Math.round(value)}</strong></div>)}
              </div>
              <div className="reason-chips">{recommendation.reasons.map((reason) => <span key={reason}><CheckCircle2 size={13} />{reason}</span>)}</div>
              <div className="tradeoff"><Info size={14} /><span>{access?.status === "pending_consent" ? "Introduction requested; contact and commercial terms remain hidden until supplier consent." : index === 0 ? "Strong product and capacity fit; supplier consent still required." : index === 1 ? "Shorter route, but payment terms require review." : "Useful split-order option; lower capacity headroom."}</span></div>
              <button className="primary-button" type="button" disabled={!canConnect || access?.status === "pending_consent"} onClick={() => onConnect(recommendation.supplierId)}><Send size={16} />{!canConnect ? "Review only" : access?.status === "pending_consent" ? "Consent pending" : "Request introduction"}</button>
            </article>
          );
        })}
      </div>
      {request ? <div className="request-success"><CheckCircle2 size={20} /><span><strong>Connection request {request.requestId} created</strong><small>{request.status} · {request.consentStatus.replace(/_/g, " ")}</small></span><span>{request.nextStep}</span></div> : null}
      <DataNotice>{periodNotice}</DataNotice>
    </div>
  );
}

function registrationTone(status: SupplyMapRegistration["status"]) {
  if (status === "approved") return "healthy";
  if (status === "rejected") return "critical";
  return "watch";
}

export function OnboardingWorkspace({
  account,
  registrations,
  connectionRequests,
  canCreate,
  canReview,
  canDecideConnectionRequest,
  onCreate,
  onDecision,
  onConnectionDecision
}: {
  account: DemoAccount;
  registrations: SupplyMapRegistration[];
  connectionRequests: ConnectionRequest[];
  canCreate: boolean;
  canReview: boolean;
  canDecideConnectionRequest: boolean;
  onCreate: (draft: {
    organizationName: string;
    stakeholderRole: SupplyMapRegistration["stakeholderRole"];
    province: string;
    category: string;
    scale: string;
    contactEmail: string;
    intendedRelationships: string[];
    dataBoundary: string;
  }) => void | Promise<void>;
  onDecision: (registrationId: string, decision: "approve" | "request_changes" | "reject", note: string) => void | Promise<void>;
  onConnectionDecision: (requestId: string, decision: "grant_consent" | "reject" | "request_changes" | "activate_relationship") => void | Promise<void>;
}) {
  const [draft, setDraft] = useState({
    organizationName: account.organizationName,
    stakeholderRole: account.actorRole === "lender" ? "financial_partner" : account.actorRole === "sme_submitter" || account.actorRole === "buyer_admin" ? "retailer" : "distributor" as SupplyMapRegistration["stakeholderRole"],
    province: "TP.HCM",
    category: account.actorRole === "lender" ? "finance" : "beverage",
    scale: "SME",
    contactEmail: `${account.actorId}@demo.vietsupply.local`,
    intendedRelationships: "supplier_review, evidence_sharing",
    dataBoundary: "masked profile, products, evidence metadata"
  });
  const [reviewNote, setReviewNote] = useState("Reviewed for demo onboarding; human approval required before unmasking relationships.");
  const [connectionFilter, setConnectionFilter] = useState<ConnectionRequestFilter>("open");
  const submittedCount = registrations.filter((item) => item.status === "submitted").length;
  const approvedCount = registrations.filter((item) => item.status === "approved").length;
  const openConnectionCount = connectionRequests.filter((item) => item.status !== "relationship_active" && item.status !== "rejected").length;
  const actionableConnectionCount = connectionRequests.filter((item) => connectionRequestIsActionable(account, item, canDecideConnectionRequest)).length;
  const filteredConnectionRequests = connectionRequests.filter((item) => connectionRequestMatchesFilter(connectionFilter, item, account, canDecideConnectionRequest));

  function updateDraft<K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function submitDraft() {
    onCreate({
      ...draft,
      intendedRelationships: draft.intendedRelationships.split(",").map((item) => item.trim()).filter(Boolean)
    });
  }

  return (
    <div className="page-stack onboarding-workspace">
      <header className="workspace-heading">
        <div><span className="eyebrow">Supply map membership</span><h1>Stakeholder Onboarding</h1><p>{account.organizationName} · {account.stakeholder}</p></div>
        <span className="qualification-badge"><ShieldCheck size={16} />Review-gated</span>
      </header>

      <section className="onboarding-summary">
        <KpiCard icon={<Building2 size={16} />} label="Visible demo nodes" value={approvedCount.toString()} note="Approved membership records" tone="green" />
        <KpiCard icon={<Clock3 size={16} />} label="Review queue" value={submittedCount.toString()} note="Submitted requests pending review" tone="amber" />
        <KpiCard icon={<Handshake size={16} />} label="Connection inbox" value={openConnectionCount.toString()} note="Consent and contract gated" tone="amber" />
        <KpiCard icon={<Users size={16} />} label="Account scope" value={canReview ? "Queue" : "Own org"} note={account.actorRole.replace("_", " ")} />
      </section>

      <div className="onboarding-grid">
        <section className="tool-panel onboarding-form-panel">
          <div className="panel-heading"><span>Registration request</span><FileText size={16} /></div>
          {canCreate ? (
            <>
              <div className="onboarding-field-grid">
                <label><span>Organization</span><input value={draft.organizationName} onChange={(event) => updateDraft("organizationName", event.target.value)} /></label>
                <label><span>Role</span><select value={draft.stakeholderRole} onChange={(event) => updateDraft("stakeholderRole", event.target.value as SupplyMapRegistration["stakeholderRole"])}><option value="retailer">SME / Retailer</option><option value="manufacturer">Manufacturer</option><option value="distributor">Distributor</option><option value="wholesaler">Wholesaler</option><option value="logistics_partner">Logistics</option><option value="financial_partner">Finance</option></select></label>
                <label><span>Province</span><select value={draft.province} onChange={(event) => updateDraft("province", event.target.value)}><option>TP.HCM</option><option>Binh Duong</option><option>Dong Nai</option><option>Lam Dong</option></select></label>
                <label><span>Category</span><input value={draft.category} onChange={(event) => updateDraft("category", event.target.value)} /></label>
                <label><span>Scale</span><select value={draft.scale} onChange={(event) => updateDraft("scale", event.target.value)}><option>Household business</option><option>SME</option><option>Anchor buyer</option><option>Finance partner</option><option>Logistics partner</option></select></label>
                <label><span>Contact</span><input value={draft.contactEmail} onChange={(event) => updateDraft("contactEmail", event.target.value)} /></label>
              </div>
              <label className="onboarding-wide-field"><span>Relationship intents</span><input value={draft.intendedRelationships} onChange={(event) => updateDraft("intendedRelationships", event.target.value)} /></label>
              <label className="onboarding-wide-field"><span>Data boundary</span><input value={draft.dataBoundary} onChange={(event) => updateDraft("dataBoundary", event.target.value)} /></label>
              <button className="primary-button" type="button" onClick={submitDraft}><Send size={15} />Submit for review</button>
            </>
          ) : <div className="intake-permission-note">This account can review onboarding records but cannot create membership requests.</div>}
        </section>

        <aside className="tool-panel onboarding-review-panel">
          <div className="panel-heading"><span>{canReview ? "Review queue" : "My registration status"}</span><ShieldAlert size={16} /></div>
          {canReview ? <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} aria-label="Onboarding review note" /> : null}
          <div className="registration-list">
            {registrations.map((item) => (
              <div className="registration-row" key={item.id}>
                <span className={`risk-pill ${registrationTone(item.status)}`}>{item.status.replace("_", " ")}</span>
                <div><strong>{item.organizationName}</strong><small>{roleLabel(item.stakeholderRole)} · {item.province} · {item.mapVisibility.replace(/_/g, " ")}</small></div>
                <p>{item.dataBoundary}</p>
                {canReview ? (
                  <div className="button-row registration-actions">
                    <button className="icon-text-button" type="button" disabled={item.status === "approved"} onClick={() => onDecision(item.id, "approve", reviewNote)}><CheckCircle2 size={14} />Approve</button>
                    <button className="icon-text-button" type="button" disabled={item.status === "approved"} onClick={() => onDecision(item.id, "request_changes", reviewNote)}><AlertTriangle size={14} />Changes</button>
                    <button className="icon-text-button" type="button" disabled={item.status === "approved"} onClick={() => onDecision(item.id, "reject", reviewNote)}><ShieldAlert size={14} />Reject</button>
                  </div>
                ) : <small>{item.reviewerNote ?? item.advisoryNotice}</small>}
              </div>
            ))}
            {!registrations.length ? <div className="empty-document-state">No onboarding records visible for this account.</div> : null}
          </div>
        </aside>
      </div>

      <section className="tool-panel connection-inbox-panel">
        <div className="panel-heading"><span>Connection consent inbox</span><Handshake size={16} /></div>
        <div className="connection-inbox-summary">
          <span><strong>{connectionRequests.length}</strong><small>visible requests</small></span>
          <span><strong>{openConnectionCount}</strong><small>awaiting action</small></span>
          <span><strong>{actionableConnectionCount}</strong><small>action needed</small></span>
          <span><strong>{account.organizationId}</strong><small>organization scope</small></span>
        </div>
        <div className="connection-filter-tabs">
          {CONNECTION_REQUEST_FILTERS.map((filter) => (
            <button key={filter} type="button" className={connectionFilter === filter ? "is-active" : ""} onClick={() => setConnectionFilter(filter)}>
              {connectionRequestFilterLabel(filter)}
            </button>
          ))}
        </div>
        <div className="connection-request-list">
          {filteredConnectionRequests.map((request) => {
            const isClosed = request.status === "relationship_active" || request.status === "rejected";
            const canAct = canDecideConnectionRequest && !isClosed;
            const canConsent = canAct && request.consentStatus !== "supplier_consented" && canGrantConnectionConsent(account, request);
            const canActivate = canAct && request.consentStatus === "supplier_consented" && canActivateConnection(account);
            const canChanges = canAct && canRequestConnectionChanges(account, request);
            const canReject = canAct && canRejectConnection(account, request);
            return (
              <div className="connection-request-row" key={request.requestId}>
                <span className={`risk-pill ${connectionRequestTone(request.status)}`}>{request.status.replace(/_/g, " ")}</span>
                <div className="connection-request-main">
                  <strong>{request.buyerId} -&gt; {request.targetSupplierId}</strong>
                  <small>{request.requestId} / {request.consentStatus.replace(/_/g, " ")}</small>
                  <small>{connectionRequestPerspectiveLabel(account, request)} / requested {new Date(request.requestedAt).toLocaleDateString()}</small>
                </div>
                {request.relationshipEdgeId ? <small>edge {request.relationshipEdgeId}</small> : <small>{request.disruptedSupplierId ? `alternative to ${request.disruptedSupplierId}` : "direct relationship request"}</small>}
                {canAct && (canConsent || canActivate || canChanges || canReject) ? (
                  <div className="button-row request-actions">
                    {canConsent ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "grant_consent")}><CheckCircle2 size={14} />Consent</button> : null}
                    {canActivate ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "activate_relationship")}><Handshake size={14} />Activate</button> : null}
                    {canChanges ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "request_changes")}><AlertTriangle size={14} />Changes</button> : null}
                    {canReject ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "reject")}><ShieldAlert size={14} />Reject</button> : null}
                  </div>
                ) : null}
                {request.nextStep ? <p>{request.nextStep}</p> : null}
              </div>
            );
          })}
          {!filteredConnectionRequests.length ? <div className="empty-document-state">No connection requests match this filter for the current account.</div> : null}
        </div>
      </section>

      <DataNotice>Supply map membership is review-gated; approved demo nodes remain masked until relationship consent and data-sharing policy allow access.</DataNotice>
    </div>
  );
}

export function DataIntakeWorkspace({
  nodes,
  selectedId,
  selectedPeriod,
  periods,
  submission,
  snapshot,
  importBatch,
  errorReport,
  pendingEvidenceUploads,
  vaultDocuments,
  evidenceScanJob,
  permittedBusinessIds,
  actionPermissions,
  reviewQueue,
  reviewQueueNotice,
  busy,
  onSelect,
  onPeriodChange,
  onCreateDraft,
  onSaveDraft,
  onValidate,
  onSubmit,
  onReviewDecision,
  onReviewQueueSelect,
  onImportCsv,
  onEvidenceUpload,
  onRunEvidenceScan,
  onLoadErrorReport
}: {
  nodes: BusinessNode[];
  selectedId: string;
  selectedPeriod: string;
  periods: PeriodKey[];
  submission: DataSubmission | null;
  snapshot: PeriodSnapshot | null;
  importBatch: CsvImportBatch | null;
  errorReport: IntakeErrorReport | null;
  pendingEvidenceUploads: PendingEvidenceUpload[];
  vaultDocuments: EvidenceDocument[];
  evidenceScanJob: EvidenceScanJobResult | null;
  permittedBusinessIds: string[];
  actionPermissions: {
    canCreateDraft: boolean;
    canSaveDraft: boolean;
    canValidateDraft: boolean;
    canSubmitDraft: boolean;
    canApproveDraft: boolean;
    canUploadEvidence: boolean;
    canScanEvidence: boolean;
  };
  reviewQueue: ReviewQueueItem[];
  reviewQueueNotice: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onPeriodChange: (period: string) => void;
  onCreateDraft: (sections: Record<string, unknown>) => Promise<void>;
  onSaveDraft: (sections: Record<string, unknown>) => Promise<void>;
  onValidate: () => Promise<void>;
  onSubmit: () => Promise<void>;
  onReviewDecision: (decision: "approve" | "reject" | "request_changes", note: string) => Promise<void>;
  onReviewQueueSelect: (item: ReviewQueueItem) => Promise<void>;
  onImportCsv: (dataset: string, fileName: string, csvText: string) => Promise<void>;
  onEvidenceUpload: (file: File, documentType: string, classification: string) => Promise<void>;
  onRunEvidenceScan: () => Promise<void>;
  onLoadErrorReport: (format?: "json" | "csv") => Promise<void>;
}) {
  const businessOptions = nodes.filter((node) => permittedBusinessIds.includes(node.id));
  const business = businessOptions.find((node) => node.id === selectedId) ?? businessOptions[0] ?? nodes.find((node) => node.id === selectedId) ?? nodes[0];
  const [financials, setFinancials] = useState({
    revenue: "790000000",
    cash_in: "810000000",
    cash_out: "730000000",
    debt: "180000000",
    accounts_receivable: "120000000",
    accounts_payable: "90000000",
    inventory_value: "160000000",
    late_payment_rate: "0.04",
    delivery_delay_rate: "0.02"
  });
  const [product, setProduct] = useState({
    sku: "SME-BEV-330",
    product_name: "Ready drink 330ml",
    category: "beverage",
    specification: "330ml can",
    available_capacity: "12000",
    min_order_value: "5000000",
    price_range: "mid",
    certifications: "HACCP"
  });
  const [evidence, setEvidence] = useState({
    document_type: "CERTIFICATION",
    title: "HACCP monthly certificate",
    document_hash: "hash-haccp-demo",
    classification: "confidential"
  });
  const [dataset, setDataset] = useState("financials");
  const [csvText, setCsvText] = useState("revenue,cash_in,cash_out,debt,accounts_receivable,accounts_payable,inventory_value,late_payment_rate,delivery_delay_rate\n620000000,640000000,590000000,140000000,80000000,70000000,120000000,0.03,0.01");
  const [uploadDocumentType, setUploadDocumentType] = useState<EvidenceDocument["type"]>("CERTIFICATION");
  const [uploadClassification, setUploadClassification] = useState("confidential");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadInputVersion, setUploadInputVersion] = useState(0);
  const [reviewDecision, setReviewDecision] = useState<"approve" | "reject" | "request_changes">("approve");
  const [reviewNote, setReviewNote] = useState("Reviewed from Data Intake queue; human approval required before downstream use.");

  const sections = {
    financials: Object.fromEntries(Object.entries(financials).map(([key, value]) => [key, Number(value)])),
    products: [Object.fromEntries(Object.entries(product).map(([key, value]) => ["available_capacity", "min_order_value"].includes(key) ? [key, Number(value)] : [key, value]))],
    evidence: [evidence]
  };
  const issues = submission?.issues ?? [];
  const reportRows = errorReport?.rows ?? [];
  const reportSummary = {
    errors: errorReport?.summary.errors ?? submission?.validationSummary.errors ?? 0,
    warnings: errorReport?.summary.warnings ?? submission?.validationSummary.warnings ?? 0,
    infos: errorReport?.summary.infos ?? submission?.validationSummary.infos ?? 0,
    rows: errorReport?.summary.rows ?? reportRows.length
  };
  const showErrorReport = Boolean(submission && (errorReport || importBatch?.status === "quarantined" || issues.length));
  const selectedReviewTask = submission ? reviewQueue.find((item) => item.submissionId === submission.id) : null;
  const selectedEvidenceBlocked = Boolean(selectedReviewTask?.evidenceReview.approvalBlocked);
  const selectedQueueRequirements = selectedReviewTask?.evidenceReview.requirements ?? [];
  const evidenceRequirementRows = intakeEvidenceRequirements.map((requirement) => {
    const vaultMatches = vaultDocuments.filter((document) => document.type === requirement.documentType);
    const uploadMatches = pendingEvidenceUploads.filter((item) => item.documentType === requirement.documentType);
    const snapshotMatches = (snapshot?.evidence ?? []).filter((row) => rowDocumentType(row) === requirement.documentType);
    const statuses = [
      ...vaultMatches.map((document) => document.verificationStatus),
      ...uploadMatches.map((item) => item.malwareScanStatus),
      ...snapshotMatches.map((row) => evidenceRecordStatus(row))
    ];
    const workflowStatus = evidenceWorkflowStatus(statuses);
    return {
      ...requirement,
      workflowStatus,
      evidenceCount: vaultMatches.length + snapshotMatches.length,
      uploadCount: uploadMatches.length
    };
  });
  const clearedRequirementCount = evidenceRequirementRows.filter((item) => item.workflowStatus === "verified").length;
  const blockedRequirementCount = evidenceRequirementRows.filter((item) => item.workflowStatus === "pending" || item.workflowStatus === "rejected").length;
  const pendingScanCount = pendingEvidenceUploads.filter((item) => item.malwareScanStatus === "pending_scan").length
    + vaultDocuments.filter((item) => Boolean(item.evidenceVersionId) && evidenceVerificationBucket(item.verificationStatus) === "PENDING").length;

  function updateFinancial(key: keyof typeof financials, value: string) {
    setFinancials((current) => ({ ...current, [key]: value }));
  }

  function updateProduct(key: keyof typeof product, value: string) {
    setProduct((current) => ({ ...current, [key]: value }));
  }

  function updateEvidence(key: keyof typeof evidence, value: string) {
    setEvidence((current) => ({ ...current, [key]: value }));
  }

  async function submitEvidenceUpload() {
    if (!uploadFile || !actionPermissions.canUploadEvidence) return;
    await onEvidenceUpload(uploadFile, uploadDocumentType, uploadClassification);
    setUploadFile(null);
    setUploadInputVersion((current) => current + 1);
  }

  function applyEvidenceRequirement(requirement: (typeof intakeEvidenceRequirements)[number]) {
    setUploadDocumentType(requirement.documentType);
    setUploadClassification(requirement.classification);
    setEvidence((current) => ({
      ...current,
      document_type: requirement.documentType,
      title: requirement.title,
      classification: requirement.classification
    }));
  }

  return (
    <div className="page-stack intake-workspace">
      <header className="workspace-heading">
        <div><span className="eyebrow">Periodic input pipeline</span><h1>Data Intake</h1><p>{business?.name ?? selectedId} · {selectedPeriod} · Draft to approved snapshot</p></div>
        <span className="qualification-badge"><Database size={16} />Raw · staging · canonical</span>
      </header>

      <section className="intake-control-strip tool-panel">
        <label><span>Business</span><select value={business?.id ?? selectedId} disabled={businessOptions.length <= 1} onChange={(event) => onSelect(event.target.value)}>{businessOptions.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}</select></label>
        <label><span>Period</span><input type="month" value={selectedPeriod} onChange={(event) => onPeriodChange(event.target.value)} /></label>
        <label><span>Known periods</span><select value={selectedPeriod} onChange={(event) => onPeriodChange(event.target.value)}><option value={selectedPeriod}>{selectedPeriod}</option>{periods.filter((period) => period.periodKey !== selectedPeriod).slice(0, 12).map((period) => <option key={period.id} value={period.periodKey}>{period.periodKey} · {period.status}</option>)}</select></label>
        <div className="intake-state"><span>Status</span><strong>{submission?.status ?? snapshot?.latestSubmissionStatus ?? "not started"}</strong></div>
      </section>

      <div className="intake-grid">
        <section className="tool-panel intake-form-panel">
          <div className="panel-heading"><span>Manual form</span><FileText size={16} /></div>
          <div className="intake-section-title"><h3>Financials</h3><small>Monthly management figures</small></div>
          <div className="intake-field-grid">
            {Object.entries(financials).map(([key, value]) => <label key={key}><span>{key.replace(/_/g, " ")}</span><input value={value} disabled={!actionPermissions.canSaveDraft} onChange={(event) => updateFinancial(key as keyof typeof financials, event.target.value)} /></label>)}
          </div>
          <div className="intake-section-title"><h3>Product capability</h3><small>One SKU for the v1 P0 flow</small></div>
          <div className="intake-field-grid">
            {Object.entries(product).map(([key, value]) => <label key={key}><span>{key.replace(/_/g, " ")}</span><input value={value} disabled={!actionPermissions.canSaveDraft} onChange={(event) => updateProduct(key as keyof typeof product, event.target.value)} /></label>)}
          </div>
          <div className="intake-section-title"><h3>Evidence</h3><small>Metadata only; object storage is a production target</small></div>
          <div className="intake-field-grid">
            {Object.entries(evidence).map(([key, value]) => <label key={key}><span>{key.replace(/_/g, " ")}</span><input value={value} disabled={!actionPermissions.canSaveDraft} onChange={(event) => updateEvidence(key as keyof typeof evidence, event.target.value)} /></label>)}
          </div>
          <div className="evidence-upload-box">
            <div className="panel-heading"><span>Create evidence upload ticket</span><Upload size={16} /></div>
            <div className="evidence-requirement-panel">
              <div className="evidence-requirement-head">
                <span>Evidence requirements</span>
                <strong>{clearedRequirementCount}/{evidenceRequirementRows.length} review-cleared</strong>
              </div>
              <div className="evidence-requirement-grid">
                {evidenceRequirementRows.map((requirement) => (
                  <button
                    key={requirement.documentType}
                    type="button"
                    disabled={!actionPermissions.canUploadEvidence}
                    className={`evidence-requirement-row ${workflowTone(requirement.workflowStatus)} ${uploadDocumentType === requirement.documentType ? "is-selected" : ""}`.trim()}
                    onClick={() => applyEvidenceRequirement(requirement)}
                  >
                    <span className="document-icon"><EvidenceIcon type={requirement.documentType} /></span>
                    <span><strong>{requirement.title}</strong><small>{requirement.section} / {requirement.classification.replace("_", " ")}</small></span>
                    <i>{evidenceWorkflowLabel(requirement.workflowStatus)}</i>
                    <small>{requirement.evidenceCount} source / {requirement.uploadCount} pending</small>
                  </button>
                ))}
              </div>
              {blockedRequirementCount ? <small>{blockedRequirementCount} requirement groups are pending scan or rejected; reviewer approval stays gated by malware scan-clear evidence status.</small> : null}
            </div>
            {actionPermissions.canUploadEvidence ? (
              <div className="upload-control-grid">
                <label><span>Document type</span><select value={uploadDocumentType} onChange={(event) => setUploadDocumentType(event.target.value as EvidenceDocument["type"])}><option value="CERTIFICATION">Certification</option><option value="GUARANTEE">Guarantee</option><option value="INVOICE">Invoice</option><option value="PURCHASE_ORDER">Purchase order</option><option value="DELIVERY_NOTE">Delivery note</option><option value="CONTRACT">Contract</option></select></label>
                <label><span>Classification</span><select value={uploadClassification} onChange={(event) => setUploadClassification(event.target.value)}><option value="confidential">confidential</option><option value="restricted_financial">restricted financial</option><option value="partner_visible">partner visible</option><option value="public">public</option></select></label>
                <label className="file-picker"><span>File</span><input key={uploadInputVersion} type="file" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} /></label>
                <button className="icon-text-button" type="button" disabled={busy || !uploadFile} onClick={submitEvidenceUpload}><Upload size={15} />Create ticket</button>
              </div>
            ) : <div className="intake-permission-note">Reviewer view: evidence upload is disabled; approval requires malware scan-clear status from the vault.</div>}
            <div className="evidence-scan-control">
              <div>
                <strong>Malware scan queue</strong>
                <small>{pendingScanCount} pending scan for {selectedPeriod}; clean means malware-clear only, not document authenticity or financing approval.</small>
              </div>
              {actionPermissions.canScanEvidence ? (
                <button className="icon-text-button" type="button" disabled={busy || pendingScanCount === 0} onClick={onRunEvidenceScan}>
                  <RefreshCw size={15} />Run demo scan
                </button>
              ) : <small>Scanner/operator role required.</small>}
            </div>
            {evidenceScanJob ? (
              <div className="evidence-scan-result">
                <span>{evidenceScanJob.processed}/{evidenceScanJob.candidates} processed · {evidenceScanJob.skipped} skipped</span>
                <small>{evidenceScanJob.advisoryNotice}</small>
                {evidenceScanJob.errors.length ? <small>{evidenceScanJob.errors.slice(0, 2).join(" / ")}</small> : null}
              </div>
            ) : null}
            <div className="upload-register">
              {pendingEvidenceUploads.length ? pendingEvidenceUploads.slice(0, 5).map((item) => (
                <div className="upload-register-row" key={item.id}>
                  <span className="document-icon"><EvidenceIcon type={item.documentType} /></span>
                  <span><strong>{item.fileName}</strong><small>{item.documentType.replace("_", " ")} / {item.classification}</small></span>
                  <EvidenceStatusPill status={item.malwareScanStatus} />
                </div>
              )) : <div className="empty-document-state">No pending evidence tickets for this period.</div>}
            </div>
          </div>
          <div className="button-row intake-actions">
            {actionPermissions.canCreateDraft ? <button className="primary-button" type="button" disabled={busy} onClick={() => onCreateDraft(sections)}><FileCheck2 size={15} />Create draft</button> : null}
            {actionPermissions.canSaveDraft ? <button className="icon-text-button" type="button" disabled={busy || !submission} onClick={() => onSaveDraft(sections)}><Check size={15} />Autosave</button> : null}
            {actionPermissions.canValidateDraft ? <button className="icon-text-button" type="button" disabled={busy || !submission} onClick={onValidate}><ShieldCheck size={15} />Validate</button> : null}
            {actionPermissions.canSubmitDraft ? <button className="primary-button" type="button" disabled={busy || !submission} onClick={onSubmit}><Send size={15} />Submit</button> : null}
          </div>
        </section>

        <aside className="tool-panel csv-panel">
          <div className="panel-heading"><span>CSV import</span><Database size={16} /></div>
          <label><span>Dataset</span><select value={dataset} disabled={!actionPermissions.canSaveDraft} onChange={(event) => setDataset(event.target.value)}><option value="financials">financials</option><option value="products">products</option><option value="evidence">evidence</option></select></label>
          <textarea value={csvText} disabled={!actionPermissions.canSaveDraft} onChange={(event) => setCsvText(event.target.value)} aria-label="CSV intake text" />
          <button className="primary-button" type="button" disabled={busy || !actionPermissions.canSaveDraft} onClick={() => onImportCsv(dataset, `${dataset}-${selectedPeriod}.csv`, csvText)}><Database size={15} />Parse CSV</button>
          {!actionPermissions.canSaveDraft ? <div className="intake-permission-note">Read/review role: CSV import is disabled for this account.</div> : null}
          {importBatch ? <div className="import-preview"><strong>{importBatch.fileName}</strong><span>{importBatch.rowCount} rows · {importBatch.status} · {importBatch.idempotentReplay ? "replay" : "new batch"}</span>{importBatch.previewRows.slice(0, 3).map((row, index) => <code key={index}>{JSON.stringify(row)}</code>)}</div> : null}
        </aside>

        <aside className="tool-panel intake-status-panel">
          <div className="panel-heading"><span>Validation & review</span><ShieldAlert size={16} /></div>
          {actionPermissions.canApproveDraft ? (
            <div className="review-queue-card">
              <div className="panel-heading"><span>Reviewer queue</span><Clock3 size={16} /></div>
              <div className="review-task-list">
                {reviewQueue.map((item) => (
                  <button
                    key={item.reviewTaskId}
                    type="button"
                    disabled={busy}
                    className={`${submission?.id === item.submissionId ? "is-active" : ""} ${item.evidenceReview.approvalBlocked ? "is-blocked" : ""}`.trim()}
                    onClick={() => { void onReviewQueueSelect(item); }}
                  >
                    <strong>{item.organizationName}</strong>
                    <span>{item.periodKey} / {item.source} v{item.version}</span>
                    <small>Assigned to {item.assignedTo ?? "unassigned"} / {item.assignmentReason?.replace(/_/g, " ") ?? item.assignedRole}</small>
                    <small>{item.validationSummary.errors} errors / {item.validationSummary.warnings} warnings</small>
                    <small>{item.evidenceReview.required ? `Evidence ${item.evidenceReview.clean} scan-cleared / ${item.evidenceReview.pending} pending / ${item.evidenceReview.rejected} rejected` : "No evidence gate items"}</small>
                    {item.evidenceReview.requirements.length ? <small>{item.evidenceReview.requirements.slice(0, 2).map((requirement) => `${requirement.documentType}:${evidenceWorkflowLabel(requirement.status as EvidenceWorkflowStatus)}`).join(" / ")}</small> : null}
                  </button>
                ))}
                {!reviewQueue.length ? <div className="empty-document-state">No submitted intake tasks waiting for review.</div> : null}
              </div>
              {reviewQueueNotice ? <small>{reviewQueueNotice}</small> : null}
            </div>
          ) : null}
          <div className="submission-card">
            <span>Submission</span>
            <strong>{submission?.id ?? "No draft"}</strong>
            <small>v{submission?.version ?? 0} · {submission?.source ?? "manual/csv"} · {submission?.validationSummary.errors ?? 0} errors · {submission?.validationSummary.warnings ?? 0} warnings</small>
          </div>
          {actionPermissions.canApproveDraft ? (
            <div className="review-decision-box">
              <label><span>Decision</span><select value={reviewDecision} onChange={(event) => setReviewDecision(event.target.value as typeof reviewDecision)}><option value="approve">Approve snapshot</option><option value="request_changes">Request changes</option><option value="reject">Reject submission</option></select></label>
              <label><span>Review note</span><textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} aria-label="Data intake review note" /></label>
              <button className="primary-button" type="button" disabled={busy || !submission?.reviewTask || (reviewDecision === "approve" && selectedEvidenceBlocked)} onClick={() => onReviewDecision(reviewDecision, reviewNote)}><CheckCircle2 size={15} />Record decision</button>
              {!submission?.reviewTask ? <small>Select an open review task before recording a decision.</small> : null}
              {reviewDecision === "approve" && selectedEvidenceBlocked ? <small>{selectedReviewTask?.evidenceReview.advisory}</small> : null}
            </div>
          ) : null}
          <div className="issue-list">
            {issues.length ? issues.map((issue) => <div key={issue.id} className={`issue-row ${issue.severity}`}><strong>{issue.severity}</strong><span>{issue.section} · {issue.message}</span></div>) : <div className="issue-row info"><strong>info</strong><span>No validation issues for the current draft.</span></div>}
          </div>
          {showErrorReport ? (
            <div className="error-report-panel">
              <div className="error-report-header">
                <div><strong>Quarantine report</strong><span>{importBatch?.status ?? "validation"} / {reportSummary.rows} rows</span></div>
                <AlertTriangle size={16} />
              </div>
              <div className="error-report-summary">
                <span><strong>{reportSummary.errors}</strong>errors</span>
                <span><strong>{reportSummary.warnings}</strong>warnings</span>
                <span><strong>{reportSummary.infos}</strong>info</span>
              </div>
              <div className="button-row report-actions">
                <button className="icon-text-button" type="button" disabled={busy || !submission} onClick={() => onLoadErrorReport("json")}><FileText size={14} />View report</button>
                <button className="icon-text-button" type="button" disabled={busy || !submission} onClick={() => onLoadErrorReport("csv")}><Download size={14} />Export CSV</button>
              </div>
              {reportRows.length ? (
                <div className="error-report-list">
                  {reportRows.slice(0, 6).map((row, index) => (
                    <div key={`${row.source}-${row.rawRecordId ?? row.path ?? index}`} className={`error-report-row ${row.severity}`}>
                      <strong>{row.row ?? "-"}</strong>
                      <span>{row.dataset ?? row.source} / {row.column ?? row.path ?? "-"} / {row.code}</span>
                      <small>{row.message}</small>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="snapshot-summary">
            <h3>Approved snapshot</h3>
            <p>{snapshot?.approvedVersion ? `Version ${snapshot.approvedVersion} approved ${snapshot.approvedAt}` : "No approved snapshot for this period."}</p>
            <span>{snapshot?.financials?.length ?? 0} financial · {snapshot?.products?.length ?? 0} products · {snapshot?.evidence?.length ?? 0} evidence</span>
          </div>
          <div className="snapshot-summary evidence-gate-summary">
            <h3>Evidence gate</h3>
            <p>{selectedReviewTask?.evidenceReview.required ? selectedReviewTask.evidenceReview.advisory : "No submitted review task is selected for this period."}</p>
            <span>{selectedReviewTask?.evidenceReview.clean ?? clearedRequirementCount} scan-cleared/review-cleared / {selectedReviewTask?.evidenceReview.pending ?? pendingEvidenceUploads.length} pending / {selectedReviewTask?.evidenceReview.rejected ?? 0} rejected</span>
            {selectedQueueRequirements.length ? (
              <div className="evidence-gate-requirements">
                {selectedQueueRequirements.map((requirement) => (
                  <i key={`${requirement.documentType}-${requirement.section}`} className={workflowTone(requirement.status as EvidenceWorkflowStatus)}>
                    {requirement.documentType}: {evidenceWorkflowLabel(requirement.status as EvidenceWorkflowStatus)}
                  </i>
                ))}
              </div>
            ) : null}
          </div>
        </aside>
      </div>

      <section className="tool-panel period-history">
        <div className="panel-heading"><span>Period history</span><Clock3 size={16} /></div>
        <div className="period-list">{periods.slice(0, 10).map((period) => <button key={period.id} type="button" onClick={() => onPeriodChange(period.periodKey)} className={period.periodKey === selectedPeriod ? "is-active" : ""}><strong>{period.periodKey}</strong><span>{period.status}</span><small>{period.latestSubmissionStatus ?? "no submission"}</small></button>)}</div>
      </section>
      <DataNotice>{submission?.advisoryNotice ?? snapshot?.advisoryNotice ?? "Data intake is decision-support only and requires human review before use."}</DataNotice>
    </div>
  );
}

function CashflowChart({ finance }: { finance: FinanceData }) {
  const max = Math.max(1, ...finance.series.flatMap((item) => [item.cashIn, item.cashOut]));
  const points = (key: "cashIn" | "cashOut") => finance.series.map((item, index) => {
    const x = finance.series.length === 1 ? 50 : 6 + (index / (finance.series.length - 1)) * 88;
    const y = 90 - (item[key] / max) * 74;
    return `${x},${y}`;
  }).join(" ");
  return (
    <div className="cashflow-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        {[20, 40, 60, 80].map((y) => <line key={y} x1="4" x2="96" y1={y} y2={y} className="grid-line" />)}
        <polyline points={points("cashIn")} className="cash-in-line" />
        <polyline points={points("cashOut")} className="cash-out-line" />
      </svg>
      <div className="month-axis">{finance.series.map((item) => <span key={item.month}>{item.month.slice(5)}</span>)}</div>
    </div>
  );
}

function scopeLabel(scope?: string) {
  return scope ? scope.replace(/_/g, " ") : "policy scoped";
}

function FinanceLockedState({ account, message }: { account: DemoAccount; message?: string | null }) {
  return (
    <div className="page-stack finance-workspace">
      <header className="workspace-heading"><div><span className="eyebrow">Restricted financial data</span><h1>Financial Health & Cash Flow</h1><p>{account.organizationName} / {account.actorRole.replace("_", " ")}</p></div><span className="qualification-badge"><ShieldAlert size={16} />Policy gated</span></header>
      <section className="tool-panel access-empty-state">
        <ShieldAlert size={22} />
        <span><strong>No financial snapshot is available for this account scope.</strong><small>{message ?? "Financials require own-organization access or active financial-summary consent."}</small></span>
      </section>
      <DataNotice>Financial indicators are management review signals only; they are not credit approval, default probability or lending eligibility.</DataNotice>
    </div>
  );
}

export function FinanceWorkspace({ finance, account, accessNotice }: { finance: FinanceData | null; account: DemoAccount; accessNotice?: string | null }) {
  if (!finance) {
    return accessNotice ? <FinanceLockedState account={account} message={accessNotice} /> : <div className="loading-state">Loading financial health model...</div>;
  }
  const latest = finance.latest;
  const periodState = financePeriodState(finance);
  const healthScore = periodState.hasSelectedPeriodData ? finance.health.score : "-";
  const healthLevel = periodState.hasSelectedPeriodData ? finance.health.level : "no data";
  return (
    <div className="page-stack finance-workspace">
      <header className="workspace-heading"><div><span className="eyebrow">Explainable management indicators</span><h1>Financial Health & Cash Flow</h1><p>{finance.business.name} · {finance.series.length} monthly synthetic snapshots · {periodState.statusLabel}</p></div><span className={`health-badge ${finance.health.level}`}><strong>{healthScore}</strong><small>{healthLevel}</small></span></header>
      <section className="tool-panel finance-scope-strip">
        <span><strong>{scopeLabel(finance.accessScope)}</strong><small>{finance.dataScope ?? "restricted_financial"}</small></span>
        <span><strong>{account.actorRole.replace("_", " ")}</strong><small>{account.organizationId}</small></span>
        <span><strong>{finance.policyDecisionId ?? "local-demo"}</strong><small>policy decision</small></span>
      </section>
      {!periodState.hasSelectedPeriodData ? (
        <section className="tool-panel access-empty-state">
          <AlertTriangle size={22} />
          <span><strong>No exact financial row exists for the selected month.</strong><small>{periodState.chartNote}</small></span>
        </section>
      ) : null}
      <div className="finance-kpis">
        <KpiCard icon={<Banknote size={17} />} label="Net cash flow" value={latest ? `${latest.netCashFlow < 0 ? "-" : "+"}VND ${moneyCompact.format(Math.abs(latest.netCashFlow))}` : "-"} note={periodState.kpiNote} tone={latest && latest.netCashFlow < 0 ? "red" : "green"} />
        <KpiCard icon={<CircleDollarSign size={17} />} label="Working capital" value={latest ? `VND ${moneyCompact.format(latest.workingCapital)}` : "-"} note="AR + inventory - AP" />
        <KpiCard icon={<Clock3 size={17} />} label="Receivable proxy" value={latest ? `${latest.receivableDaysProxy} days` : "-"} note="Not audited DSO" tone="amber" />
        <KpiCard icon={<Landmark size={17} />} label="Debt pressure" value={latest ? `${latest.debtToMonthlyRevenue}x` : "-"} note="Debt / monthly revenue" tone="red" />
      </div>
      <div className="finance-main-grid">
        <section className="tool-panel cashflow-panel">
          <div className="panel-heading"><span>Cash in vs cash out</span><div className="chart-legend"><span><i className="line-key green" />Cash in</span><span><i className="line-key red" />Cash out</span></div></div>
          <CashflowChart finance={finance} />
        </section>
        <section className="tool-panel health-components">
          <div className="panel-heading"><span>Health components</span><Info size={14} /></div>
          {Object.entries(finance.health.components).map(([label, value]) => <div key={label}><span>{label.replace(/_/g, " ")}</span><i><b style={{ width: `${value}%` }} /></i><strong>{value}</strong></div>)}
          <p>{finance.health.explanation}</p>
          <small>{finance.health.formulaVersion}</small>
        </section>
      </div>
      <section className="tool-panel finance-table">
        <div className="panel-heading"><span>Monthly cash-flow register</span><Database size={15} /></div>
        <div className="table-scroll"><table><thead><tr><th>Month</th><th>Cash in</th><th>Cash out</th><th>Net</th><th>Working capital</th><th>Late payment</th></tr></thead><tbody>{finance.series.length ? finance.series.map((item) => <tr key={item.month}><td>{item.month}</td><td>VND {moneyCompact.format(item.cashIn)}</td><td>VND {moneyCompact.format(item.cashOut)}</td><td className={item.netCashFlow < 0 ? "negative" : "positive"}>VND {moneyCompact.format(item.netCashFlow)}</td><td>VND {moneyCompact.format(item.workingCapital)}</td><td>{Math.round(item.latePaymentRate * 100)}%</td></tr>) : <tr><td colSpan={6}>No financial register rows are visible for this account scope.</td></tr>}</tbody></table></div>
      </section>
      <DataNotice>{periodState.notice}</DataNotice>
    </div>
  );
}

function InvoiceLockedState({ account, message }: { account: DemoAccount; message?: string | null }) {
  return (
    <div className="page-stack invoice-workspace">
      <header className="workspace-heading"><div><span className="eyebrow">Restricted invoice register</span><h1>Invoice Integrity Review</h1><p>{account.organizationName} / {account.actorRole.replace("_", " ")}</p></div><span className="qualification-badge"><ShieldAlert size={16} />Consent required</span></header>
      <section className="tool-panel access-empty-state">
        <ShieldAlert size={22} />
        <span><strong>No invoice register item is available for this account scope.</strong><small>{message ?? "Invoice review requires seller/buyer party membership or explicit invoice-claim consent."}</small></span>
      </section>
      <DataNotice>Invoice registry signals do not confirm invoice authenticity, legal enforceability or financing approval.</DataNotice>
    </div>
  );
}

export function InvoiceWorkspace({ invoice, account, accessNotice }: { invoice: InvoiceVerificationData | null; account: DemoAccount; accessNotice?: string | null }) {
  if (!invoice) {
    return accessNotice ? <InvoiceLockedState account={account} message={accessNotice} /> : <div className="loading-state">Loading invoice review...</div>;
  }
  const hashMatch = invoice.storedHash === invoice.computedHash;
  const fundingStateLabel = invoiceFundingStateLabel(invoice.fundingStatus);
  const fundingStateNotice = invoiceFundingStateNotice(invoice.fundingStatus);
  return (
    <div className="page-stack invoice-workspace">
      <header className="workspace-heading"><div><span className="eyebrow">Evidence integrity & financing guardrail</span><h1>Invoice Integrity Review</h1><p>{invoice.invoiceId} · seller {invoice.sellerId} · buyer {invoice.buyerId}</p></div><span className={invoice.doubleFinancingAlert ? "invoice-state danger" : "invoice-state clear"}>{invoice.doubleFinancingAlert ? <ShieldAlert size={18} /> : <ShieldCheck size={18} />}{invoice.doubleFinancingAlert ? "Review required" : "No duplicate registry signal"}</span></header>
      <section className="tool-panel finance-scope-strip">
        <span><strong>{scopeLabel(invoice.accessScope)}</strong><small>{invoice.dataScope ?? "restricted_financial"}</small></span>
        <span><strong>{account.actorRole.replace("_", " ")}</strong><small>{account.organizationId}</small></span>
        <span><strong>{invoice.policyDecisionId ?? "local-demo"}</strong><small>policy decision</small></span>
      </section>
      <div className="invoice-grid">
        <section className="tool-panel invoice-paper">
          <div className="invoice-top"><div><FileText size={25} /><span><small>E-INVOICE</small><strong>{invoice.invoiceId}</strong></span></div><span className="verified-badge"><BadgeCheck size={15} />Demo signal</span></div>
          <div className="invoice-parties"><div><span>Seller</span><strong>{invoice.sellerId}</strong></div><ArrowRight size={18} /><div><span>Buyer</span><strong>{invoice.buyerId}</strong></div></div>
          <div className="invoice-amount"><span>Total amount</span><strong>VND {invoice.amount.toLocaleString()}</strong></div>
          <div className="invoice-dates"><div><span>Issue date</span><strong>{invoice.issueDate}</strong></div><div><span>Due date</span><strong>{invoice.dueDate}</strong></div><div><span>Lender-recorded funding state</span><strong>{fundingStateLabel}</strong><small>{fundingStateNotice}</small></div></div>
        </section>
        <section className="tool-panel verification-checks">
          <div className="panel-heading"><span>Three-party review signals</span><FileCheck2 size={16} /></div>
          {[{ label: "Seller confirmation signal", ok: invoice.confirmedBy.includes("seller") }, { label: "Buyer confirmation signal", ok: invoice.confirmedBy.includes("buyer") }, { label: "Hash match signal", ok: hashMatch }, { label: "Duplicate financing registry scan", ok: !invoice.doubleFinancingAlert }].map((check) => <div key={check.label}><span className={check.ok ? "check-ok" : "check-bad"}>{check.ok ? <Check size={15} /> : <AlertTriangle size={15} />}</span><span><strong>{check.label}</strong><small>{check.ok ? "Signal present; still subject to review" : "Manual review required"}</small></span></div>)}
          <div className="hash-compare"><div><span>Stored hash</span><code>{invoice.storedHash}</code></div><div><span>Computed hash</span><code>{invoice.computedHash}</code></div></div>
        </section>
      </div>
      <section className="guarantee-band"><FileKey2 size={21} /><span><strong>Linked financial assurance</strong><small>Performance guarantee GUA-001 · VND 350M · issuer BIZ-061 · expires 2026-09-30</small></span><span className="review-state">review</span></section>
      <DataNotice>{`${invoice.advisoryNotice} Funding lifecycle states are registry/lender records, not VietSupply financing approval.`}</DataNotice>
    </div>
  );
}

function opsStatusTone(status: string) {
  if (["failed", "skipped"].includes(status)) return "critical";
  if (["queued", "running", "pending"].includes(status)) return "watch";
  return "healthy";
}

function demoAccountCapabilities(account: DemoAccount) {
  return [
    { label: "Intake", enabled: account.allowedViews.includes("intake"), detail: account.scopes.includes("intake:write") ? "write" : "view/review" },
    { label: "Onboarding", enabled: account.allowedViews.includes("onboarding"), detail: ["reviewer", "system_admin", "demo_operator"].includes(account.actorRole) ? "review queue" : "own org" },
    { label: "Graph", enabled: account.allowedViews.includes("map") || account.allowedViews.includes("matching"), detail: account.scopes.includes("commercial_graph:read") ? "masked analysis" : "consent gated" },
    { label: "Finance", enabled: account.allowedViews.includes("finance") || account.allowedViews.includes("invoice"), detail: account.actorRole === "lender" ? "review only" : "restricted" },
    { label: "Audit/Ops", enabled: account.allowedViews.includes("audit"), detail: account.scopes.includes("ops:read") ? "ops read" : "denied" }
  ];
}

export function AuditWorkspace({
  audit,
  adminOps,
  accounts,
  activeAccount,
  canDecideConnectionRequest,
  onConnectionDecision
}: {
  audit: AuditData | null;
  adminOps: AdminOpsData | null;
  accounts: DemoAccount[];
  activeAccount: DemoAccount;
  canDecideConnectionRequest: boolean;
  onConnectionDecision: (requestId: string, decision: "grant_consent" | "reject" | "request_changes" | "activate_relationship") => Promise<void>;
}) {
  if (!audit) return <div className="loading-state">Loading audit trail...</div>;
  const [selectedAccountId, setSelectedAccountId] = useState(activeAccount.id);
  const [auditRequestFilter, setAuditRequestFilter] = useState<ConnectionRequestFilter>("open");
  const selectedAccount = accounts.find((account) => account.id === selectedAccountId) ?? activeAccount;
  const selectedCapabilities = demoAccountCapabilities(selectedAccount);
  const visibleAuditConnectionRequests = audit.connectionRequests.filter((request) => connectionRequestMatchesFilter(auditRequestFilter, request, activeAccount, canDecideConnectionRequest));
  const queuedJobs = adminOps?.recomputeJobs.filter((job) => job.status === "queued").length ?? 0;
  const modelRows = adminOps?.models.length ? adminOps.models : [{ id: "no-model", artifactType: "none", modelVersion: "No model versions", name: "No model versions", status: "empty", config: {} }];
  const rulesetRows = adminOps?.rulesets.length ? adminOps.rulesets : [{ id: "no-ruleset", artifactType: "none", rulesetVersion: "No ruleset versions", name: "No ruleset versions", status: "empty", config: {} }];
  const jobRows = adminOps?.recomputeJobs.length ? adminOps.recomputeJobs : [{ id: "no-job", organizationId: "-", jobType: "No queued jobs", status: "empty", attempts: 0, maxAttempts: 0, payload: {} }];
  return (
    <div className="page-stack audit-workspace">
      <header className="workspace-heading"><div><span className="eyebrow">Governance & human control</span><h1>Audit Trail</h1><p>Every evidence review, simulation and connection request is traceable.</p></div><span className="qualification-badge"><ShieldCheck size={16} />Append-only demo log</span></header>
      <div className="audit-grid">
        <section className="tool-panel audit-events">
          <div className="panel-heading"><span>Recent events</span><Database size={16} /></div>
          {audit.events.slice(0, 20).map((event) => <div className="audit-row" key={event.eventId}><span className="audit-mark"><Fingerprint size={15} /></span><span><strong>{event.eventType.replace(/_/g, " ")}</strong><small>{event.actorId} · {event.purpose.replace(/_/g, " ")} · subject {event.subjectId}</small></span><time>{new Date(event.timestamp).toLocaleString()}</time></div>)}
        </section>
        <section className="tool-panel request-register">
          <div className="panel-heading"><span>Human approval queue</span><Handshake size={16} /></div>
          <div className="connection-filter-tabs">
            {CONNECTION_REQUEST_FILTERS.map((filter) => (
              <button key={filter} type="button" className={auditRequestFilter === filter ? "is-active" : ""} onClick={() => setAuditRequestFilter(filter)}>
                {connectionRequestFilterLabel(filter)}
              </button>
            ))}
          </div>
          {visibleAuditConnectionRequests.map((request) => {
            const isClosed = request.status === "relationship_active" || request.status === "rejected";
            const canAct = canDecideConnectionRequest && !isClosed;
            return (
              <div className="request-row" key={request.requestId}>
                <div><strong>{request.requestId}</strong><span>{request.buyerId} to {request.targetSupplierId}</span></div>
                <span className={`risk-pill ${connectionRequestTone(request.status)}`}>{request.status.replace(/_/g, " ")}</span>
                <small>{connectionRequestPerspectiveLabel(activeAccount, request)} / {request.consentStatus.replace(/_/g, " ")}</small>
                {request.relationshipEdgeId ? <small>edge {request.relationshipEdgeId}</small> : null}
                {request.auditEventId ? <small>audit {request.auditEventId}</small> : null}
                {canAct ? (
                  <div className="button-row request-actions">
                    {request.consentStatus !== "supplier_consented" && canGrantConnectionConsent(activeAccount, request) ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "grant_consent")}><CheckCircle2 size={14} />Consent</button> : null}
                    {request.consentStatus === "supplier_consented" && canActivateConnection(activeAccount) ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "activate_relationship")}><Handshake size={14} />Activate</button> : null}
                    {canRequestConnectionChanges(activeAccount, request) ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "request_changes")}><AlertTriangle size={14} />Changes</button> : null}
                    {canRejectConnection(activeAccount, request) ? <button className="icon-text-button" type="button" onClick={() => onConnectionDecision(request.requestId, "reject")}><ShieldAlert size={14} />Reject</button> : null}
                  </div>
                ) : null}
                {request.nextStep ? <small>{request.nextStep}</small> : null}
              </div>
            );
          })}
          {!visibleAuditConnectionRequests.length ? <div className="empty-document-state">No connection requests match this queue filter.</div> : null}
          <div className="guardrail-list"><h3>Enforced boundaries</h3>{["No automatic supplier replacement", "No contract amendment", "No lending decision", "Consent before contact release", "Evidence provenance retained"].map((item) => <span key={item}><CheckCircle2 size={14} />{item}</span>)}</div>
        </section>
      </div>
      <section className="tool-panel ops-panel">
        <div className="panel-heading"><span>Ops registry & recompute</span><RefreshCw size={16} /></div>
        {adminOps ? (
          <>
            <div className="ops-summary">
              <div><span>Models</span><strong>{adminOps.models.length}</strong></div>
              <div><span>Rulesets</span><strong>{adminOps.rulesets.length}</strong></div>
              <div><span>Queued jobs</span><strong>{queuedJobs}</strong></div>
              <div><span>Access</span><strong>{adminOps.access}</strong></div>
            </div>
            <div className="ops-grid">
              <div>
                <h3>Model registry</h3>
                {modelRows.slice(0, 5).map((model) => <div className="ops-row" key={model.id}><span><strong>{model.artifactType}</strong><small>{model.modelVersion}</small></span><i className={`risk-pill ${opsStatusTone(model.status)}`}>{model.status}</i></div>)}
              </div>
              <div>
                <h3>Ruleset registry</h3>
                {rulesetRows.slice(0, 5).map((ruleset) => <div className="ops-row" key={ruleset.id}><span><strong>{ruleset.artifactType}</strong><small>{ruleset.rulesetVersion}</small></span><i className={`risk-pill ${opsStatusTone(ruleset.status)}`}>{ruleset.status}</i></div>)}
              </div>
              <div>
                <h3>Recompute jobs</h3>
                {jobRows.slice(0, 6).map((job) => <div className="ops-row" key={job.id}><span><strong>{job.jobType}</strong><small>{job.organizationId} / {job.attempts}/{job.maxAttempts}</small></span><i className={`risk-pill ${opsStatusTone(job.status)}`}>{job.status}</i></div>)}
              </div>
            </div>
            <DataNotice>{adminOps.advisoryNotice}</DataNotice>
          </>
        ) : (
          <div className="ops-locked"><ShieldAlert size={18} /><span><strong>Ops policy gate locked</strong><small>No authorized registry or recompute view for this actor.</small></span></div>
        )}
      </section>
      <section className="tool-panel access-governance-panel">
        <div className="panel-heading"><span>Access governance</span><UserRoundCheck size={16} /></div>
        <div className="access-governance-grid">
          <div className="account-roster">
            {accounts.map((account) => (
              <button key={account.id} type="button" className={account.id === selectedAccount.id ? "is-active" : ""} onClick={() => setSelectedAccountId(account.id)}>
                <span><strong>{account.label}</strong><small>{account.stakeholder}</small></span>
                <i className={`risk-pill ${account.allowedViews.includes("audit") ? "healthy" : account.allowedViews.includes("intake") ? "watch" : "critical"}`}>{account.actorRole.replace("_", " ")}</i>
              </button>
            ))}
          </div>
          <div className="account-detail-panel">
            <div className="account-detail-head">
              <span><strong>{selectedAccount.personName}</strong><small>{selectedAccount.organizationName} / {selectedAccount.organizationId}</small></span>
              <i className="access-badge healthy">{selectedAccount.actorRole.replace("_", " ")}</i>
            </div>
            <p>{selectedAccount.description}</p>
            <div className="scope-chip-list">{selectedAccount.scopes.map((scope) => <span key={scope}>{scope}</span>)}</div>
            <div className="capability-grid">
              {selectedCapabilities.map((item) => (
                <div key={item.label} className={item.enabled ? "capability-enabled" : "capability-disabled"}>
                  <span>{item.enabled ? <CheckCircle2 size={13} /> : <ShieldAlert size={13} />}{item.label}</span>
                  <small>{item.detail}</small>
                </div>
              ))}
            </div>
            <div className="allowed-view-list"><strong>Views</strong>{selectedAccount.allowedViews.map((view) => <span key={view}>{view}</span>)}</div>
          </div>
        </div>
        <DataNotice>Demo RBAC mirrors the active account headers. Real pilot mode must enforce roles with verified JWT/OIDC, backend policy decisions and database RLS.</DataNotice>
      </section>
      <DataNotice>{audit.dataScope}</DataNotice>
    </div>
  );
}
