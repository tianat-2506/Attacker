# API Contract

API version: `/api/v1`

Response envelope:

```json
{
  "data": {},
  "meta": {
    "request_id": "req_123",
    "generated_at": "2026-06-22T10:00:00Z"
  },
  "errors": []
}
```

Error envelope:

```json
{
  "data": null,
  "meta": {
    "request_id": "req_123"
  },
  "errors": [
    {
      "code": "BUSINESS_NOT_FOUND",
      "message": "Business does not exist",
      "field": "business_id"
    }
  ]
}
```

Nguon format/API: [OpenAPI Specification](https://spec.openapis.org/oas/latest.html), [FastAPI](https://fastapi.tiangolo.com/).

## 1. GET `/api/v1/businesses`

Lay danh sach doanh nghiep de hien tren map/filter.

Query params:

| Param | Type | Required | Note |
| --- | --- | --- | --- |
| `province` | string | no | `TP.HCM`, `Binh Duong`, `Dong Nai`, `Lam Dong` |
| `type` | string | no | `manufacturer`, `distributor`, `wholesaler`, `retailer` |
| `product_category` | string | no | Taxonomy MVP |
| `risk_level` | string | no | `green`, `yellow`, `red` |

Response `200`:

```json
{
  "data": [
    {
      "business_id": "BIZ-005",
      "name": "Dai Tin Distribution",
      "display_name": "Dai Tin Distribution",
      "type": "distributor",
      "province": "Binh Duong",
      "lat": 10.9804,
      "lng": 106.6519,
      "product_category": "beverage",
      "scale": "medium",
      "financial_health_score": 47,
      "supply_risk_score": 76,
      "risk_level": "red"
    }
  ],
  "meta": {
    "count": 1
  },
  "errors": []
}
```

## 2. GET `/api/v1/businesses/{business_id}`

Lay detail mot doanh nghiep, supply risk signal va financial summary.

Path params:

| Param | Type | Required |
| --- | --- | --- |
| `business_id` | string | yes |

Response `200`:

```json
{
  "data": {
    "business": {
      "business_id": "BIZ-005",
      "name": "Dai Tin Distribution",
      "type": "distributor",
      "industry": "F&B/FMCG",
      "province": "Binh Duong",
      "monthly_revenue": 3400000000,
      "capacity": 95000
    },
    "risk": {
      "score": 76,
      "level": "red",
      "formula_version": "risk-v1",
      "drivers": [
        {
          "feature": "cashflow_risk",
          "value": 82,
          "weight": 0.25,
          "message": "Cash inflow giam 18% trong 3 thang gan nhat"
        }
      ],
      "explanation": "Dai Tin Distribution bi canh bao vi dong tien vao giam, thanh toan tre tang va ton kho cao."
    },
    "financial_summary": {
      "last_month": "2026-05",
      "cash_in": 2800000000,
      "cash_out": 3050000000,
      "late_payment_rate": 0.22,
      "delivery_delay_rate": 0.14,
      "inventory_value": 910000000
    },
    "dependency_summary": {
      "downstream_business_count": 12,
      "monthly_volume_supplied": 78000
    }
  },
  "meta": {},
  "errors": []
}
```

Errors:

- `404 BUSINESS_NOT_FOUND`.

## 3. GET `/api/v1/graph`

Lay nodes va edges cho map.

Query params:

| Param | Type | Required | Note |
| --- | --- | --- | --- |
| `province` | string | no | Filter optional |
| `masked` | boolean | no | Default `true` for public/demo |

Response `200`:

```json
{
  "data": {
    "nodes": [
      {
        "id": "BIZ-005",
        "label": "Dai Tin Distribution",
        "type": "distributor",
        "lat": 10.9804,
        "lng": 106.6519,
        "risk_level": "red",
        "size": 18
      }
    ],
    "edges": [
      {
        "id": "EDGE-041",
        "source_id": "BIZ-005",
        "target_id": "BIZ-009",
        "product": "sua hat dong hop",
        "monthly_volume": 12000,
        "lead_time_days": 2,
        "reliability": 0.88
      }
    ]
  },
  "meta": {
    "node_count": 1,
    "edge_count": 1
  },
  "errors": []
}
```

## 4. POST `/api/v1/risk/score`

Tinh supply risk signal cho mot doanh nghiep tu input indicators. Trong MVP endpoint nay co the dung cho test/demo; production nen job batch, co versioning, evidence va human-review workflow.

Request:

```json
{
  "business_id": "BIZ-005",
  "features": {
    "cashflow_risk": 82,
    "late_payment_risk": 78,
    "inventory_risk": 70,
    "delivery_delay_risk": 65,
    "debt_risk": 72,
    "dependency_risk": 84
  }
}
```

Response `200`:

```json
{
  "data": {
    "business_id": "BIZ-005",
    "score": 76,
    "level": "red",
    "drivers": [
      "cashflow_risk",
      "dependency_risk",
      "late_payment_risk"
    ],
    "explanation": "Risk cao do cashflow, dependency va thanh toan tre."
  },
  "meta": {
    "formula_version": "risk-v1"
  },
  "errors": []
}
```

Errors:

- `422 INVALID_FEATURE_RANGE`.

## 5. POST `/api/v1/simulation/shock`

Gia lap node dut gay va tra downstream impact.

Request:

```json
{
  "shock_business_id": "BIZ-005",
  "severity": "high",
  "product_category": "beverage",
  "inventory_coverage_days": 5
}
```

Response `200`:

```json
{
  "data": {
    "shock_node": "BIZ-005",
    "affected_nodes": [
      {
        "business_id": "BIZ-009",
        "severity": "red",
        "dependency_ratio": 0.72,
        "estimated_stockout_days": 4
      }
    ],
    "affected_edges": ["EDGE-041"],
    "impact": {
      "affected_sme_count": 12,
      "monthly_volume_at_risk": 78000,
      "estimated_revenue_at_risk": 1850000000,
      "avg_stockout_days": 3.8
    },
    "recommendations": [
      {
        "target_business_id": "BIZ-009",
        "suppliers": [
          {
            "business_id": "BIZ-007",
            "name": "An Phu FMCG Hub",
            "match_score": 86,
            "reason_codes": [
              "product_fit",
              "capacity_ok",
              "short_lead_time"
            ]
          }
        ]
      }
    ]
  },
  "meta": {},
  "errors": []
}
```

Errors:

- `404 BUSINESS_NOT_FOUND`.
- `422 INVALID_SHOCK_NODE`.

## 6. POST `/api/v1/recommendations/suppliers`

Tra top 3 nha cung cap thay the dang shortlist cho mot buyer/product.

Request:

```json
{
  "buyer_id": "BIZ-009",
  "disrupted_supplier_id": "BIZ-005",
  "product_category": "beverage",
  "product_specification": "UHT, 1L, khong duong",
  "required_monthly_volume": 12000,
  "preferred_payment_term_days": 30,
  "max_lead_time_days": 4,
  "top_k": 3
}
```

Response `200`:

```json
{
  "data": [
    {
      "supplier_id": "BIZ-007",
      "supplier_name": "An Phu FMCG Hub",
      "match_score": 86,
      "components": {
        "product_spec_fit": 92,
        "capacity_fit": 88,
        "distance_score": 81,
        "financial_health_score": 71,
        "delivery_reliability": 90,
        "payment_term_fit": 100,
        "price_score": 75
      },
      "reason_codes": [
        "Dung product spec",
        "Con capacity 28,000 units/month",
        "Lead time 2 ngay",
        "Chap nhan net-30"
      ],
      "new_edge_preview": {
        "source_id": "BIZ-007",
        "target_id": "BIZ-009",
        "product": "sua hat dong hop",
        "lead_time_days": 2
      }
    }
  ],
  "meta": {
    "top_k": 3
  },
  "errors": []
}
```

Errors:

- `422 NO_SUPPLIER_CANDIDATES`.

## 7. GET `/api/v1/invoices/{invoice_id}/verification`

Optional endpoint cho invoice verification.

Response `200`:

```json
{
  "data": {
    "invoice_id": "INV-0241",
    "invoice_hash": "b6c1d2...",
    "funding_status": "funded",
    "confirmed_by": ["buyer", "seller"],
    "double_financing_alert": false,
    "ledger_mode": "simulated"
  },
  "meta": {},
  "errors": []
}
```

Errors:

- `404 INVOICE_NOT_FOUND`.

## 8. Non-functional API requirements

- CORS chi allow frontend origins da cau hinh.
- Moi request co `request_id`.
- API khong tra stack trace ra client.
- Input validation voi Pydantic.
- `GET` endpoints cacheable trong MVP.
- Error code on dinh de UI hien message than thien.

Nguon: [FastAPI error handling/testing docs](https://fastapi.tiangolo.com/), [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/).
