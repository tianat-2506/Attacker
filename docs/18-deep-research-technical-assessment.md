# Deep Research Technical Assessment

## 1. Muc tieu va ket luan dieu hanh

Tai lieu nay doi chieu `deep-research-report.md` voi demo VietSupply Radar hien tai de tra loi bon cau hoi:

1. Nhung yeu cau ky thuat nao thuc su can cho phan ruot cua san pham?
2. Giai phap nao hop ly va tuong thich voi code hien tai?
3. Demo da tao ra ket qua dung nhu ky vong hay moi chi chung minh mot kich ban synthetic?
4. Can lam lai theo vong nao de tung nang luc dat rating >= 9/10?

Ket luan ngan:

- Huong kien truc trong report la hop ly: modular monolith, FastAPI, React, PostgreSQL/PostGIS, object storage, RLS, consent va audit la mot bo giai phap tuong thich.
- Demo hien tai dat muc tot cho pitch/MVP deterministic: data validator pass, 15 backend tests pass va frontend build pass.
- Demo chua du dieu kien pilot voi du lieu that va chua san sang production. Cac khoang trong lon nhat la identity/tenancy, RLS, ingestion co lineage, persisted decision artifacts, evidence upload/versioning, order state machine, mutual consent, PostgreSQL migration, observability va security/E2E tests.
- Khong duoc dung diem kien truc cao de suy ra rang risk signal hay supplier matching da chinh xac ngoai thuc te. Hai ket qua nay chi co the dat rating >= 9 sau khi pilot co outcome that, backtest va nguoi dung xac nhan.

## 2. Pham vi san pham phai giu co dinh

San pham la nen tang ho tro quyet dinh ve lien tuc chuoi cung ung va dieu phoi niem tin, khong phai marketplace cong khai, credit bureau hay he thong tu dong ra quyet dinh thuong mai.

Ranh gio bat buoc:

- Khong tu dong cham dut hoac thay nha cung cap.
- Khong tu dong phe duyet tin dung, giai ngan, xac dinh default hoac ket luan vi pham hop dong.
- Risk score la management signal co nguon va co the review/override, khong phai xac suat vo no.
- Supplier recommendation la shortlist; qualification, dam phan va ky ket do con nguoi thuc hien.
- Invoice hash chi chung minh payload da nhan khong doi, khong chung minh hoa don la that hoac co hieu luc phap ly/ke toan.
- Danh tinh, contact, supplier graph va financial details chi duoc mo theo muc dich, quan he va consent da ghi audit.
- Synthetic data phai luon duoc gan nhan demo, khong duoc trinh bay nhu du lieu doanh nghiep that.

## 3. Danh muc yeu cau ky thuat

| Nhom | MVP/demo | Pilot/production | Future chi khi co decision gate |
| --- | --- | --- | --- |
| Product posture | Decision-support, human review, advisory notices | Review/override workflow va policy versioning | ML-assisted decision support |
| Kien truc | FastAPI modular monolith, React/TypeScript/Leaflet | Bounded contexts, application handlers, workers | Tach service khi boundary va tai da duoc chung minh |
| Identity/tenancy | Auth skeleton va actor context | OIDC/JWT, membership, RBAC + relationship policy, RLS default-deny | Federation/SSO nang cao |
| Database | SQLite cho local deterministic demo | PostgreSQL + PostGIS, Alembic migrations, `jsonb` co kiem soat | Neo4j neu SQL multi-hop la bottleneck da do duoc |
| Ingestion | CSV seed va generic upload | Raw -> normalized -> derived, checksum, lineage, idempotency, replay | ERP/POS/e-invoice/logistics connectors |
| Canonical model | Business, product, edge, finance, PO, delivery, invoice | Tenant, organization, facility, inventory/payment snapshots, document versions | Vertical-specific extensions |
| Sector rules | Product category/spec/capacity | Shelf life, temperature band, packaging, MOQ, case pack, certifications, substitution group | Rule packs ngoai F&B/FMCG |
| Risk/finance | Rule-based score va explanations | Persisted/versioned feature snapshot va risk run, evidence refs, review status, backtest | ML khi co labeled outcomes va governance |
| Shock | Directed downstream traversal, impact metrics | Persisted scenario/run, version va performance test | Graph engine neu can |
| Matching | Hard eligibility truoc weighted score | Fit/caution/missing reasons, anonymous candidate, mutual consent va qualification | Learning-to-rank sau pilot |
| Evidence | Metadata, hash, classification | S3-compatible encrypted storage, document version, scoped access, malware scan, retention/legal hold | OCR/extraction |
| Digital order | PO va delivery records | Three-party state machine, signatures/evidence, structured discrepancy | External trading integrations |
| Invoice | Hash va duplicate-funded warning | PO/delivery/signature reconciliation, partner review, claim registry | Selective notarization/Fabric anchoring |
| Audit | Record domain actions | Append-only enforcement, actor/purpose, hash chaining, retention va export | External anchor cho proof quan trong |
| API/UI | Typed APIs cho 8 workspace hien tai | Recompute/drivers, approve/decline, stable error envelope, query cache | Streaming alerts khi co nhu cau |
| Ops/quality | Local run, validation, backend tests, build | Containers, CI, OTel, backup/restore, SLO, API/security/frontend/E2E tests | Redis/Kafka chi khi DB-backed jobs khong du |

## 4. Giai phap de xuat va muc tuong thich

| Nang luc | Giai phap chon | Tuong thich voi repo | Quyet dinh |
| --- | --- | --- | --- |
| Backend | Giu FastAPI + Pydantic, modular monolith theo business capability | Cao; `backend/app/domain`, `services`, `schemas` da ton tai | Giu, khong viet lai microservices |
| Persistence | SQLAlchemy 2 + Alembic + psycopg cho PostgreSQL/PostGIS | Trung binh-cao; repository boundary giup, nhung `sqlite3`, placeholder va schema hien tai khong portable truc tiep | Tao adapter Postgres va migration, giu SQLite adapter cho local |
| Auth | OIDC provider + JWT validation; `RequestContext(tenant, organization, actor, role)` | Cao o API boundary, hien chua co auth nen can foundation moi | Khong tu viet password/identity provider |
| Authorization | RBAC + relationship-aware policy + PostgreSQL RLS default-deny | Cao voi target DB; khong the thuc thi day du tren SQLite | Application policy va RLS phai co test doc lap |
| Documents | MinIO local/S3-compatible production; metadata/version/hash trong Postgres | Cao, khong lam thay doi frontend shell | File bytes khong luu trong relational DB |
| Ingestion | Import batch + staging tables + normalizer + lineage | Cao voi service architecture | Uu tien CSV accounting, inventory, supply edge truoc connectors |
| Jobs | Postgres-backed job/outbox va worker rieng | Cao, it ha tang hon Kafka | Khong dung FastAPI BackgroundTasks cho job can durability |
| Risk/matching | Pure domain rules + persisted run/result artifacts | Rat cao; pure functions hien tai co the tai su dung | Them provenance/version/policy, khong doi sang ML som |
| Frontend data | Giu API client typed; them query cache khi mutations/invalidations tang | Cao | Khong redesign 8 workspace |
| Observability | OpenTelemetry SDK + OTLP collector, domain spans | Cao | Span phai gan tenant/request/run id, khong ghi raw secret/document |
| Testing | pytest/TestClient/Testcontainers, Vitest/RTL, Playwright | Cao; package/test setup can bo sung | RLS va cross-tenant tests la release gate |
| Blockchain | Khong dua vao operational core; chi optional hash anchor | Cao vi core hien tai off-chain | Chi lam sau multi-party pilot va cost/benefit review |

Luu y tuong thich quan trong: repository pattern giup giam pham vi migration, nhung PostgreSQL khong phai drop-in replacement. `backend/app/services/database.py` dung truc tiep `sqlite3`, SQLite DDL va parameter style rieng; can adapter/migration that, khong chi doi connection string.

## 5. Bang diem tong hop

Thang diem 0-10. `Solution fit` danh gia quyet dinh kien truc neu duoc trien khai dung. `Current readiness` danh gia code hien tai cho pilot/production, khong phai muc do dep cua demo.

Trong so dung de audit tung muc:

- Business fit: 15%.
- Legal/financial safety: 20%.
- Technical feasibility: 15%.
- Compatibility: 15%.
- Data readiness: 15%.
- Testability: 10%.
- Expected-outcome evidence: 10%.

| Workstream | Solution fit | Current readiness | Danh gia ket qua hien tai |
| --- | ---: | ---: | --- |
| Decision-support + human review | 9.7 | 8.3 | Advisory text dung; chua co actor/policy enforcement day du |
| Modular monolith | 9.5 | 8.1 | Hop ly va da co domain/repository/service; service con gom nhieu responsibility |
| Tenant, identity, RBAC, RLS | 9.6 | 1.2 | Chua co auth dependency, tenant schema hay RLS |
| Canonical ingestion + lineage | 9.4 | 2.5 | Moi doc/seed CSV co dinh; khong upload batch, staging, idempotency hay replay |
| PostgreSQL/PostGIS + migrations | 9.3 | 1.0 | Chua co driver/ORM/migration/PostGIS; SQLite-specific code |
| Product capability/rule packs | 9.4 | 4.5 | Co category/spec/capacity; thieu field va policy F&B bat buoc |
| Persisted/versioned risk artifacts | 9.5 | 5.0 | Formula va drivers co; tinh on-demand, thieu source refs/run/review/backtest |
| Shock scenario registry | 9.2 | 6.7 | Directed simulation dung voi fixture; chua persist run/version/perf gate |
| Hard-filter matching + consent | 9.5 | 4.8 | Weighted ranking co; spec mismatch van co diem >=70, lo danh tinh som, chi co create request |
| Evidence vault + document version | 9.4 | 3.0 | Chi co seeded metadata tables; khong upload/object/ACL/version/malware scan |
| Order state machine + discrepancy | 9.5 | 1.5 | PO/delivery la records tinh, khong transition/signature/exception |
| Invoice reconciliation | 9.0 | 4.2 | Hash deterministic va funded-duplicate check co; chua doi chieu PO/DN/signature/claim ownership |
| Append-only audit | 9.5 | 3.8 | Co insert event; khong bat bien, hash chain, actor context hay retention enforcement |
| Workers + observability | 9.1 | 0.5 | Chua co job durability, OTel, metrics, SLO |
| Deployment/security/backup | 9.4 | 1.5 | Local run tot; chua co production stack va restore drill |
| Test strategy | 9.6 | 4.5 | 15 backend tests pass; chua co API auth/RLS, frontend component hay Playwright suite |

Tong ket:

- Rating kien truc de xuat: **9.4/10**.
- Rating demo deterministic trong pham vi pitch: **8.4/10**.
- Rating pilot readiness voi du lieu that: **4.1/10**.
- Rating production readiness: **3.2/10**.
- Rating bang chung ve do chinh xac business outcome: **chua du du lieu de cham >= 6/10**.

Khong duoc nang diem expected outcome bang cach them test tren chinh synthetic fixture. Diem nay chi tang khi co du lieu pilot doc lap va outcome da xac nhan.

## 6. Gap matrix co bang chung code

| Nhom | Bang chung hien tai | Khoang trong |
| --- | --- | --- |
| API | `backend/app/main.py:39-141` co 15 endpoints | Khong auth dependency/actor context; thieu recompute/drivers va request approve/decline |
| Privacy | `graph` mac dinh masked, nhung `frontend/src/api/client.ts:166` goi `masked=false` | Capability-before-identity chua duoc enforce |
| Domain | `backend/app/domain/*.py` tach pure risk, shock, matching, hash | Critical outputs chua persisted/versioned voi source refs |
| Risk | `backend/app/domain/risk_scoring.py:7-128` co formula va explanation | Khong co feature snapshot, risk run, review, counterfactual, calibration |
| Matching | `backend/app/domain/supplier_matching.py:92-164` co filter va weighted score | `_product_fit` van tra diem cao khi spec khong match; thieu cold-chain/certification hard rules |
| Consent | `backend/app/services/repositories.py:191-244` tao/list request | Khong co hai chieu approve/decline/identity-release transition |
| Database | `backend/app/services/database.py:19-206` co 13 SQLite tables | Khong tenant/org/user/policy/document version/scenario/risk run/job/outbox |
| Ingestion | `backend/app/services/data_loader.py:27-92` doc cac CSV co dinh | Khong batch/source/checksum/staging/normalization/lineage |
| Evidence | `backend/app/services/radar_service.py:271-394` tong hop seeded records | Khong file upload, object storage, version, access policy, scan |
| Order | `backend/app/services/database.py:104-147` co PO/DN/cert/guarantee records | Khong order transition hay discrepancy note |
| Invoice | `backend/app/domain/invoice_verification.py:8-28` canonical hash va duplicate warning | Khong xac thuc issuer, unique claim, PO/DN/signature reconciliation |
| Audit | `backend/app/services/repositories.py:97-132` insert/list audit events | Khong append-only enforcement, RLS, hash chain, retention/export |
| Tests | `backend/tests` co 15 tests; data validator pass; frontend build pass | Khong frontend test file, API TestClient, authorization/RLS, E2E, restore/performance |

## 7. Ket qua co dung nhu ky vong khong?

| Ky vong | Ket luan | Pham vi chung minh |
| --- | --- | --- |
| Demo 62 businesses, 120 edges, 12 months | Dung | `scripts/validate_data.py` pass |
| Risk score deterministic va co drivers | Dung trong fixture | Unit/service tests va pure formula |
| BIZ-005 shock anh huong >=12 downstream retailers | Dung trong fixture | Directed traversal test pass |
| Top 3 khong chua disrupted supplier | Dung trong fixture | Matching test pass |
| Invoice hash deterministic/duplicate funded warning | Dung o muc payload demo | Hash tests pass; khong suy ra invoice authenticity |
| Consent bao ve danh tinh/contact | Chua dung | Moi co create pending request; API/UI van co the hien identity |
| Tenant isolation va confidential graph | Chua dung | Khong auth/RLS; `masked=false` duoc client goi |
| Risk canh bao dung disruption that | Chua biet | Khong co labeled outcomes, holdout/backtest/pilot |
| Matching de xuat supplier that su thay the duoc | Chua biet | Khong qualification outcome, certification/cold-chain hard gates va hit-rate pilot |
| San sang production | Khong | Thieu production data/security/ops stack |

## 8. Luong lam lai de rating >= 9

Moi vong chi duoc pass khi acceptance gate co bang chung. Neu fail, sua dung workstream, chay lai regression suite va cham lai theo cung rubric; khong ha tieu chuan de nang diem.

### Vong 0 - Scope va contract lock

Output:

- Domain glossary, API/error contract, data classification va forbidden automated actions.
- ADR cho modular monolith, Postgres/PostGIS, OIDC, object storage, job/outbox va no-blockchain-core.
- Traceability matrix tu requirement -> schema/API/service/test/control.

Gate >= 9:

- 100% critical requirement co owner, acceptance test va data classification.
- Khong con endpoint/workflow mo identity hoac commercial action ma khong co policy.

### Vong 1 - Trust foundation

Output:

- Tenant, organization, user, membership, role, relationship va visibility policy.
- OIDC/JWT actor context cho moi request.
- SQLAlchemy/Alembic adapter; PostgreSQL/PostGIS cho staging, SQLite van duoc giu cho local.
- RLS default-deny cho financials, documents, supply edges, connection requests va audit.

Gate >= 9:

- 100% sensitive request co tenant/org/actor/role context.
- Cross-tenant negative tests bi deny; khong the bypass qua query `masked=false`.
- Migration up/down va seed staging deterministic pass.

### Vong 2 - Data plane co truy vet

Output:

- `ingestion_batch`, raw objects, staging records, validation errors, canonical upsert va lineage.
- Generic CSV cho accounting, inventory va supply edge; checksum/idempotency/replay.
- Product capability fields va versioned F&B hard-rule policy.

Gate >= 9:

- Import lap lai khong tao duplicate.
- 100% canonical facts truy nguoc duoc source batch/row/version.
- Invalid row bi quarantine co reason; valid rows van xu ly theo policy ro rang.
- Re-import mot business cap nhat nhat quan map, finance, evidence va cac derived jobs.

### Vong 3 - Decision artifacts

Output:

- Persisted `feature_snapshot`, `risk_run`, `risk_driver`, `scenario_run`, `shortlist_run`, policy/formula versions va evidence refs.
- Finance, risk va alerts dung chung mot `risk_run_id`.
- Matching hard filters cho spec, shelf life, temperature, certification, capacity va lead time truoc ranking.
- Candidate an danh tinh, co fit/caution/missing requirements.

Gate >= 9 ve engineering:

- Cung input/version tao cung result; moi output co source refs va audit event.
- 100% hard-rule violations bi loai trong property/fixture tests.
- Invalid/stale run khong bi UI dung nhu current result.

Gate expected outcome van chua duoc pass neu chua co pilot data.

### Vong 4 - Consented transaction va evidence

Output:

- Document record/version, encrypted object storage, presigned upload, malware scan, classification/ACL.
- Connection state machine: anonymous -> requested -> supplier approved/declined -> buyer confirmed -> identity released/expired.
- Order state machine ba ben va structured discrepancy note.
- Invoice claim registry va PO/delivery/signature reconciliation.

Gate >= 9:

- Identity/contact chi mo sau dung mutual-consent transition.
- Transition khong hop le tra 409; moi transition co actor/time/purpose/evidence/audit.
- Quantity mismatch tao exception co cau truc.
- Duplicate funded claim bi flag; message khong bao gio tuyen bo invoice authentic.

### Vong 5 - Production hardening

Output:

- Durable workers/outbox, retries/idempotency/dead-letter policy.
- OTel traces/metrics/logs cho domain actions, CI gates, secrets/KMS, retention, backup/restore.
- Testcontainers Postgres RLS tests, API tests, Vitest/RTL, Playwright, performance va security suite.

Gate >= 9:

- Khong P0/P1 security finding mo.
- Restore drill dat RPO/RTO da cong bo.
- Common APIs dat SLO; shock/matching seed p95 < 1 second.
- Toan bo unit/data/API/auth/RLS/frontend/E2E regression pass.

### Vong 6 - Pilot validation, vong bat buoc cho outcome rating

Output:

- Data agreement va labeled outcomes voi it nhat mot anchor network.
- Backtest theo time split, calibration/threshold report, buyer/supplier qualification outcomes.
- Human review disagreement log va false-positive/false-negative review.

Gate de expected outcome >= 9:

- KPI va threshold phai duoc business owner chot truoc khi do.
- Risk precision/recall tren holdout dat threshold pilot da ky duyet, khong chi tren seed.
- Matching `hit_rate@3`, qualification pass rate va time-to-match dat threshold pilot.
- Khong co confidentiality incident; consent/revocation/retention tests va audit review pass.
- Neu fail: sua feature/rule/data mapping, version policy moi, backtest tren time split moi va lap lai. Khong overwrite ket qua cu.

## 9. Thu tu backlog de trien khai

| Priority | Epic | Phu thuoc | Definition of done ngan |
| --- | --- | --- | --- |
| P0 | Scope/policy/traceability | None | Requirement-control-test matrix du |
| P0 | Auth/tenant/Postgres/RLS | Scope | Cross-tenant deny va migrations pass |
| P0 | Ingestion/lineage | Database | Idempotent import va source trace 100% |
| P1 | Persisted risk/scenario artifacts | Ingestion | UI dung persisted current run co evidence refs |
| P1 | F&B hard filters + anonymous matching | Product capability | Vi pham hard rule bi loai; identity hidden |
| P1 | Mutual consent workflow | Auth/policy/matching | Approve/decline/revoke/release audited |
| P1 | Evidence vault | Auth/object storage | Upload/version/access/scan pass |
| P1 | Order/discrepancy state machine | Evidence | Invalid transition reject; discrepancy structured |
| P1 | Invoice reconciliation | Order/evidence | Hash + PO/DN/signature/claim review |
| P2 | Workers/OTel/backup/security/E2E | Core workflows | Production quality gates pass |
| P2 | Pilot validation | Governance + real data | Outcome metrics dat agreed thresholds |
| P3 | ML/Neo4j/Kafka/Fabric | Decision gates | Chi build khi bottleneck/value duoc do |

## 10. Bang chung kiem tra tai thoi diem danh gia

- `python scripts/validate_data.py`: pass, 62 businesses, 120 edges, 12 months, BIZ-005 scenario ready.
- `python -m unittest discover -s backend/tests -v`: 15/15 tests pass.
- `npm run build`: TypeScript va Vite production build pass.
- Frontend package co lenh `vitest`, nhung repo chua co component test files va chua cau hinh React Testing Library/Playwright.
- `git` khong kha dung trong environment hien tai, nen khong co git diff/status evidence trong lan danh gia nay.

## 11. Gioi han cua deep-research-report

Noi dung kien truc cua report co gia tri, nhung file dang co ky tu mojibake va cac `filecite/cite` token cung `sandbox:/mnt/data/...` image link tu mot lan export khac. Cac token do khong phai bang chung co the truy cap trong repo. Danh gia nay vi vay chi dung cac claim duoc doi chieu truc tiep voi source code, tests, data validator va build hien tai.
