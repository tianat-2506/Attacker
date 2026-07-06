# VietSupply Radar Current Demo Diagrams

This document captures the demo that is currently implemented in the repository. It covers the activity flows, OOP surface, database model and system backbone used by the React + FastAPI + SQLite demo.

Editable draw.io version: [VietSupply_Radar_Current_Demo_Backbone.drawio](diagrams/VietSupply_Radar_Current_Demo_Backbone.drawio)

## Demo Activity 0 - App Bootstrap And Overview

```mermaid
flowchart TD
    Start(("User opens web app"))
    React["React App.tsx mounts"]
    Load["Promise.all initial API calls"]
    Graph["GET /api/v1/graph?masked=false"]
    Scenario["GET /api/v1/demo/scenario"]
    Dashboard["GET /api/v1/dashboard"]
    Shortlist["POST /api/v1/recommendations/suppliers"]
    Invoice["GET /api/v1/invoices/INV-0242/verification"]
    Audit["GET /api/v1/audit"]
    ApiOk{"API available?"}
    DatabaseMode["Set apiMode = database"]
    FallbackMode["Set apiMode = fallback and use demoData.ts"]
    Render["Render overview workspace"]
    Map["MapView: Southern Vietnam + Binh Duong focus"]
    KPIs["KPI cards, alerts, charts, top risks"]
    Select["Default selected company = BIZ-005"]

    Start --> React --> Load
    Load --> Graph
    Load --> Scenario
    Load --> Dashboard
    Load --> Shortlist
    Load --> Invoice
    Load --> Audit
    Graph --> ApiOk
    Scenario --> ApiOk
    Dashboard --> ApiOk
    Shortlist --> ApiOk
    Invoice --> ApiOk
    Audit --> ApiOk
    ApiOk -- yes --> DatabaseMode
    ApiOk -- no --> FallbackMode
    DatabaseMode --> Render
    FallbackMode --> Render
    Render --> Map
    Render --> KPIs
    Render --> Select
```

## Demo Activity 1 - Node Selection, Evidence Vault And Risk Signal

```mermaid
flowchart TD
    Select(("User selects a business node"))
    State["setSelectedId(businessId)"]
    Parallel["React effect loads business detail data"]
    Detail["GET /api/v1/businesses/{business_id}"]
    Evidence["GET /api/v1/businesses/{business_id}/evidence"]
    Risk["GET /api/v1/businesses/{business_id}/risk-signal"]
    Finance["GET /api/v1/businesses/{business_id}/finance"]
    Service["VietSupplyRadarService"]
    Repos["Business, Edge, Financial, Product, Evidence repositories"]
    EvidenceDocs["contracts, purchase orders, delivery notes, certifications, guarantees, invoices"]
    Rules["Rule trace: late PO, overdue in-transit PO, expiring certificate"]
    Decision{">= 3 late POs or critical evidence?"}
    High["HIGH signal, confidence 86"]
    Medium["MEDIUM signal, confidence 67"]
    UI["Companies & Evidence and Risk Analysis workspaces"]
    Audit["AuditRepository.record evidence/detail view"]

    Select --> State --> Parallel
    Parallel --> Detail --> Service
    Parallel --> Evidence --> Service
    Parallel --> Risk --> Service
    Parallel --> Finance --> Service
    Service --> Repos --> EvidenceDocs
    EvidenceDocs --> Rules --> Decision
    Decision -- yes --> High --> UI
    Decision -- no --> Medium --> UI
    Service --> Audit
```

## Demo Activity 2 - Supply Shock Simulation

```mermaid
flowchart TD
    Start(("User clicks Run simulation"))
    Request["POST /api/v1/simulation/shock"]
    Payload["shock_business_id=BIZ-005, category=beverage, inventory_coverage_days=5"]
    Service["VietSupplyRadarService.shock_payload"]
    LoadGraph["Load all businesses and supply_edges"]
    Domain["domain.shock_simulation.simulate_shock"]
    Dependency["Calculate incoming dependency ratio per downstream node"]
    Severity{"Dependency + stockout impact"}
    Critical["Critical affected node"]
    Watch["Watch affected node"]
    Clear["No material impact"]
    Audit["Record SUPPLY_SHOCK_SIMULATED"]
    UI["Highlight affected nodes/edges on Leaflet map"]
    Notice["Show advisory notice: simulation only, no automatic switching"]

    Start --> Request --> Payload --> Service --> LoadGraph --> Domain --> Dependency --> Severity
    Severity --> Critical
    Severity --> Watch
    Severity --> Clear
    Critical --> UI
    Watch --> UI
    Clear --> UI
    Service --> Audit
    UI --> Notice
```

## Demo Activity 3 - Supplier Matching And Human Introduction Request

```mermaid
flowchart TD
    Start(("User opens Matching or clicks Review risk"))
    MatchReq["POST /api/v1/recommendations/suppliers"]
    Input["buyer=BIZ-009, disrupted_supplier=BIZ-005, category=beverage, top_k=3"]
    Service["VietSupplyRadarService.recommendations_payload"]
    Domain["domain.supplier_matching.rank_suppliers"]
    Score["Score product spec, capacity, distance, health, reliability, payment term, price"]
    Top3["Return top 3 alternatives with trade-offs"]
    AuditShortlist["Record SUPPLIER_SHORTLIST_GENERATED"]
    UI["Render supplier cards"]
    Click["User clicks Request introduction"]
    Request["POST /api/v1/connection-requests"]
    Validate{"Buyer and supplier exist?"}
    Create["ConnectionRequestRepository.create"]
    Pending["status=pending; consent_status=awaiting_supplier_consent"]
    AuditRequest["Record CONNECTION_REQUEST_CREATED"]
    Guardrails["No contact release, no contract amendment, no order commitment"]

    Start --> MatchReq --> Input --> Service --> Domain --> Score --> Top3 --> UI
    Service --> AuditShortlist
    UI --> Click --> Request --> Validate
    Validate -- no --> Guardrails
    Validate -- yes --> Create --> Pending --> AuditRequest --> Guardrails
```

## Demo Activity 4 - Financial Health And Invoice Verification

```mermaid
flowchart TD
    Start(("User opens Finance or Invoice Verification"))
    FinanceReq["GET /api/v1/businesses/BIZ-005/finance"]
    InvoiceReq["GET /api/v1/invoices/INV-0242/verification"]
    FinanceSvc["finance_payload"]
    InvoiceSvc["invoice_payload"]
    FinancialRepo["FinancialRepository.for_business"]
    InvoiceRepo["InvoiceRepository.get/list_all"]
    Series["Build 12-month series"]
    Metrics["Compute net cash flow, working capital, margin, DSO proxy, inventory days, leverage"]
    Components["Health components: cashflow, payment discipline, delivery reliability, leverage pressure"]
    Hash["invoice_hash(canonical_invoice)"]
    DoubleFunding["double_financing_alert(existing_invoices)"]
    FinanceUI["Finance workspace: KPI, chart, table, advisory notice"]
    InvoiceUI["Invoice workspace: parties, hash comparison, guarantee band, advisory notice"]
    AuditInvoice["Record INVOICE_VERIFICATION_VIEWED"]

    Start --> FinanceReq --> FinanceSvc --> FinancialRepo --> Series --> Metrics --> Components --> FinanceUI
    Start --> InvoiceReq --> InvoiceSvc --> InvoiceRepo --> Hash --> DoubleFunding --> InvoiceUI
    InvoiceSvc --> AuditInvoice
```

## Demo Activity 5 - Audit And Governance Backbone

```mermaid
flowchart TD
    Action(("Any governed demo action"))
    Detail["Business detail viewed"]
    Evidence["Evidence vault viewed"]
    Shock["Supply shock simulated"]
    Shortlist["Supplier shortlist generated"]
    Invoice["Invoice verification viewed"]
    Connection["Connection request created"]
    AuditRepo["AuditRepository.record"]
    AuditTable[("audit_logs")]
    RequestRepo["ConnectionRequestRepository"]
    RequestTable[("connection_requests")]
    AuditAPI["GET /api/v1/audit"]
    UI["Audit Trail workspace"]
    Boundaries["Boundary cards: no automatic supplier replacement, no contract amendment, no lending decision, consent before contact release"]

    Action --> Detail --> AuditRepo
    Action --> Evidence --> AuditRepo
    Action --> Shock --> AuditRepo
    Action --> Shortlist --> AuditRepo
    Action --> Invoice --> AuditRepo
    Action --> Connection --> RequestRepo --> RequestTable
    Connection --> AuditRepo
    AuditRepo --> AuditTable
    AuditTable --> AuditAPI --> UI --> Boundaries
    RequestTable --> AuditAPI
```

## Backbone Architecture

```mermaid
flowchart LR
    User["Demo operator"]
    Browser["Browser"]
    React["React + TypeScript App.tsx"]
    Workspaces["WorkspaceViews + MapView"]
    ApiClient["frontend/src/api/client.ts"]
    FastAPI["FastAPI app in backend/app/main.py"]
    Schemas["Pydantic request schemas"]
    Service["VietSupplyRadarService"]
    Domain["Domain algorithms: risk, shock, matching, invoice hash"]
    Repos["Repository layer"]
    SQLite[("SQLite vietsupply.db")]
    CSV["Deterministic CSV seed data"]
    Loader["data_loader + Database seed"]
    Leaflet["Leaflet + CARTO dark tiles"]

    User --> Browser --> React --> Workspaces
    Workspaces --> ApiClient --> FastAPI
    FastAPI --> Schemas
    FastAPI --> Service
    Service --> Domain
    Service --> Repos --> SQLite
    CSV --> Loader --> SQLite
    Workspaces --> Leaflet
```

## OOP Domain Classes

```mermaid
classDiagram
    class Business {
        +business_id: str
        +name: str
        +type: str
        +industry: str
        +product_category: str
        +province: str
        +lat: float
        +lng: float
        +scale: str
        +monthly_revenue: int
        +capacity: int
        +financial_health_score: int
        +supply_risk_score: int
        +risk_level: str
        +from_mapping(row)
        +to_domain()
        +to_api_node(masked)
    }
    class SupplyEdge {
        +edge_id: str
        +source_id: str
        +target_id: str
        +product: str
        +product_category: str
        +monthly_volume: int
        +lead_time_days: int
        +transport_cost: int
        +reliability: float
        +payment_term_days: int
        +to_api_edge()
    }
    class FinancialSnapshot {
        +business_id: str
        +month: str
        +cash_in: int
        +cash_out: int
        +revenue: int
        +debt: int
        +accounts_receivable: int
        +accounts_payable: int
        +inventory_value: int
        +late_payment_rate: float
        +delivery_delay_rate: float
    }
    class Product {
        +business_id: str
        +sku: str
        +product_name: str
        +category: str
        +specification: str
        +available_capacity: int
        +min_order_value: int
        +price_range: str
        +certifications: str
    }
    class InvoiceVerification {
        +invoice_id: str
        +seller_id: str
        +buyer_id: str
        +amount: int
        +issue_date: str
        +due_date: str
        +invoice_hash: str
        +funding_status: str
        +confirmed_by: str
    }
    class ConsentRecord {
        +consent_id: str
        +actor_id: str
        +subject_id: str
        +scope: str
        +purpose: str
        +status: str
        +expires_at: str
        +revoked_at: str
    }
    class AuditLog {
        +event_id: str
        +event_type: str
        +actor_id: str
        +actor_role: str
        +subject_id: str
        +purpose: str
        +timestamp: str
        +request_id: str
    }
    class RiskResult {
        +score: float
        +level: str
        +drivers: list
        +explanation: str
        +formula_version: str
    }
    class ShockResult {
        +shock_business_id: str
        +affected_nodes: list
        +affected_edges: list
        +summary: str
    }
    class SupplierRecommendation {
        +supplier_id: str
        +supplier_name: str
        +match_score: float
        +components: dict
        +reason_codes: list
        +tradeoff: str
    }
    Business "1" --> "many" SupplyEdge : source/target
    Business "1" --> "many" FinancialSnapshot
    Business "1" --> "many" Product
    Business "1" --> "many" InvoiceVerification : buyer/seller
    Business "1" --> "many" ConsentRecord
    Business "1" --> "many" AuditLog : subject
```

## OOP Service And Repository Classes

```mermaid
classDiagram
    class Database {
        +path: Path
        +connect()
        +initialize()
        +has_seed_data()
        +seed()
        +reset()
    }
    class VietSupplyRadarService {
        +overview_payload()
        +dashboard_payload()
        +scenario_payload()
        +businesses_payload(masked)
        +graph_payload(masked)
        +business_detail_payload(business_id)
        +evidence_payload(business_id)
        +risk_signal_payload(business_id)
        +finance_payload(business_id)
        +shock_payload(...)
        +recommendations_payload(...)
        +invoice_payload(invoice_id)
        +connection_request_payload(...)
        +audit_payload()
    }
    class BusinessRepository {
        +list_all()
        +get(business_id)
    }
    class SupplyEdgeRepository {
        +list_all()
        +outgoing(business_id, product_category)
    }
    class FinancialRepository {
        +for_business(business_id)
    }
    class ProductRepository {
        +list_all()
        +for_business(business_id)
    }
    class InvoiceRepository {
        +list_all()
        +get(invoice_id)
    }
    class EvidenceRepository {
        +contracts_for_business()
        +purchase_orders_for_business()
        +delivery_notes_for_business()
        +certifications_for_business()
        +guarantees_for_business()
        +all_for_business()
    }
    class AuditRepository {
        +record(event_type, actor_role, subject_id, purpose)
        +list_recent(limit)
    }
    class ConnectionRequestRepository {
        +create(...)
        +list_recent(limit)
    }
    VietSupplyRadarService *-- BusinessRepository
    VietSupplyRadarService *-- SupplyEdgeRepository
    VietSupplyRadarService *-- FinancialRepository
    VietSupplyRadarService *-- ProductRepository
    VietSupplyRadarService *-- InvoiceRepository
    VietSupplyRadarService *-- EvidenceRepository
    VietSupplyRadarService *-- AuditRepository
    VietSupplyRadarService *-- ConnectionRequestRepository
    BusinessRepository --> Database
    SupplyEdgeRepository --> Database
    FinancialRepository --> Database
    ProductRepository --> Database
    InvoiceRepository --> Database
    EvidenceRepository --> Database
    AuditRepository --> Database
    ConnectionRequestRepository --> Database
```

## Database ERD

```mermaid
erDiagram
    BUSINESSES {
        TEXT business_id PK
        TEXT name
        TEXT type
        TEXT industry
        TEXT product_category
        TEXT province
        REAL lat
        REAL lng
        TEXT scale
        INTEGER monthly_revenue
        INTEGER capacity
        INTEGER financial_health_score
        INTEGER supply_risk_score
    }
    SUPPLY_EDGES {
        TEXT edge_id PK
        TEXT source_id FK
        TEXT target_id FK
        TEXT product
        TEXT product_category
        INTEGER monthly_volume
        INTEGER lead_time_days
        INTEGER transport_cost
        REAL reliability
        INTEGER payment_term_days
    }
    FINANCIAL_SNAPSHOTS {
        TEXT business_id PK,FK
        TEXT month PK
        INTEGER cash_in
        INTEGER cash_out
        INTEGER revenue
        INTEGER debt
        INTEGER accounts_receivable
        INTEGER accounts_payable
        INTEGER inventory_value
        REAL late_payment_rate
        REAL delivery_delay_rate
    }
    PRODUCTS {
        TEXT sku PK
        TEXT business_id FK
        TEXT product_name
        TEXT category
        TEXT specification
        INTEGER available_capacity
        INTEGER min_order_value
        TEXT price_range
        TEXT certifications
    }
    INVOICE_VERIFICATIONS {
        TEXT invoice_id PK
        TEXT seller_id FK
        TEXT buyer_id FK
        INTEGER amount
        TEXT issue_date
        TEXT due_date
        TEXT invoice_hash
        TEXT funding_status
        TEXT confirmed_by
    }
    CONTRACTS {
        TEXT contract_id PK
        TEXT supplier_id FK
        TEXT buyer_id FK
        TEXT product_category
        TEXT status
        TEXT effective_date
        TEXT expiry_date
        INTEGER payment_term_days
        INTEGER sla_lead_time_days
        INTEGER has_exclusivity
        INTEGER has_backup_supplier_clause
        TEXT verification_status
        TEXT source_label
        TEXT document_hash
    }
    PURCHASE_ORDERS {
        TEXT po_id PK
        TEXT contract_id FK
        TEXT supplier_id FK
        TEXT buyer_id FK
        TEXT sku
        TEXT order_date
        TEXT expected_delivery_date
        TEXT actual_delivery_date
        INTEGER quantity
        INTEGER value
        TEXT status
        TEXT verification_status
        TEXT document_hash
    }
    DELIVERY_NOTES {
        TEXT delivery_note_id PK
        TEXT po_id FK
        TEXT supplier_id FK
        TEXT buyer_id FK
        TEXT logistics_partner_id FK
        TEXT delivery_date
        INTEGER delivered_quantity
        INTEGER delay_days
        INTEGER verified_by_buyer
        INTEGER logistics_confirmed
        TEXT status
        TEXT document_hash
    }
    CERTIFICATIONS {
        TEXT certification_id PK
        TEXT business_id FK
        TEXT certification_type
        TEXT issuer
        TEXT effective_date
        TEXT expiry_date
        TEXT status
        TEXT verification_status
        TEXT document_hash
    }
    GUARANTEES {
        TEXT guarantee_id PK
        TEXT applicant_id FK
        TEXT beneficiary_id FK
        TEXT issuer_id FK
        TEXT guarantee_type
        INTEGER amount
        TEXT effective_date
        TEXT expiry_date
        TEXT status
        TEXT verification_status
        TEXT document_hash
    }
    CONNECTION_REQUESTS {
        TEXT request_id PK
        TEXT requester_id
        TEXT buyer_id FK
        TEXT target_supplier_id FK
        TEXT disrupted_supplier_id FK
        TEXT purpose
        TEXT status
        TEXT consent_status
        TEXT requested_at
        TEXT decided_at
    }
    CONSENT_RECORDS {
        TEXT consent_id PK
        TEXT actor_id
        TEXT subject_id
        TEXT scope
        TEXT purpose
        TEXT status
        TEXT expires_at
        TEXT revoked_at
    }
    AUDIT_LOGS {
        TEXT event_id PK
        TEXT event_type
        TEXT actor_id
        TEXT actor_role
        TEXT subject_id
        TEXT purpose
        TEXT timestamp
        TEXT request_id
    }

    BUSINESSES ||--o{ SUPPLY_EDGES : source_id
    BUSINESSES ||--o{ SUPPLY_EDGES : target_id
    BUSINESSES ||--o{ FINANCIAL_SNAPSHOTS : business_id
    BUSINESSES ||--o{ PRODUCTS : business_id
    BUSINESSES ||--o{ INVOICE_VERIFICATIONS : seller_id
    BUSINESSES ||--o{ INVOICE_VERIFICATIONS : buyer_id
    BUSINESSES ||--o{ CONTRACTS : supplier_id
    BUSINESSES ||--o{ CONTRACTS : buyer_id
    CONTRACTS ||--o{ PURCHASE_ORDERS : contract_id
    BUSINESSES ||--o{ PURCHASE_ORDERS : supplier_id
    BUSINESSES ||--o{ PURCHASE_ORDERS : buyer_id
    PURCHASE_ORDERS ||--o{ DELIVERY_NOTES : po_id
    BUSINESSES ||--o{ DELIVERY_NOTES : logistics_partner_id
    BUSINESSES ||--o{ CERTIFICATIONS : business_id
    BUSINESSES ||--o{ GUARANTEES : applicant_id
    BUSINESSES ||--o{ GUARANTEES : beneficiary_id
    BUSINESSES ||--o{ GUARANTEES : issuer_id
    BUSINESSES ||--o{ CONNECTION_REQUESTS : buyer_id
    BUSINESSES ||--o{ CONNECTION_REQUESTS : target_supplier_id
    BUSINESSES ||--o{ CONNECTION_REQUESTS : disrupted_supplier_id
```

## API Surface

```mermaid
flowchart TD
    FastAPI["backend/app/main.py"]
    Health["GET /api/v1/health"]
    Overview["GET /api/v1/overview"]
    Dashboard["GET /api/v1/dashboard"]
    Scenario["GET /api/v1/demo/scenario"]
    Businesses["GET /api/v1/businesses"]
    BusinessDetail["GET /api/v1/businesses/{id}"]
    Evidence["GET /api/v1/businesses/{id}/evidence"]
    Risk["GET /api/v1/businesses/{id}/risk-signal"]
    Finance["GET /api/v1/businesses/{id}/finance"]
    Graph["GET /api/v1/graph"]
    Shock["POST /api/v1/simulation/shock"]
    Recs["POST /api/v1/recommendations/suppliers"]
    Invoice["GET /api/v1/invoices/{id}/verification"]
    Request["POST /api/v1/connection-requests"]
    Audit["GET /api/v1/audit"]
    Service["VietSupplyRadarService"]

    FastAPI --> Health
    FastAPI --> Overview
    FastAPI --> Dashboard
    FastAPI --> Scenario
    FastAPI --> Businesses
    FastAPI --> BusinessDetail
    FastAPI --> Evidence
    FastAPI --> Risk
    FastAPI --> Finance
    FastAPI --> Graph
    FastAPI --> Shock
    FastAPI --> Recs
    FastAPI --> Invoice
    FastAPI --> Request
    FastAPI --> Audit
    Health --> Service
    Overview --> Service
    Dashboard --> Service
    Scenario --> Service
    Businesses --> Service
    BusinessDetail --> Service
    Evidence --> Service
    Risk --> Service
    Finance --> Service
    Graph --> Service
    Shock --> Service
    Recs --> Service
    Invoice --> Service
    Request --> Service
    Audit --> Service
```
