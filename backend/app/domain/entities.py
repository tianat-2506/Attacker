from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _get(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return value if value is not None else default


def _bucket(value: int, steps: tuple[int, ...]) -> str:
    for step in steps:
        if value <= step:
            return f"<= {step:,}"
    return f"> {steps[-1]:,}"


@dataclass(frozen=True)
class Business:
    business_id: str
    name: str
    type: str
    industry: str
    product_category: str
    province: str
    lat: float
    lng: float
    scale: str
    monthly_revenue: int
    capacity: int
    financial_health_score: int
    supply_risk_score: int

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "Business":
        return cls(
            business_id=str(_get(row, "business_id")),
            name=str(_get(row, "name")),
            type=str(_get(row, "type")),
            industry=str(_get(row, "industry")),
            product_category=str(_get(row, "product_category")),
            province=str(_get(row, "province")),
            lat=float(_get(row, "lat", 0)),
            lng=float(_get(row, "lng", 0)),
            scale=str(_get(row, "scale", "")),
            monthly_revenue=int(_get(row, "monthly_revenue", 0)),
            capacity=int(_get(row, "capacity", 0)),
            financial_health_score=int(_get(row, "financial_health_score", 0)),
            supply_risk_score=int(_get(row, "supply_risk_score", 0)),
        )

    def to_domain(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "name": self.name,
            "type": self.type,
            "industry": self.industry,
            "product_category": self.product_category,
            "province": self.province,
            "lat": self.lat,
            "lng": self.lng,
            "scale": self.scale,
            "monthly_revenue": self.monthly_revenue,
            "capacity": self.capacity,
            "financial_health_score": self.financial_health_score,
            "supply_risk_score": self.supply_risk_score,
        }

    def to_api_node(self, masked: bool = False) -> dict[str, Any]:
        display_name = f"{self.type.title()} {self.business_id[-3:]}" if masked else self.name
        revenue = 0 if masked else round(self.monthly_revenue / 1_000_000_000, 2)
        monthly_revenue = 0 if masked else self.monthly_revenue
        capacity = 0 if masked else self.capacity
        health = 0 if masked else self.financial_health_score
        risk = 0 if masked else self.supply_risk_score
        return {
            "id": self.business_id,
            "business_id": self.business_id,
            "name": display_name,
            "legal_name": self.name if not masked else None,
            "label": display_name,
            "type": self.type,
            "industry": self.industry,
            "province": self.province,
            "category": self.product_category,
            "lat": round(self.lat, 1) if masked else self.lat,
            "lng": round(self.lng, 1) if masked else self.lng,
            "scale": self.scale,
            "revenue": revenue,
            "monthly_revenue": monthly_revenue,
            "revenue_band": _bucket(self.monthly_revenue, (500_000_000, 1_000_000_000, 3_000_000_000, 7_000_000_000)),
            "capacity": capacity,
            "capacity_band": _bucket(self.capacity, (10_000, 50_000, 100_000, 200_000)),
            "health": health,
            "financial_health_score": health,
            "risk": risk,
            "supply_risk_score": risk,
            "risk_level": "masked" if masked else self.risk_level,
            "size": 12 if masked else 10 + min(18, self.monthly_revenue // 550_000_000),
            "masked": masked,
        }

    @property
    def risk_level(self) -> str:
        if self.supply_risk_score >= 70:
            return "red"
        if self.supply_risk_score >= 40:
            return "yellow"
        return "green"


@dataclass(frozen=True)
class SupplyEdge:
    edge_id: str
    source_id: str
    target_id: str
    product: str
    product_category: str
    monthly_volume: int
    lead_time_days: int
    transport_cost: int
    reliability: float
    payment_term_days: int

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "SupplyEdge":
        return cls(
            edge_id=str(_get(row, "edge_id")),
            source_id=str(_get(row, "source_id")),
            target_id=str(_get(row, "target_id")),
            product=str(_get(row, "product")),
            product_category=str(_get(row, "product_category")),
            monthly_volume=int(_get(row, "monthly_volume", 0)),
            lead_time_days=int(_get(row, "lead_time_days", 0)),
            transport_cost=int(_get(row, "transport_cost", 0)),
            reliability=float(_get(row, "reliability", 0)),
            payment_term_days=int(_get(row, "payment_term_days", 0)),
        )

    def to_domain(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "product": self.product,
            "product_category": self.product_category,
            "monthly_volume": self.monthly_volume,
            "lead_time_days": self.lead_time_days,
            "transport_cost": self.transport_cost,
            "reliability": self.reliability,
            "payment_term_days": self.payment_term_days,
        }

    def to_api_edge(self, masked: bool = False) -> dict[str, Any]:
        monthly_volume = 0 if masked else self.monthly_volume
        transport_cost = 0 if masked else self.transport_cost
        payment_term_days = 0 if masked else self.payment_term_days
        return {
            "id": self.edge_id,
            "edge_id": self.edge_id,
            "sourceId": self.source_id,
            "targetId": self.target_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "product": self.product,
            "category": self.product_category,
            "product_category": self.product_category,
            "volume": monthly_volume,
            "monthly_volume": monthly_volume,
            "volume_band": _bucket(self.monthly_volume, (5_000, 10_000, 25_000, 50_000, 100_000)),
            "leadTimeDays": self.lead_time_days,
            "lead_time_days": self.lead_time_days,
            "transport_cost": transport_cost,
            "reliability": self.reliability,
            "payment_term_days": payment_term_days,
            "masked": masked,
        }


@dataclass(frozen=True)
class FinancialSnapshot:
    business_id: str
    month: str
    cash_in: int
    cash_out: int
    revenue: int
    debt: int
    accounts_receivable: int
    accounts_payable: int
    inventory_value: int
    late_payment_rate: float
    delivery_delay_rate: float

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "FinancialSnapshot":
        return cls(
            business_id=str(_get(row, "business_id")),
            month=str(_get(row, "month")),
            cash_in=int(_get(row, "cash_in", 0)),
            cash_out=int(_get(row, "cash_out", 0)),
            revenue=int(_get(row, "revenue", 0)),
            debt=int(_get(row, "debt", 0)),
            accounts_receivable=int(_get(row, "accounts_receivable", 0)),
            accounts_payable=int(_get(row, "accounts_payable", 0)),
            inventory_value=int(_get(row, "inventory_value", 0)),
            late_payment_rate=float(_get(row, "late_payment_rate", 0)),
            delivery_delay_rate=float(_get(row, "delivery_delay_rate", 0)),
        )

    def to_domain(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "month": self.month,
            "cash_in": self.cash_in,
            "cash_out": self.cash_out,
            "revenue": self.revenue,
            "debt": self.debt,
            "accounts_receivable": self.accounts_receivable,
            "accounts_payable": self.accounts_payable,
            "inventory_value": self.inventory_value,
            "late_payment_rate": self.late_payment_rate,
            "delivery_delay_rate": self.delivery_delay_rate,
        }


@dataclass(frozen=True)
class Product:
    business_id: str
    sku: str
    product_name: str
    category: str
    specification: str
    available_capacity: int
    min_order_value: int
    price_range: str
    certifications: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "Product":
        return cls(
            business_id=str(_get(row, "business_id")),
            sku=str(_get(row, "sku")),
            product_name=str(_get(row, "product_name")),
            category=str(_get(row, "category")),
            specification=str(_get(row, "specification")),
            available_capacity=int(_get(row, "available_capacity", 0)),
            min_order_value=int(_get(row, "min_order_value", 0)),
            price_range=str(_get(row, "price_range")),
            certifications=str(_get(row, "certifications", "")),
        )

    def to_domain(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "sku": self.sku,
            "product_name": self.product_name,
            "category": self.category,
            "specification": self.specification,
            "available_capacity": self.available_capacity,
            "min_order_value": self.min_order_value,
            "price_range": self.price_range,
            "certifications": self.certifications,
        }


@dataclass(frozen=True)
class InvoiceVerification:
    invoice_id: str
    seller_id: str
    buyer_id: str
    amount: int
    issue_date: str
    due_date: str
    invoice_hash: str
    funding_status: str
    confirmed_by: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "InvoiceVerification":
        return cls(
            invoice_id=str(_get(row, "invoice_id")),
            seller_id=str(_get(row, "seller_id")),
            buyer_id=str(_get(row, "buyer_id")),
            amount=int(_get(row, "amount", 0)),
            issue_date=str(_get(row, "issue_date")),
            due_date=str(_get(row, "due_date")),
            invoice_hash=str(_get(row, "invoice_hash")),
            funding_status=str(_get(row, "funding_status")),
            confirmed_by=str(_get(row, "confirmed_by")),
        )

    def to_domain(self) -> dict[str, Any]:
        return {
            "invoice_id": self.invoice_id,
            "seller_id": self.seller_id,
            "buyer_id": self.buyer_id,
            "amount": self.amount,
            "issue_date": self.issue_date,
            "due_date": self.due_date,
            "invoice_hash": self.invoice_hash,
            "funding_status": self.funding_status,
            "confirmed_by": self.confirmed_by,
        }


@dataclass(frozen=True)
class ConsentRecord:
    consent_id: str
    actor_id: str
    subject_id: str
    scope: str
    purpose: str
    status: str
    expires_at: str | None = None
    revoked_at: str | None = None


@dataclass(frozen=True)
class AuditLog:
    event_id: str
    event_type: str
    actor_id: str
    actor_role: str
    subject_id: str
    purpose: str
    timestamp: str
    request_id: str
