# Shock Simulation Design

## 1. Muc tieu

Shock simulation cho ban giam khao thay he thong khong chi "ve ban do", ma co the:

- Xac dinh node supplier/distributor bi dut gay.
- Tim downstream buyers bi anh huong theo directed graph.
- Tinh impact: so SME, monthly volume, doanh thu at risk, ngay thieu hang.
- Goi y supplier shortlist va preview quan he cung ung de review; khong tao edge moi nhu giao dich that neu chua co consent/PO.

Nguon graph: [NetworkX Centrality and graph algorithms](https://networkx.org/documentation/stable/reference/algorithms/centrality.html), [Neo4j Cypher docs](https://neo4j.com/docs/cypher-manual/current/).

## 2. Input

```json
{
  "shock_business_id": "BIZ-005",
  "severity": "high",
  "product_category": "beverage",
  "inventory_coverage_days": 5
}
```

## 3. Output

```json
{
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
  "new_edge_previews": [
    {
      "source_id": "BIZ-007",
      "target_id": "BIZ-009",
      "product": "sua hat dong hop",
      "match_score": 86
    }
  ]
}
```

## 4. Graph direction

Edge direction:

```text
source_id = supplier
target_id = buyer/downstream customer
```

Khi `BIZ-005` bi shock, traversal di theo outgoing edges cua `BIZ-005`, roi tiep tuc neu target cung la distributor/wholesaler co downstream buyers.

## 5. Impact formula

```text
affected_sme_count = count(affected nodes where type in retailer/sme)

monthly_volume_at_risk =
  sum(edge.monthly_volume for affected_edges matching product_category)

dependency_ratio for buyer =
  volume_from_shocked_supplier / total_inbound_volume_for_product_category

estimated_stockout_days =
  max(0, suggested_supplier_lead_time_days - inventory_coverage_days)

estimated_revenue_at_risk =
  monthly_volume_at_risk * average_unit_price_proxy
```

Severity:

| Condition | Severity |
| --- | --- |
| dependency_ratio >= 0.7 or stockout_days >= 4 | `red` |
| dependency_ratio >= 0.4 or stockout_days >= 2 | `yellow` |
| otherwise | `green` |

## 6. Pseudocode

```python
def simulate_shock(graph: SupplyGraph, request: ShockRequest) -> ShockResult:
    shock_node = graph.get_business(request.shock_business_id)
    affected_edges = []
    affected_nodes = {}
    queue = [shock_node.business_id]
    visited = set()

    while queue:
        source_id = queue.pop(0)
        if source_id in visited:
            continue
        visited.add(source_id)

        for edge in graph.outgoing_edges(source_id):
            if request.product_category and edge.product_category != request.product_category:
                continue
            affected_edges.append(edge)
            target = graph.get_business(edge.target_id)
            impact = calculate_node_impact(target, edge, graph, request)
            affected_nodes[target.business_id] = impact
            if target.type in {"distributor", "wholesaler"}:
                queue.append(target.business_id)

    recommendations = build_recommendations_for_affected_buyers(affected_nodes)
    return ShockResult(...)
```

## 7. Cycle handling

MVP graph co the khong nen co cycle, nhung code van can:

- `visited` set de tranh infinite loop.
- Max traversal depth default 3.
- Bo qua edge bi duplicate.

## 8. UI behavior

- Shock node doi mau do.
- Affected nodes doi vang/do theo severity.
- Affected edges noi bat.
- KPI bar hien `affected_sme_count`, `monthly_volume_at_risk`, `avg_stockout_days`.
- Recommendation cards hien top 3 cho selected affected SME hoac aggregate top suppliers.
- Nut reset shock khoi phuc graph.

## 9. Unit test cases

| Test | Graph | Expected |
| --- | --- | --- |
| Single downstream | A -> B | B affected, 1 edge |
| Multi-level downstream | A -> B -> C | B and C affected if B is distributor/wholesaler |
| Wrong direction | B -> A only, shock A | B not affected |
| Product filter | A supplies beverage and snack | Only requested category affected |
| Cycle | A -> B -> A | No infinite loop |
| Severity red | dependency 0.8, stockout 5 | Red |
| Reset | Shock cleared | UI graph returns base state |

## 10. Acceptance criteria

- Direction source->target is correct and tested.
- Shock target co visible downstream impact trong seed.
- Impact numbers are reproducible from fixture data.
- Recommendation integrates with matching module.
- UI can explain each metric in plain Vietnamese.
