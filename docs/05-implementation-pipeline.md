# Implementation Pipeline

Pipeline nay chia theo 15 phase nhu prompt yeu cau. Moi phase co muc tieu, input, output, tasks, acceptance criteria, risks, mitigation, files/folders va role phu trach.

## Phase 0 - Research & problem framing

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Chot problem statement, scope MVP va research source co citation. |
| Input | 2 PDF, web research, yeu cau pitch ATTACKER 2026. |
| Output | `docs/00`, `docs/01`, scope demo 1 nganh. |
| Tasks | Doc tai lieu, xac dinh pain point, lap bang nguon, chot F&B/FMCG mien Nam. |
| Acceptance | Co one-liner du an, core demo flow, nguon research cho 18 mang. |
| Risks | Scope qua rong, thieu citation. |
| Mitigation | Tach MVP/pilot/production, link nguon trong docs. |
| Files | `docs/00-executive-summary.md`, `docs/01-atom-level-knowledge-map.md`. |
| Owner | Product manager + technical writer. |

## Phase 1 - Domain modeling & data dictionary

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Dinh nghia entities, user journey, data schema. |
| Input | Scope MVP, supply chain/procurement flow. |
| Output | Domain model, data dictionary, validation checklist. |
| Tasks | Tao entity model, luong SME/supplier/financial partner, field validation. |
| Acceptance | 4 dataset bat buoc co field/type/validation; co optional invoice verification. |
| Risks | Data khong lien ket duoc qua IDs. |
| Mitigation | Bat buoc PK/FK va validation script. |
| Files | `docs/02-domain-model.md`, `docs/03-data-dictionary.md`. |
| Owner | Data engineer + backend architect. |

## Phase 2 - MVP scope & user journey

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Chot flow demo: map -> risk -> shock -> recommendation. |
| Input | Domain model, pitch story. |
| Output | Screen list, click path, demo script. |
| Tasks | Xac dinh 5 screen, KPI, default shock node, top 3 recommendation. |
| Acceptance | Co luong demo 5-7 phut khong can dang nhap hay data that. |
| Risks | UI nhieu tab nhung khong co khoanh khac "wow". |
| Mitigation | Shock button va visual impact la trong tam. |
| Files | `docs/13-pitch-demo-script.md`, future `frontend/src/components`. |
| Owner | Product manager + frontend engineer. |

## Phase 3 - Data generation & synthetic dataset

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Tao seed deterministic cho 50-80 businesses, 100-200 edges, 12 thang financials. |
| Input | Data dictionary, region/category taxonomy. |
| Output | CSV/JSON seed va validation report. |
| Tasks | Sinh toa do mien Nam, product categories, risk target, downstream dependencies. |
| Acceptance | Default shock node co it nhat 5 downstream SMEs; validation pass. |
| Risks | Synthetic data qua ngau nhien, khong ke duoc cau chuyen. |
| Mitigation | Dat scenario truoc roi sinh data xung quanh. |
| Files | future `data/*.csv`, `scripts/generate_synthetic_data.py`, `scripts/validate_data.py`. |
| Owner | Data engineer. |

## Phase 4 - System architecture

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Chon stack, layer, repo structure, API boundary. |
| Input | MVP scope, team skill, deploy constraints. |
| Output | Architecture doc. |
| Tasks | Chon React/TS/Leaflet, FastAPI/Pydantic, CSV/JSON, pure domain functions. |
| Acceptance | FE/BE co boundary ro; domain logic khong nam trong UI. |
| Risks | Overengineering voi microservices/real blockchain. |
| Mitigation | Modular monolith MVP, production path rieng. |
| Files | `docs/04-technical-architecture.md`. |
| Owner | Backend architect + frontend engineer. |

## Phase 5 - Frontend map dashboard

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Hien ban do, markers, edges, sidebar detail. |
| Input | `GET /api/v1/graph`, `GET /api/v1/businesses/{id}`. |
| Output | Usable map dashboard. |
| Tasks | MapView, Sidebar, KPI cards, risk color legend, loading/error states. |
| Acceptance | Click node mo sidebar; marker mau theo risk; edge visible; mobile khong vo layout. |
| Risks | Ban do blank do tile/network; text overlap. |
| Mitigation | Fallback local mock + screenshot check. |
| Files | future `frontend/src/components/MapView.tsx`, `Sidebar.tsx`. |
| Owner | Frontend engineer. |

## Phase 6 - Backend API & business logic

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Serve graph, business detail, risk, shock, recommendation. |
| Input | Seed data, domain modules. |
| Output | FastAPI app co OpenAPI. |
| Tasks | Routes, schemas, repositories, error format, logging. |
| Acceptance | API contract trong `docs/06` duoc implement; integration tests pass. |
| Risks | API tra data tuy tien, khong version. |
| Mitigation | `/api/v1`, Pydantic schemas, fixtures. |
| Files | future `backend/app/main.py`, `backend/app/api`, `backend/app/schemas`. |
| Owner | Backend engineer. |

## Phase 7 - Risk scoring module

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Tinh supply risk signal 0-100, threshold xanh/vang/do va explanation. |
| Input | `financials`, dependency metrics. |
| Output | `RiskResult`. |
| Tasks | Normalize features, weighted formula, reason drivers, unit tests. |
| Acceptance | Test low/medium/high risk pass; explanation co top drivers. |
| Risks | Score khong giai thich duoc. |
| Mitigation | Rule-based formula va feature contribution. |
| Files | `docs/07-risk-scoring-design.md`, future `domain/risk_scoring.py`. |
| Owner | AI/risk engineer. |

## Phase 8 - Supplier matching module

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Tra top 3 suppliers thay the dang shortlist theo weighted score. |
| Input | Target SME, disrupted supplier/product, products, businesses, edges. |
| Output | Ranked recommendations. |
| Tasks | Candidate filter, scoring, tie-break, explanation, tests. |
| Acceptance | Khong de xuat supplier cung bi shock; score khong chi theo distance. |
| Risks | Candidate khong du hoac sai spec. |
| Mitigation | Controlled taxonomy, fallback "no candidate" co reason. |
| Files | `docs/08-supplier-matching-design.md`, future `domain/supplier_matching.py`. |
| Owner | Backend/AI engineer. |

## Phase 9 - Shock simulation module

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Xac dinh downstream nodes va impact metrics khi node dut gay. |
| Input | Graph edges, selected shock node, inventory coverage assumptions. |
| Output | Affected nodes, affected edges, impacted volume, stockout days. |
| Tasks | BFS/DFS downstream, volume aggregation, severity level, new edge preview. |
| Acceptance | Direction dung source->target; metrics khop fixture. |
| Risks | Lan truyen sai huong graph. |
| Mitigation | Unit test edge direction va cycles. |
| Files | `docs/09-shock-simulation-design.md`, future `domain/shock_simulation.py`. |
| Owner | Backend engineer. |

## Phase 10 - Optional invoice verification/blockchain simulation

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Mo phong hash hoa don va double financing alert. |
| Input | Invoice JSON canonical. |
| Output | Hash SHA-256, funding status, verification response. |
| Tasks | Canonicalize invoice, hash, duplicate funded check. |
| Acceptance | Same invoice -> same hash; duplicate funded -> alert. |
| Risks | BGK hieu nham blockchain lam du lieu dung. |
| Mitigation | Ghi ro la ledger simulation, raw invoice off-chain. |
| Files | future `domain/invoice_verification.py`. |
| Owner | Security/fintech engineer. |

## Phase 11 - Testing & validation

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Dam bao domain logic, API va demo flow on dinh. |
| Input | Code, seed data, docs. |
| Output | Unit/integration/frontend/data validation tests. |
| Tasks | Test risk, matching, shock, API, click node, shock UI, data validator. |
| Acceptance | Test suite pass; demo rehearsal checklist done. |
| Risks | Demo chi chay tren may dev. |
| Mitigation | Docker/local fallback/video backup. |
| Files | `docs/11-testing-plan.md`, future `backend/tests`, `frontend/tests`. |
| Owner | QA + engineers. |

## Phase 12 - Deployment

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Chay demo online va local fallback. |
| Input | Build FE/BE, env config. |
| Output | Deploy URL, local runbook. |
| Tasks | Build frontend, deploy API, configure CORS, smoke test. |
| Acceptance | URL public chay; local `docker compose up` chay; README ro. |
| Risks | Cloud downtime hoac CORS loi. |
| Mitigation | Local demo + mock API + video. |
| Files | `README.md`, future `docker-compose.yml`. |
| Owner | DevOps engineer. |

## Phase 13 - Monitoring, maintenance, documentation

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Co runbook, logs, changelog, dependency update, backup. |
| Input | Deployed app. |
| Output | Maintenance guide. |
| Tasks | Define logs, error metrics, data validation failure, changelog process. |
| Acceptance | Co guide them schema/nganh/feature/algorithm va migrate. |
| Risks | Sau demo khong ai bao tri duoc. |
| Mitigation | Docs va modular architecture. |
| Files | `docs/12-maintenance-scalability-guide.md`. |
| Owner | Technical writer + DevOps. |

## Phase 14 - Scalability roadmap

| Muc | Noi dung |
| --- | --- |
| Muc tieu | Roadmap tu MVP len pilot/production. |
| Input | MVP learnings, pilot data. |
| Output | 4-week MVP roadmap + 3-12 month production path. |
| Tasks | Postgres/PostGIS, Neo4j, Redis, auth, observability, ML model, governance. |
| Acceptance | Roadmap co milestone, deliverables va risk. |
| Risks | Mo rong truoc khi validate use case. |
| Mitigation | Anchor pilot, metric-led roadmap. |
| Files | `docs/14-roadmap.md`. |
| Owner | Product + architecture lead. |
