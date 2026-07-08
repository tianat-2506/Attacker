# Pitch Demo Script

Use `docs/21-competition-demo-runbook.md` as the operational click-path. This file keeps the spoken story short enough for a 3-5 minute pitch.

## 1. One-Liner

VietSupply Radar is a B2B supply-chain risk cockpit for Vietnamese SMEs. It turns periodic business input, evidence documents and supply relationships into an explainable disruption warning, shock simulation and human-reviewed supplier shortlist.

## 2. Five-Minute Script

### 0:00-0:45 - Data Intake

Open the official URL with `account=demo-operator`. From the overview checklist, open `Data Intake`.

Say:

"The system starts from monthly SME input, not from a magic dashboard. A business can enter financials and products by form, import CSV, upload supporting evidence, then pass validation and review before an approved snapshot is used downstream."

Point to:

- Input lineage rail: raw input, staging validation, human review and approved snapshot.
- Demo proof checklist: draft package, CSV proof, evidence gate and source-linked snapshot.
- Selected organization and reporting month.
- Form + CSV import.
- Evidence upload ticket and scan/review gate.
- Approved snapshot section.

### 0:45-1:45 - Supply Map + Risk

Return to Overview and open the Dai Tin/Binh Duong risk case.

Say:

"Dai Tin Distribution is a beverage distributor in Binh Duong. The system flags an early warning signal from cash-flow trend, late payment, delivery delay and downstream dependency. This is not a credit score, default probability or legal breach finding. It is an operational warning for human review."

Point to:

- Masked-by-default supply graph.
- Downstream SME dependency.
- Risk explanation and rule trace.
- Policy-gated evidence chain.

### 1:45-2:30 - Shock Simulation

Click `Simulate Supply Shock`.

Say:

"When this node is disrupted, the impact propagates through the directed supply graph. The demo shows exposed units, revenue at risk, stockout window and affected downstream SMEs."

Point to:

- Shock sequence: baseline, disruption and recovery.
- Shock banner.
- Impact metrics.
- Affected routes/nodes.

### 2:30-3:30 - Recovery Matching

Open `Recovery Matching`.

Say:

"The system now suggests a recovery shortlist. Matching is based on product fit, capacity, logistics, reliability, payment terms and financial health. It does not auto-replace a supplier. Contact and commercial action still require consent and human approval."

Point to:

- Top recommendation.
- Match drivers.
- Consent-gated introduction action.

### 3:30-5:00 - Consent, Audit And Business Model

Open `Audit Trail`.

Say:

"Every sensitive action needs role, purpose, consent or review, and an audit record. The MVP uses synthetic data to prove the workflow. A real pilot would connect anchor distributor, POS/accounting/e-invoice and logistics data under consent and audit. Business model: SaaS for risk operations, success fee for qualified matching, and referral workflow with finance partners, while lenders still do their own KYB/KYC and underwriting."

Point to:

- Connection/request queue.
- Policy/audit IDs.
- Access governance.
- Enforced boundaries.

## 3. Seven-Minute Additions

- 30 seconds: trust gaps and controls: masking, consent, RBAC, audit, evidence provenance.
- 45 seconds: architecture: React/Leaflet, FastAPI modular monolith, SQLite demo, PostgreSQL/PostGIS/RLS pilot path.
- 45 seconds: validation: backend tests for intake, risk, matching, shock, evidence gates and audit boundaries.
- 30 seconds: invoice workflow: hash/claim registry simulation for double-financing risk, not proof of invoice authenticity.

## 4. Demo Click Path

1. Open the official URL from `docs/21-competition-demo-runbook.md`.
2. Confirm account is `Demo operator`.
3. Open `Data Intake`; show monthly input, lineage, proof checklist, CSV, evidence gate and snapshot area.
4. Return to Overview; open `Supply Map + Risk` for Dai Tin Distribution.
5. Show risk panel, policy-gated evidence and downstream dependency count.
6. Click `Simulate Supply Shock`.
7. Read KPI impact and point to affected routes/nodes.
8. Open `Recovery Matching`; show top recommendation and consent-gated introduction.
9. Open `Audit Trail`; show policy/audit trace and enforced boundaries.
10. Close with business model and pilot path.

## 5. Q&A

| Question | Answer |
| --- | --- |
| Where does real data come from? | The MVP uses deterministic synthetic data. A pilot would start with one anchor distributor/manufacturer and collect POS/accounting/e-invoice/logistics data with consent. |
| Is this AI trained on real outcomes? | No overclaim. The MVP uses transparent rule-based scoring plus explanations. Real outcome data would be backtested before any ML upgrade. |
| What if a signal is wrong? | It is an advisory early warning with explanation, threshold, human review and feedback loop, not an automatic decision. |
| Are alternative suppliers guaranteed? | No. Matching is a decision-support shortlist. Supplier qualification, sample approval, consent and commercial review are still required. |
| Is blockchain required? | No. The invoice hash/claim workflow is only an optional simulation for double-financing risk; it is not the center of the pitch. |
| How do you prevent supplier data leakage? | Graph data is masked by default. Unmasking requires role, relationship, purpose, consent/policy and audit. |
| How do you solve cold start? | Start with one narrow industry, one region and an anchor company, then expand with consented pilot data. |
| How is this different from a B2B marketplace? | Marketplaces focus on buying and selling. VietSupply Radar focuses on risk sensing, dependency impact and explainable recovery shortlist. |
| Is this pilot-ready today? | No. The demo is competition-ready. Real pilot claims require live OIDC, PostgreSQL/RLS, object storage, malware scan and legal/data governance gates. |

## 6. Slide Deck Outline

1. Title: VietSupply Radar.
2. Problem: SME dependency and disruption.
3. Insight: source, cash flow and trust data are connected.
4. Solution: intake -> supply graph -> risk signal -> shock -> matching -> audit.
5. Demo story: one Binh Duong distributor disruption.
6. Algorithm: risk signal and match score.
7. Data and governance: synthetic MVP, consent, masking and audit.
8. Business model.
9. Roadmap and pilot gates.
10. Ask: pilot partners, data access, mentorship/funding.
