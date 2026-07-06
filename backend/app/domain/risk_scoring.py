from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RISK_WEIGHTS = {
    "cashflow_risk": 0.25,
    "late_payment_risk": 0.20,
    "inventory_risk": 0.15,
    "delivery_delay_risk": 0.15,
    "debt_risk": 0.15,
    "dependency_risk": 0.10,
}


@dataclass(frozen=True)
class RiskDriver:
    feature: str
    value: float
    weight: float
    contribution: float
    message: str


@dataclass(frozen=True)
class RiskResult:
    score: int
    level: str
    drivers: list[RiskDriver]
    explanation: str
    formula_version: str = "risk-v1"


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def classify_level(score: float) -> str:
    if score < 40:
        return "green"
    if score < 70:
        return "yellow"
    return "red"


def _message(feature: str, value: float) -> str:
    messages = {
        "cashflow_risk": "Dong tien vao giam hoac net cash flow am trong cac thang gan nhat.",
        "late_payment_risk": "Ty le thanh toan tre cao, cho thay cong no thu hoi cham.",
        "inventory_risk": "Ton kho cao so voi doanh thu, dong tien co the bi khoa trong hang.",
        "delivery_delay_risk": "Ty le giao hang tre tang, lam rui ro dut gay downstream cao hon.",
        "debt_risk": "No cao so voi doanh thu, tao ap luc thanh toan ngan han.",
        "dependency_risk": "Nhieu buyer downstream phu thuoc vao node nay.",
    }
    return messages[feature]


def score_from_features(features: dict[str, float]) -> RiskResult:
    normalized = {name: clamp(float(features.get(name, 0))) for name in RISK_WEIGHTS}
    score = sum(normalized[name] * weight for name, weight in RISK_WEIGHTS.items())
    drivers = [
        RiskDriver(
            feature=name,
            value=round(normalized[name], 2),
            weight=weight,
            contribution=round(normalized[name] * weight, 2),
            message=_message(name, normalized[name]),
        )
        for name, weight in RISK_WEIGHTS.items()
    ]
    drivers.sort(key=lambda driver: driver.contribution, reverse=True)
    top_drivers = drivers[:3]
    level = classify_level(score)
    explanation = render_explanation(level, top_drivers)
    return RiskResult(score=round(score), level=level, drivers=top_drivers, explanation=explanation)


def render_explanation(level: str, drivers: list[RiskDriver]) -> str:
    level_text = {"green": "rui ro thap", "yellow": "can theo doi", "red": "rui ro cao"}[level]
    driver_names = ", ".join(driver.feature.replace("_", " ") for driver in drivers)
    return f"Doanh nghiep dang o muc {level_text}. Cac tac nhan chinh: {driver_names}."


def features_from_financials(
    financial_rows: list[dict[str, Any]],
    downstream_count: int = 0,
    monthly_volume_supplied: int = 0,
) -> dict[str, float]:
    if not financial_rows:
        return {name: 50 for name in RISK_WEIGHTS}

    rows = sorted(financial_rows, key=lambda row: row["month"])
    latest = rows[-1]
    prev = rows[-4:-1] if len(rows) >= 4 else rows[:-1]
    previous_cash_in = sum(float(row["cash_in"]) for row in prev) / max(1, len(prev))
    latest_cash_in = float(latest["cash_in"])
    cash_drop = 0 if previous_cash_in == 0 else max(0, (previous_cash_in - latest_cash_in) / previous_cash_in)
    net_cash_flow = float(latest["cash_in"]) - float(latest["cash_out"])
    net_margin_pressure = max(0, -net_cash_flow / max(1, float(latest["revenue"])))
    cashflow_risk = clamp(cash_drop * 220 + net_margin_pressure * 180)

    late_payment_risk = clamp(float(latest["late_payment_rate"]) * 400)
    inventory_ratio = float(latest["inventory_value"]) / max(1, float(latest["revenue"]))
    inventory_risk = clamp((inventory_ratio - 0.12) * 300)
    delivery_delay_risk = clamp(float(latest["delivery_delay_rate"]) * 500)
    debt_ratio = float(latest["debt"]) / max(1, float(latest["revenue"]))
    debt_risk = clamp((debt_ratio - 0.18) * 180)
    dependency_risk = clamp(downstream_count * 5 + monthly_volume_supplied / 2_000)

    return {
        "cashflow_risk": cashflow_risk,
        "late_payment_risk": late_payment_risk,
        "inventory_risk": inventory_risk,
        "delivery_delay_risk": delivery_delay_risk,
        "debt_risk": debt_risk,
        "dependency_risk": dependency_risk,
    }


def calculate_business_risk(
    business_id: str,
    financial_rows: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    product_category: str | None = None,
) -> RiskResult:
    outgoing = [
        edge
        for edge in edges
        if edge["source_id"] == business_id and (product_category is None or edge["product_category"] == product_category)
    ]
    downstream_count = len({edge["target_id"] for edge in outgoing})
    monthly_volume = sum(int(edge["monthly_volume"]) for edge in outgoing)
    features = features_from_financials(financial_rows, downstream_count, monthly_volume)
    return score_from_features(features)
