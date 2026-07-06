# Domain Model

## 1. Bounded context

VietSupply Radar co 5 bounded contexts cho MVP:

1. `SupplyGraph`: doanh nghiep, quan he cung ung, toa do, dependency.
2. `RiskIntelligence`: financial indicators, supply risk, explanation.
3. `SupplierMatching`: candidate suppliers, weighted match score, reason codes.
4. `ShockSimulation`: node disruption, downstream impact, proposed alternative-sourcing scenarios.
5. `InvoiceVerification`: invoice hash, funding status, double financing alert.
6. `Governance`: consent, RBAC, masking, evidence, audit, dispute/appeal.

## 2. Tac nhan chinh

| Tac nhan | Muc tieu | Quyen xem MVP |
| --- | --- | --- |
| SME retailer | Tim nguon thay the, xem risk signal cua nha cung cap hien tai, du tru hang | Node cua minh, supplier public/masked, recommendation, own financial summary |
| Distributor/supplier | Quan ly downstream buyers, nhan lead matching, chung minh nang luc | Node cua minh, demand/anonymized buyer, performance metrics |
| Manufacturer | Quan ly kenh phan phoi, phat hien distributor co rui ro | Network aggregate, distributor risk, impacted volume |
| Financial partner | Xem risk signal va invoice verification de tham dinh rieng | Masked graph, risk signal, invoice status khi co consent |
| Admin/demo operator | Van hanh demo, seed data, trigger shock | Full synthetic data |

## 3. Entity model

| Entity | Mo ta | Thuoc tinh quan trong | Quan he |
| --- | --- | --- | --- |
| Business | Mot doanh nghiep trong chuoi cung ung | `business_id`, `name`, `type`, `industry`, `province`, `lat`, `lng`, `scale`, `monthly_revenue`, `capacity`, `financial_health_score`, `supply_risk_score` | Co products, financials; la source/target cua supply_edges |
| SupplyEdge | Quan he cung ung co huong | `source_id`, `target_id`, `product`, `monthly_volume`, `lead_time_days`, `transport_cost`, `reliability`, `payment_term_days` | source supplier -> target buyer |
| FinancialSnapshot | Du lieu tai chinh theo thang | `cash_in`, `cash_out`, `revenue`, `debt`, `AR`, `AP`, `inventory_value`, `late_payment_rate`, `delivery_delay_rate` | Thuoc mot Business |
| Product | Nang luc cung ung theo SKU/category | `sku`, `product_name`, `category`, `specification`, `available_capacity`, `min_order_value`, `price_range`, `certifications` | Thuoc Business |
| RiskSignal | Tin hieu canh bao thong ke | `score`, `level`, `drivers`, `calculated_at`, `formula_version`, `evidence_refs` | Thuoc Business; khong phai credit score/default probability |
| Recommendation | Ket qua matching | `target_business_id`, `candidate_supplier_id`, `match_score`, `reason_codes`, `new_edge_preview` | Tao tu shock/supplier request |
| InvoiceVerification | Trang thai hoa don | `invoice_id`, `hash`, `amount`, `buyer_id`, `seller_id`, `funding_status`, `confirmed_by` | Dung trong module optional |
| ConsentRecord | Dong y chia se du lieu | `actor_id`, `subject_id`, `scope`, `purpose`, `expires_at`, `revoked_at` | Bat buoc truoc khi mo contact/financial/invoice data |
| AuditLog | Vet truy cap va hanh dong | `event_type`, `actor_role`, `subject_id`, `purpose`, `timestamp`, `request_id` | Tao khi xem financials, invoice, contact, export |
| DisputeCase | Phan hoi/sua du lieu | `case_id`, `subject_id`, `claim`, `evidence_refs`, `status` | Cho phep supplier/SME yeu cau xem lai signal |

## 4. Luong nghiep vu SME

1. SME mo dashboard va xem nha cung cap hien tai.
2. SME click node supplier, thay risk level va giai thich.
3. SME bam shock simulation hoac nhan alert tu he thong.
4. He thong tinh downstream impact: SME bi anh huong, volume, ngay thieu hang.
5. He thong goi y top 3 supplier thay the dang shortlist.
6. SME xem ly do match va request introduction; contact/chi tiet thuong mai chi mo khi co mutual consent.
7. Neu cash runway thap, he thong goi y financial partner referral; SME quyet dinh co chia se ho so hay khong.

Acceptance criteria:

- SME luon thay duoc vi sao mot supplier duoc de xuat, khong chi thay diem.
- Recommendation khong hien lien he that neu chua co consent.
- Shock simulation co metric tac dong ro rang.
- Nen tang khong auto switch supplier, khong terminate hop dong va khong ket luan vi pham/default.

## 5. Luong nghiep vu distributor/supplier

1. Supplier tao/duoc seed profile voi products, capacity, certifications, delivery reliability.
2. Supplier thay nhu cau anonymous tu SME phu hop.
3. Khi duoc match, supplier xem product need va khoang lead time.
4. Supplier chap nhan introduction de mo thong tin lien he hai ben.

Acceptance criteria:

- Supplier khong xem duoc full customer list cua doi thu.
- Supplier co reason code de biet diem match den tu dau.

## 6. Luong nghiep vu financial partner

1. Financial partner nhan request funding tu SME sau shock.
2. He thong gui risk signal, cashflow summary va invoice verification status khi SME consent.
3. Partner xem hash/trang thai funded cua invoice.
4. Partner quyet dinh thuc hien quy trinh KYB/KYC va tham dinh rieng.

Acceptance criteria:

- He thong khong noi day la credit approval.
- Moi truy cap invoice/financial summary co audit log va consent.

## 7. Procurement flow trong demo

MVP khong can full procurement suite, nhung can mo phong cac moc:

1. Demand signal: SME can hang `sua hat dong hop`, volume 8,000 units/month.
2. RFQ/quotation simplified: he thong so sanh candidate suppliers.
3. Purchase order preview: supplier, SKU, quantity, lead time, payment term.
4. Goods receipt signal: reliability va delivery delay rate cap nhat.
5. Invoice verification: hash invoice va funding status.

Nguon tham chieu: [Microsoft Dynamics 365 Procurement and sourcing overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-sourcing-overview).

## 8. Domain events

| Event | Trigger | Consumers |
| --- | --- | --- |
| `BusinessRiskCalculated` | Risk module tinh xong supply risk signal | Frontend risk panel, alert service |
| `SupplyShockSimulated` | User bam shock | Impact panel, recommendation module |
| `ReplacementSuppliersRanked` | Matching module tra top 3 | Frontend recommendation cards |
| `InvoiceHashRegistered` | Tao invoice verification | Double financing checker |
| `SupplierIntroRequested` | SME muon ket noi | Consent workflow, notification |
| `ConsentGranted` | Data subject dong y chia se du lieu | Access control, audit service |
| `DisputeOpened` | SME/supplier phan hoi ve signal/du lieu | Admin review, evidence workflow |

## 9. Quyen rieng tu theo domain

- `Business.name` co the masked thanh `Distributor A` trong graph public.
- `SupplyEdge.monthly_volume` co the hien range thay vi exact value.
- `FinancialSnapshot` chi hien summary cho financial partner khi co consent.
- `InvoiceVerification.hash` duoc chia se, raw invoice off-chain va chi dung khi co quyen.

Nguon: [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/), [NIST Privacy Framework](https://www.nist.gov/privacy-framework).
