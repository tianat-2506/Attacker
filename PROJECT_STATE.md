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

- Added Shock/Matching recovery playbook for the competition demo.
- Overview now shows recovery coverage, primary route, alternate route count, recoverable/residual volume, lead time, and guardrail after shock.
- Matching now shows a wide "Shock recovery plan" panel above supplier cards.
- `demo-operator` recovery matching now uses affected buyer `BIZ-009` when present, not disrupted supplier `BIZ-005`.
- New tests cover recovery playbook math/guardrails and demo recovery buyer selection.
- Prior slice added rendered rehearsal page at `http://127.0.0.1:5173/demo-rehearsal.html`.
- Prior slice added route-level workspace code splitting and `npm.cmd run test:bundle`; largest JS chunk remains about `265.48 kB`.
- Prior slice seeded analytics provenance in Audit: 2 model entries, 4 rulesets, manifest SHA-256 prefix, creator, active status.
- Prior slice completed Data Intake upload/scan -> draft -> validate -> submit -> approve -> canonical snapshot.

## Verification

- Frontend full: `npm.cmd test -- --run --cache=false` passed `97/97`.
- Frontend bundle gate: `npm.cmd run test:bundle` passed; largest JS chunk `268562` bytes.
- Frontend build: `npm.cmd run build` passed with no chunk-size warning.
- Backend full: `python -B -m unittest discover -s backend\tests` passed `150`, skipped `3`.
- Browser Shock/Matching: official route shock run shows ready recovery playbook, 3 supplier cards, guardrail copy; desktop/mobile have no console errors or horizontal overflow.
- Browser rehearsal page: desktop/mobile render 5 steps, official/buyer links, guardrail copy; no console errors or horizontal overflow.
- Browser smoke: Overview and Audit lazy routes render; Audit shows `2` models, `4` rulesets, `manifest sha256`; desktop/mobile have no console errors or horizontal overflow.
- Runtime API: `demo_operator` reads registry as `demo-user`, not hidden admin impersonation.
- Browser Intake: `2027-05` completed with `approved`, 1 financial, 1 product, 1 evidence.

## Hard Boundaries

- Do not claim: pilot/production ready, credit score/default probability, bank approval, verified supplier, invoice authenticity, legal breach/fraud, or confirmed double financing.
- Proven: deterministic seeded demo behavior plus local/static trust gates.
- Unproven: real OIDC/JWKS, S3/MinIO, ClamAV, live PostgreSQL RLS, tamper-proof/WORM audit, production graph confidentiality, real finance automation.

## Next Best Work

- Keep the competition story at 3-5 minutes; do not dilute it.
- Polish Supply Map/Risk around disrupted supplier `BIZ-005`; Matching now has recovery playbook but supplier cards can still be visually sharpened.
- Make Shock more cinematic with staged route propagation/map emphasis if time remains.
- Preserve role, period, consent, privacy, and human-review gates.

## QA/Subagents

- QA charter: test as real stakeholders; flag token waste, unsupported legal/finance claims, broken role flows, and UI-only features without backend policy/data paths.
- Recent attempted agents `Descartes` and `Hume` hit usage limits.
- Prior QA names: `Heisenberg`, `Ampere`, `Zeno`, `Peirce`, `Lovelace`, `Hegel`, `Confucius`, `Locke`, `Popper`, `Herschel`, `Raman`, `Poincare`, `Galileo`.
