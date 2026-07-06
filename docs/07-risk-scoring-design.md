# Supply Risk Signal Design

## 1. Nguyen tac

MVP dung rule-based scoring de minh bach va de test. Khong goi score nay la credit score hay default probability. Ten dung khi pitch/UI: `Supply Risk Signal`, `Supply Chain Risk Signal` hoac `Early Warning Signal`.

Nguon nen tham chieu khi noi ve model risk/validation: [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework), [Federal Reserve SR 11-7](https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm), [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html).

## 2. Output

```json
{
  "score": 76,
  "level": "red",
  "drivers": [
    {
      "feature": "cashflow_risk",
      "value": 82,
      "weight": 0.25,
      "contribution": 20.5,
      "message": "Cash inflow giam 18% trong 3 thang gan nhat"
    }
  ],
  "explanation": "Doanh nghiep bi canh bao vi dong tien vao giam, thanh toan tre tang va phu thuoc downstream cao."
}
```

## 3. Formula MVP

```text
Supply Risk Signal =
  0.25 * cashflow_risk
+ 0.20 * late_payment_risk
+ 0.15 * inventory_risk
+ 0.15 * delivery_delay_risk
+ 0.15 * debt_risk
+ 0.10 * dependency_risk
```

Threshold:

| Score | Level | UI color | Meaning |
| --- | --- | --- | --- |
| 0-39 | `green` | Green | Rui ro thap |
| 40-69 | `yellow` | Yellow | Can theo doi |
| 70-100 | `red` | Red | Rui ro cao |

## 4. Feature definitions

| Feature | Input | Normalization idea | Meaning |
| --- | --- | --- | --- |
| `cashflow_risk` | `cash_in`, `cash_out`, trend 3 thang | Tang khi cash_in giam va net cash flow am | Rui ro thanh khoan |
| `late_payment_risk` | `late_payment_rate` | `min(100, late_payment_rate * 400)` | Thanh toan cham, AR thu hoi cham |
| `inventory_risk` | `inventory_value`, `revenue`, turnover proxy | Tang khi inventory/revenue cao va tang lien tiep | Hang ton khong xoay vong |
| `delivery_delay_risk` | `delivery_delay_rate` | `min(100, delivery_delay_rate * 500)` | Rui ro van hanh/giao hang |
| `debt_risk` | `debt`, `revenue`, assets proxy | Tang khi debt/revenue cao | Ap luc no ngan han |
| `dependency_risk` | graph downstream, supplier dependency | Tang khi node la single point of failure hoac buyer phu thuoc >60% | Rui ro lan truyen chuoi cung ung |

## 5. Pseudocode

```python
def calculate_risk_score(features: RiskFeatures) -> RiskResult:
    normalized = normalize_features(features)
    weights = {
        "cashflow_risk": 0.25,
        "late_payment_risk": 0.20,
        "inventory_risk": 0.15,
        "delivery_delay_risk": 0.15,
        "debt_risk": 0.15,
        "dependency_risk": 0.10,
    }
    score = sum(normalized[name] * weight for name, weight in weights.items())
    level = classify_level(score)
    drivers = top_contributors(normalized, weights, limit=3)
    explanation = render_explanation(drivers, level)
    return RiskResult(score=round(score), level=level, drivers=drivers, explanation=explanation)
```

## 6. Explanation templates

| Driver | Template |
| --- | --- |
| `cashflow_risk` | "Dong tien vao giam lien tuc trong 3 thang gan nhat, lam runway ngan hon." |
| `late_payment_risk` | "Ty le thanh toan tre tang, cho thay cong no thu hoi cham." |
| `inventory_risk` | "Ton kho tang so voi doanh thu, co the lam dong tien bi khoa trong hang." |
| `delivery_delay_risk` | "Ty le giao tre tang, lam rui ro dut gay cho downstream buyers." |
| `debt_risk` | "Ty le no cao so voi doanh thu, lam ap luc thanh toan ngan han tang." |
| `dependency_risk` | "Nhieu SME phu thuoc vao node nay, nen rui ro co kha nang lan truyen." |

Example:

```text
Dai Tin Distribution dang o muc do do vi dong tien vao giam 18% trong 3 thang,
late payment rate tang len 22% va 12 SME downstream phu thuoc vao nguon hang nay.
Day la risk signal de SME chuan bi phuong an thay the, khong phai credit approval.
Neu signal dan den hanh dong thuong mai/tai chinh, can co evidence package, consent va human approval.
```

## 7. Unit test cases

| Test | Input | Expected |
| --- | --- | --- |
| Low risk | All features <= 20 | Score 0-39, level green |
| Medium risk | Cashflow 55, late payment 45, others 40 | Score 40-69, level yellow |
| High risk | Cashflow 85, late 80, dependency 90 | Score >=70, level red |
| Clamp high values | `late_payment_rate=0.9` | Normalized <=100 |
| Missing data fallback | Missing inventory | Use neutral/default + warning driver |
| Explanation order | Contributions cashflow > late > debt | Drivers sorted by contribution |

## 8. Validation roadmap

MVP:

- Unit tests + reasonableness review.
- Sensitivity test: tang/giam 1 feature xem score co thay doi dung huong.
- Demo scenario manually verified.

Pilot:

- Backtesting tren actual disruptions/late deliveries.
- Precision/recall cho alert red/yellow.
- False positive review voi business users.
- Versioned formula va changelog.

Production:

- Model registry, independent validation, monitoring drift/data quality.
- Human review cho quyet dinh tai chinh va moi hanh dong co tac dong den hop dong/doi tac.
- Governance theo model risk management.
