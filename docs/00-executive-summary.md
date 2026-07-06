# VietSupply Radar - Executive Summary

Ngay cap nhat: 2026-06-22

## 1. Hieu biet cot loi ve du an

VietSupply Radar la nen tang ban do chuoi cung ung B2B cho SME, ho kinh doanh, nha phan phoi va doi tac tai chinh. He thong bieu dien doanh nghiep nhu node tren ban do Viet Nam, quan he cung ung nhu edge, sau do dung supply risk signal va explanation co truy vet de canh bao rui ro dut gay, do tac dong downstream va goi y shortlist nha cung cap thay the cho con nguoi review.

Van de can giai quyet:

- SME phu thuoc vao mot vai nha cung cap co dinh va khong nhan biet som rui ro dut gay.
- Du lieu giao dich, dong tien, ton kho, giao hang va cong no bi phan manh.
- Viec tim nha cung cap thay the hien nay dua nhieu vao quan he ca nhan, khong dua tren product fit, capacity, risk signal va logistics.
- SME kho tiep can von ngan han do thieu tin hieu du lieu dang tin cay.

Giai phap de pitching:

- Ban do chuoi cung ung F&B/FMCG khu vuc TP.HCM - Binh Duong - Dong Nai - Lam Dong.
- Dashboard hien node doanh nghiep, edge cung ung, risk level va dependency.
- AI/rule-based panel giai thich rui ro theo dong tien, cong no, ton kho, giao hang tre va dependency.
- Nut `Simulate Supply Shock` de bien mot nha phan phoi thanh node do, lan truyen tac dong toi SME downstream.
- Shortlist top 3 nha cung cap thay the dua tren product spec, capacity, khoang cach, lead time, reliability, payment terms, price va financial health.
- Consent, evidence, audit va human approval la guardrail bat buoc truoc khi mo contact, chia se financial summary, gioi thieu doi tac tai chinh hoac hanh dong thuong mai.
- Invoice Verification la module phu, mo phong hash SHA-256 va trang thai tai tro hoa don, khong pitch nhu blockchain giai quyet tat ca.

## 2. Pham vi MVP demo

| Hang muc | Quyet dinh MVP |
| --- | --- |
| Nganh | F&B/FMCG, uu tien thuc pham dong goi va nong san che bien |
| Dia ly | TP.HCM, Binh Duong, Dong Nai, Lam Dong |
| Du lieu | Synthetic data co logic: 50-80 doanh nghiep, 100-200 edges, 12 thang financials |
| Node | Manufacturer, distributor, wholesaler/agent, SME retailer, financial partner |
| Core flow | Map -> node detail -> AI risk explanation -> shock simulation -> top 3 suppliers -> working capital hint |
| AI | Rule-based scoring + explainable text generation; ML la roadmap pilot/production |
| Blockchain | Ledger simulation cho invoice hash va double financing alert |

## 3. MVP, pilot va production

| Lop | Muc tieu | Khong lam qua som |
| --- | --- | --- |
| MVP demo | Thuyet phuc ban giam khao bang mot luong demo on dinh | Dang nhap phuc tap, mobile app, marketplace day du, blockchain that |
| Pilot | Lay du lieu tu 1-2 anchor companies, POS/ERP/accounting/e-invoice, kiem chung score | Credit score thay ngan hang, cong khai graph quan he |
| Production | Postgres/PostGIS, RBAC, audit logs, data consent, monitoring, model validation | Mo rong toan quoc khi chua co data governance |

## 4. Cau chuyen demo 5 phut

1. Mo dashboard ban do mien Nam, chi ra nha phan phoi `Dai Tin Distribution` dang cung cap cho nhieu SME.
2. Click node va hien supply risk signal vang/do: dong tien vao giam, DSO tang, ton kho cao, giao tre tang.
3. Bam `Simulate Supply Shock`; node chuyen do, cac SME phu thuoc chuyen vang/do, KPI hien so SME bi anh huong, monthly volume va ngay thieu hang du kien.
4. He thong goi y 3 nha cung cap thay the voi match score va ly do: product/spec fit, capacity con trong, lead time, reliability, payment terms. Day la shortlist de SME review, khong phai auto switch.
5. Neu SME thieu tien nhap hang, hien working capital hint va invoice verification tab nhu tin hieu ho tro tham dinh.

## 5. Business model

- SaaS cho SME/nhu cau quan tri rui ro chuoi cung ung: goi basic xem ban do rieng, goi pro co shock simulation, recommendation va risk alert.
- Matching fee khi ket noi thanh cong nha mua - nha cung cap.
- Referral fee tu doi tac tai chinh khi SME consent chia se ho so cho san pham invoice financing/working capital; doi tac tai chinh tu thuc hien KYB/KYC va underwriting.
- Enterprise pilot fee cho anchor distributor/manufacturer muon quan tri downstream network.

## 6. Nguyen tac chien luoc khi pitch

- Noi `risk signal` hoac `early warning score`, khong noi AI thay the ngan hang.
- Noi ro nen tang la decision-support/intermediary; khong tu ket luan breach/default, khong terminate supplier, khong credit approval.
- Noi blockchain luu hash/trang thai cua du lieu da xac thuc, khong noi blockchain lam du lieu dau vao thanh dung.
- Noi matching da yeu to, khong noi nha cung cap gan nhat la tot nhat.
- Noi graph co masking, consent va RBAC, khong cong khai quan he thuong mai nhay cam.
- Giu demo nho nhung logic sau: phat hien rui ro -> do tac dong -> goi y thay the -> giai thich bang du lieu.

## 7. Success criteria

- Mo web len thay ban do, node, edge va KPI.
- Click mot node thay thong tin doanh nghiep, supply risk signal, cashflow health va explanation.
- Shock simulation tinh duoc downstream impact tu graph co huong.
- Recommendation tra ve top 3 supplier kem match score va reason codes.
- API contract du ro de frontend/backend lam song song.
- Co test cho risk scoring, supplier matching, shock simulation va data validation.
- Co fallback demo local, mock API va video backup.

## 8. Nguon research chinh

- Supply chain va logistics: [CSCMP Supply Chain Management Definitions and Glossary](https://cscmp.org/CSCMP/Educate/SCM_Definitions_and_Glossary_of_Terms.aspx).
- Procurement: [Microsoft Dynamics 365 Procurement and sourcing overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-sourcing-overview).
- Financial statements: [SEC Beginners' Guide to Financial Statements](https://www.sec.gov/about/reports-publications/investorpubsbegfinstmtguide).
- SME finance: [World Bank SME Finance](https://www.worldbank.org/ext/en/topic/competitiveness/small-and-medium-enterprises-smes-finance), [IFC MSME Finance](https://www.ifc.org/en/what-we-do/sector-expertise/financial-institutions/msme-finance).
- AI/model risk: [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework), [Federal Reserve SR 11-7 Model Risk Management](https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm).
- Tech stack: [React](https://react.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Leaflet](https://leafletjs.com/reference.html), [GeoJSON RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946), [PostgreSQL docs](https://www.postgresql.org/docs/current/).
- Security/governance: [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/), [NIST Privacy Framework](https://www.nist.gov/privacy-framework), [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
- Blockchain/hash: [NIST FIPS 180-4 Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final), [Hyperledger Fabric Introduction](https://hyperledger-fabric.readthedocs.io/en/latest/blockchain.html).
