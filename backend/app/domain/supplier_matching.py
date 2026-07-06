from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


MATCH_WEIGHTS = {
    "product_spec_fit": 0.25,
    "capacity_fit": 0.20,
    "distance_score": 0.15,
    "financial_health_score": 0.15,
    "delivery_reliability": 0.10,
    "payment_term_fit": 0.10,
    "price_score": 0.05,
}


@dataclass(frozen=True)
class SupplierRecommendation:
    supplier_id: str
    supplier_name: str
    match_score: int
    components: dict[str, float]
    reason_codes: list[str]
    new_edge_preview: dict[str, Any]


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _avg_source_metric(edges: list[dict[str, Any]], supplier_id: str, category: str, field: str, default: float) -> float:
    source_edges = [edge for edge in edges if edge["source_id"] == supplier_id and edge["product_category"] == category]
    if not source_edges:
        return default
    return sum(float(edge[field]) for edge in source_edges) / len(source_edges)


def _product_fit(product: dict[str, Any], product_category: str, product_specification: str | None) -> float:
    if product["category"] != product_category:
        return 0
    if not product_specification:
        return 85
    required_terms = {term.strip().lower() for term in product_specification.replace(",", ";").split(";") if term.strip()}
    actual_terms = product["specification"].lower()
    if not required_terms:
        return 85
    matches = sum(1 for term in required_terms if term in actual_terms)
    return clamp(70 + (matches / len(required_terms)) * 30)


def _payment_fit(candidate_term: float, preferred_term: int) -> float:
    if candidate_term >= preferred_term:
        return 100
    if candidate_term >= preferred_term - 15:
        return 70
    if candidate_term > 0:
        return 50
    return 30


def _price_score(price_range: str) -> float:
    return {"low": 95, "mid": 82, "premium": 68}.get(price_range, 70)


def _reason_codes(components: dict[str, float], product: dict[str, Any], lead_time: float, payment_term: float) -> list[str]:
    reasons = []
    if components["product_spec_fit"] >= 85:
        reasons.append(f"Dung product/spec: {product['product_name']}")
    if components["capacity_fit"] >= 80:
        reasons.append(f"Con capacity {product['available_capacity']:,} units/month")
    if components["distance_score"] >= 70:
        reasons.append("Khoang cach logistics phu hop")
    if components["delivery_reliability"] >= 85:
        reasons.append(f"Delivery reliability {components['delivery_reliability']:.0f}%")
    if components["payment_term_fit"] >= 90:
        reasons.append(f"Chap nhan payment term {int(payment_term)} ngay")
    if not reasons:
        reasons.append(f"Lead time du kien {int(round(lead_time))} ngay, can review them")
    return reasons[:4]


def rank_suppliers(
    buyer_id: str,
    disrupted_supplier_id: str,
    product_category: str,
    required_monthly_volume: int,
    businesses: dict[str, dict[str, Any]],
    products: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    product_specification: str | None = None,
    preferred_payment_term_days: int = 30,
    max_lead_time_days: int = 4,
    top_k: int = 3,
) -> list[SupplierRecommendation]:
    if buyer_id not in businesses:
        raise ValueError(f"Unknown buyer_id {buyer_id}")
    buyer = businesses[buyer_id]
    recommendations: list[SupplierRecommendation] = []

    for product in products:
        supplier_id = product["business_id"]
        if supplier_id == buyer_id or supplier_id == disrupted_supplier_id:
            continue
        supplier = businesses.get(supplier_id)
        if not supplier or supplier["type"] in {"retailer", "financial_partner"}:
            continue
        if supplier["supply_risk_score"] >= 85:
            continue

        product_fit = _product_fit(product, product_category, product_specification)
        if product_fit <= 0:
            continue

        capacity_fit = clamp(float(product["available_capacity"]) / max(1, required_monthly_volume) * 100)
        if capacity_fit < 50:
            continue

        distance = haversine_km(float(buyer["lat"]), float(buyer["lng"]), float(supplier["lat"]), float(supplier["lng"]))
        distance_score = clamp(100 - (distance / 220) * 100)
        avg_lead = _avg_source_metric(edges, supplier_id, product_category, "lead_time_days", max(1, distance / 80))
        if avg_lead > max_lead_time_days * 2:
            continue

        reliability = _avg_source_metric(edges, supplier_id, product_category, "reliability", 0.80) * 100
        payment_term = _avg_source_metric(edges, supplier_id, product_category, "payment_term_days", 15)
        components = {
            "product_spec_fit": product_fit,
            "capacity_fit": capacity_fit,
            "distance_score": distance_score,
            "financial_health_score": float(supplier["financial_health_score"]),
            "delivery_reliability": clamp(reliability),
            "payment_term_fit": _payment_fit(payment_term, preferred_payment_term_days),
            "price_score": _price_score(str(product["price_range"])),
        }
        score = sum(components[name] * weight for name, weight in MATCH_WEIGHTS.items())
        recommendations.append(
            SupplierRecommendation(
                supplier_id=supplier_id,
                supplier_name=str(supplier["name"]),
                match_score=round(score),
                components={name: round(value, 2) for name, value in components.items()},
                reason_codes=_reason_codes(components, product, avg_lead, payment_term),
                new_edge_preview={
                    "source_id": supplier_id,
                    "target_id": buyer_id,
                    "product": product["product_name"],
                    "product_category": product_category,
                    "lead_time_days": round(avg_lead, 1),
                },
            )
        )

    recommendations.sort(key=lambda item: (-item.match_score, item.new_edge_preview["lead_time_days"], item.supplier_name))
    return recommendations[:top_k]
