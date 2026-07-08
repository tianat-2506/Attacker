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

- Run docs: `README.md`, `docs/17-run-project-after-restart.md`, `docs/21-competition-demo-runbook.md`.
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

- Demo competition focus accepted: prioritize a polished 3-5 minute story over deeper production backend work unless user redirects.
- Overview now has a live `3-5 min demo run` checklist: Data Intake -> Supply Map/Risk -> Shock Simulation -> Recovery Matching -> Consent/Audit.
- Shock Simulation now surfaces active-story status plus impact metrics for exposed units, revenue at risk, stockout window and downstream SMEs.
- Shock path now keeps a separate disrupted supplier context so Risk/Matching stay tied to Dai Tin/`BIZ-005` instead of drifting to the buyer selected business.
- URL `business` state now survives initial React dev hydration; direct rehearsal links like buyer + `BIZ-005` no longer reset to buyer default on first mount.
- QA subagent reviewed the demo path; addressed the highest-impact items for direct-link stability, buyer/disrupted-supplier mismatch, and stronger shock-to-recovery handoff.
- Added `frontend/src/utils/demoStory.ts` with tests so future sessions do not accidentally break the locked demo flow.
- Synced competition docs to the locked flow. `docs/21-competition-demo-runbook.md` is now the official 3-5 minute click-path: `demo-operator` -> Data Intake -> Supply Map/Risk -> Shock -> Matching -> Consent/Audit.
- `docs/13-pitch-demo-script.md` was rewritten to match the runbook and preserve legal/finance guardrails; README now points to the official rehearsal URL.
- `frontend/src/utils/demoStory.test.ts` now asserts `demo-operator` has all 5 demo steps live and `buyer-admin` is intentionally scoped with Intake/Audit blocked.
- Demo boundary copy now uses `frontend/src/utils/demoBoundary.ts`: demo fallback is framed as `Competition demo mode` / `Demo dataset active`, while pilot/non-demo wording remains strict about verified authorization.

## Verification

- Latest targeted frontend: `npm.cmd exec vitest -- run src\utils\demoStory.test.ts --cache=false` passed, 5 tests.
- Latest frontend typecheck/build: `npm.cmd run build` passed.
- Latest backend full: `python -B -m unittest discover -s backend\tests` passed, 146 tests, 2 skipped.
- Latest targeted frontend: `npm.cmd exec vitest -- run src\api\client.test.ts --cache=false` passed, 13 tests.
- Latest frontend typecheck: `npm.cmd exec tsc -- --noEmit` passed.
- Latest targeted frontend: `npm.cmd exec vitest -- run src\utils\demoBoundary.test.ts src\utils\demoStory.test.ts --cache=false` passed, 9 tests.
- Latest frontend tests: `npm.cmd exec vitest -- run --cache=false` passed, 60 tests.
- Browser smoke: opened `http://127.0.0.1:5173/?view=overview&account=demo-operator&period=2026-07`; verified story panel renders 5 steps, shock activation shows impact panel, no console errors or horizontal overflow.
- Browser smoke: opened `http://127.0.0.1:5173/?view=overview&account=buyer-admin&business=BIZ-005&period=2026-07`; verified URL business persists, shock band appears, Matching header separates buyer from disrupted supplier, no console errors or horizontal overflow.

## Hard Boundaries

- Do not claim: pilot-ready, production-ready, credit score, default probability, bank approval, verified supplier, invoice authenticity, legal breach, fraud, confirmed double financing.
- Current strong guarantee: deterministic SQLite demo behavior over seeded fixtures plus local/static trust gates.
- Not guaranteed: real OIDC/JWKS, S3/MinIO, ClamAV, PostgreSQL RLS live checks, WORM/tamper-proof audit, production graph confidentiality, real finance automation.

## Next Best Work

- Continue demo competition completion:
- Keep demo story locked to 3-5 minutes; avoid adding steps that dilute the pitch.
- Add automated browser rehearsal/E2E for the official runbook when a lightweight tool path is chosen.
- Polish Supply Map + Risk + Matching around the Dai Tin disruption story.
- Make Shock Simulation more impressive with clear before/after paths and recovery sequencing.
- Make Data Intake visibly prove input lineage: form, CSV, evidence upload, scan, review, approved snapshot.
- Keep audit/consent/privacy visible in every cross-org action.
- Per-account RBAC across one supply chain; each org owns separate data.
- Vault should show scan-cleared/reviewed documents without legal authenticity claims.
- Continue tightening Postgres live-readiness proof and evidence object-store/malware-scan integration.
- Onboarding, map, matching, finance, invoice, audit must keep role and period gates.
- Configure disposable real services for OIDC, object storage, malware scan, PostgreSQL/PostGIS, then run live readiness gate before any pilot claim.

## QA/Subagents

- Standing QA charter: act as real stakeholder users; penalize token waste, unsupported legal/finance claims, broken role workflows, and UI-only features without backend permission/data path.
- Recent attempted QA subagents hit usage limits: `Descartes`, `Hume`.
- Previous QA names to recall if useful: `Heisenberg`, `Ampere`, `Zeno`, `Peirce`, `Lovelace`, `Hegel`, `Confucius`, `Locke`, `Popper`, `Herschel`, `Raman`, `Poincare`, `Galileo`.
