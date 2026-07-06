# Deep Technical Analysis of the MultimodalText Supply Chain Risk Platform

## Product frame and what should be built first

This project is best understood not as a generic B2B marketplace, but as a **supply-chain continuity and trust orchestration platform**. The core problem in the prompt is very specific: ingest enterprise accounting, debt, revenue, inventory, import/export, POS, logistics, and supporting documents; detect operational and cash-flow distress early; estimate the risk of supply disruption; and then propose **sector-aware recovery actions** without exposing sensitive commercial relationships. The uploaded concept also requires immutable evidence handling, digital order workflows, post-receipt discrepancy notes, invoice and contract uploads, and a strong confidentiality model that prevents one enterprise from trivially discovering another enterprise’s supplier network. The current repository already narrows the MVP into a Southern Vietnam, F&B/FMCG-focused cockpit with explainable risk signals, supplier shortlisting, evidence review, audit trail, and invoice verification. fileciteturn0file0 fileciteturn0file1

In practical terms, the “engine room” you need now is a **decision-support core**, not more presentational UI. The screenshots and README already define the main application workspaces: Overview, Supply Map, Companies & Evidence, Risk Analysis, Matching, Finance, Invoice Verification, and Audit Trail. The attached visuals on pages two and three of the prompt, along with the current app screenshots, show that the information architecture is already coherent: a geospatial network view, business profile and evidence vault, supplier shortlist, finance health dashboard, invoice verification panel, and append-only audit log are all present. That means the next phase should focus on backend services, domain models, ingestion, scoring, permissions, and evidence governance rather than redesigning the shell. fileciteturn0file0 fileciteturn0file1

![Current overview and supply network shell](sandbox:/mnt/data/image%2817%29.png)

The current MVP definition in the README is also a strong constraint that should be preserved. It already specifies a React cockpit frontend, a FastAPI backend, SQLite seeded from deterministic CSV data, explicit domain/repository/service classes, a 10-node Binh Duong disruption case, 62 seeded businesses, and explainable rule-based matching and risk formulas. That is a good architectural baseline because it gives you a **modular monolith** that is simple enough to ship quickly while still leaving room for later migration to PostgreSQL/PostGIS and a graph database only if complexity demands it. fileciteturn0file1

The most important product decision is this: the platform should **not** make autonomous commercial or credit decisions. Your own materials already position it as advisory only, and the UI shell reinforces that with consent-based introductions, review steps, and audit boundaries. That is exactly the correct posture for an early product that uses explainable AI and risk signals instead of opaque underwriting or automated supplier switching. NIST describes the AI RMF as a voluntary framework to improve the incorporation of trustworthiness into the design, development, use, and evaluation of AI systems, which aligns well with your “human-reviewed recovery” model. citeturn3view0turn3view4 fileciteturn0file0 fileciteturn0file1

## Recommended system architecture

The best fit for this project is a **modular monolith with clear bounded contexts**, backed by PostgreSQL in production and SQLite only for local demo speed. React is still a strong choice for the frontend because it is a component-oriented UI library and does not prescribe a backend or data-fetching model, which fits your already-existing shell. FastAPI remains a good backend choice because it is type-hint-based, production-ready, OpenAPI-friendly, and already supports interactive documentation, WebSockets, and background-task patterns useful for alerts, ingestion, and dashboard workflows. Leaflet is an appropriate map layer because it is an open-source library for interactive maps and matches the geospatial dashboard already shown in the prototype. citeturn1view0turn2view0turn2view1turn7view0turn7view1turn2view2 fileciteturn0file1

The production data backbone should be **PostgreSQL + PostGIS**, with `jsonb` for semi-structured evidence metadata and Row-Level Security for tenant isolation. PostgreSQL’s documentation is especially relevant here: row security policies restrict visibility and modification on a per-user basis, and if row security is enabled without a policy, a default-deny posture applies. PostgreSQL also documents that `jsonb` is usually the preferred JSON storage format because it is significantly faster to process and supports indexing. PostGIS can be enabled directly as an extension and is intended for spatial SQL and spatial data analysis, which is exactly what your supply map and province-level flow analysis need. citeturn2view3turn5view0turn6view3

The graph portion should **not** start in Neo4j unless your queries truly outgrow relational adjacency tables. The README already recommends delaying Neo4j, and that advice is sound. Neo4j’s property graph model of nodes and relationships is excellent for dense path analysis and relationship-heavy traversals, but starting with `business`, `facility`, `product`, and `supply_edge` tables in PostgreSQL will be simpler, cheaper, and easier to secure. Move to Neo4j only when you need repeated multi-hop path search, subgraph ranking, or interactive graph analytics that become painful in SQL. citeturn2view5 fileciteturn0file1

At the storage layer, I recommend separating concerns into four data planes. The **system of record** should be PostgreSQL/PostGIS. The **document plane** should be encrypted object storage for invoices, delivery notes, guarantees, certifications, contracts, and signed proofs. The **analytics plane** should consist of materialized views plus worker-generated snapshots for scoring and simulation. The **integrity plane** should be an append-only audit stream with optional blockchain anchoring only for selected hashes and statuses, not for primary reads and writes. This division is consistent with your prompt, which requires both operational analysis and immutable evidence handling, while the README correctly warns against making blockchain the center of the pitch. Hyperledger Fabric explicitly frames blockchain as a shared ledger with world state and transaction log; that is valuable for selective evidence anchoring, but it is still too heavy to serve as the transactional core of the platform. citeturn2view8 fileciteturn0file0 fileciteturn0file1

A clean target architecture looks like this in practice:

| Layer | Recommended role now | Recommended role later |
|---|---|---|
| Web frontend | Keep current React + TypeScript + Leaflet shell | Add stronger state/query caching and streaming alerts |
| API layer | FastAPI modular monolith | Split only after domain boundaries are proven |
| Primary database | SQLite for local demo only | PostgreSQL + PostGIS in staging/production |
| Graph model | SQL adjacency + denormalized graph views | Neo4j only if graph analytics become a bottleneck |
| Document store | Encrypted object storage + metadata table | Add retention, legal hold, and virus scanning |
| Worker layer | DB-backed jobs or simple queue | Dedicated worker pool with Redis/Kafka later |
| Integrity layer | Audit tables + hash chaining | Optional Fabric anchoring for high-value proofs |
| Observability | OpenTelemetry tracing, metrics, logs | Full dashboards, SLOs, and alert routing |

This structure keeps the platform simple enough for Codex to implement in a disciplined way while preserving a credible path to scale. OpenTelemetry is a particularly good choice because it is open source and vendor-agnostic for traces, metrics, and logs, which prevents lock-in while you are still discovering the right operational tooling. citeturn2view9 fileciteturn0file1

## Core backend capabilities and the internal services to build

The most useful way to organize the “inside” of this platform is by **business capability**, not just technical layers. Codex should build each capability as a bounded context with its own entities, repositories, service methods, API routers, and tests. The contexts below are the real product core.

### Tenant, identity, and control boundary

Every request in the platform should resolve to a `tenant_id`, `organization_id`, `actor_id`, and `role`. Roles should not be generic. They should model your supply-chain classes directly: retailer, supplier, distributor, logistics provider, finance partner, auditor, and platform operator. The prompt makes it clear that data is highly sensitive and class-specific, so the system needs both **role-aware authorization** and **relationship-aware authorization**. A business should see its own detailed financials, inventory, and supplier relationships, but counterparties should see only the minimal information needed for continuity workflows. PostgreSQL Row-Level Security is a strong fit for enforcing these visibility boundaries below the application layer as a second line of defense. citeturn2view3 fileciteturn0file0

Codex should therefore implement these primary tables early: `tenant`, `organization`, `user_account`, `membership`, `role`, `facility`, `organization_profile`, and `visibility_policy`. The key design point is that visibility must be **data-domain specific**. For example, a downstream buyer may be allowed to see a supplier’s product capability score and verified certifications, but not the supplier’s upstream supplier names, exact debt balances, or unrelated invoices. That is the concrete answer to the supplier-confidentiality problem raised in the prompt. fileciteturn0file0

### Data ingestion and canonical supply model

The platform’s value depends on turning inconsistent enterprise data into a canonical model. The prompt names accounting, debt, revenue, inventory, goods movement, POS, delivery, invoices, contracts, and guarantees as key sources. That means Codex should build an ingestion pipeline with three layers: **raw ingestion**, **normalization**, and **derived facts**. The raw layer stores uploaded CSV, Excel, API payloads, or ERP extracts unchanged for traceability. The normalization layer maps them into canonical entities such as `invoice`, `purchase_order`, `delivery_note`, `inventory_snapshot`, `financial_snapshot`, `payment_event`, and `supply_edge`. The derived layer calculates monthly KPIs and signal features. fileciteturn0file0 fileciteturn0file1

For the sector logic, the canonical product model must include category-specific fields. Your prompt explicitly distinguishes F&B from fashion and home goods because shelf life, handling, and operating patterns differ. So the `product_sku` and `product_capability` models should support fields such as `shelf_life_days`, `temperature_band`, `packaging_type`, `minimum_order_qty`, `case_pack`, `compliance_tags`, and `substitution_group`. That makes later matching and risk logic more accurate without requiring full ML. fileciteturn0file0

### Risk engine and explainability layer

The current README provides a weighted risk formula and clearly states that the MVP is rule-based and explainable. Keep that direction. For now, the platform should compute a **versioned risk signal**, not a black-box prediction. The current formula combines cash-flow, late payment, inventory, delivery delay, debt, and dependency risks; that is a reasonable base for the first working engine. The main improvement needed is not more model sophistication but more rigor around **feature provenance, normalization, weight versioning, evidence linking, and explanation generation**. fileciteturn0file1

Codex should split this into five subcomponents: `feature_calculator`, `signal_aggregator`, `threshold_policy`, `explanation_builder`, and `scenario_registry`. Every feature should carry `source_entity_ids`, `source_period`, `calculation_version`, and `evidence_refs`. Every risk output should also store `score`, `severity`, `drivers`, `counterfactual_notes`, and `human_review_status`. That design supports the UI already shown in the financial and risk screens, where risk is broken into components rather than presented as one mysterious number. It also aligns with the AI RMF’s emphasis on trustworthiness and governance over the design and use of AI-enabled systems. citeturn3view0turn3view4 fileciteturn0file1

The minimum APIs for this context should be:

- `GET /businesses/{id}/risk-signal`
- `POST /businesses/{id}/risk-signal/recompute`
- `GET /businesses/{id}/risk-drivers`
- `GET /scenarios/{id}/network-impact`
- `POST /scenarios/simulate-shock`

These routes map naturally to the existing Overview, Risk Analysis, and supply disruption views shown in the uploaded materials. fileciteturn0file0 fileciteturn0file1

### Matching, recovery planning, and consented introductions

The supplier matching function is one of the most strategic parts of the product. The README already defines a supplier match score built from product fit, capacity, distance, financial health, reliability, payment terms, and price. That is good for an MVP because it is understandable and tunable. What Codex should add is **hard filters before scoring**. For example, in F&B a candidate that fails shelf-life, cold-chain, or certification requirements should be removed before weighted scoring starts. Weighted ranking should happen only among valid candidates. fileciteturn0file1 fileciteturn0file0

The shortlist service should consume a `disruption_case`, a `required_sku_profile`, and a `buyer_constraint_profile`; apply hard eligibility rules; compute a weighted match score; and then produce a shortlist with reasons for fit, reasons for caution, and missing requirements. The current matching screen already visualizes component weights and requires an introduction request instead of revealing direct contacts. That is exactly right. Continue that pattern and make contact release contingent on supplier consent, commercial review, and audit logging. fileciteturn0file1

![Current supplier shortlist shell](sandbox:/mnt/data/image%2821%29.png)

The required APIs here are:

- `POST /matching/shortlist`
- `GET /matching/requests/{id}`
- `POST /matching/requests`
- `POST /matching/requests/{id}/approve`
- `POST /matching/requests/{id}/decline`

The most important design rule is that the platform should expose **capability before identity**. In other words, the buyer can see that “Candidate A” matches the SKU, capacity, geography, and reliability threshold, but the full legal entity and direct contact information are only disclosed after mutual approval. That solves the “do not reveal my supplier” concern without killing the usefulness of the network. fileciteturn0file0 fileciteturn0file1

### Evidence vault, digital order, invoice verification, and audit trail

This context combines four pieces that are tightly linked in your prompt: uploaded proofs, three-party order verification, discrepancy notes, and immutable auditability. The evidence vault should model every uploaded document as `document_record` plus `document_version`, with OCR or extraction metadata added later if needed. The first version should focus on metadata, classification, verified status, digital fingerprints, signer references, and scoped access. The prompt and screenshots already show purchase orders, delivery notes, certifications, guarantees, invoices, and contracts as first-class evidence types. fileciteturn0file0 fileciteturn0file1

The digital order workflow should be treated as a **state machine** rather than a free-form document flow. A recommended sequence is: `draft -> buyer_submitted -> supplier_confirmed -> logistics_confirmed -> dispatched -> received -> discrepancy_logged -> reconciled -> closed`. Each transition should capture actor, timestamp, optional signature reference, and evidence links. If receipt quantity differs from shipment quantity, the discrepancy should create a structured `exception_note` rather than an ad hoc comment, because that exception may later affect invoicing, reputation, and risk signals. fileciteturn0file0

Invoice verification should also be narrow and explicit. The README correctly says that invoice verification simulates a ledger/hash workflow for double-financing prevention and does **not** prove the invoice is true. Preserve that caution in the code and UI. Verification should answer questions like: Does this invoice hash already exist, has funding status already been claimed, are the referenced PO and delivery note consistent, and do signatures and attachments line up? It should not claim judicial or accounting finality. fileciteturn0file1

Finally, every meaningful action needs an audit event: risk review, evidence view, shortlist generation, consent request, status change, verification result, and admin override. The audit screen in the current shell is not decorative; it should be treated as a product requirement. OWASP ASVS is a good baseline here because it provides a structured basis for verifying web application security controls and secure development requirements. citeturn2view7 fileciteturn0file1

## Privacy, confidentiality, and blockchain without overengineering

The hardest requirement in the prompt is not the map, the scoring, or the dashboard. It is this: **help companies find alternatives and assess network fragility without exposing commercially harmful relationship data**. The correct solution is a layered disclosure model.

At the lowest layer, raw financials, supplier names, invoice contents, and full document contents stay private to the owning organization and explicitly authorized reviewers. At the network layer, counterparties see only **derived risk and capability signals**: continuity score, certified product categories, rough geography, lead-time band, capacity band, and verified compliance markers. At the introduction layer, direct identity disclosure happens only after a mutual consent workflow. At the audit layer, every disclosure is logged and reviewable. This combines the prompt’s confidentiality requirement with the consent-based matching design already present in the README. fileciteturn0file0 fileciteturn0file1

The database enforcement for this should use a combination of tenant-scoped keys, role grants, and Row-Level Security. PostgreSQL’s default-deny behavior when RLS is enabled without a policy is particularly valuable for sensitive tables such as invoices, documents, and supply edges. You should also store sensitive derived metrics in separate tables where the exposed subset can be safely queried without joining into forbidden detail tables. `jsonb` is useful for flexible metadata, but do not hide all business logic in giant documents; keep the authorization-sensitive fields relational. citeturn2view3turn5view0

The evidence model should also support **document classification and redaction tiers**. I recommend at least four classes: `private`, `counterparty-shareable`, `auditor-shareable`, and `public-proof`. A supplier HACCP certificate can often be shareable, while debt schedules, upstream supplier contracts, and internal revenue ledgers generally remain private. This is where the NIST Privacy Framework is useful: it frames privacy as an enterprise risk management problem, which is exactly how this platform should treat data disclosure design. citeturn4view0 fileciteturn0file0

On blockchain, the most pragmatic approach is **hash anchoring, not ledger-first architecture**. Hyperledger Fabric’s shared-ledger model is meaningful when multiple organizations need tamper-evident shared state, but using blockchain as the main operational store would slow development, complicate queries, and make confidentiality harder. A better pattern is this: keep primary writes in PostgreSQL and object storage, compute cryptographic hashes for selected documents or workflow events, and optionally anchor those hashes and status changes into a Fabric network or a simpler append-only notarization service. That gives you integrity and audit narratives without putting every dashboard query on chain. citeturn2view8 fileciteturn0file0 fileciteturn0file1

The AI posture should stay intentionally conservative. Your own materials already say the platform should not approve credit, declare legal default, terminate suppliers, or automatically switch procurement. That is not just good messaging; it is good architecture. The risk engine should produce **reviewable management indicators** with evidence links and explanation text, and the audit module should record who accepted or overrode a recommendation. That model is much easier to defend operationally and aligns with trustworthiness-oriented guidance from NIST. citeturn3view0turn3view4 fileciteturn0file1

## Deployment blueprint and how to ship the inside of the platform

For Codex, the first deployment goal should be **boring reliability**. The existing repository already supports local backend and frontend startup, synthetic data generation, and seeded SQLite. Preserve that local path for fast iteration, but introduce a production-shaped environment early: containerized backend, frontend, PostgreSQL/PostGIS, object storage, and a worker service. FastAPI’s deployment documentation explicitly supports container-based deployment concepts, and the existing README already anticipates local Docker fallback and a future migration from SQLite to PostgreSQL/PostGIS. citeturn7view0turn7view3 fileciteturn0file1

A practical environment split is:

- **Local development**: React dev server, FastAPI, SQLite, local file storage, synthetic seed data.
- **Shared staging**: React static hosting, FastAPI container, PostgreSQL/PostGIS, encrypted S3-compatible storage, seeded plus fixture data.
- **Production**: replicated Postgres, encrypted object storage, worker pool, observability stack, key management, backup/restore, and secret rotation.

You do not need to split services aggressively at this stage. What you do need is a strict internal package layout so Codex can keep concerns separate. A good project skeleton is:

```text
backend/app
  api/
    routers/
    schemas/
    deps/
  domain/
    entities/
    value_objects/
    policies/
    services/
  application/
    commands/
    queries/
    handlers/
  infrastructure/
    db/
    repositories/
    storage/
    messaging/
    telemetry/
  workers/
    jobs/
    schedulers/
  tests/

frontend/src
  app/
  pages/
  features/
    overview/
    network/
    evidence/
    risk/
    matching/
    finance/
    invoice/
    audit/
  shared/
```

That structure builds on the repo’s current domain/repository/service boundary while making later extraction possible if the platform grows. fileciteturn0file1

For runtime quality, you should instrument from the start. OpenTelemetry is well suited here because it supports traces, metrics, and logs in a vendor-neutral way. In this product, the most valuable spans are not just HTTP requests; they are domain actions such as `risk_signal.compute`, `matching.shortlist.generate`, `document.verify`, `invoice.hash.check`, and `connection_request.release_contacts`. That form of observability is much more useful than generic server metrics when debugging sensitive workflows. citeturn2view9

Testing must also mirror the product’s real risk profile. The README already recommends pytest for backend logic, Vitest and React Testing Library for the frontend, and Playwright for demo flow coverage. Keep that, but add security and authorization tests as first-class gates. OWASP ASVS is a strong verification baseline for authentication, access control, session management, input validation, file handling, and logging requirements. citeturn2view7 fileciteturn0file1

## Detailed implementation order for Codex

Codex should not try to build every feature simultaneously. The fastest path is to lock the domain, then the data, then the workflows.

### Foundation pass

Codex should first implement the canonical domain entities, tenant context resolution, auth skeleton, PostgreSQL migration path, and repository interfaces. The output of this pass is not visible glamour; it is a stable schema and service contract layer. The definition of done is that the current frontend shell can switch from static/demo responses to typed API calls for organization profile, risk summary, finance summary, evidence list, shortlist, invoice verification, and audit events. fileciteturn0file1

### Ingestion and normalization pass

Next, Codex should build importers for synthetic CSV plus one generic CSV upload path for accounting snapshots, inventory snapshots, and supply edges. The goal here is to establish the raw-to-canonical path and evidence traceability. The minimum success criterion is that one business can be re-seeded from uploaded data and the UI updates consistently across map, risk, finance, and evidence views. fileciteturn0file0 fileciteturn0file1

### Risk and finance pass

Then Codex should implement versioned feature extraction and the explainable risk engine from the README formula, along with monthly finance registers and component breakdowns. This pass should also add “why” text generation from rules, because the screenshots already show explanatory language rather than naked numbers. The definition of done is that the finance dashboard, risk analysis cards, and alert feed all derive from the same persisted risk computation run. fileciteturn0file1

### Matching and disruption pass

After that, Codex should implement shock simulation, candidate filtering, weighted shortlist generation, recommendation cards, and introduction requests. This is where industry-specific rule packs begin to matter. For F&B, hard filters should cover product spec, freshness and shelf-life constraints, certifications, and cold-chain readiness; later verticals can add their own rule packs. The definition of done is that a disruption case can travel from a flagged node to a justified shortlist and a consent-based introduction request without manual database edits. fileciteturn0file0 fileciteturn0file1

### Evidence, order, and invoice pass

Codex should then implement document upload, metadata extraction stubs, status workflows, digital order confirmation across three parties, discrepancy notes, invoice hash checking, and proof linking. This is the pass that makes the platform defensible in enterprise settings because it connects decision-support outputs to durable evidence. The definition of done is that a user can review a business profile, open linked evidence, verify invoice uniqueness against stored hashes, and see the resulting actions in the audit trail. fileciteturn0file0 fileciteturn0file1

### Hardening pass

Only after the functional core works should Codex implement stronger security controls, RLS policies, redaction, observability, background jobs, retention rules, backup/restore, and optional blockchain anchoring. This is also the moment to add performance tests on supply-map queries and matching workloads. At that point, you will know whether SQL adjacency is still enough or whether a graph store is justified. citeturn2view3turn2view5turn2view9turn2view8

A compact backlog for Codex, ordered by business leverage, looks like this:

| Workstream | What Codex should produce | Why it matters first |
|---|---|---|
| Domain core | Entities, value objects, repository interfaces, migrations | Prevents architecture drift |
| Auth and tenancy | Actor context, memberships, role checks, tenant scoping | Required for any sensitive data |
| Canonical data | Importers, normalizers, derived facts | Everything else depends on this |
| Risk engine | Features, weighted scoring, explanations, alerts | Main product value |
| Matching engine | Hard filters, ranking, consent flow | Main recovery workflow |
| Evidence vault | Document metadata, permissions, versioning | Makes signals reviewable |
| Order workflow | Three-party confirmation and discrepancy notes | Matches prompt requirements |
| Invoice verification | Hashing, status check, linkage to PO and delivery note | High-trust workflow |
| Audit and approvals | Append-only events, review queues, overrides | Required governance layer |
| Hardening | RLS, redaction, telemetry, backups, retention | Production readiness |

The single most important instruction for Codex is this: **build every derived score, recommendation, and alert as a persisted, versioned artifact with source references**. Do not compute critical business outputs only on the fly. Persisted runs make your explanations deterministic, your audit trail coherent, and your debugging manageable. That one discipline will matter more than almost any framework decision. citeturn3view0turn4view0turn2view7 fileciteturn0file1

### Final architectural judgment

If I were making the call today, I would keep the current frontend shell, keep FastAPI, preserve the modular-monolith repository/service structure, move production data to PostgreSQL + PostGIS, implement strict tenant and relationship confidentiality using RLS plus consent-mediated identity release, use an evidence vault with append-only audit logs, and treat blockchain as an optional integrity anchor instead of the primary operational substrate. That architecture fits the product you described, matches the MVP scaffold you already have, stays explainable, and is realistic for Codex to implement in stages without collapsing under premature complexity. citeturn2view0turn2view1turn2view2turn2view3turn5view0turn6view3turn2view8turn2view9 fileciteturn0file0 fileciteturn0file1