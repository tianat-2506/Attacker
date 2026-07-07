import { describe, expect, it, vi, afterEach } from "vitest";
import {
  completeEvidenceUploadTicket,
  createEvidenceDownloadTicket,
  createConsent,
  createDataSubmission,
  createEvidenceUploadTicket,
  createConnectionRequest,
  createImportBatch,
  createInvoiceClaim,
  decideConnectionRequest,
  decideReviewTask,
  getAdminOps,
  getAuthMe,
  getBusinessDetail,
  getConnectionRequests,
  getDataSubmissionErrorReport,
  getDashboard,
  getEvidence,
  getFinance,
  getGraph,
  getInvoiceVerification,
  getMatchRuns,
  getPendingEvidenceUploads,
  getPeriodSnapshot,
  getPeriods,
  getRecommendations,
  getReviewQueue,
  getRiskSignal,
  getRiskRuns,
  runEvidenceScanJob,
  setDemoAccountContext,
  submitDataSubmission,
  transitionInvoiceClaim,
  validateDataSubmission
} from "./client";
import { defaultDemoAccount, demoAccounts } from "../utils/demoAccounts";

afterEach(() => {
  setDemoAccountContext(defaultDemoAccount);
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("api client trust headers", () => {
  it("requests the masked graph with demo actor headers and parses masked metrics", async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({
        data: {
          nodes: [
            {
              id: "BIZ-005",
              name: "Distributor 005",
              type: "distributor",
              province: "Binh Duong",
              category: "beverage",
              lat: 11,
              lng: 106.7,
              revenue: 0,
              capacity: 0,
              health: 0,
              risk: 0
            }
          ],
          edges: [
            {
              id: "EDGE-001",
              sourceId: "BIZ-002",
              targetId: "BIZ-005",
              category: "beverage",
              volume: 0,
              leadTimeDays: 2,
              reliability: 0.93,
              relation_type: "supply"
            }
          ]
        }
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    ));
    vi.stubGlobal("fetch", fetchMock);

    const graph = await getGraph();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init?.headers as Headers;

    expect(String(url)).toMatch(/\/api\/v1\/graph$/);
    expect(headers.get("X-Actor-Id")).toBe("demo-user");
    expect(headers.get("X-Actor-Role")).toBe("demo_operator");
    expect(headers.get("X-Purpose")).toBe("demo_view");
    expect(graph.fallback).toBe(false);
    expect(graph.nodes[0].name).toBe("Distributor 005");
    expect(graph.nodes[0].risk).toBe(0);
    expect(graph.edges[0].volume).toBe(0);
  });

  it("uses the selected demo stakeholder account in request headers", async () => {
    const lender = demoAccounts.find((account) => account.id === "lender")!;
    setDemoAccountContext(lender);
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({ data: { nodes: [], edges: [] } }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    ));
    vi.stubGlobal("fetch", fetchMock);

    await getGraph();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init?.headers as Headers;

    expect(headers.get("X-Organization-Id")).toBe("BIZ-062");
    expect(headers.get("X-Actor-Id")).toBe("lender-062");
    expect(headers.get("X-Actor-Role")).toBe("lender");
    expect(headers.get("X-Purpose")).toBe("invoice_financing_review");
  });

  it("does not hide demo policy denials behind fallback data", async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({ detail: { code: "POLICY_DENIED" } }),
      { status: 403, headers: { "Content-Type": "application/json" } }
    ));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getGraph()).rejects.toThrow("/api/v1/graph returned 403");
    await expect(getFinance("BIZ-005")).rejects.toThrow("/api/v1/businesses/BIZ-005/finance returned 403");
    await expect(getInvoiceVerification("INV-0242")).rejects.toThrow("/api/v1/invoices/INV-0242/verification returned 403");
  });

  it("keeps offline invoice fallback tied to the requested invoice id", async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError("offline");
    });
    vi.stubGlobal("fetch", fetchMock);

    const invoice = await getInvoiceVerification("INV-0241");
    expect(invoice.invoiceId).toBe("INV-0241");
    expect(invoice.sellerId).toBe("BIZ-002");
    expect(invoice.buyerId).toBe("BIZ-005");
    expect(invoice.amount).toBe(240_000_000);
    expect(invoice.fundingStatus).toBe("funded");
    await expect(getInvoiceVerification("INV-999")).rejects.toThrow("No synthetic invoice fallback is mapped for INV-999");
  });

  it("does not send demo headers or silently fallback outside demo mode", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_APP_MODE", "pilot");
    vi.stubEnv("VITE_AUTH_TOKEN", "pilot-token");
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({ detail: { code: "SERVICE_UNAVAILABLE" } }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    ));
    vi.stubGlobal("fetch", fetchMock);

    const { getGraph } = await import("./client");
    await expect(getGraph()).rejects.toThrow("/api/v1/graph returned 503");

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer pilot-token");
    expect(headers.get("X-Actor-Id")).toBeNull();
    expect(headers.get("X-Actor-Role")).toBeNull();
    expect(headers.get("X-Purpose")).toBeNull();
  });

  it("adds the selected period to company evidence risk and finance reads", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/risk-signal")) return new Response(JSON.stringify({ data: { signal_id: "RISK-1", business_id: "BIZ-005", risk_type: "DELIVERY", level: "MEDIUM", confidence: 67, summary: "Period signal.", triggers: [], evidence_ids: [], evidence: [], suggested_actions: [], formula_version: "risk-v1", evidence_scope: "evidence_blocked_by_policy", policy_decision_id: "POL-RISK", audit_event_id: "AUD-RISK", disclaimer: "Advisory." } }), { status: 200 });
      if (url.includes("/finance")) return new Response(JSON.stringify({ data: { business: { id: "BIZ-005", name: "Dai Tin Distribution", type: "distributor", province: "Binh Duong", category: "beverage", lat: 10.9, lng: 106.7, revenue: 1, capacity: 1, health: 40, risk: 70 }, health: { score: 0, level: "no_period_data", components: {}, formula_version: "finance-v1", explanation: "No row." }, latest: null, previous: null, series: [], access_scope: "owner", data_scope: "restricted_financial", advisory_notice: "Selected period.", policy_decision_id: "POL-F" } }), { status: 200 });
      if (url.includes("/evidence")) return new Response(JSON.stringify({ data: { business_id: "BIZ-005", period_key: "2026-07", documents: [], summary: { total: 0, verified: 0, needs_review: 0 }, data_scope: "Selected period." } }), { status: 200 });
      return new Response(JSON.stringify({ data: { business: { id: "BIZ-005", name: "Dai Tin Distribution", type: "distributor", province: "Binh Duong", category: "beverage", lat: 10.9, lng: 106.7, revenue: 1, capacity: 1, health: 40, risk: 70 }, products: [], risk: { score: 50, level: "watch", formula_version: "risk-v1", drivers: [], explanation: "Period detail.", advisory_notice: "Advisory." }, financial_summary: null, dependency_summary: { downstream_business_count: 0, monthly_volume_supplied: 0 }, evidence_summary: { total: 0, verified: 0, by_type: {} } } }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await getBusinessDetail("BIZ-005", "2026-07");
    await getEvidence("BIZ-005", "2026-07");
    const riskSignal = await getRiskSignal("BIZ-005", "2026-07");
    await getFinance("BIZ-005", "2026-07");

    const urls = fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://localhost"));
    expect(urls.some((url) => url.pathname === "/api/v1/businesses/BIZ-005" && url.searchParams.get("period") === "2026-07")).toBe(true);
    expect(urls.some((url) => url.pathname === "/api/v1/businesses/BIZ-005/evidence" && url.searchParams.get("period") === "2026-07")).toBe(true);
    expect(urls.some((url) => url.pathname === "/api/v1/businesses/BIZ-005/risk-signal" && url.searchParams.get("period") === "2026-07")).toBe(true);
    expect(urls.some((url) => url.pathname === "/api/v1/businesses/BIZ-005/finance" && url.searchParams.get("period") === "2026-07")).toBe(true);
    expect(riskSignal.evidenceScope).toBe("evidence_blocked_by_policy");
    expect(riskSignal.policyDecisionId).toBe("POL-RISK");
    expect(riskSignal.auditEventId).toBe("AUD-RISK");
  });

  it("maps dashboard alert business ids for risk navigation", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      data: {
        overview: {
          active_companies: 62,
          at_risk_nodes: 5,
          affected_smes: 0,
          supply_health_score: 72,
          monthly_network_volume: 547000,
          advisory_notice: "Decision support only."
        },
        disruption_trend: [],
        regional_flow: [],
        recent_alerts: [
          {
            id: "ALT-001",
            severity: "high",
            title: "Delivery risk signal at Dai Tin Distribution",
            detail: "3 reviewed purchase-order records exceeded the contracted delivery SLA.",
            age: "27 min",
            business_id: "BIZ-005"
          }
        ],
        risky_businesses: [],
        data_scope: "Synthetic demonstration dataset."
      }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const dashboard = await getDashboard();

    expect(dashboard.recentAlerts[0].businessId).toBe("BIZ-005");
  });

  it("adds the selected period to supplier recommendation requests", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ data: [{ supplier_id: "BIZ-007", supplier_name: "An Phu FMCG Hub", match_score: 82, new_edge_preview: { lead_time_days: 2 }, reason_codes: ["period_context"], components: { capacity: 80 }, period_key: "2026-07", advisory_notice: "Suggested alternative for selected period 2026-07 only." }] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const recommendations = await getRecommendations("BIZ-009", "2026-07", "BIZ-013");

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.period_key).toBe("2026-07");
    expect(body.disrupted_supplier_id).toBe("BIZ-013");
    expect(recommendations[0].periodKey).toBe("2026-07");
    expect(recommendations[0].advisoryNotice).toContain("selected period 2026-07");
  });

  it("filters fallback recommendations away from the selected disrupted supplier", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: { code: "SERVICE_UNAVAILABLE" } }), { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    const recommendations = await getRecommendations("BIZ-009", "2026-07", "BIZ-007");

    expect(recommendations.map((item) => item.supplierId)).not.toContain("BIZ-007");
    expect(recommendations[0].periodKey).toBe("2026-07");
    expect(recommendations[0].advisoryNotice).toContain("excludes the selected disrupted supplier");
  });

  it("maps periodic intake endpoints and preserves selected period in requests", async () => {
    const submissionPayload = {
      id: "SUB-1",
      business_id: "BIZ-009",
      organization_id: "BIZ-009",
      period: { id: "PER-BIZ-009-2026-07", period_type: "month", period_key: "2026-07", period_start: "2026-07-01", period_end: "2026-07-31", status: "open" },
      source: "manual",
      status: "draft",
      version: 1,
      sections: { financials: { status: "draft", payload: { revenue: 1 }, updated_at: "2026-07-01T00:00:00Z" } },
      issues: [],
      validation_summary: { errors: 0, warnings: 0, infos: 0 },
      review_task: { id: "REV-1", status: "open", assigned_role: "reviewer", assigned_to: "reviewer-001", assignment_reason: "auto_assigned_primary_org_reviewer", assigned_at: "2026-07-01T00:00:00Z" },
      advisory_notice: "Decision support only."
    };
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/periods?")) return new Response(JSON.stringify({ data: [submissionPayload.period] }), { status: 200 });
      if (url.endsWith("/import-batches")) return new Response(JSON.stringify({ data: { id: "BATCH-1", submission_id: "SUB-1", dataset: "financials", file_name: "f.csv", row_count: 1, status: "parsed", checksum: "abc", preview_rows: [{ revenue: "1" }], idempotent_replay: false } }), { status: 201 });
      if (url.includes("/review-tasks?")) return new Response(JSON.stringify({ data: { review_tasks: [{ review_task_id: "REV-1", submission_id: "SUB-1", organization_id: "BIZ-009", organization_name: "Thu Duc Retail Mart", period_key: "2026-07", period_start: "2026-07-01", period_end: "2026-07-31", review_status: "open", assigned_role: "reviewer", assigned_to: "reviewer-001", assignment_reason: "auto_assigned_primary_org_reviewer", assigned_at: "2026-07-01T00:00:00Z", submission_status: "in_review", source: "manual", version: 1, submitted_by: "sme-biz-009", submitted_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z", validation_summary: { errors: 0, warnings: 1, infos: 0 }, evidence_review: { total: 1, clean: 0, pending: 1, rejected: 0, required: true, approval_blocked: true, advisory: "Scan pending.", requirements: [{ document_type: "GUARANTEE", title: "Guarantee document", section: "Finance", total: 1, clean: 0, pending: 1, rejected: 0, status: "pending", satisfied: false }] }, sections: [{ section: "financials", status: "ready" }] }], policy_decision_id: "POL-Q", audit_event_id: "AUD-Q", advisory_notice: "Human review only." } }), { status: 200 });
      if (url.includes("/error-report")) return new Response(JSON.stringify({ data: { submission_id: "SUB-1", format: "json", summary: { errors: 1, warnings: 0, infos: 0, rows: 1 }, rows: [{ source: "validation_issue", batch_id: "BATCH-1", dataset: "products", file_name: "f.csv", raw_record_id: "RAW-1", row: 2, column: "sku", path: "sku", code: "SKU_REQUIRED", severity: "error", message: "SKU is required.", suggestion: null, payload: { sku: "" } }], csv: null, policy_decision_id: "POL-ERR", audit_event_id: "AUD-ERR", advisory_notice: "Fix validation errors." } }), { status: 200 });
      if (url.endsWith("/validate") || url.endsWith("/submit") || url.includes("/review-tasks/") || url.endsWith("/data-submissions")) return new Response(JSON.stringify({ data: submissionPayload }), { status: 200 });
      if (url.includes("/periods/2026-07/snapshot")) return new Response(JSON.stringify({ data: { business_id: "BIZ-009", organization_id: "BIZ-009", period: submissionPayload.period, approved_version: 1, sections: {}, financials: [], products: [], evidence: [], source_submission_ids: ["SUB-1"], advisory_notice: "Decision support only." } }), { status: 200 });
      return new Response(JSON.stringify({ data: submissionPayload }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const periods = await getPeriods("BIZ-009");
    const submission = await createDataSubmission("BIZ-009", "2026-07", { financials: { revenue: 1 } });
    const batch = await createImportBatch({ businessId: "BIZ-009", periodKey: "2026-07", dataset: "financials", fileName: "f.csv", csvText: "revenue\n1", submissionId: submission.id });
    await validateDataSubmission(submission.id);
    const report = await getDataSubmissionErrorReport(submission.id);
    await submitDataSubmission(submission.id);
    const queue = await getReviewQueue("open", 10);
    await decideReviewTask("REV-1", "approve", "ok");
    const snapshot = await getPeriodSnapshot("BIZ-009", "2026-07");

    const createCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/data-submissions")) as unknown as [string, RequestInit];
    expect(periods[0].periodKey).toBe("2026-07");
    expect(JSON.parse(String(createCall[1].body)).period_key).toBe("2026-07");
    expect(batch.previewRows[0].revenue).toBe("1");
    expect(queue.reviewTasks[0].submissionId).toBe("SUB-1");
    expect(queue.reviewTasks[0].assignedTo).toBe("reviewer-001");
    expect(submission.reviewTask?.assignedTo).toBe("reviewer-001");
    expect(queue.reviewTasks[0].validationSummary.warnings).toBe(1);
    expect(queue.reviewTasks[0].evidenceReview.approvalBlocked).toBe(true);
    expect(queue.reviewTasks[0].evidenceReview.pending).toBe(1);
    expect(queue.reviewTasks[0].evidenceReview.requirements[0].documentType).toBe("GUARANTEE");
    expect(queue.reviewTasks[0].evidenceReview.requirements[0].status).toBe("pending");
    expect(String(fetchMock.mock.calls.find(([url]) => String(url).includes("/review-tasks?"))?.[0])).toContain("limit=10");
    expect(report.rows[0].code).toBe("SKU_REQUIRED");
    expect(snapshot.sourceSubmissionIds).toContain("SUB-1");
  });

  it("maps trust foundation endpoints for consent evidence invoice and versioned runs", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/auth/me")) return new Response(JSON.stringify({ data: { tenant_id: "tenant-demo", actor_id: "demo-user", organization_id: "BIZ-009", organization_ids: ["BIZ-009"], roles: ["demo_operator"], scopes: ["demo:read"], purpose: "demo_view", request_id: "req-1", auth_assurance: "demo-header", app_mode: "demo", capabilities: { can_read_graph: true, can_create_submission: true, can_review_submission: true, can_create_evidence_upload: true, can_read_connection_request: true, can_decide_connection_request: true, can_record_evidence_scan_result: true, can_read_match_run: true, can_read_audit: true, allowed_actions: ["read_graph", "create_submission", "review_submission", "create_evidence_upload", "read_connection_request", "decide_connection_request", "record_malware_scan_result", "read_match_run", "read_audit"] }, workspace_access: { views: { overview: true, map: true, intake: true, audit: true }, allowed_views: ["overview", "map", "intake", "audit", "unknown"], default_view: "overview" }, advisory_notice: "Decision support only." } }), { status: 200 });
      if (url.endsWith("/consents")) return new Response(JSON.stringify({ data: { consent_id: "CONS-1", subject_id: "BIZ-009", recipient_id: "BIZ-062", scope: "financial_summary", purpose: "working_capital_review", legal_basis: "explicit_consent", status: "granted", expires_at: null, revoked_at: null, policy_decision_id: "POL-1", audit_event_id: "AUD-1", advisory_notice: "Decision support only." } }), { status: 201 });
      if (url.endsWith("/evidence/upload-url")) return new Response(JSON.stringify({ data: { evidence_version_id: "EVV-1", organization_id: "BIZ-009", period_key: "2026-07", document_type: "GUARANTEE", file_name: "cert.pdf", content_type: "application/pdf", byte_size: 1024, classification: "confidential", object_key: "s3://demo/file.pdf", upload_url: "demo-presigned://file.pdf", expires_in_seconds: 900, malware_scan_status: "pending_upload", policy_decision_id: "POL-2", audit_event_id: "AUD-2", advisory_notice: "Scan required." } }), { status: 201 });
      if (url.includes("/connection-requests?")) return new Response(JSON.stringify({ data: { connection_requests: [{ request_id: "REQ-1", requester_id: "buyer-admin-009", buyer_id: "BIZ-009", target_supplier_id: "BIZ-007", disrupted_supplier_id: "BIZ-005", status: "pending", consent_status: "awaiting_supplier_consent", requested_at: "2026-07-01T00:00:00Z", policy_decision_id: "POL-CONN-LIST", audit_event_id: "AUD-CONN-LIST", next_step: "Supplier consent required.", advisory_notice: "Decision support only." }], scope: "own_organization", policy_decision_id: "POL-LIST", audit_event_id: "AUD-LIST" } }), { status: 200 });
      if (url.endsWith("/connection-requests/REQ-1/decision")) return new Response(JSON.stringify({ data: { request_id: "REQ-1", requester_id: "buyer-admin-009", buyer_id: "BIZ-009", target_supplier_id: "BIZ-007", disrupted_supplier_id: "BIZ-005", status: "relationship_active", consent_status: "contract_evidence_recorded", requested_at: "2026-07-01T00:00:00Z", decided_at: "2026-07-01T00:10:00Z", decided_by: "reviewer-001", decision_note: "ok", contract_evidence_id: "EVD-CONTRACT-REQ-1", relationship_id: "REL-REQ-1", relationship_edge_id: "EDGE-REQ-1", policy_decision_id: "POL-CONN", audit_event_id: "AUD-CONN", next_step: "Relationship basis recorded.", advisory_notice: "Decision support only." } }), { status: 200 });
      if (url.includes("/evidence/upload-tickets/EVV-1/complete")) return new Response(JSON.stringify({ data: { evidence_version_id: "EVV-1", evidence_document_id: "EVD-1", organization_id: "BIZ-009", period_key: "2026-07", document_type: "GUARANTEE", title: "cert.pdf", object_key: "s3://demo/file.pdf", object_version: "uploaded-demo", document_hash: "a".repeat(64), malware_scan_status: "pending_scan", usable: false, policy_decision_id: "POL-2C", audit_event_id: "AUD-2C", advisory_notice: "Recorded." } }), { status: 200 });
      if (url.includes("/evidence/versions/EVV-1/download-url")) return new Response(JSON.stringify({ data: { evidence_version_id: "EVV-1", evidence_document_id: "EVD-1", organization_id: "BIZ-009", download_url: "demo-download-ticket://EVV-1", download_method: "GET", expires_in_seconds: 300, object_storage_status: "demo", object_version: "uploaded-demo", document_hash: "a".repeat(64), content_type: "application/pdf", byte_size: 1024, malware_scan_status: "clean", policy_decision_id: "POL-DL", audit_event_id: "AUD-DL", object_access_id: "OBJ-DL", advisory_notice: "Download tickets are audited." } }), { status: 200 });
      if (url.endsWith("/evidence/scan-jobs")) return new Response(JSON.stringify({ data: { mode: "scan_pending_versions", dry_run: false, candidates: 1, processed: 1, skipped: 0, errors: [], organization_id: "BIZ-009", period_key: "2026-07", scanner: "local_demo", policy_decision_id: "POL-SCAN", audit_event_id: "AUD-SCAN", advisory_notice: "Malware scan only." } }), { status: 202 });
      if (url.includes("/evidence/upload-tickets?")) return new Response(JSON.stringify({ data: { tickets: [{ id: "EVV-1", evidence_version_id: "EVV-1", organization_id: "BIZ-009", business_id: "BIZ-009", period_key: "2026-07", document_type: "GUARANTEE", file_name: "cert.pdf", content_type: "application/pdf", byte_size: 1024, classification: "confidential", status: "upload_ticket_created", malware_scan_status: "pending_upload", uploaded_at: "2026-07-01T00:00:00Z", policy_decision_id: "POL-2", audit_event_id: "AUD-2", advisory_notice: "Pending only." }] } }), { status: 200 });
      if (url.endsWith("/invoice-claims")) return new Response(JSON.stringify({ data: { claim_id: "CLM-1", seller_id: "BIZ-005", buyer_id: "BIZ-009", financier_id: "BIZ-062", invoice_id: "INV-1", invoice_hash: "hash1234567890abc", invoice_identity_hash: "identity", amount: 68000000, currency: "VND", due_date: "2026-07-08", status: "registered", review_status: "pending_review", policy_decision_id: "POL-3", audit_event_id: "AUD-3", advisory_notice: "Registry only." } }), { status: 201 });
      if (url.endsWith("/invoice-claims/CLM-1/transition")) return new Response(JSON.stringify({ data: { claim_id: "CLM-1", seller_id: "BIZ-005", buyer_id: "BIZ-009", financier_id: "BIZ-062", invoice_id: "INV-1", invoice_hash: "hash1234567890abc", invoice_identity_hash: "identity", amount: 68000000, currency: "VND", due_date: "2026-07-08", status: "verified", review_status: "reviewed", policy_decision_id: "POL-4", audit_event_id: "AUD-4", advisory_notice: "Registry only." } }), { status: 200 });
      if (url.includes("/risk-runs?")) return new Response(JSON.stringify({ data: { organization_id: "BIZ-009", period_key: "2026-07", risk_runs: [{ risk_run_id: "RR-1" }], policy_decision_id: "POL-5", advisory_notice: "Decision support only." } }), { status: 200 });
      if (url.includes("/match-runs?")) return new Response(JSON.stringify({ data: { organization_id: "BIZ-009", period_key: "2026-07", match_runs: [{ match_run_id: "MR-1" }], policy_decision_id: "POL-6", advisory_notice: "Decision support only." } }), { status: 200 });
      return new Response(JSON.stringify({ data: {} }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const me = await getAuthMe();
    const consent = await createConsent({ subjectId: "BIZ-009", recipientId: "BIZ-062", scope: "financial_summary", purpose: "working_capital_review", legalBasis: "explicit_consent" });
    const ticket = await createEvidenceUploadTicket({ organizationId: "BIZ-009", fileName: "cert.pdf", contentType: "application/pdf", byteSize: 1024, documentType: "GUARANTEE", periodKey: "2026-07" });
    const connectionRequests = await getConnectionRequests(25);
    const connectionDecision = await decideConnectionRequest({ requestId: "REQ-1", decision: "activate_relationship", note: "ok", contractEvidenceId: "EVD-CONTRACT-REQ-1" });
    const pendingTickets = await getPendingEvidenceUploads("BIZ-009", "2026-07");
    const completedTicket = await completeEvidenceUploadTicket("EVV-1", { organizationId: "BIZ-009", documentHash: "a".repeat(64), title: "cert.pdf" });
    const scanJob = await runEvidenceScanJob({ organizationId: "BIZ-009", periodKey: "2026-07", scanner: "local_demo", dryRun: false });
    const downloadTicket = await createEvidenceDownloadTicket("EVV-1");
    const claim = await createInvoiceClaim({ sellerId: "BIZ-005", buyerId: "BIZ-009", financierId: "BIZ-062", invoiceHash: "hash1234567890abc", amount: 68000000, dueDate: "2026-07-08", invoiceId: "INV-1" });
    const transitioned = await transitionInvoiceClaim("CLM-1", "verified", "ok");
    const riskRuns = await getRiskRuns("BIZ-009", "2026-07");
    const matchRuns = await getMatchRuns("BIZ-009", "2026-07");

    expect(me.roles).toContain("demo_operator");
    expect(me.capabilities.canCreateSubmission).toBe(true);
    expect(me.capabilities.canReadConnectionRequest).toBe(true);
    expect(me.capabilities.canDecideConnectionRequest).toBe(true);
    expect(me.capabilities.canRecordEvidenceScanResult).toBe(true);
    expect(me.capabilities.canReadMatchRun).toBe(true);
    expect(me.capabilities.allowedActions).toContain("read_audit");
    expect(me.workspaceAccess.allowedViews).toEqual(["overview", "map", "intake", "audit"]);
    expect(me.workspaceAccess.defaultView).toBe("overview");
    expect(consent.status).toBe("granted");
    expect(ticket.malwareScanStatus).toBe("pending_upload");
    expect(ticket.documentType).toBe("GUARANTEE");
    expect(ticket.periodKey).toBe("2026-07");
    expect(connectionRequests[0].requestId).toBe("REQ-1");
    expect(connectionRequests[0].buyerId).toBe("BIZ-009");
    expect(connectionDecision.relationshipEdgeId).toBe("EDGE-REQ-1");
    expect(connectionDecision.policyDecisionId).toBe("POL-CONN");
    expect(pendingTickets[0].documentType).toBe("GUARANTEE");
    expect(pendingTickets[0].periodKey).toBe("2026-07");
    expect(completedTicket.evidenceDocumentId).toBe("EVD-1");
    expect(completedTicket.usable).toBe(false);
    expect(scanJob.processed).toBe(1);
    expect(scanJob.policyDecisionId).toBe("POL-SCAN");
    expect(downloadTicket.downloadUrl).toBe("demo-download-ticket://EVV-1");
    expect(downloadTicket.objectAccessId).toBe("OBJ-DL");
    expect(claim.status).toBe("registered");
    expect(transitioned.status).toBe("verified");
    expect(riskRuns.riskRuns[0].risk_run_id).toBe("RR-1");
    expect(matchRuns.matchRuns[0].match_run_id).toBe("MR-1");
    const scanCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/evidence/scan-jobs")) as unknown as [string, RequestInit];
    expect(JSON.parse(String(scanCall[1].body)).period_key).toBe("2026-07");
    expect(JSON.parse(String(scanCall[1].body)).scanner).toBe("local_demo");
    const connectionDecisionCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/connection-requests/REQ-1/decision")) as unknown as [string, RequestInit];
    expect(JSON.parse(String(connectionDecisionCall[1].body)).contract_evidence_id).toBe("EVD-CONTRACT-REQ-1");
    expect(String(fetchMock.mock.calls.find(([url]) => String(url).includes("/connection-requests?"))?.[0])).toContain("limit=25");
  });

  it("sends connection requests for the selected buyer instead of a hardcoded demo buyer", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      data: {
        request_id: "REQ-1",
        buyer_id: "BIZ-042",
        target_supplier_id: "BIZ-007",
        disrupted_supplier_id: "BIZ-005",
        status: "pending",
        consent_status: "awaiting_supplier_consent",
        requested_at: "2026-07-01T00:00:00Z",
        next_step: "Supplier consent required.",
        advisory_notice: "Decision support only."
      }
    }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    const request = await createConnectionRequest({ buyerId: "BIZ-042", targetSupplierId: "BIZ-007", disruptedSupplierId: "BIZ-005" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body));

    expect(String(url)).toMatch(/\/api\/v1\/connection-requests$/);
    expect(body.buyer_id).toBe("BIZ-042");
    expect(body.target_supplier_id).toBe("BIZ-007");
    expect(body.disrupted_supplier_id).toBe("BIZ-005");
    expect(request.buyerId).toBe("BIZ-042");
  });

  it("maps admin ops endpoints with scoped demo admin headers", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/admin/model-registry")) return new Response(JSON.stringify({ data: { models: [{ model_registry_id: "MOD-1", artifact_type: "risk", model_version: "deterministic-v1", name: "Risk v1", status: "active", config: { deterministic: true }, created_at: "2026-07-01T00:00:00Z" }], policy_decision_id: "POL-M", audit_event_id: "AUD-M", advisory_notice: "Decision support only." } }), { status: 200 });
      if (url.includes("/admin/ruleset-registry")) return new Response(JSON.stringify({ data: { rulesets: [{ ruleset_registry_id: "RULE-1", artifact_type: "risk", ruleset_version: "risk-rules-v1", name: "Risk rules", status: "active", config: { source: "intake" }, created_at: "2026-07-01T00:00:00Z" }], policy_decision_id: "POL-R", audit_event_id: "AUD-R", advisory_notice: "Decision support only." } }), { status: 200 });
      if (url.includes("/admin/recompute-jobs")) return new Response(JSON.stringify({ data: { jobs: [{ job_id: "JOB-1", organization_id: "BIZ-009", reporting_period_id: "PER-1", source_submission_id: "SUB-1", job_type: "analytics_recompute", status: "queued", attempts: 0, max_attempts: 3, last_error: null, payload: { period_key: "2026-07" }, created_at: "2026-07-01T00:00:00Z" }], policy_decision_id: "POL-J", audit_event_id: "AUD-J", advisory_notice: "Ops view audited." } }), { status: 200 });
      return new Response(JSON.stringify({ data: {} }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const ops = await getAdminOps("BIZ-009");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init?.headers as Headers;

    expect(headers.get("X-Actor-Id")).toBe("demo-admin");
    expect(headers.get("X-Actor-Role")).toBe("demo_admin");
    expect(headers.get("X-Demo-Scopes")).toContain("policy:override");
    expect(ops.models[0].modelVersion).toBe("deterministic-v1");
    expect(ops.rulesets[0].rulesetVersion).toBe("risk-rules-v1");
    expect(ops.recomputeJobs[0].status).toBe("queued");
    expect(ops.policyDecisionIds).toEqual(["POL-M", "POL-R", "POL-J"]);
    expect(ops.auditEventIds).toEqual(["AUD-M", "AUD-R", "AUD-J"]);
    expect(ops.access).toBe("authorized");
  });
});
