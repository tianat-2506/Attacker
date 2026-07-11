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

- Added a policy-safe Risk-to-Shock bridge for the official `BIZ-005` competition path.
- Risk now separates an observed advisory signal from a hypothetical scenario, hides seeded/stale values, and requires selected-period plus run/ruleset/model/source provenance; non-fallback results also require policy and audit IDs.
- Backend shock execution now has a dedicated capability and audited denial path. Graph read and simulation permission are separate.
- Risk hands the presenter into the staged Overview cinematic; Matching stays independent and recovery recommendations load without blocking the Shock result.
- Overview, Map and Matching ignore Shock results from another period; Overview Run controls reflect account capability.
- Added a four-phase Shock cinematic: `origin -> propagation -> impact -> recovery` in 2.2 seconds.
- Overview now gates impact/recovery facts by phase; reset cancels pending transitions and reduced-motion resolves immediately.
- Supply Map auto-focuses the affected subnetwork, pulses the disrupted/affected nodes, staggers impacted routes, and labels each phase.
- Added pure phase/scheduler/map-key tests plus finite SVG animation to avoid continuous compositor load.
- Added Shock/Matching recovery playbook for the competition demo.
- Overview now shows recovery coverage, primary route, alternate route count, recoverable/residual volume, lead time, and guardrail after shock.
- Matching now shows a wide "Shock recovery plan" panel above supplier cards.
- `demo-operator` recovery matching now uses affected buyer `BIZ-009` when present, not disrupted supplier `BIZ-005`.
- New tests cover recovery playbook math/guardrails and demo recovery buyer selection.
- Prior slice added rendered rehearsal page at `http://127.0.0.1:5173/demo-rehearsal.html`.
- Prior slice added route-level workspace code splitting and `npm.cmd run test:bundle`.
- Prior slice seeded analytics provenance in Audit: 2 model entries, 4 rulesets, manifest SHA-256 prefix, creator, active status.
- Prior slice completed Data Intake upload/scan -> draft -> validate -> submit -> approve -> canonical snapshot.

## Verification

- Frontend full: `npm.cmd test -- --run --cache=false` passed `120/120`.
- Frontend bundle gate: `npm.cmd run test:bundle` passed; largest JS chunk `273388` bytes.
- Frontend build: `npm.cmd run build` passed with no chunk-size warning.
- Backend full: `python -B -m unittest discover -s backend\tests` passed `151`, skipped `3`.
- Browser Risk-to-Shock: official Risk bridge starts `ready`, routes to Overview, and reaches guarded recovery with `92%` coverage, `3` alternate routes and no horizontal overflow.
- Browser role boundary: `supplier-admin` Risk bridge is `unavailable`; scenario CTA is disabled with graph-access explanation.
- Browser responsive/reset: desktop 1280x720 and mobile 390x844 have no horizontal overflow; mobile phase overlays do not overlap; reset remains baseline after 2.5 seconds; no console errors/warnings.
- Browser Matching: official route shows ready recovery playbook, 3 supplier cards and guardrail copy.
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
- Sharpen Matching supplier-card hierarchy and consent/review actions, then rehearse the complete official route once more.
- Keep Data Intake, policy/audit provenance and explicit synthetic fallback visible enough for judges without extending the 3-5 minute story.
- Preserve role, period, consent, privacy, and human-review gates.

## QA/Subagents

- QA charter: test as real stakeholders; flag token waste, unsupported legal/finance claims, broken role flows, and UI-only features without backend policy/data paths.
- Recent attempted agents `Descartes` and `Hume` hit usage limits.
- Prior QA names: `Dirac`, `Heisenberg`, `Ampere`, `Zeno`, `Peirce`, `Lovelace`, `Hegel`, `Confucius`, `Locke`, `Popper`, `Herschel`, `Raman`, `Poincare`, `Galileo`.
