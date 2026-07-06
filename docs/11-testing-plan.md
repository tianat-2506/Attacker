# Testing Plan

Nguon tham chieu: [pytest](https://docs.pytest.org/en/stable/), [FastAPI testing/docs](https://fastapi.tiangolo.com/), [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html).

## 1. Test pyramid MVP

| Level | Scope | Tools suggested |
| --- | --- | --- |
| Unit | Pure domain functions: risk, matching, shock, invoice hash | pytest |
| Data validation | CSV/JSON schema, FK, ranges, deterministic seed | pytest + custom script |
| API integration | FastAPI routes, schemas, status codes | pytest + TestClient |
| Frontend component | Click node, sidebar, shock button, cards | Vitest/React Testing Library |
| E2E/demo | Local app flow map -> risk -> shock -> recommendation | Playwright |
| Rehearsal | Pitch timing, fallback, offline demo | Manual checklist |

## 2. Unit tests - risk signal

| Test | Input | Expected |
| --- | --- | --- |
| `test_low_risk_score_green` | All normalized features <=20 | Score <40, `green` |
| `test_medium_risk_score_yellow` | Mixed features around 50 | 40-69, `yellow` |
| `test_high_risk_score_red` | Cashflow/late/dependency high | >=70, `red` |
| `test_feature_values_are_clamped` | Feature >100 or <0 | Clamped or validation error |
| `test_driver_contributions_sorted` | Known contributions | Drivers sorted descending |
| `test_explanation_uses_only_present_drivers` | Missing inventory | No false inventory message |

## 3. Unit tests - supplier matching

| Test | Input | Expected |
| --- | --- | --- |
| `test_product_mismatch_excluded` | Request beverage, supplier snack only | Excluded |
| `test_disrupted_supplier_excluded` | Candidate id equals shocked supplier | Excluded |
| `test_capacity_affects_score` | Same candidate, capacity varies | Higher capacity higher score |
| `test_distance_not_only_factor` | Near bad spec vs far good spec | Good spec ranks higher |
| `test_payment_term_affects_score` | COD vs net-30 | net-30 higher for cash-strained buyer |
| `test_top_k_deterministic` | Ties | Stable sorted result |
| `test_no_candidates_error` | All filtered out | Domain error with reasons |

## 4. Unit tests - shock simulation

| Test | Input graph | Expected |
| --- | --- | --- |
| `test_downstream_direction` | A -> B, shock A | B affected |
| `test_upstream_not_affected` | A -> B, shock B | A not affected |
| `test_multilevel_traversal` | A -> B -> C | B/C affected if B can propagate |
| `test_product_filter` | Two categories | Only selected category counted |
| `test_cycle_safe` | A -> B -> A | No infinite loop |
| `test_impact_metrics` | Known volumes/prices | Expected aggregate |
| `test_severity_thresholds` | dependency/stockout variants | red/yellow/green correct |

## 5. Unit tests - invoice verification

| Test | Input | Expected |
| --- | --- | --- |
| `test_hash_stable_for_same_invoice` | Same canonical invoice | Same SHA-256 |
| `test_hash_changes_when_amount_changes` | Amount changed | Different hash |
| `test_double_financing_alert` | Same hash funded twice | Alert true |
| `test_unfunded_invoice_no_alert` | Same hash unfunded | Alert false |

## 6. Data validation tests

- `business_id` unique.
- All FK references exist.
- `lat/lng` inside expected bbox.
- Edges have no self-loop.
- Required fields non-null.
- Financials have 12 months per business.
- Risk target node has at least 5 downstream SMEs.
- Product categories are in controlled taxonomy.
- Numeric values are within ranges.

## 7. API integration tests

| Endpoint | Assertions |
| --- | --- |
| `GET /api/v1/businesses` | 200, list, filters work, envelope shape |
| `GET /api/v1/businesses/{id}` | 200 for known ID, 404 for missing |
| `GET /api/v1/graph` | nodes/edges present, masked default |
| `POST /api/v1/risk/score` | 200 valid, 422 invalid range |
| `POST /api/v1/simulation/shock` | affected nodes and impact metrics |
| `POST /api/v1/recommendations/suppliers` | top 3, components, reason codes |
| `GET /api/v1/invoices/{id}/verification` | hash/status, 404 missing |

## 8. Frontend tests

- Map renders non-empty loading state and data state.
- Marker click opens sidebar with correct business.
- Risk level color matches API response.
- Shock button disables while simulating and then updates KPI.
- Recommendation cards show score, supplier name and reasons.
- Empty/error states do not overlap layout.
- Mobile viewport keeps sidebar usable.

## 9. Demo rehearsal checklist

- [ ] Local app starts without internet-critical dependencies.
- [ ] Default map view focuses TP.HCM - Binh Duong - Dong Nai - Lam Dong.
- [ ] Default shock node visible and click target easy.
- [ ] 5-minute demo script rehearsed at least 3 times.
- [ ] Reset button works.
- [ ] Backup browser tab with static screenshot/video ready.
- [ ] API mock JSON available if backend fails.
- [ ] Pitch Q&A notes open.
- [ ] Laptop charger/network fallback ready.

## 10. Fallback plan

| Failure | Fallback |
| --- | --- |
| Backend down | Frontend reads static mock JSON |
| Map tiles unavailable | Use cached screenshot/static SVG-free map image or local tile fallback |
| Internet unavailable | Local demo with seeded data |
| UI bug during shock | Play backup video and explain flow |
| Recommendation empty | Use preselected demo buyer/product seed |

## 11. Definition of done for MVP

- Core domain tests pass.
- Data validation pass.
- API smoke tests pass.
- Frontend main flow works on desktop and mobile width.
- README run instructions verified.
- Demo rehearsal checklist completed.
