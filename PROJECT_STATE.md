# Project State

- Workspace: `D:\attacker`.
- Product: VietSupply Radar, supply-chain/SME finance-ready demo converging toward trust-first backend/data/security platform.
- User language: Vietnamese.
- Active goal: keep implementing toward complete web app; do not claim pilot/production readiness.
- Current dev servers:
  - Frontend: `http://127.0.0.1:5173`, listener PID `652`.
  - Backend SQLite demo: `http://127.0.0.1:8000`, uvicorn PID `14664`.

## Source Pointers

- Run docs: `README.md`, `docs/17-run-project-after-restart.md`.
- Multi-account workflow: `docs/19-multi-account-collaboration-protocol.md`, `docs/20-session-handoff-and-workload-map.md`.
- Source inputs: `Prompt_Codex_VietSupply_Radar.pdf`, `Noi_dung_hoi_thoai_du_an_VietSupply_Radar.pdf`, `deep-research-report.md`.
- Diagrams: `docs/16-current-demo-diagrams.md`, `docs/diagrams/*.drawio`.
- Tech assessment: `docs/18-deep-research-technical-assessment.md`.
- PostgreSQL trust boundary: `backend/migrations/versions/0001_trust_foundation_postgres.sql`, `backend/app/services/postgres_pilot_service.py`.

## Latest Slice

- Dynamic disrupted-supplier recommendations slice completed.
- Frontend `getRecommendations` now accepts `disruptedSupplierId` and sends it as `disrupted_supplier_id`.
- App loads recommendation shortlist in a dedicated effect keyed by buyer, selected business and period, instead of during full app load.
- Matching header selected disrupted supplier and backend recommendation request now stay aligned when the selected business changes.
- Demo shock simulation still explicitly uses `BIZ-005`, matching the seeded shock scenario.
- Matching component masking slice completed.
- Matching cards now hide commercial/financial/reliability/payment-term component scores when supplier access is `masked` or `pending_consent`.
- Masked recommendation cards still show low-sensitivity product/distance fit and a restricted-metrics count.
- Matching header wording changed from `Qualified candidates only` to `Review-gated shortlist`.
- Added helper tests for recommendation component visibility by access status.
- Risk UI evidence-scope display completed.
- Frontend `RiskSignal` now carries `evidenceScope`, `policyDecisionId`, and `auditEventId` from `/risk-signal`.
- Risk workspace now labels blocked-evidence responses as `High-level advisory`, not evidence-based analysis.
- Empty evidence panel now says linked evidence is blocked by policy when `evidence_scope="evidence_blocked_by_policy"`.
- Risk workspace shows policy/audit/scope correlation when backend provides it.
- Frontend high-level risk scope alignment completed.
- `canRequestRiskSignal` now separates masked high-level risk preview from sensitive company/evidence visibility.
- App risk loading now uses the selected business access decision, so masked relationship risk can call the backend high-level risk path without opening evidence or finance.
- Backend high-level risk test now covers buyer `BIZ-009` reading related supplier `BIZ-005` without evidence access.
- Risk signal trust-boundary slice completed.
- Backend `risk_signal_payload` now authorizes `read_risk_run` separately from `read_evidence`.
- If an actor can read risk but cannot read linked evidence, backend returns a high-level advisory signal with `evidence_scope="evidence_blocked_by_policy"` and no evidence documents.
- Full evidence-backed risk signal remains available only when evidence policy passes; all risk reads now write `RISK_SIGNAL_VIEWED` with policy/audit ids.
- Frontend Risk workspace now shows a policy-gated locked state when the selected business is outside account scope, instead of indefinite loading.
- Frontend data permissions now track `canReadRiskRun` separately from evidence/finance permissions.
- Dashboard alert subject routing completed.
- Backend dashboard alerts now carry `business_id` for the affected demo business.
- Frontend maps dashboard alert `business_id` to `businessId`; fallback alerts carry the same subject ids.
- Clicking a specific Overview alert now selects that business before opening Risk; generic `Review risk` keeps the current selected business.
- Overview simulation subject guardrail completed.
- Simulation strip now derives the disrupted supplier label from `shock.shockNodeId` instead of hardcoded `Dai Tin disruption`.
- Matching workspace stakeholder subject guardrail completed.
- Matching header now displays dynamic buyer and disrupted supplier names from active account/default business and selected business.
- Matching no longer hardcodes `Thu Duc Retail Mart` / `Dai Tin Distribution` in the workspace header; scenario text elsewhere remains intentional demo copy.
- Risk workspace stakeholder subject guardrail completed.
- Risk view now displays the selected business name instead of hardcoded `Dai Tin Distribution`.
- Risk evidence chain now shows an explicit empty state when no evidence is visible for the current account/business/period scope.
- Risk evidence facts now fallback safely when a document has no visible facts.
- Session handoff/workload map documented for multi-account continuation.
- New accounts should use `docs/20-session-handoff-and-workload-map.md` for the startup prompt, recommended parallel tracks, high-conflict files, and end-of-session state template.
- Multi-account GitHub collaboration protocol documented.
- Rule now persisted: every account/session pulls latest GitHub state first, updates `PROJECT_STATE.md` before context runs low, commits, and pushes back to GitHub before ending.
- Parallel work should use task branches or clearly separated file ownership; no force push or wholesale state rewrite.
- Frontend mutation handler permission guardrail completed.
- App handlers now return before sending API mutations when the active account lacks permission for:
  - supply-map registration create/review.
  - intake draft create/save/validate/submit, review decision and review queue selection.
  - CSV import, evidence upload and demo evidence scan.
- Evidence file ticket view now checks evidence read permission and selected-business scope before issuing a download ticket.
- Search result navigation now uses guarded `openView("companies")` instead of raw `setActiveView("companies")`.
- Role-aware workspace shortcut guardrail completed.
- Overview CTA buttons now disable `Review risk` / recovery matching actions when the active account lacks the target view.
- Risk view no longer calls raw `setActiveView("matching")`; it uses the guarded `openView("matching")` path and disables the action for accounts without Matching access.
- Disabled shortcut styles were added for text, alert and recovery CTA buttons.
- Intake evidence snapshot status guardrail completed.
- Data Intake evidence requirements now read snapshot row status from `verification_status`, `status`, or `malware_scan_status`; missing status becomes `pending_scan`, not review-cleared.
- Clean approved snapshot evidence still counts as scan-cleared through `malware_scan_status=clean`.
- Evidence gate wording now says `scan-cleared/review-cleared` and uses ASCII separators to avoid mojibake.
- Period no-data UI guardrails completed for Finance and Matching.
- Finance UI now marks `health.level=no_period_data` as no exact selected-month row:
  - badge shows `-` / `no data`, not a score-like health level.
  - KPI note says no exact row for the selected month.
  - historical rows remain visible only as trend/context, not fallback current snapshot.
- Matching UI now has an explicit empty state when no shortlist exists for the selected period.
- Matching cards display the recommendation period returned by the API, falling back to selected period only for display.
- Period-aware matching/recommendations completed for SQLite demo adapter.
- Supplier recommendation API now accepts `period_key=YYYY-MM`, returns `period_key` on each recommendation, and audits the selected period.
- Frontend now sends selected period to `POST /api/v1/recommendations/suppliers`.
- Matching UI displays the selected period and uses the API advisory notice for the shortlist guardrail.
- Previous period-aware read slice remains in place:
  - Companies/Evidence/Risk/Finance reads receive the selected monthly period.
  - Finance does not silently fallback when the selected month has no exact financial row.
  - Evidence/Risk filter documents by validity window or upload `period_key`.
- Frontend now sends selected `period=YYYY-MM` to:
  - `GET /api/v1/businesses/{id}`
  - `GET /api/v1/businesses/{id}/evidence`
  - `GET /api/v1/businesses/{id}/risk-signal`
  - `GET /api/v1/businesses/{id}/finance`
- Backend accepts `period` on those routes and returns `meta.period_key`.
- Finance does not silently fallback: if selected month has no exact financial row, `latest=null` and `health.level=no_period_data`.
- Evidence/Risk filter documents by validity window or upload `period_key`; documents effective after the selected period are excluded.
- Previous URL slice remains in place:
  - query params support `account`, `business`, `period`, `view`.
  - backend-auth default view does not overwrite a valid URL-selected view.
- Previous connection-filter slice remains in place:
  - Onboarding connection inbox shows visible/open/action-needed counts and filtered request history.
  - Audit human approval queue has the same status filters and shows perspective/audit metadata.
- Previous wording slice remains in place:
  - Evidence/Vault scan-clean/reviewed labels avoid legal authenticity claims.
  - Invoice funding state displays lender/registry wording, not VietSupply approval.
- `evidenceStatusLabel` now displays:
  - `clean`/malware clean as `scan-cleared`.
  - approved use as `review-cleared`.
  - legacy `VERIFIED` as `reviewed`.
- Vault filters, pills, download actions, upload tickets, intake requirements, reviewer queue and evidence gate no longer display `verified file/document` claims.
- Frontend and backend dashboard alerts no longer claim verified purchase orders or verified suppliers.
- Invoice funding state now displays lender/registry wording:
  - `financed`/`funded` -> `lender-recorded financed`.
  - `pledged` -> `lender-recorded pledge`.
  - `unfunded` -> `no lender funding recorded`.
- Invoice claim advisory in SQLite and Postgres pilot services says registry does not approve financing; lender/human decision remains required.
- Backend evidence status semantics were not renamed; display layer changed only to preserve compatibility.
- Previous access-control slice remains in place: finance/invoice scope payloads, buyer-party invoice access, lender consent denial, and financier-org guard.

## Current Posture

- FastAPI modular monolith; SQLite is demo adapter only.
- PostgreSQL/PostGIS/RLS migration and pilot adapter exist, but live RLS smoke has not run.
- Demo auth uses headers; `/auth/me` exposes backend capability matrix and workspace access/default view.
- Stakeholder demo accounts include SME submitter, buyer admin, supplier admins `BIZ-005` and `BIZ-007`, reviewer, lender, network analyst, demo operator, system admin.
- Monthly Data Intake supports draft/validate/submit/review/approve, CSV import, error report, period snapshot, evidence upload tickets, scan job and Vault download ticket for clean uploaded evidence.
- Global workspace state is URL-backed for account, selected business, active view and monthly period.
- Companies/Evidence/Risk/Finance/Matching reads now receive the selected monthly period; SQLite demo filtering is explicit and conservative.
- Supply-map onboarding is policy-gated; approved registration creates demo graph node only, not a verified supplier or commercial relationship.
- Supply relationship activation requires supplier consent plus `contract_evidence_id`; activation creates zero-volume demo edge until real contract/intake data exists.
- Supplier-facing connection inbox exists in Onboarding; request list is scoped by buyer/target supplier/reviewer/operator, network analyst is denied, and UI supports status/action filters.
- Trust gates remain demo/static/local unless real OIDC, object storage, ClamAV and PostgreSQL RLS live checks are configured.

## Verification

- Backend full: `python -B -m unittest discover -s backend\tests` passed, 130 tests, 2 skipped.
- Frontend typecheck: `npm.cmd exec tsc -- --noEmit` passed.
- Frontend tests: `npm.cmd exec vitest -- run --cache=false` passed, 34 tests.
- Build: `npm.cmd exec vite -- build --outDir .vite-check-dist` passed; temp output removed.
- Latest targeted frontend proof:
  - `npm.cmd exec tsc -- --noEmit` passed.
  - `npm.cmd exec vitest -- run src\api\client.test.ts --cache=false` passed, 11 tests.
  - `npm.cmd exec vitest -- run --cache=false` passed, 34 tests.
  - `npm.cmd exec vite -- build --outDir .vite-check-dist` passed; temp output removed.
  - Recommendation API client test confirms selected `disrupted_supplier_id` is sent in the request body.
  - Recommendation helper test confirms masked cards expose product/distance only and count restricted metrics.
  - Risk API client test confirms `evidence_scope`, `policy_decision_id`, and `audit_event_id` map into `RiskSignal`.
  - `canRequestRiskSignal` test confirms masked high-level risk can be requested without enabling sensitive company/vault visibility.
  - Dashboard alert mapper test confirms `recent_alerts[].business_id` becomes `recentAlerts[].businessId`.
- Latest targeted backend proof:
  - `python -B -m unittest backend.tests.test_trust_foundation.TrustFoundationTests.test_risk_signal_can_be_high_level_without_evidence_access` passed.
  - `python -B -m unittest discover -s backend\tests` passed, 130 tests, 2 skipped.
  - `python -B -m unittest backend.tests.test_database_service.DatabaseServiceTests.test_recommendations_are_shortlist_not_disrupted_supplier` passed.
  - `python -B -m unittest backend.tests.test_trust_foundation.TrustFoundationTests.test_selected_period_context_does_not_silently_fallback_for_finance_or_evidence` passed.
- Live connection inbox smoke request `REQ-6BF5994C8C52`:
  - buyer seen `true`.
  - supplier `BIZ-007` seen `true`.
  - unrelated supplier `BIZ-005` seen `false`.
  - reviewer seen `true`.
  - network analyst denied `true`.
  - supplier consented; reviewer activated; graph has edge `EDGE-REQ-6BF5994C8C52`.
- Live finance/invoice scope smoke:
  - lender `BIZ-062` reading `INV-0242` without invoice consent denied `true`.
  - buyer `BIZ-009` reads `INV-0242` with `access_scope="buyer_party"`.
  - invoice claim with mismatched `financier_id=BIZ-999` denied `true`.
- Local ops smoke: `python -B scripts\run_local_operational_smoke.py --json` passed, `pilot_ready=false`.
- Trust readiness gate: `python -B scripts\run_trust_readiness_gate.py --allow-missing-live --json` passed, `pilot_ready=false`.
- Missing live proof: real OIDC/JWKS signed token, S3/MinIO object storage, ClamAV, PostgreSQL/PostGIS RLS.
- No browser visual proof captured for the latest period-aware read slice.

## QA/Subagents

- Latest attempted QA subagent: `Descartes`, errored due usage limit; main agent completed Finance/Matching no-data QA locally.
- Latest attempted QA subagent: `Hume`, errored due usage limit; main agent completed evidence wording QA locally.
- Previous QA subagent: `Heisenberg`, closed.
- Heisenberg findings fixed in recent slices:
  - Lender Finance/Invoice UI implied access before concrete consent.
  - Invoice claim could accept arbitrary `financier_id`.
  - Invoice wording overclaimed verification/satisfied evidence.
- Previous QA subagent before Heisenberg: `Ampere`.
- Ampere findings fixed:
  - Onboarding lacked supplier/reviewer connection inbox and status/history filters.
  - Audit queue must not be used as scoped supplier inbox.
  - Action UI needed stakeholder-specific visibility.
  - Inbox state would go stale after create/decision.
  - Demo lacked supplier persona for target `BIZ-007`.
- Previous QA names to recall if useful: `Zeno`, `Peirce`, `Lovelace`, `Hegel`, `Confucius`, `Locke`, `Popper`, `Herschel`, `Raman`, `Poincare`, `Galileo`.
- Standing QA charter: act as real stakeholder users; penalize token waste, unsupported legal/finance claims, broken role workflows, and UI-only features without backend permission/data path.

## Hard Boundaries

- Do not claim: pilot-ready, production-ready, credit score, default probability, bank approval, verified supplier, invoice authenticity, legal breach, fraud, confirmed double financing.
- Strong guarantee now: deterministic SQLite demo behavior over seeded fixtures plus local/static trust gates.
- Not guaranteed: live PostgreSQL RLS, real OIDC, real object storage, malware scanning service, WORM/tamper-proof audit, production graph confidentiality, real finance automation.

## Next Best Work

- Continue functional completion over polish:
  - per-account RBAC across one supply chain.
  - each org owns separate data.
  - Vault shows scan-cleared/reviewed documents without legal authenticity claims.
  - Intake uploads supporting evidence/guarantee documents.
  - onboarding, map, matching, finance and audit obey role permissions.
- Configure real/disposable OIDC issuer token, S3/MinIO, ClamAV and PostgreSQL/PostGIS, then run live readiness gate before pilot claims.
