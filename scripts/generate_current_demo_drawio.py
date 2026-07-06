from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "diagrams" / "VietSupply_Radar_Current_Demo_Backbone.drawio"


def lines(*items: str) -> str:
    return "<br/>".join(items)


STYLES = {
    "title": "text;html=1;strokeColor=none;fillColor=none;fontSize=24;fontStyle=1;align=left;verticalAlign=middle;whiteSpace=wrap;",
    "note": "text;html=1;strokeColor=none;fillColor=none;fontSize=12;fontColor=#4b5563;align=left;verticalAlign=top;whiteSpace=wrap;",
    "actor": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#e8f1ff;strokeColor=#2f5fb3;",
    "frontend": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#e0f7fa;strokeColor=#168a99;",
    "api": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#f0f9ff;strokeColor=#0369a1;",
    "service": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#e9f8ef;strokeColor=#2f7d4a;",
    "domain": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#fef3c7;strokeColor=#a66a00;",
    "repo": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#fff7ed;strokeColor=#c2410c;",
    "db": "shape=cylinder3d;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;fontSize=12;fillColor=#f3e8ff;strokeColor=#7e22ce;",
    "data": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#f8fafc;strokeColor=#64748b;",
    "guard": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#ffe9e9;strokeColor=#b33a3a;",
    "start": "ellipse;whiteSpace=wrap;html=1;fontSize=12;fillColor=#dcfce7;strokeColor=#15803d;",
    "action": "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fillColor=#e8f1ff;strokeColor=#2f5fb3;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fontSize=11;fillColor=#fff4db;strokeColor=#a66a00;",
    "table": "rounded=0;whiteSpace=wrap;html=1;fontSize=10;align=left;verticalAlign=top;spacing=8;fillColor=#ffffff;strokeColor=#64748b;",
    "class": "rounded=0;whiteSpace=wrap;html=1;fontSize=10;align=left;verticalAlign=top;spacing=8;fillColor=#f8fafc;strokeColor=#475569;",
}

EDGE = "endArrow=block;html=1;rounded=0;strokeColor=#64748b;fontSize=10;fontColor=#475569;"


class Page:
    def __init__(self, name: str, width: int = 1800, height: int = 1160) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.cells: list[str] = []
        self._seq = 1

    def _id(self, prefix: str = "v") -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    def vertex(self, value: str, x: int, y: int, w: int, h: int, kind: str = "action") -> str:
        cell_id = self._id()
        safe_value = escape(value, quote=True)
        self.cells.append(
            f'<mxCell id="{cell_id}" value="{safe_value}" style="{STYLES[kind]}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            "</mxCell>"
        )
        return cell_id

    def edge(self, source: str, target: str, value: str = "") -> str:
        cell_id = self._id("e")
        safe_value = escape(value, quote=True)
        self.cells.append(
            f'<mxCell id="{cell_id}" value="{safe_value}" style="{EDGE}" edge="1" parent="1" source="{source}" target="{target}">'
            '<mxGeometry relative="1" as="geometry"/>'
            "</mxCell>"
        )
        return cell_id

    def header(self, title: str, subtitle: str) -> None:
        self.vertex(title, 40, 24, 1200, 34, "title")
        self.vertex(subtitle, 42, 62, 1320, 50, "note")

    def xml(self, diagram_id: str) -> str:
        body = "\n".join(self.cells)
        return f"""  <diagram id="{diagram_id}" name="{escape(self.name)}">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.width}" pageHeight="{self.height}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
{body}
      </root>
    </mxGraphModel>
  </diagram>"""


def class_box(title: str, *items: str) -> str:
    return lines(title, "-" * min(28, len(title)), *items)


def table_box(title: str, *fields: str) -> str:
    return lines(title, *fields)


def backbone_page() -> Page:
    p = Page("01 Backbone Architecture")
    p.header(
        "01 Backbone Architecture",
        "Current demo spine: React cockpit -> API client -> FastAPI -> application service -> repositories -> SQLite seeded from CSV.",
    )
    user = p.vertex(lines("Demo operator", "Nguyen Minh"), 60, 180, 150, 60, "actor")
    browser = p.vertex("Browser", 280, 180, 130, 60, "actor")
    react = p.vertex(lines("React App.tsx", "state + view router"), 480, 160, 180, 90, "frontend")
    workspaces = p.vertex(lines("WorkspaceViews", "Overview, Map, Companies, Risk, Matching, Finance, Invoice, Audit"), 720, 140, 240, 130, "frontend")
    mapview = p.vertex(lines("MapView", "Leaflet + CARTO dark tiles"), 720, 310, 240, 70, "frontend")
    client = p.vertex(lines("api/client.ts", "snake_case -> camelCase", "fallback data"), 1040, 160, 200, 110, "api")
    fastapi = p.vertex(lines("FastAPI main.py", "15 demo endpoints", "CORS localhost"), 1320, 160, 210, 110, "api")
    service = p.vertex(lines("VietSupplyRadarService", "orchestrates demo use cases"), 1320, 360, 210, 90, "service")
    domain = p.vertex(lines("Domain algorithms", "risk scoring, shock, matching, invoice hash"), 1040, 360, 210, 90, "domain")
    repos = p.vertex(lines("Repositories", "business, edge, finance, product, invoice, evidence, audit, request"), 1320, 540, 250, 120, "repo")
    db = p.vertex(lines("SQLite", "backend/app/data/vietsupply.db"), 1040, 560, 200, 100, "db")
    csv = p.vertex(lines("CSV seed data", "data/*.csv"), 760, 560, 180, 80, "data")
    loader = p.vertex(lines("Data loader + seed", "generate_synthetic_data.py", "seed_database.py"), 760, 700, 220, 100, "data")
    guard = p.vertex(lines("Governance boundaries", "advisory only", "human approval", "consent before contact release"), 1320, 760, 250, 120, "guard")
    for a, b, label in [
        (user, browser, ""),
        (browser, react, ""),
        (react, workspaces, ""),
        (workspaces, client, "API calls"),
        (client, fastapi, "HTTP JSON"),
        (fastapi, service, "payload methods"),
        (service, domain, "pure calculations"),
        (service, repos, "queries + commands"),
        (repos, db, "SQL"),
        (csv, loader, ""),
        (loader, db, "seed/reset"),
        (service, guard, "notices + audit"),
        (workspaces, mapview, "map surface"),
    ]:
        p.edge(a, b, label)
    return p


def boot_page() -> Page:
    p = Page("02 Activity - App Bootstrap")
    p.header("02 Activity - App Bootstrap", "Initial React load, API fan-out and fallback path.")
    start = p.vertex("Open http://127.0.0.1:5173", 70, 170, 170, 60, "start")
    mount = p.vertex("App.tsx mounts", 330, 170, 160, 60, "action")
    fanout = p.vertex(lines("Promise.all", "graph, scenario, dashboard, recommendations, invoice, audit"), 580, 150, 230, 100, "action")
    apiok = p.vertex("API available?", 920, 155, 130, 100, "decision")
    dbmode = p.vertex("apiMode=database", 1160, 130, 180, 60, "service")
    fallback = p.vertex(lines("apiMode=fallback", "demoData.ts"), 1160, 240, 180, 70, "guard")
    render = p.vertex(lines("Render overview", "map + KPI + alerts"), 1440, 170, 210, 80, "frontend")
    selected = p.vertex(lines("Default selection", "BIZ-005 Dai Tin Distribution"), 1440, 330, 210, 80, "frontend")
    detail = p.vertex(lines("Load selected detail", "business, evidence, risk, finance"), 1160, 400, 240, 80, "api")
    p.edge(start, mount)
    p.edge(mount, fanout)
    p.edge(fanout, apiok)
    p.edge(apiok, dbmode, "yes")
    p.edge(apiok, fallback, "no")
    p.edge(dbmode, render)
    p.edge(fallback, render)
    p.edge(render, selected)
    p.edge(selected, detail)
    return p


def evidence_page() -> Page:
    p = Page("03 Activity - Evidence And Risk Signal")
    p.header("03 Activity - Evidence And Risk Signal", "Node selection loads the evidence vault and rule-traced risk card.")
    select = p.vertex("Select business node", 70, 190, 170, 60, "start")
    effect = p.vertex("React selectedId effect", 330, 175, 180, 90, "frontend")
    detail = p.vertex("GET /businesses/{id}", 600, 100, 190, 55, "api")
    evidence = p.vertex("GET /businesses/{id}/evidence", 600, 180, 190, 55, "api")
    risk = p.vertex("GET /businesses/{id}/risk-signal", 600, 260, 190, 55, "api")
    finance = p.vertex("GET /businesses/{id}/finance", 600, 340, 190, 55, "api")
    service = p.vertex("VietSupplyRadarService", 900, 190, 210, 80, "service")
    repos = p.vertex(lines("Repositories", "business, edge, financial, product, evidence"), 1220, 160, 230, 100, "repo")
    docs = p.vertex(lines("Evidence docs", "contracts, POs, delivery notes, certifications, guarantees, invoices"), 1220, 330, 250, 110, "data")
    decision = p.vertex("Late PO >= 3?", 900, 360, 130, 100, "decision")
    high = p.vertex(lines("HIGH risk", "confidence 86"), 700, 500, 160, 70, "guard")
    medium = p.vertex(lines("MEDIUM risk", "confidence 67"), 1020, 500, 170, 70, "domain")
    ui = p.vertex(lines("Companies & Evidence", "Risk Analysis"), 1320, 560, 220, 80, "frontend")
    audit = p.vertex("AuditRepository.record", 1320, 700, 220, 60, "repo")
    for node in [detail, evidence, risk, finance]:
        p.edge(effect, node)
        p.edge(node, service)
    p.edge(select, effect)
    p.edge(service, repos)
    p.edge(repos, docs)
    p.edge(docs, decision)
    p.edge(decision, high, "yes")
    p.edge(decision, medium, "no")
    p.edge(high, ui)
    p.edge(medium, ui)
    p.edge(service, audit, "view events")
    return p


def shock_page() -> Page:
    p = Page("04 Activity - Shock Simulation")
    p.header("04 Activity - Shock Simulation", "BIZ-005 disruption is simulated; no commercial action is automated.")
    run = p.vertex("Click Run simulation", 70, 210, 170, 60, "start")
    req = p.vertex(lines("POST /simulation/shock", "BIZ-005, beverage, 5 days"), 330, 190, 220, 90, "api")
    svc = p.vertex("shock_payload", 650, 205, 160, 60, "service")
    load = p.vertex(lines("Load businesses", "Load supply_edges"), 900, 190, 180, 90, "repo")
    sim = p.vertex("simulate_shock()", 1190, 205, 170, 60, "domain")
    impact = p.vertex(lines("Dependency ratio", "stockout impact", "affected edges"), 1190, 360, 190, 100, "domain")
    sev = p.vertex("Severity?", 930, 360, 130, 100, "decision")
    ui = p.vertex(lines("Highlight map", "affected nodes/edges"), 650, 370, 180, 80, "frontend")
    audit = p.vertex("SUPPLY_SHOCK_SIMULATED", 330, 390, 220, 60, "repo")
    notice = p.vertex(lines("Advisory notice", "no breach/default", "no automatic switching"), 650, 540, 220, 90, "guard")
    p.edge(run, req)
    p.edge(req, svc)
    p.edge(svc, load)
    p.edge(load, sim)
    p.edge(sim, impact)
    p.edge(impact, sev)
    p.edge(sev, ui, "critical/watch/clear")
    p.edge(svc, audit)
    p.edge(ui, notice)
    return p


def matching_page() -> Page:
    p = Page("05 Activity - Matching And Connection Request")
    p.header("05 Activity - Matching And Connection Request", "Top 3 supplier alternatives are advisory; introduction requires a human request and supplier consent.")
    start = p.vertex("Open Matching", 70, 210, 150, 60, "start")
    req = p.vertex(lines("POST /recommendations/suppliers", "buyer=BIZ-009", "disrupted=BIZ-005"), 300, 180, 220, 110, "api")
    svc = p.vertex("recommendations_payload", 610, 205, 190, 60, "service")
    rank = p.vertex(lines("rank_suppliers", "score: spec, capacity, distance, health, reliability, terms, price"), 900, 170, 260, 120, "domain")
    top = p.vertex("Return top 3 cards", 1260, 205, 180, 60, "frontend")
    click = p.vertex("Click Request introduction", 70, 460, 210, 60, "start")
    post = p.vertex("POST /connection-requests", 360, 450, 220, 70, "api")
    valid = p.vertex("Buyer and supplier exist?", 690, 435, 150, 110, "decision")
    create = p.vertex(lines("Create request", "pending", "awaiting_supplier_consent"), 940, 430, 220, 100, "repo")
    audit = p.vertex("CONNECTION_REQUEST_CREATED", 1260, 430, 220, 60, "repo")
    guard = p.vertex(lines("Guardrails", "no contact release", "no contract amendment", "no order commitment"), 1260, 580, 230, 100, "guard")
    p.edge(start, req)
    p.edge(req, svc)
    p.edge(svc, rank)
    p.edge(rank, top)
    p.edge(top, click)
    p.edge(click, post)
    p.edge(post, valid)
    p.edge(valid, create, "yes")
    p.edge(valid, guard, "no")
    p.edge(create, audit)
    p.edge(audit, guard)
    return p


def finance_page() -> Page:
    p = Page("06 Activity - Finance And Invoice Verification")
    p.header("06 Activity - Finance And Invoice Verification", "Financial health is a management indicator; invoice hash is a verification signal, not proof of truth.")
    start = p.vertex("Open Finance / Invoice", 70, 230, 180, 60, "start")
    finreq = p.vertex("GET /businesses/BIZ-005/finance", 340, 150, 230, 60, "api")
    invreq = p.vertex("GET /invoices/INV-0242/verification", 340, 330, 250, 60, "api")
    finsvc = p.vertex("finance_payload", 680, 150, 170, 60, "service")
    invsvc = p.vertex("invoice_payload", 680, 330, 170, 60, "service")
    series = p.vertex(lines("12-month series", "cash flow + working capital"), 950, 120, 220, 90, "domain")
    comps = p.vertex(lines("Health components", "cashflow, payment, delivery, leverage"), 1240, 120, 240, 90, "domain")
    hashnode = p.vertex(lines("canonical_invoice", "invoice_hash"), 950, 310, 200, 90, "domain")
    double = p.vertex("double_financing_alert", 1240, 325, 210, 60, "domain")
    finui = p.vertex(lines("Finance UI", "KPI, chart, table, notice"), 1240, 250, 230, 70, "frontend")
    invui = p.vertex(lines("Invoice UI", "hash comparison, guarantee band, notice"), 1240, 440, 240, 80, "frontend")
    audit = p.vertex("INVOICE_VERIFICATION_VIEWED", 680, 500, 230, 60, "repo")
    p.edge(start, finreq)
    p.edge(start, invreq)
    p.edge(finreq, finsvc)
    p.edge(invreq, invsvc)
    p.edge(finsvc, series)
    p.edge(series, comps)
    p.edge(comps, finui)
    p.edge(invsvc, hashnode)
    p.edge(hashnode, double)
    p.edge(double, invui)
    p.edge(invsvc, audit)
    return p


def audit_page() -> Page:
    p = Page("07 Activity - Audit And Governance")
    p.header("07 Activity - Audit And Governance", "All governed demo actions write traceable events and are shown in the Audit Trail workspace.")
    action = p.vertex("Governed action", 80, 220, 160, 60, "start")
    events = p.vertex(lines("Detail viewed", "Evidence viewed", "Shock simulated", "Shortlist generated", "Invoice viewed", "Connection request created"), 340, 160, 230, 180, "action")
    auditrepo = p.vertex("AuditRepository.record", 690, 200, 210, 70, "repo")
    auditdb = p.vertex("audit_logs", 1010, 190, 180, 90, "db")
    request = p.vertex(lines("ConnectionRequestRepository", "create + list_recent"), 690, 400, 230, 80, "repo")
    requestdb = p.vertex("connection_requests", 1010, 390, 190, 90, "db")
    api = p.vertex("GET /api/v1/audit", 1320, 280, 180, 60, "api")
    ui = p.vertex(lines("Audit Trail UI", "recent events + approval queue"), 1320, 430, 220, 80, "frontend")
    guard = p.vertex(lines("Boundaries", "no supplier auto-replacement", "no contract amendment", "no lending decision", "consent before contact release"), 1320, 600, 250, 130, "guard")
    p.edge(action, events)
    p.edge(events, auditrepo)
    p.edge(auditrepo, auditdb)
    p.edge(events, request)
    p.edge(request, requestdb)
    p.edge(auditdb, api)
    p.edge(requestdb, api)
    p.edge(api, ui)
    p.edge(ui, guard)
    return p


def oop_page() -> Page:
    p = Page("08 OOP Classes And Service Layer", 2200, 1300)
    p.header("08 OOP Classes And Service Layer", "Python domain dataclasses, repositories and application service currently used by the demo.")
    business = p.vertex(class_box("Business", "business_id, name, type, province", "lat, lng, scale", "monthly_revenue, capacity", "financial_health_score", "supply_risk_score", "to_api_node(), risk_level"), 60, 150, 270, 180, "class")
    edge = p.vertex(class_box("SupplyEdge", "edge_id, source_id, target_id", "product, product_category", "monthly_volume", "lead_time_days", "reliability", "to_api_edge()"), 380, 150, 260, 170, "class")
    finance = p.vertex(class_box("FinancialSnapshot", "business_id, month", "cash_in, cash_out", "revenue, debt", "accounts_receivable/payable", "inventory_value", "late_payment_rate", "delivery_delay_rate"), 700, 150, 280, 190, "class")
    product = p.vertex(class_box("Product", "business_id, sku", "product_name, category", "specification", "available_capacity", "min_order_value", "price_range", "certifications"), 1040, 150, 260, 180, "class")
    invoice = p.vertex(class_box("InvoiceVerification", "invoice_id", "seller_id, buyer_id", "amount", "issue_date, due_date", "invoice_hash", "funding_status", "confirmed_by"), 1360, 150, 270, 180, "class")
    audit = p.vertex(class_box("AuditLog / ConsentRecord", "event_id, event_type", "actor_id, actor_role", "subject_id, purpose", "timestamp, request_id", "consent scope/status"), 1690, 150, 300, 180, "class")
    service = p.vertex(class_box("VietSupplyRadarService", "dashboard_payload()", "scenario_payload()", "business_detail_payload()", "evidence_payload()", "risk_signal_payload()", "finance_payload()", "shock_payload()", "recommendations_payload()", "connection_request_payload()", "audit_payload()"), 760, 470, 360, 260, "service")
    repos = p.vertex(class_box("Repositories", "BusinessRepository", "SupplyEdgeRepository", "FinancialRepository", "ProductRepository", "InvoiceRepository", "EvidenceRepository", "AuditRepository", "ConnectionRequestRepository"), 1200, 500, 360, 210, "repo")
    db = p.vertex(class_box("Database", "connect()", "initialize()", "has_seed_data()", "seed/reset schema", "SQLite row_factory"), 1660, 520, 260, 160, "db")
    domain = p.vertex(class_box("Domain algorithms", "calculate_business_risk()", "simulate_shock()", "rank_suppliers()", "invoice_hash()", "double_financing_alert()"), 300, 500, 320, 180, "domain")
    for node in [business, edge, finance, product, invoice, audit]:
        p.edge(service, node, "payload DTOs")
    p.edge(service, repos, "composition")
    p.edge(repos, db, "SQL")
    p.edge(service, domain, "pure logic")
    return p


def db_page() -> Page:
    p = Page("09 Database ERD", 2400, 1600)
    p.header("09 Database ERD", "SQLite schema seeded from deterministic CSV files. Foreign keys are enabled at connection time.")
    biz = p.vertex(table_box("businesses", "PK business_id", "name, type, industry", "product_category, province", "lat, lng, scale", "monthly_revenue, capacity", "financial_health_score", "supply_risk_score"), 940, 120, 300, 190, "table")
    edges = p.vertex(table_box("supply_edges", "PK edge_id", "FK source_id -> businesses", "FK target_id -> businesses", "product/category", "volume, lead_time, cost", "reliability, payment_terms"), 560, 100, 290, 190, "table")
    financial = p.vertex(table_box("financial_snapshots", "PK business_id + month", "FK business_id -> businesses", "cash_in, cash_out", "revenue, debt", "AR, AP, inventory", "late_payment_rate", "delivery_delay_rate"), 1320, 100, 300, 205, "table")
    products = p.vertex(table_box("products", "PK sku", "FK business_id -> businesses", "product_name, category", "specification", "available_capacity", "min_order_value", "price_range, certifications"), 1700, 100, 300, 200, "table")
    invoices = p.vertex(table_box("invoice_verifications", "PK invoice_id", "FK seller_id -> businesses", "FK buyer_id -> businesses", "amount, issue_date, due_date", "invoice_hash", "funding_status, confirmed_by"), 1700, 420, 320, 190, "table")
    contracts = p.vertex(table_box("contracts", "PK contract_id", "FK supplier_id -> businesses", "FK buyer_id -> businesses", "product_category, status", "effective/expiry date", "payment_term_days", "sla_lead_time_days", "clauses, verification, hash"), 940, 420, 330, 230, "table")
    pos = p.vertex(table_box("purchase_orders", "PK po_id", "FK contract_id -> contracts", "FK supplier_id/buyer_id -> businesses", "sku, order_date", "expected/actual delivery", "quantity, value", "status, verification, hash"), 560, 440, 330, 230, "table")
    dns = p.vertex(table_box("delivery_notes", "PK delivery_note_id", "FK po_id -> purchase_orders", "FK supplier_id/buyer_id -> businesses", "FK logistics_partner_id -> businesses", "delivery_date, quantity", "delay_days", "buyer/logistics verification", "status, hash"), 160, 460, 330, 250, "table")
    certs = p.vertex(table_box("certifications", "PK certification_id", "FK business_id -> businesses", "certification_type, issuer", "effective/expiry date", "status, verification", "document_hash"), 1320, 430, 300, 180, "table")
    guarantees = p.vertex(table_box("guarantees", "PK guarantee_id", "FK applicant_id -> businesses", "FK beneficiary_id -> businesses", "FK issuer_id -> businesses", "guarantee_type, amount", "effective/expiry date", "status, verification, hash"), 940, 800, 330, 220, "table")
    requests = p.vertex(table_box("connection_requests", "PK request_id", "requester_id", "FK buyer_id -> businesses", "FK target_supplier_id -> businesses", "FK disrupted_supplier_id -> businesses", "purpose, status", "consent_status", "requested/decided at"), 560, 820, 330, 240, "table")
    consent = p.vertex(table_box("consent_records", "PK consent_id", "actor_id, subject_id", "scope, purpose", "status", "expires_at, revoked_at"), 1320, 820, 300, 170, "table")
    audit = p.vertex(table_box("audit_logs", "PK event_id", "event_type", "actor_id, actor_role", "subject_id, purpose", "timestamp, request_id"), 1700, 820, 300, 180, "table")
    for source, target, label in [
        (biz, edges, "source/target"),
        (biz, financial, "business_id"),
        (biz, products, "business_id"),
        (biz, invoices, "seller/buyer"),
        (biz, contracts, "supplier/buyer"),
        (contracts, pos, "contract_id"),
        (biz, pos, "supplier/buyer"),
        (pos, dns, "po_id"),
        (biz, dns, "supplier/buyer/logistics"),
        (biz, certs, "business_id"),
        (biz, guarantees, "applicant/beneficiary/issuer"),
        (biz, requests, "buyer/target/disrupted"),
    ]:
        p.edge(source, target, label)
    return p


def frontend_page() -> Page:
    p = Page("10 Frontend State And API Flow")
    p.header("10 Frontend State And API Flow", "React state slices and API adapter functions used by the current dashboard.")
    app = p.vertex(lines("App.tsx state", "activeView, allNodes, allEdges", "scenario, dashboard", "selectedId, detail, evidence", "riskSignal, finance", "recommendations, invoice, audit", "shock, connectionRequest"), 80, 160, 310, 230, "frontend")
    client = p.vertex(lines("api/client.ts", "requestJson()", "mapping functions", "fallback on read APIs"), 500, 210, 230, 110, "api")
    views = p.vertex(lines("WorkspaceViews", "OverviewWorkspace", "MapWorkspace", "CompaniesWorkspace", "RiskWorkspace", "MatchingWorkspace", "FinanceWorkspace", "InvoiceWorkspace", "AuditWorkspace"), 840, 150, 290, 230, "frontend")
    map = p.vertex(lines("MapView.tsx", "react-leaflet", "Binh Duong polygon", "nodes/edges/affected paths"), 1240, 190, 260, 140, "frontend")
    api = p.vertex(lines("Backend endpoints", "graph/scenario/dashboard", "business/evidence/risk/finance", "shock/recommendations", "invoice/request/audit"), 500, 500, 270, 160, "api")
    ui = p.vertex(lines("Rendered UX", "dark operational cockpit", "human approval", "legal/finance disclaimers"), 840, 520, 290, 130, "guard")
    p.edge(app, client, "loads data")
    p.edge(app, views, "props + callbacks")
    p.edge(views, map, "network props")
    p.edge(client, api, "HTTP")
    p.edge(views, ui)
    p.edge(map, ui)
    return p


def main() -> None:
    pages = [
        backbone_page(),
        boot_page(),
        evidence_page(),
        shock_page(),
        matching_page(),
        finance_page(),
        audit_page(),
        oop_page(),
        db_page(),
        frontend_page(),
    ]
    modified = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    diagrams = "\n".join(page.xml(f"{idx:02d}-{page.name.lower().replace(' ', '-')}") for idx, page in enumerate(pages, 1))
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<mxfile host="app.diagrams.net" modified="{modified}" agent="Codex" version="24.7.17" type="device">\n'
        f"{diagrams}\n"
        "</mxfile>\n"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(xml, encoding="utf-8")
    ET.parse(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
