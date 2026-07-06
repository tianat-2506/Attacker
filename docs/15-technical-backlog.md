# Technical Backlog

Backlog nay chuyen bo tai lieu VietSupply Radar thanh cac epic, feature, user story va task ky thuat uu tien MVP demo 4 tuan.

## Epic 1 - Data Foundation

### Feature 1.1 - Synthetic seed data

User story: La demo operator, toi muon co seed data on dinh cho 62 doanh nghiep, 120 edges va 12 thang financials de demo khong bi lech moi lan chay.

Tasks:

| Task | Muc tieu | Output | Files | Do kho | Phu thuoc | Test | Demo impact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Generate businesses | Tao 62 businesses theo docs | `data/businesses.csv` | `scripts/generate_synthetic_data.py` | M | Data dictionary | Count/type/province validation | Map co node |
| Generate edges | Tao 120 directed edges | `data/supply_edges.csv` | `scripts/generate_synthetic_data.py` | M | Businesses | FK/no self-loop/default shock | Graph co dependency |
| Generate financials | Tao 12 thang financial snapshots | `data/financials.csv` | `scripts/generate_synthetic_data.py` | M | Businesses | Month coverage/range | Risk panel co data |
| Generate products | Tao SKU/capacity/spec | `data/products.csv` | `scripts/generate_synthetic_data.py` | S | Businesses | Product taxonomy | Matching co candidates |
| Validate data | Bat loi seed truoc demo | CLI validation report | `scripts/validate_data.py` | M | All CSV | Validation script pass | Demo on dinh |

Acceptance criteria:

- `BIZ-005` la default shock node va co it nhat 12 downstream beverage SME.
- Moi business co 12 thang financials.
- Validation script pass.

## Epic 2 - Backend Domain Logic

### Feature 2.1 - Risk scoring

User story: La SME, toi muon xem supply risk signal va ly do canh bao de hieu vi sao mot supplier can duoc theo doi.

Tasks:

| Task | Muc tieu | Output | Files | Do kho | Phu thuoc | Test | Demo impact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Normalize features | Chuyen financials thanh 0-100 | `RiskFeatures` | `backend/app/domain/risk_scoring.py` | M | Financials | Low/medium/high cases | Signal co nghia |
| Weighted signal | Tinh formula risk-v1 | `RiskResult` | `risk_scoring.py` | S | Normalize | Threshold tests | Node mau xanh/vang/do |
| Explanation | Render top drivers | Vietnamese message | `risk_scoring.py` | S | Score | Driver order test | BGK hieu logic |

Acceptance criteria:

- Signal trong 0-100, level green/yellow/red.
- Explanation chi dua tren drivers that.
- Output ghi ro day la decision-support signal, khong phai credit approval/default probability.

### Feature 2.2 - Supplier matching

User story: La SME bi anh huong, toi muon nhan top 3 supplier thay the dang shortlist co ly do ro rang.

Tasks:

| Task | Muc tieu | Output | Files | Do kho | Phu thuoc | Test | Demo impact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Candidate filter | Loai supplier sai category/rui ro/shock | Candidate list | `supplier_matching.py` | M | Data | Mismatch/excluded tests | Goi y dung |
| Score components | Tinh product, capacity, distance, health, reliability, term, price | Component scores | `supplier_matching.py` | M | Products/edges | Component tests | Score da yeu to |
| Rank top 3 | Sap xep deterministic | Recommendations | `supplier_matching.py` | S | Components | Top-k tests | Card recommendation |

Acceptance criteria:

- Khong de xuat `disrupted_supplier_id`.
- Nha cung cap gan nhat nhung sai spec khong duoc xep dau.
- Recommendation chi la shortlist; contact/commercial action can consent va human approval.

### Feature 2.3 - Shock simulation

User story: La demo operator, toi muon bam shock va thay cac SME downstream bi anh huong.

Tasks:

| Task | Muc tieu | Output | Files | Do kho | Phu thuoc | Test | Demo impact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Build adjacency | Doc edge source->target | Graph | `shock_simulation.py` | S | Edges | Direction tests | Impact dung |
| Traverse downstream | BFS safe voi cycles | Affected nodes | `shock_simulation.py` | M | Graph | Multi-level/cycle tests | Node vang/do |
| Impact metrics | Tinh count/volume/stockout | Impact summary | `shock_simulation.py` | M | Affected edges | Fixture tests | KPI bar |

Acceptance criteria:

- Direction source->target dung.
- `BIZ-005` shock tao affected SME count >= 12.

## Epic 3 - Backend API

User story: La frontend engineer, toi can API versioned de lay graph, business detail, shock va recommendation.

Tasks:

| Task | Output | Files | Test |
| --- | --- | --- | --- |
| FastAPI app skeleton | `/api/v1/health`, `/graph`, `/businesses/{id}` | `backend/app/main.py` | Import test/manual run |
| Repository loader | Load CSV into dataclasses/dicts | `backend/app/services/data_loader.py` | Data load tests |
| API routes for shock/matching | POST endpoints | `backend/app/main.py` | Future integration tests |
| Error envelope | Stable error format | `main.py` | 404/422 checks |

Acceptance criteria:

- Domain logic can run without FastAPI dependency.
- API skeleton follows `docs/06-api-contract.md`.

## Epic 4 - Frontend Demo

User story: La ban giam khao, toi muon mo demo va thay ngay ban do/graph, risk panel, shock va recommendations.

Tasks:

| Task | Output | Files | Test |
| --- | --- | --- | --- |
| Vite/React scaffold | Package/config/src | `frontend/package.json`, `frontend/src` | `npm run build` when deps installed |
| Map dashboard | Markers/edges/sidebar | `MapView.tsx`, `App.tsx` | Visual smoke |
| API client | Fetch graph/business/shock | `frontend/src/api/client.ts` | Mockable functions |
| UI fallback data | Static mock flow if API unavailable | `frontend/src/utils/demoData.ts` | Manual demo offline |

Acceptance criteria:

- First screen is usable dashboard, not landing page.
- Shock button visible and recommendation cards present.

## Epic 5 - Testing, README and Demo Ops

Tasks:

| Task | Output | Files | Test |
| --- | --- | --- | --- |
| Python unit tests | Domain/data tests | `backend/tests` | `python -m unittest discover -s backend/tests` |
| Data validation command | CLI validator | `scripts/validate_data.py` | `python scripts/validate_data.py` |
| README update | Setup/run/test/demo flow | `README.md` | Commands verified where possible |
| Demo fallback notes | Local/mock/video backup | `README.md`, `docs/11` | Manual checklist |

Acceptance criteria:

- Data validator passes.
- Domain unit tests pass.
- README tells how to continue to full React/FastAPI run.
