# Roadmap

## 1. Roadmap 4 tuan cho MVP demo

| Tuan | Focus | Deliverables | Acceptance |
| --- | --- | --- | --- |
| Week 1 | Scope, data, map | Seed data 50-80 businesses, 100-200 edges; map dashboard; sidebar basic | Mo web thay map, node, edge; click node hien info |
| Week 2 | Risk scoring | Risk formula, financial panel, explanation, tests | Node target hien risk do/vang va drivers |
| Week 3 | Shock + recommendation | Shock simulation, impact metrics, top 3 suppliers, tests | Bam shock thay affected nodes/KPI/recommendations |
| Week 4 | Polish + pitch | UI polish, README, deploy, video backup, slide/script/Q&A | Demo on dinh 5-7 phut, fallback ready |

## 2. Backlog MVP by epic

| Epic | Features |
| --- | --- |
| Data foundation | Generate seed, validate schema, load repository |
| Map dashboard | Markers, polylines, risk colors, sidebar |
| Risk intelligence | Feature normalization, formula, explanation |
| Shock simulation | Downstream traversal, severity, impact metrics |
| Supplier matching | Candidate filter, weighted ranking, reason cards |
| Invoice verification optional | Hash invoice, funding status, double financing alert |
| Testing/deployment | Unit tests, API tests, README, local/dev deploy |

## 3. Pilot roadmap 2-3 thang

| Milestone | Goal | Key work |
| --- | --- | --- |
| Pilot design | Chon anchor partner va data scope | Consent, data agreement, field mapping |
| Data ingestion | Import POS/accounting/e-invoice/logistics | ETL, validation, lineage |
| Risk calibration | So sanh risk signal voi outcome thuc | Backtesting, threshold tuning |
| Matching validation | Kiem chung top 3 supplier co dung khong | Buyer feedback, supplier qualification |
| Governance | Bao ve data nhay cam | RBAC, masking, audit, retention |
| Pilot report | Chung minh gia tri | Time-to-match, disruptions detected, alternative-sourcing success |

## 4. Production roadmap 6-12 thang

| Layer | Upgrade |
| --- | --- |
| Data | PostgreSQL/PostGIS, object storage, data contracts |
| Graph | Graph service/Neo4j neu can multi-hop queries lon |
| AI | ML risk model, model registry, monitoring, explainability |
| Product | Multi-tenant orgs, roles, consent workflow, supplier onboarding |
| Security | Auth, RBAC, audit, encryption, secrets manager |
| Fintech | Financial partner workflow, KYB/KYC integration, invoice verification |
| DevOps | CI/CD, staging/prod, observability, backups |

## 5. Metrics

MVP demo metrics:

- Demo completion time <= 7 minutes.
- Shock response < 1 second on seed data.
- Recommendation returns top 3 for default scenario.
- Unit tests pass for risk/match/shock.

Pilot metrics:

- Alert precision/recall against known disruption/late delivery outcomes.
- `hit_rate@3` for supplier recommendations.
- Average time-to-match reduction.
- % matched suppliers passing qualification.
- User trust score for explanation clarity.

Business metrics:

- Active SME accounts.
- Monthly risk checks.
- Matching conversion rate.
- Referral conversion to working capital partner.
- Churn and expansion by anchor network.

## 6. Risks and mitigation

| Risk | Stage | Mitigation |
| --- | --- | --- |
| Data cold start | MVP/pilot | Synthetic demo + anchor company pilot |
| Sensitive relationship leakage | Pilot/production | Masking, consent, RBAC, audit |
| AI overclaim | Pitch/pilot | Say rule-based risk signal, document limitation |
| Supplier replacement not feasible | MVP/pilot | Multi-factor shortlist + qualification flow + human approval |
| Regulatory/fintech concerns | Pilot/production | Position as decision support/referral, not lender |
| Blockchain distraction | Pitch | Keep invoice verification optional |
| Demo instability | MVP | Local fallback, mock API, video backup |

## 7. Decision gates

| Gate | Criteria to proceed |
| --- | --- |
| MVP -> pilot | Demo works, pitch story clear, at least one interested anchor partner |
| Pilot -> production | Real data validates risk/matching, consent model accepted, users see value |
| Rule-based -> ML | Enough labeled outcomes, baseline/backtesting defined, model governance ready |
| CSV -> Postgres | Multiple users/data updates, need persistence/query performance |
| Relational -> graph DB | Multi-hop graph queries become bottleneck or core product feature |

## 8. Immediate next tasks after this docs package

1. Create issue backlog from docs.
2. Generate synthetic seed files.
3. Scaffold FastAPI backend and pure domain modules.
4. Scaffold React/TypeScript/Leaflet frontend.
5. Implement tests for risk, matching, shock.
6. Wire demo flow and README run commands.
