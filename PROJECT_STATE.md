# Project State

- Workspace: `D:\attacker`.
- Repo: `https://github.com/tianat-2506/Attacker`, branch `main`.
- Product: VietSupply Radar; supply-chain/SME finance-ready demo converging toward a trust-first backend/data/security platform.
- User language: Vietnamese.
- Active goal: keep completing the web app; do not claim pilot/production readiness.

## Collaboration Rule

- Every account/session must pull GitHub first, take a narrow slice, test it, update this file, commit, and push before ending.
- Avoid overlapping edits; use task branches or separate file ownership for parallel work.
- No force push, broad rewrites, or unrelated refactors.
- When context/token is low: stop feature work, record current state here, commit/push.

## Source Pointers

- Run docs: `README.md`, `docs/17-run-project-after-restart.md`.
- Multi-account workflow: `docs/19-multi-account-collaboration-protocol.md`, `docs/20-session-handoff-and-workload-map.md`.
- Source inputs: `Prompt_Codex_VietSupply_Radar.pdf`, `Noi_dung_hoi_thoai_du_an_VietSupply_Radar.pdf`, `deep-research-report.md`.
- Diagrams: `docs/16-current-demo-diagrams.md`, `docs/diagrams/*.drawio`.
- Tech assessment: `docs/18-deep-research-technical-assessment.md`.
- Postgres trust boundary: `backend/migrations/versions/0001_trust_foundation_postgres.sql`, `backend/app/services/postgres_pilot_service.py`.

## Current Posture

- FastAPI modular monolith; SQLite remains demo adapter only.
- PostgreSQL/PostGIS/RLS migration and pilot adapter exist; live RLS smoke not proven.
- Demo auth uses headers/JWT-dev; `/auth/me` exposes capability matrix and workspace access.
- Demo stakeholder accounts include SME submitter, buyer admin, supplier admins, reviewer, lender, network analyst, demo operator, system admin.
- URL-backed frontend state: account, selected business, active view, monthly period.
- Data Intake supports draft/validate/submit/review/approve, CSV import, period snapshot, evidence upload tickets, scan job, and Vault download ticket for clean uploaded evidence.
- Period-aware reads exist for Companies, Evidence, Risk, Finance, Matching; no silent fallback for missing selected-month finance.
- Supply-map onboarding, connection inbox, graph, evidence, finance, invoices, matching, risk, audit/admin ops are policy/role gated in demo.

## Latest Slice

- CSV raw-record lineage slice completed.
- Approved canonical financial/product rows now use CSV `raw_records.raw_record_id` as `source_record_id` when materialized from CSV import batches.
- Manual form fallback still uses the existing section-derived source ids.
- Regression coverage proves approved CSV financials and products link back to the exact raw rows used for ingestion.

## Verification

- Latest backend targeted: `python -B -m unittest backend.tests.test_periodic_intake.PeriodicIntakeTests.test_csv_raw_records_link_to_approved_canonical_rows backend.tests.test_periodic_intake.PeriodicIntakeTests.test_csv_import_replay_is_idempotent backend.tests.test_periodic_intake.PeriodicIntakeTests.test_draft_validate_submit_approve_materializes_period_snapshot` passed.
- Latest backend full: `python -B -m unittest discover -s backend\tests` passed, 137 tests, 2 skipped.
- Frontend baseline from prior slices: `npm.cmd exec tsc -- --noEmit`, `npm.cmd exec vitest -- run --cache=false` 51 tests, and `npm.cmd exec vite -- build --outDir .vite-check-dist` passed.
- Latest slice did not require frontend rerun.

## Hard Boundaries

- Do not claim: pilot-ready, production-ready, credit score, default probability, bank approval, verified supplier, invoice authenticity, legal breach, fraud, confirmed double financing.
- Current strong guarantee: deterministic SQLite demo behavior over seeded fixtures plus local/static trust gates.
- Not guaranteed: real OIDC/JWKS, S3/MinIO, ClamAV, PostgreSQL RLS live checks, WORM/tamper-proof audit, production graph confidentiality, real finance automation.

## Next Best Work

- Continue functional completion over UI polish:
- Per-account RBAC across one supply chain; each org owns separate data.
- Vault should show scan-cleared/reviewed documents without legal authenticity claims.
- Continue tightening Intake/Vault provenance for evidence object versions and reviewer history.
- Onboarding, map, matching, finance, invoice, audit must keep role and period gates.
- Configure disposable real services for OIDC, object storage, malware scan, PostgreSQL/PostGIS, then run live readiness gate before any pilot claim.

## QA/Subagents

- Standing QA charter: act as real stakeholder users; penalize token waste, unsupported legal/finance claims, broken role workflows, and UI-only features without backend permission/data path.
- Recent attempted QA subagents hit usage limits: `Descartes`, `Hume`.
- Previous QA names to recall if useful: `Heisenberg`, `Ampere`, `Zeno`, `Peirce`, `Lovelace`, `Hegel`, `Confucius`, `Locke`, `Popper`, `Herschel`, `Raman`, `Poincare`, `Galileo`.
