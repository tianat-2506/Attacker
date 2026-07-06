# Technical Architecture

## 1. Quyet dinh stack cho MVP

| Lop | Chon cho MVP | Ly do | Duong nang cap |
| --- | --- | --- | --- |
| Frontend | React + TypeScript + Leaflet | Nhanh, de build dashboard map, component/state ro rang, khong can token Mapbox cho MVP | Mapbox/deck.gl khi can arc layer, heatmap dep hon |
| Backend | FastAPI + Pydantic | Hop voi Python domain logic, OpenAPI tu dong, type hints ro | Tach service rieng, async jobs, auth, rate limit |
| Data | JSON/CSV seed static trong repo | Nhanh, de demo offline, deterministic | PostgreSQL + PostGIS, sau do Neo4j neu graph lon |
| Risk/matching | Pure Python functions | De test, de giai thich, khong phu thuoc DB/UI | ML model, feature store, model registry |
| Deployment | Frontend Vercel/Netlify, backend Render/Fly/Railway, Docker local | Nhanh cho hackathon/demo | Docker Compose, CI/CD, managed Postgres |

Nguon: [React](https://react.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Leaflet](https://leafletjs.com/reference.html), [Pydantic](https://docs.pydantic.dev/latest/), [Docker docs](https://docs.docker.com/).

## 2. Layer architecture

```text
Data Source Layer
  CSV/JSON synthetic data
  Future: POS, ERP, accounting, e-invoice, bank statement, logistics API

Data Processing Layer
  ETL, cleaning, validation, normalization, deduplication

Storage Layer
  MVP: files loaded into memory
  Pilot: PostgreSQL
  Production: PostgreSQL + PostGIS, Neo4j optional, object storage

Intelligence Layer
  Risk scoring
  Supplier matching
  Shock simulation
  AI explanation
  Invoice verification simulation

API Layer
  FastAPI endpoints, OpenAPI contract, Pydantic schemas

Frontend Layer
  Map dashboard, sidebar, KPI cards, risk panel, shock button, recommendation cards

Security/Governance Layer
  Auth/RBAC later, masking, consent, audit logs, secrets, TLS
```

## 3. Repository structure de build sau tai lieu

```text
vietsupply-radar/
  README.md
  .env.example
  docs/
  data/
    businesses.csv
    supply_edges.csv
    financials.csv
    products.csv
    seed_notes.md
  backend/
    app/
      main.py
      api/
      domain/
        risk_scoring.py
        supplier_matching.py
        shock_simulation.py
        invoice_verification.py
      schemas/
      services/
    tests/
  frontend/
    src/
      components/
        MapView.tsx
        Sidebar.tsx
        RiskPanel.tsx
        RecommendationCard.tsx
        ShockSimulationButton.tsx
      api/
      types/
      utils/
  scripts/
    generate_synthetic_data.py
    validate_data.py
  docker-compose.yml
```

## 4. Data flow MVP

1. Backend start: load CSV/JSON seed vao in-memory repositories.
2. Data validation chay truoc khi serve API.
3. Frontend goi `GET /api/v1/graph` de ve markers va polylines.
4. User click marker: `GET /api/v1/businesses/{id}` tra detail, risk, financial summary.
5. User bam shock: `POST /api/v1/simulation/shock` tra affected nodes/edges/metrics.
6. Frontend goi `POST /api/v1/recommendations/suppliers` hoac shock API tra luon recommendations.
7. Optional invoice tab: `GET /api/v1/invoices/{id}/verification`.

## 5. Frontend component map

| Component | Responsibility | State |
| --- | --- | --- |
| `MapView` | Leaflet map, markers, polylines, risk color, selected node event | `selectedBusinessId`, `shockResult` |
| `Sidebar` | Business detail, tabs: Overview/Risk/Financials/Invoice | `businessDetail` |
| `RiskPanel` | Risk score, threshold, drivers, explanation text | `riskScore` |
| `ShockSimulationButton` | Trigger selected/default shock node | `isSimulating` |
| `RecommendationCard` | Top 3 supplier cards, score, reason codes | `recommendations` |
| `KpiBar` | Affected SMEs, volume, stockout days, replacement readiness | `impactMetrics` |

## 6. Backend module map

| Module | Responsibility | Test focus |
| --- | --- | --- |
| `domain/risk_scoring.py` | Pure functions tinh risk 0-100 va level | Feature normalization, thresholds, explanations |
| `domain/supplier_matching.py` | Filter va rank suppliers | Weighted score, reason codes, tie-break |
| `domain/shock_simulation.py` | Traversal downstream va impact metrics | BFS/DFS direction, affected volume |
| `domain/invoice_verification.py` | Hash canonical invoice, double financing check | Stable hash, duplicate funded invoice |
| `services/repositories.py` | Load/search data | Data integrity |
| `api/routes.py` | HTTP endpoints | Status code, schema, error format |

## 7. API and schema principles

- Version API tu dau: `/api/v1`.
- Response JSON co `data`, `meta`, `errors`.
- Domain errors co code ro: `BUSINESS_NOT_FOUND`, `INVALID_SHOCK_NODE`, `NO_SUPPLIER_CANDIDATES`.
- OpenAPI la contract chinh de FE/BE lam song song.
- Validation dung Pydantic, khong tin input tu UI.

Nguon: [OpenAPI Specification](https://spec.openapis.org/oas/latest.html), [FastAPI](https://fastapi.tiangolo.com/).

## 8. Security architecture cho MVP va pilot

MVP demo:

- Khong co user data that.
- Khong commit secrets.
- `.env.example` chi co bien mau.
- Masking logic duoc mo ta va co placeholder implementation.

Pilot/production:

- Auth + RBAC.
- Audit logs cho moi truy cap financials/invoices.
- TLS bat buoc.
- Secret manager thay cho `.env` plain text.
- Data minimization, retention, deletion workflow.
- Consent record cho viec chia se supplier/customer/financial data.

Nguon: [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/), [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [NIST Privacy Framework](https://www.nist.gov/privacy-framework).

## 9. Architecture risks

| Rui ro | Tac dong | Giam thieu |
| --- | --- | --- |
| Scope qua rong | Khong kip demo | Chi build 5 screen va 3 core functions |
| Synthetic data phi logic | BGK khong tin | Seed theo business story, validation, risk target ro |
| Map cham/roi | Demo mat flow | Dung 50-80 nodes, cluster neu can, fallback static JSON |
| Score bi xem la tuy tien | Bi phan bien AI | Formula minh bach, weight giai thich, test va limitation |
| Lo graph nhay cam trong pilot | Mat niem tin | Masking, consent, RBAC, audit |
