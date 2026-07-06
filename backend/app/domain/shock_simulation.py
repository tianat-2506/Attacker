from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AffectedNode:
    business_id: str
    severity: str
    dependency_ratio: float
    estimated_stockout_days: int


@dataclass(frozen=True)
class ShockImpact:
    affected_sme_count: int
    monthly_volume_at_risk: int
    estimated_revenue_at_risk: int
    avg_stockout_days: float


@dataclass(frozen=True)
class ShockResult:
    shock_node: str
    affected_nodes: list[AffectedNode]
    affected_edges: list[str]
    impact: ShockImpact


def _incoming_volume(edges: list[dict[str, Any]], target_id: str, category: str) -> int:
    return sum(int(edge["monthly_volume"]) for edge in edges if edge["target_id"] == target_id and edge["product_category"] == category)


def _severity(dependency_ratio: float, stockout_days: int) -> str:
    if dependency_ratio >= 0.7 or stockout_days >= 4:
        return "red"
    if dependency_ratio >= 0.4 or stockout_days >= 2:
        return "yellow"
    return "green"


def simulate_shock(
    shock_business_id: str,
    businesses: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    product_category: str,
    inventory_coverage_days: int = 5,
    max_depth: int = 3,
) -> ShockResult:
    if shock_business_id not in businesses:
        raise ValueError(f"Unknown shock_business_id {shock_business_id}")

    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge["product_category"] == product_category:
            adjacency[edge["source_id"]].append(edge)

    affected_by_id: dict[str, AffectedNode] = {}
    affected_edges: list[str] = []
    monthly_volume_at_risk = 0
    queue: deque[tuple[str, int]] = deque([(shock_business_id, 0)])
    visited: set[str] = set()

    while queue:
        source_id, depth = queue.popleft()
        if source_id in visited or depth > max_depth:
            continue
        visited.add(source_id)

        for edge in adjacency.get(source_id, []):
            target_id = edge["target_id"]
            target = businesses[target_id]
            affected_edges.append(edge["edge_id"])
            monthly_volume_at_risk += int(edge["monthly_volume"])
            inbound_total = max(1, _incoming_volume(edges, target_id, product_category))
            dependency_ratio = int(edge["monthly_volume"]) / inbound_total
            stockout_days = max(0, int(edge["lead_time_days"]) + 3 - inventory_coverage_days)
            node = AffectedNode(
                business_id=target_id,
                severity=_severity(dependency_ratio, stockout_days),
                dependency_ratio=round(dependency_ratio, 2),
                estimated_stockout_days=stockout_days,
            )
            previous = affected_by_id.get(target_id)
            if previous is None or node.dependency_ratio > previous.dependency_ratio:
                affected_by_id[target_id] = node
            if target["type"] in {"distributor", "wholesaler"}:
                queue.append((target_id, depth + 1))

    affected_nodes = sorted(affected_by_id.values(), key=lambda node: (node.severity != "red", node.business_id))
    affected_smes = [node for node in affected_nodes if businesses[node.business_id]["type"] == "retailer"]
    avg_stockout = sum(node.estimated_stockout_days for node in affected_smes) / max(1, len(affected_smes))
    average_unit_price_proxy = 24_000
    impact = ShockImpact(
        affected_sme_count=len(affected_smes),
        monthly_volume_at_risk=monthly_volume_at_risk,
        estimated_revenue_at_risk=monthly_volume_at_risk * average_unit_price_proxy,
        avg_stockout_days=round(avg_stockout, 2),
    )
    return ShockResult(
        shock_node=shock_business_id,
        affected_nodes=affected_nodes,
        affected_edges=sorted(set(affected_edges)),
        impact=impact,
    )
