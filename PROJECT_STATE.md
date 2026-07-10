# Project State

- Workspace: `D:\attacker`.
- Repo: `https://github.com/tianat-2506/Attacker`; active branch `main`.
- Product: VietSupply Radar, a competition demo converging toward a trust-first supply-chain data platform.
- Active goal: complete the web demo/product; never claim pilot/production readiness.
- User language: Vietnamese.

## Collaboration

- Pull GitHub before work; take one narrow slice; test; update this file; commit and push.
- Avoid overlapping ownership; use task branches for parallel work.
- Never force-push, broadly rewrite, or revert unrelated user changes.

## Pointers

- Run/rehearse: `README.md`, `docs/17-run-project-after-restart.md`, `docs/21-competition-demo-runbook.md`.
- Collaboration/handoff: `docs/19-multi-account-collaboration-protocol.md`, `docs/20-session-handoff-and-workload-map.md`.
- Requirements/research: the two root PDFs and `deep-research-report.md`.
- Architecture/diagrams: `docs/16-current-demo-diagrams.md`, `docs/diagrams/*.drawio`, `docs/18-deep-research-technical-assessment.md`.
- Postgres trust boundary: `backend/migrations/versions/0001_trust_foundation_postgres.sql`, `backend/app/services/postgres_pilot_service.py`.

## Current Product

- FastAPI modular monolith; SQLite is demo-only. Postgres/PostGIS/RLS artifacts exist, but live RLS is unproven.
- Demo accounts cover SME submitter, buyer/supplier admin, reviewer, lender, analyst, operator, and system admin.
- URL state carries account, view, business, and monthly period.
- Role/policy-gated workspaces: Data Intake, Onboarding, Supply Map, Companies/Vault, Risk, Matching, Finance, Invoice Review, Audit.
- Official 3-5 minute story: Intake proof -> Supply Map/Risk -> Shock -> Recovery Matching -> Consent/Audit.
- Hard product details and endpoint inventory are recoverable from source and docs above.

## Latest Slice

- Added route-level code splitting for workspace screens with React `lazy`/`Suspense`.
- New bundle budget gate: `frontend/scripts/assert-build-budget.mjs`, run by `npm.cmd run test:bundle`.
- Build now emits 2 JS chunks: entry around `238.72 kB`, workspace around `265.48 kB`; no `>500 kB` warning.
- Prior slice seeded analytics provenance in Audit: 2 model entries, 4 rulesets, manifest SHA-256 prefix, creator, active status.
- Prior slice completed Data Intake upload/scan -> draft -> validate -> submit -> approve -> canonical snapshot.

## Verification

- Frontend full: `npm.cmd test -- --run --cache=false` passed `93/93`.
- Frontend bundle gate: `npm.cmd run test:bundle` passed; largest JS chunk `265518` bytes.
- Frontend build: `npm.cmd run build` passed with no chunk-size warning.
- Backend full: `python -B -m unittest discover -s backend\tests` passed `150`, skipped `3`.
- Browser smoke: Overview and Audit lazy routes render; Audit shows `2` models, `4` rulesets, `manifest sha256`; desktop/mobile have no console errors or horizontal overflow.
- Runtime API: `demo_operator` reads registry as `demo-user`, not hidden admin impersonation.
- Browser Intake: `2027-05` completed with `approved`, 1 financial, 1 product, 1 evidence.

## Hard Boundaries

- Do not claim: pilot/production ready, credit score/default probability, bank approval, verified supplier, invoice authenticity, legal breach/fraud, or confirmed double financing.
- Proven: deterministic seeded demo behavior plus local/static trust gates.
- Unproven: real OIDC/JWKS, S3/MinIO, ClamAV, live PostgreSQL RLS, tamper-proof/WORM audit, production graph confidentiality, real finance automation.

## Next Best Work

- Keep the competition story at 3-5 minutes; do not dilute it.
- Add a lightweight rendered browser rehearsal for the official runbook.
- Polish Supply Map/Risk/Matching around disrupted supplier `BIZ-005`.
- Make Shock the signature moment with staged route propagation and recovery visuals.
- Preserve role, period, consent, privacy, and human-review gates.

## QA/Subagents

- QA charter: test as real stakeholders; flag token waste, unsupported legal/finance claims, broken role flows, and UI-only features without backend policy/data paths.
- Recent attempted agents `Descartes` and `Hume` hit usage limits.
- Prior QA names: `Heisenberg`, `Ampere`, `Zeno`, `Peirce`, `Lovelace`, `Hegel`, `Confucius`, `Locke`, `Popper`, `Herschel`, `Raman`, `Poincare`, `Galileo`.
