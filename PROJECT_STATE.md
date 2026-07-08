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

- Fixed Data Intake review synchronization: submit now reloads the reviewer queue.
- Added fail-closed review CTA state in `frontend/src/utils/intakeReviewDecision.ts`.
- Review decisions stay disabled until the exact queue task is hydrated; approval also obeys the evidence gate.
- Removed self-declared inline evidence from manual submission payloads via `frontend/src/utils/intakeSubmissionSections.ts`.
- Evidence now follows the trustworthy demo path: upload ticket -> checksum/object record -> malware scan -> Vault/snapshot provenance.
- Browser-tested a fresh `2027-05` flow: demo upload/scan -> draft -> validate -> submit -> approve -> canonical snapshot v1.

## Verification

- Frontend full: `npm.cmd exec vitest -- run --cache=false` passed `83/83`.
- Frontend build: `npm.cmd run build`; latest bundle `499.90 kB` minified, below the previous warning threshold.
- Backend full: `python -B -m unittest discover -s backend\tests` passed `146`, skipped `2`.
- Browser: `2027-05` completed with `approved`, 1 financial, 1 product, 1 evidence; no console errors or horizontal overflow.
- Regression tests: `intakeReviewDecision.test.ts`, `intakeSubmissionSections.test.ts`.

## Hard Boundaries

- Do not claim: pilot/production ready, credit score/default probability, bank approval, verified supplier, invoice authenticity, legal breach/fraud, or confirmed double financing.
- Proven: deterministic seeded demo behavior plus local/static trust gates.
- Unproven: real OIDC/JWKS, S3/MinIO, ClamAV, live PostgreSQL RLS, tamper-proof/WORM audit, production graph confidentiality, real finance automation.

## Next Best Work

- Keep the competition story at 3-5 minutes; do not dilute it.
- Add a lightweight rendered browser rehearsal for the official runbook.
- Polish Supply Map/Risk/Matching around disrupted supplier `BIZ-005`.
- Make Shock the signature moment with staged route propagation and recovery visuals.
- Seed/show deterministic model/ruleset provenance in Audit.
- Preserve role, period, consent, privacy, and human-review gates.

## QA/Subagents

- QA charter: test as real stakeholders; flag token waste, unsupported legal/finance claims, broken role flows, and UI-only features without backend policy/data paths.
- Recent attempted agents `Descartes` and `Hume` hit usage limits.
- Prior QA names: `Heisenberg`, `Ampere`, `Zeno`, `Peirce`, `Lovelace`, `Hegel`, `Confucius`, `Locke`, `Popper`, `Herschel`, `Raman`, `Poincare`, `Galileo`.
