# Competition Demo Runbook

Use this file as the single source for the 3-5 minute competition demo. Keep it aligned with `frontend/src/utils/demoStory.ts`.

## Official Setup

- Backend: `http://127.0.0.1:8000`.
- Frontend: `http://127.0.0.1:5173`.
- Rendered rehearsal page: `http://127.0.0.1:5173/demo-rehearsal.html`.
- Official URL: `http://127.0.0.1:5173/?view=overview&account=demo-operator&business=BIZ-005&period=2026-07`.
- Main persona: `demo-operator`.
- Buyer rehearsal URL: `http://127.0.0.1:5173/?view=overview&account=buyer-admin&business=BIZ-005&period=2026-07`.
- Buyer persona is intentionally scoped: Data Intake and Audit may be blocked to prove RBAC.

## 3-5 Minute Flow

1. `0:00` Data Intake
   - Open `Data Intake` from the overview checklist.
   - Show the input lineage rail: raw input, staging validation, human review, approved snapshot.
   - Show the demo proof checklist and next-action pills: draft package, CSV proof, evidence gate, approved snapshot.
   - Show selected organization and month, form input, CSV import, `Use demo file`, evidence upload ticket, evidence scan gate and approved snapshot area.
   - Say: "The risk map is not magic. It starts from monthly SME input, evidence documents and a review gate before any approved snapshot is used."

2. `0:45` Supply Map + Risk
   - Return to Overview and open the Dai Tin/Binh Duong risk case.
   - Show masked-by-default graph, policy-gated evidence chain and deterministic rule trace.
   - Say: "This is an early warning signal for supply continuity, not a credit score or legal conclusion."

3. `1:45` Shock Simulation
   - Click `Run` / `Simulate Supply Shock`.
   - Read the shock sequence: baseline graph, live disruption, recovery shortlist.
   - Read the impact panel: exposed units, revenue at risk, stockout window and downstream SMEs.
   - Say: "The system turns one supplier disruption into a visible operational exposure."

4. `2:30` Recovery Matching
   - Open `Recovery Matching`.
   - Show top alternative suppliers, period label, fit drivers and consent-gated contact/introduction.
   - Say: "This is a decision-support shortlist. It does not auto-replace suppliers."

5. `3:30` Consent + Audit
   - Open `Audit Trail`.
   - Show request queue, policy/audit IDs, access governance and enforced boundaries.
   - Say: "Every sensitive action needs role, purpose, consent or review, and an audit record."

## Do Not Say

- Do not say credit score, default probability, bank-approved, loan eligible or financing approved.
- Do not say verified supplier, invoice authenticity verified, fraud confirmed or legal breach.
- Do not say production-ready or pilot-ready unless live OIDC, PostgreSQL/RLS, object storage and malware scan gates have been proven.

## Fast Recovery

- If the app opens with a local synthetic permissions banner, frame it as demo boundary: the dataset is synthetic and role policy is simulated for competition.
- If backend is down, start it using `docs/17-run-project-after-restart.md`; do not present fallback mode as real backend authorization.
- If a scoped persona shows blocked steps, switch back to `demo-operator` for the official full path.
