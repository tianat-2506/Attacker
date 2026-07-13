# Project State

- Updated: `2026-07-13`.
- Repository: `https://github.com/tianat-2506/Attacker`.
- Canonical handoff branch: `main`.
- Handoff baseline: `c2b0391` (`Document risk-to-shock demo handoff`).
- Working tree was clean and synchronized with `origin/main` before this handoff edit.
- Product: VietSupply Radar, a synthetic competition demo evolving toward a trust-first supply-chain platform for Vietnamese SMEs.
- Active objective: finish a polished 3-5 minute competition demo; do not claim pilot or production readiness.
- User language: Vietnamese.

## Start Here

- Run `git pull --ff-only origin main` before making changes.
- Read `docs/21-competition-demo-runbook.md` for the official story and `docs/17-run-project-after-restart.md` for setup.
- Open the official route: `http://127.0.0.1:5173/?view=overview&account=demo-operator&business=BIZ-005&period=2026-07`.
- Use `README.md` for architecture, commands and trust-readiness boundaries.
- Use `docs/19-multi-account-collaboration-protocol.md` and `docs/20-session-handoff-and-workload-map.md` when another agent/account is active.

## Current Demo

- Official story: Data Intake proof -> Supply Map/Risk -> staged Shock -> Recovery Matching -> Consent/Audit.
- Data Intake already demonstrates raw/staging/review/approved lineage and evidence scan gating.
- Risk-to-Shock bridge is period- and provenance-aware, separates observed advisory signals from hypothetical scenarios, and enforces distinct graph-read/simulation capabilities.
- Shock is a 2.2-second four-phase sequence: `origin -> propagation -> impact -> recovery`; reset and reduced-motion behavior are covered.
- Recovery playbook exposes coverage, primary/alternate routes, recoverable/residual volume, lead time and a human-review guardrail.
- Role-gated workspaces and demo stakeholder accounts already exist; recover exact roles, endpoints and component ownership from source.
- SQLite remains the deterministic demo adapter. PostgreSQL/PostGIS/RLS, OIDC, object storage and malware scanning are architecture/readiness artifacts, not proven live controls.

## Next Slice

- Highest-value task: sharpen Matching supplier-card hierarchy and make the consent/review workflow legible without lengthening the official story.
- Proposed design is not yet approved or committed.
- Proposed hierarchy: one featured candidate plus compact alternatives.
- Proposed states: `shortlisted -> consent requested -> supplier consented -> reviewer activation -> relationship active`.
- Buyer may request an introduction only; supplier consent and reviewer activation remain in the correct role workspace.
- Matching should reload persisted connection requests, show the current request state, next actor, `policy_decision_id` and `audit_event_id`, and keep errors stable and visible.
- Likely touchpoints: `frontend/src/components/WorkspaceViews.tsx`, `frontend/src/App.tsx`, `frontend/src/utils/connectionRequests.ts`, access-decision utilities and their tests.
- Before implementation, get product-design approval, write the design under `docs/superpowers/specs/`, then write the implementation plan under `docs/superpowers/plans/`.
- Acceptance: clear featured/alternative hierarchy; correct buyer/supplier/reviewer permissions; state survives reload; no automatic replacement implication; no desktop/mobile overflow; official route still fits 3-5 minutes.

## Verified Baseline

- Frontend tests: `120/120` passed.
- Backend tests: `151` passed, `3` skipped.
- Frontend build and bundle gate passed; largest JavaScript chunk was `273388` bytes.
- Browser checks passed for official Risk-to-Shock path, scoped supplier denial, staged reset/reduced motion, Matching recovery playbook, rehearsal page and desktop/mobile overflow.
- These results belong to baseline `c2b0391`; rerun affected checks after any change.

## Non-Negotiable Boundaries

- Never claim credit score, default probability, bank approval, verified supplier, verified invoice authenticity, legal breach/fraud, confirmed double financing, pilot-ready or production-ready.
- Keep outputs advisory, consent-gated and subject to human review.
- Do not expose commercial graph, finance or evidence data by default.
- Do not silently fall back across organizations or reporting periods.
- Preserve policy/audit provenance and explicit synthetic/demo labeling.
- Never force-push, broadly rewrite or revert unrelated changes.

## Handoff Discipline

- Take one narrow slice; avoid files owned by another active agent.
- Test proportionally, update this file with only unrecoverable state, commit intentionally and push before ending the session.
- Do not copy architecture, endpoint inventories or run instructions into this file; reference their canonical documents instead.
- If work stops mid-slice, record changed files, failing command/output, unresolved decision and the exact next command here.
