# Pitch Demo Script

## 1. One-liner

VietSupply Radar la ban do chuoi cung ung B2B giup SME phat hien som rui ro dut gay, do tac dong tai chinh va lap supplier shortlist bang rule-based matching co giai thich.

## 2. Script 5 phut

### Phut 1 - Problem

SME Viet Nam thuong phu thuoc vao mot vai nha cung cap co dinh. Khi mot nha phan phoi gap van de ve dong tien, giao hang hoac ton kho, cac SME downstream thuong chi biet khi hang da tre. Luc do ho vua thieu hang ban, vua khong co du thoi gian lap danh sach nha cung cap thay the, vua co the thieu von de nhap lo hang moi.

### Phut 2 - Solution

VietSupply Radar bieu dien doanh nghiep nhu node tren ban do, quan he cung ung nhu edge. He thong tinh risk signal tu dong tien, cong no, ton kho, giao hang va dependency graph. Khi phat hien rui ro, he thong giai thich bang ngon ngu de hieu va goi y supplier shortlist dua tren product fit, capacity, logistics, reliability, payment terms va financial health. Moi hanh dong ket noi/thuong mai/tai chinh van can consent va human approval.

### Phut 3 - Map and risk demo

Mo dashboard mien Nam. Click `Dai Tin Distribution`.

Noi:

"Day la mot nha phan phoi beverage tai Binh Duong. He thong danh dau do vi cash inflow giam 18% trong 3 thang, late payment rate tang len 22%, delivery delay tang len 14% va 12 SME downstream dang phu thuoc vao node nay. Day khong phai credit score, ma la early warning signal de SME chuan bi phuong an."

### Phut 4 - Supply shock and recommendation

Bam `Simulate Supply Shock`.

Noi:

"Khi node nay bi shock, he thong lan truyen tac dong theo directed graph. 12 SME bi anh huong, 78,000 units/month at risk va thoi gian thieu hang du kien 3-4 ngay neu khong co nguon thay the. Bay gio he thong goi y top 3 supplier dang shortlist. Diem match khong chi dua tren khoang cach, ma co product spec, capacity, lead time, reliability, payment term va financial health. Day khong phai auto switch; SME can review va request introduction."

Click recommendation card.

"Vi du An Phu FMCG Hub duoc xep hang cao vi dung spec UHT 1L, con capacity 28,000 units/thang, lead time 2 ngay va chap nhan net-30."

### Phut 5 - Business model and roadmap

"MVP chung toi dung synthetic data de chung minh flow. Pilot se bat dau voi anchor distributor F&B, tich hop POS/accounting/e-invoice de kiem chung risk signal voi consent va audit. Business model gom SaaS cho quan tri rui ro, matching fee khi ket noi thanh cong va referral fee voi doi tac tai chinh cho working capital/invoice financing; doi tac tai chinh van tu KYB/KYC va underwriting. Blockchain chi la module phu cho hash hoa don va double-financing alert, khong duoc pitch nhu giai phap than ky."

## 3. Script 7 phut

Them cac diem sau vao script 5 phut:

- 30 giay ve kẽ hở logic va cach trám: data masking, consent, multi-factor matching.
- 45 giay ve architecture: React/Leaflet, FastAPI, CSV demo -> PostgreSQL/PostGIS/Neo4j path.
- 45 giay ve validation: unit tests cho risk/match/shock, data validation, pilot backtesting.
- 30 giay ve invoice verification: hash SHA-256, funded status, double financing alert.

## 4. Demo click path

1. Open dashboard.
2. Zoom/point to South Vietnam cluster.
3. Click `Dai Tin Distribution`.
4. Show risk panel and explanation.
5. Show downstream dependency count.
6. Click `Simulate Supply Shock`.
7. Point to red/yellow affected nodes.
8. Read KPI impact.
9. Click top recommendation.
10. Open invoice verification tab if time allows.
11. Close with business model and roadmap.

## 5. Q&A phan bien

| Cau hoi | Tra loi |
| --- | --- |
| Du lieu that lay tu dau? | MVP dung synthetic data co logic. Pilot se bat dau voi anchor distributor/manufacturer co downstream SME, lay POS/accounting/e-invoice/logistics data co consent. |
| AI co train bang du lieu that chua? | Chua overclaim. MVP dung rule-based scoring minh bach + AI explanation. Khi co du lieu outcome se backtest va nang len ML risk model. |
| Neu score sai lam SME hoang mang? | Score la early warning signal, co explanation va threshold; pilot can human review, feedback va model validation. |
| Nha cung cap thay the co dam bao chat luong khong? | Matching co product spec, certification, capacity, reliability, payment terms. Pilot them supplier qualification va sample approval. |
| Blockchain co can thiet khong? | Khong la trung tam demo. Chi dung cho invoice hash/funding status simulation de giai thich double financing risk; production co the dung consortium ledger. |
| Lam sao tranh lo bi mat nha cung cap? | Graph mac dinh masked/aggregate; ten that va lien he chi mo khi co mutual consent; financial data co RBAC va audit. |
| Cold start giai quyet sao? | Bat dau mot nganh hep, mot vung hep, anchor company, synthetic demo de ban y tuong, sau do pilot voi data cua anchor. |
| Khac marketplace B2B o dau? | Marketplace tim mua/ban. VietSupply Radar tap trung risk sensing, dependency impact va supplier shortlist co giai thich. |
| Tai sao khong dung app mobile? | Demo pitch can dashboard map va shock simulation; mobile la sau khi use case duoc validate. |
| Co the lam trong 4 tuan khong? | Co neu giu scope: static seed, React/Leaflet, FastAPI, pure functions, 5 screen, 3 domain modules. |

## 6. Slide deck 10 trang de xuat

1. Title: VietSupply Radar.
2. Problem: SME dependency and disruption.
3. Insight: source, cash flow, trust data are connected.
4. Solution: supply graph + risk signal + matching.
5. Demo architecture: map -> risk -> shock -> recommendation.
6. Algorithm: risk signal and match score.
7. Data and governance: synthetic MVP, consent/masking pilot.
8. Business model.
9. Roadmap 4 weeks and pilot path.
10. Ask: pilot partners, data access, mentorship/funding.
