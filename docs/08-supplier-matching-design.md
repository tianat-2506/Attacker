# Supplier Matching Design

## 1. Nguyen tac

Supplier matching khong duoc chi dua vao khoang cach. Trong hang hoa vat ly, nha cung cap thay the can khop san pham, spec, capacity, reliability, lead time, payment terms, price va financial health. Output la shortlist/khuyen nghi co giai thich, khong phai lenh tu dong doi nha cung cap.

Nguon: [ASQ Supplier Quality](https://asq.org/quality-resources/supplier-quality), [CSCMP](https://cscmp.org/CSCMP/Educate/SCM_Definitions_and_Glossary_of_Terms.aspx), [ICC Incoterms](https://iccwbo.org/business-solutions/incoterms-rules/).

## 2. Candidate filter

Loai candidate neu:

- Candidate la supplier dang bi shock.
- Candidate khong co product category phu hop.
- `available_capacity < required_monthly_volume * 0.5` neu khong cho phep split order.
- `supply_risk_score >= 85`.
- `lead_time_days > max_lead_time_days * 2`.
- Supplier chua qua basic qualification trong pilot.

## 3. Formula MVP

```text
Match Score =
  0.25 * product_spec_fit
+ 0.20 * capacity_fit
+ 0.15 * distance_score
+ 0.15 * financial_health_score
+ 0.10 * delivery_reliability
+ 0.10 * payment_term_fit
+ 0.05 * price_score
```

Output 0-100, top 3 suppliers dang shortlist de SME review.

## 4. Component definitions

| Component | Cach tinh MVP | Giai thich |
| --- | --- | --- |
| `product_spec_fit` | 100 neu category/spec/certification match; 70 neu category match nhung spec partial; 0 neu mismatch | Dieu kien quan trong nhat |
| `capacity_fit` | `min(100, available_capacity / required_volume * 100)` | Co du cong suat thay the |
| `distance_score` | Haversine buyer-supplier, decay theo service radius | Logistics proxy |
| `financial_health_score` | Lay tu business profile, 0-100 | Tranh thay supplier rui ro cao |
| `delivery_reliability` | `reliability * 100` | Lich su giao dung han |
| `payment_term_fit` | 100 neu term >= preferred; 60 neu cham hon 15 ngay; 30 neu COD khi SME can credit | Tac dong cash runway |
| `price_score` | 100 neu trong target range, 70 neu cao hon 10%, 40 neu cao hon 20% | Gia nhung khong phai yeu to duy nhat |

## 5. Distance proxy

MVP dung haversine tu lat/lng:

```text
distance_score = max(0, 100 - (distance_km / service_radius_km) * 100)
```

Pilot co the thay bang route API/logistics lead time.

## 6. Pseudocode

```python
def rank_suppliers(request: MatchRequest, data: DataStore) -> list[SupplierRecommendation]:
    candidates = filter_candidates(request, data)
    scored = []
    for supplier in candidates:
        components = calculate_components(request, supplier)
        score = weighted_sum(components, MATCH_WEIGHTS)
        reason_codes = explain_match(components, supplier)
        scored.append(SupplierRecommendation(supplier=supplier, score=score, components=components, reason_codes=reason_codes))
    return sorted(scored, key=lambda item: (-item.score, item.supplier.lead_time_days, item.supplier.name))[: request.top_k]
```

## 7. Reason code examples

| Component high | Reason code |
| --- | --- |
| Product/spec | "Dung category beverage va spec UHT 1L" |
| Capacity | "Con capacity 28,000 units/month, du bu 12,000 units" |
| Distance/lead time | "Cach buyer 38 km, lead time 2 ngay" |
| Payment | "Chap nhan net-30, phu hop cash runway cua SME" |
| Reliability | "Delivery reliability 93%" |
| Health | "Financial health score 74, khong nam trong risk filter" |

## 8. Tie-break rules

1. Higher match score.
2. Lower `lead_time_days`.
3. Higher `delivery_reliability`.
4. Higher `available_capacity`.
5. Stable alphabetical/name or `business_id` to keep deterministic.

## 9. Unit test cases

| Test | Input | Expected |
| --- | --- | --- |
| Product mismatch | Candidate only packaged_food for beverage request | Excluded |
| Disrupted supplier excluded | Candidate id equals `disrupted_supplier_id` | Excluded |
| Capacity partial allowed | Capacity 60% required | Included but capacity score 60 |
| Distance not dominant | Far supplier perfect spec beats near wrong spec | Far supplier ranks higher |
| Payment term matters | Same supplier metrics, net-30 vs COD | Net-30 higher |
| Top 3 deterministic | 5 similar candidates | Same order every run |
| No candidates | All filtered | `NO_SUPPLIER_CANDIDATES` with reasons |

## 10. Pilot validation metrics

- `hit_rate@3`: buyer contacts one of top 3.
- `conversion_rate`: recommendation -> introduction -> PO.
- `time_to_match`: minutes from shock to viable supplier shortlist.
- `replacement_success_rate`: candidate delivered acceptable order.
- User feedback on reason codes.
- Consent rate and dispute rate: ty le mo contact co mutual consent va ty le candidate/supplier phan hoi ve du lieu sai.

Nguon ranking/evaluation: [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html), [arXiv recommender metrics consistency](https://arxiv.org/abs/2206.12858).
