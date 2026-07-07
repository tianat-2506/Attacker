# VietSupply Radar

VietSupply Radar is a proposed B2B supply-chain risk dashboard for Vietnamese SMEs. It maps businesses as geospatial graph nodes, models supply relationships as directed edges, uses transparent rule-based signals to flag cash-flow and disruption risk, and produces explainable supplier shortlists for human review.

This repository now contains the research package plus a runnable MVP demo scaffold. The demo uses a React cockpit frontend, a FastAPI backend, a SQLite database seeded from deterministic CSV data, and explicit domain/repository/service classes so the code can scale beyond the first prototype.

## Project Focus

- Industry: F&B/FMCG, packaged food and processed agriculture.
- Region: TP.HCM, Binh Duong, Dong Nai, Lam Dong.
- MVP demo flow: overview map -> 10-node Binh Duong disruption case -> evidence vault -> risk signal review -> supply shock -> top 3 suggested supplier alternatives -> consent-based introduction request -> audit trail -> invoice verification.
- Data: synthetic, deterministic, 62 businesses, supply edges, procurement documents, certifications, guarantees, audit events and 12 months of financial snapshots.
- AI stance: rule-based risk signal plus explainable text. ML is a later pilot/production upgrade.
- Blockchain stance: optional invoice hash/funding-status simulation, not the center of the pitch.
- Legal/finance stance: advisory decision-support only. The platform does not terminate suppliers, approve credit, declare breach/default, or reveal sensitive data without consent, evidence and audit.

## Documentation

- [Executive summary](docs/00-executive-summary.md)
- [Atom-level knowledge map](docs/01-atom-level-knowledge-map.md)
- [Domain model](docs/02-domain-model.md)
- [Data dictionary](docs/03-data-dictionary.md)
- [Technical architecture](docs/04-technical-architecture.md)
- [Implementation pipeline](docs/05-implementation-pipeline.md)
- [API contract](docs/06-api-contract.md)
- [Risk scoring design](docs/07-risk-scoring-design.md)
- [Supplier matching design](docs/08-supplier-matching-design.md)
- [Shock simulation design](docs/09-shock-simulation-design.md)
- [Security and data governance](docs/10-security-data-governance.md)
- [Testing plan](docs/11-testing-plan.md)
- [Maintenance and scalability guide](docs/12-maintenance-scalability-guide.md)
- [Pitch demo script](docs/13-pitch-demo-script.md)
- [Roadmap](docs/14-roadmap.md)
- [Current demo diagrams](docs/16-current-demo-diagrams.md)
- [Run project after restart](docs/17-run-project-after-restart.md)
- [Draw.io system blueprint](docs/diagrams/VietSupply_Radar_System_Blueprint.drawio)
- [Current demo draw.io backbone](docs/diagrams/VietSupply_Radar_Current_Demo_Backbone.drawio)

## Recommended MVP Stack

- Frontend: React + TypeScript + Leaflet.
- Backend: FastAPI + Python domain services.
- Data MVP: SQLite database seeded from CSV, with repository classes over the database.
- Future data path: PostgreSQL + PostGIS; Neo4j only when graph queries outgrow adjacency lists.
- Testing: pytest for backend/domain logic, Vitest/React Testing Library for frontend, Playwright for demo flow.
- Deployment: local Docker fallback plus simple frontend/backend hosting.

## Current Demo Architecture

```text
frontend/src
  App.tsx                     API-first dashboard shell
  api/client.ts               frontend API adapter + mock fallback
  components/MapView.tsx      Leaflet dark map with Southern Vietnam/Binh Duong focus
  components/WorkspaceViews.tsx
                              overview, evidence, risk, matching, finance, invoice and audit workspaces

backend/app
  domain/entities.py          OOP dataclasses: Business, SupplyEdge, Product, FinancialSnapshot, InvoiceVerification
  domain/*.py                 pure domain logic: risk signal, matching, shock simulation, invoice hash
  services/database.py        SQLite schema + deterministic seed process
  services/repositories.py    repositories for graph, documents, guarantees, audit and connection requests
  services/radar_service.py   application service coordinating repositories + domain logic
  main.py                     FastAPI endpoints

backend/app/data/vietsupply.db
  Generated SQLite demo database.
```

The current DB is intentionally SQLite for fast local iteration. The repository/service boundary is designed so a later PostgreSQL/PostGIS migration can keep most domain logic and API behavior stable.

## PostgreSQL Pilot Path

The demo runtime still uses SQLite, but the trust foundation now has a PostgreSQL/PostGIS/RLS migration artifact and runner.

Plan migrations without connecting:

```powershell
cd D:\attacker
python scripts/apply_postgres_migrations.py --database-url postgresql://user:password@localhost:5432/vietsupply --plan-only
```

Apply migrations to a prepared PostgreSQL database:

```powershell
cd D:\attacker
$env:DATABASE_URL="postgresql://user:password@localhost:5432/vietsupply"
python scripts/apply_postgres_migrations.py
```

Run the DB-level RLS smoke test against a prepared PostgreSQL/PostGIS database:

```powershell
cd D:\attacker
$env:POSTGRES_TEST_DATABASE_URL="postgresql://user:password@localhost:5432/vietsupply_smoke"
python scripts/postgres_rls_smoke.py
```

Run the trust readiness gate before claiming pilot readiness:

```powershell
cd D:\attacker
python scripts/run_trust_readiness_gate.py
```

For local development without live PostgreSQL/OIDC/object storage, use the explicit non-pilot mode:

```powershell
python scripts/run_trust_readiness_gate.py --allow-missing-live
```

This can pass local checks while still reporting `pilot_ready=false` until live RLS, real OIDC/JWKS signed-token proof, S3/MinIO evidence storage PUT/GET/DELETE proof, and malware-scanner proof exist.

Run the local operational smoke gate for the SQLite demo adapter:

```powershell
python scripts/run_local_operational_smoke.py
```

This covers deterministic seed counts, SQLite backup/restore, masked graph redaction, security negative checks, audit tamper detection, and local latency baselines. It is not a substitute for live PostgreSQL/RLS/OIDC/object-storage/malware-scanner proof.

If Docker Desktop is available, start disposable MinIO and ClamAV containers and run the evidence live smokes:

```powershell
cd D:\attacker
powershell -ExecutionPolicy Bypass -File scripts/run_evidence_live_smoke_docker.ps1
```

To also feed the evidence live-smoke flags into the readiness gate while still allowing missing OIDC/PostgreSQL proof:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_evidence_live_smoke_docker.ps1 -RunReadinessGate
```

Or, if Docker Desktop is available, start a disposable PostGIS container and run the same smoke test:

```powershell
cd D:\attacker
powershell -ExecutionPolicy Bypass -File scripts/run_postgres_rls_smoke_docker.ps1
```

Pilot/production auth must use a real OIDC/JWKS issuer, not the local dev JWT adapter:

```powershell
$env:APP_MODE="pilot"
$env:ALLOW_DEMO_HEADERS="false"
$env:AUTH_PROVIDER="oidc"
$env:AUTH_JWKS_URL="https://issuer.example/.well-known/jwks.json"
$env:AUTH_JWT_ISSUER="https://issuer.example/"
$env:AUTH_JWT_AUDIENCE="vietsupply-api"
```

Check OIDC verifier mechanics with a local synthetic JWKS server. This is not pilot proof:

```powershell
python scripts/run_oidc_jwks_smoke.py --synthetic --json
```

After configuring a real issuer, run a live signed-token smoke with a disposable token from that issuer. This proves only the OIDC slice; the full readiness gate still also needs PostgreSQL RLS, S3/MinIO and ClamAV live proof:

```powershell
$env:OIDC_SMOKE_TOKEN="<signed test token from issuer>"
python scripts/run_oidc_jwks_smoke.py --json
$env:OIDC_SIGNED_TOKEN_LIVE_SMOKE="1"
python scripts/run_trust_readiness_gate.py
```

Pilot/production requests must set the following PostgreSQL RLS session variables per request before sensitive queries:

- `app.tenant_id`
- `app.actor_id`
- `app.organization_ids`
- `app.purpose`
- `app.scopes`

Important: `APP_MODE=pilot|production` runs only the PostgreSQL workflows that have been explicitly ported; unported workflows fail fast instead of falling back to SQLite/demo data.

## Run The Demo

From a clean checkout, use two terminals.

Terminal 1 - backend API:

```powershell
cd D:\attacker
python -m pip install -r backend/requirements.txt
python scripts/generate_synthetic_data.py
python scripts/seed_database.py
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 - web frontend:

```powershell
cd D:\attacker\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Then open:

- Web app: http://127.0.0.1:5173
- Backend health check: http://127.0.0.1:8000/api/v1/health
- API docs: http://127.0.0.1:8000/docs

If dependencies are already installed, the short run loop is:

```powershell
cd D:\attacker
python scripts/seed_database.py
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Optional frontend API override:

```bash
set VITE_API_BASE_URL=http://127.0.0.1:8000
```

Useful verification commands:

```powershell
python -m unittest discover -s backend/tests
python scripts/validate_data.py
python scripts/validate_postgres_migrations.py
cd D:\attacker\frontend
npm run build
```

Key demo API checks:

```powershell
@'
import json
from urllib.request import urlopen
for path in [
    "/api/v1/demo/scenario",
    "/api/v1/businesses/BIZ-005/evidence",
    "/api/v1/businesses/BIZ-005/risk-signal",
    "/api/v1/businesses/BIZ-005/finance",
    "/api/v1/audit",
]:
    with urlopen("http://127.0.0.1:8000" + path) as response:
        payload = json.load(response)
    print(path, "ok", sorted(payload.keys()))
'@ | python -
```

## Core Formulas

Supply risk signal:

```text
Supply Risk Signal =
  0.25 * cashflow_risk
+ 0.20 * late_payment_risk
+ 0.15 * inventory_risk
+ 0.15 * delivery_delay_risk
+ 0.15 * debt_risk
+ 0.10 * dependency_risk
```

Supplier match score:

```text
Match Score =
  0.25 * product_spec_fit
+ 0.20 * capacity_fit
+ 0.15 * distance_score
+ 0.15 * financial_health_score
+ 0.10 * delivery_reliability
+ 0.10 * payment_term_fit
+ 0.05 * price_score
```

## Pitch Positioning

Do say:

- "This is an early warning risk signal for supply-chain continuity."
- "Matching uses product fit, capacity, logistics, reliability, payment terms and financial health."
- "Supplier cards are suggested alternatives that require human review, supplier qualification and mutual consent before contact details or commercial action."
- "Invoice verification simulates a ledger/hash workflow for double-financing prevention, not proof that the original invoice is true."

Do not say:

- "AI replaces bank underwriting."
- "Blockchain makes all data true."
- "The nearest supplier is automatically the best supplier."
- "The whole commercial graph is public."
- "The platform automatically switches suppliers or approves financing."

## Primary Sources Used

- [CSCMP Supply Chain Management Definitions and Glossary](https://cscmp.org/CSCMP/Educate/SCM_Definitions_and_Glossary_of_Terms.aspx)
- [Microsoft Dynamics 365 Procurement and sourcing overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-sourcing-overview)
- [SEC Beginners' Guide to Financial Statements](https://www.sec.gov/about/reports-publications/investorpubsbegfinstmtguide)
- [World Bank SME Finance](https://www.worldbank.org/ext/en/topic/competitiveness/small-and-medium-enterprises-smes-finance)
- [IFC MSME Finance](https://www.ifc.org/en/what-we-do/sector-expertise/financial-institutions/msme-finance)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [Federal Reserve SR 11-7 Model Risk Management](https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm)
- [React](https://react.dev/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Leaflet](https://leafletjs.com/reference.html)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework)
- [Hyperledger Fabric Introduction](https://hyperledger-fabric.readthedocs.io/en/latest/blockchain.html)
