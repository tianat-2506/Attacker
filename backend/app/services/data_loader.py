from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _to_int(row: dict[str, str], fields: list[str]) -> None:
    for field in fields:
        row[field] = int(row[field])  # type: ignore[assignment]


def _to_float(row: dict[str, str], fields: list[str]) -> None:
    for field in fields:
        row[field] = float(row[field])  # type: ignore[assignment]


def load_data(data_dir: Path | None = None) -> dict[str, Any]:
    base = data_dir or DATA_DIR
    businesses = _read_csv(base / "businesses.csv")
    edges = _read_csv(base / "supply_edges.csv")
    financials = _read_csv(base / "financials.csv")
    products = _read_csv(base / "products.csv")
    invoices_path = base / "invoice_verifications.csv"
    invoices = _read_csv(invoices_path) if invoices_path.exists() else []
    contracts_path = base / "contracts.csv"
    contracts = _read_csv(contracts_path) if contracts_path.exists() else []
    purchase_orders_path = base / "purchase_orders.csv"
    purchase_orders = _read_csv(purchase_orders_path) if purchase_orders_path.exists() else []
    delivery_notes_path = base / "delivery_notes.csv"
    delivery_notes = _read_csv(delivery_notes_path) if delivery_notes_path.exists() else []
    certifications_path = base / "certifications.csv"
    certifications = _read_csv(certifications_path) if certifications_path.exists() else []
    guarantees_path = base / "guarantees.csv"
    guarantees = _read_csv(guarantees_path) if guarantees_path.exists() else []

    for row in businesses:
        _to_float(row, ["lat", "lng"])
        _to_int(row, ["monthly_revenue", "capacity", "financial_health_score", "supply_risk_score"])

    for row in edges:
        _to_int(row, ["monthly_volume", "lead_time_days", "transport_cost", "payment_term_days"])
        _to_float(row, ["reliability"])

    for row in financials:
        _to_int(row, ["cash_in", "cash_out", "revenue", "debt", "accounts_receivable", "accounts_payable", "inventory_value"])
        _to_float(row, ["late_payment_rate", "delivery_delay_rate"])

    for row in products:
        _to_int(row, ["available_capacity", "min_order_value"])

    for row in invoices:
        _to_int(row, ["amount"])

    for row in contracts:
        _to_int(row, ["payment_term_days", "sla_lead_time_days"])
        row["has_exclusivity"] = row["has_exclusivity"].lower() == "true"
        row["has_backup_supplier_clause"] = row["has_backup_supplier_clause"].lower() == "true"

    for row in purchase_orders:
        _to_int(row, ["quantity", "value"])

    for row in delivery_notes:
        _to_int(row, ["delivered_quantity", "delay_days"])
        row["verified_by_buyer"] = row["verified_by_buyer"].lower() == "true"
        row["logistics_confirmed"] = row["logistics_confirmed"].lower() == "true"

    for row in guarantees:
        _to_int(row, ["amount"])

    return {
        "businesses": {row["business_id"]: row for row in businesses},
        "business_list": businesses,
        "edges": edges,
        "financials": financials,
        "products": products,
        "invoices": invoices,
        "contracts": contracts,
        "purchase_orders": purchase_orders,
        "delivery_notes": delivery_notes,
        "certifications": certifications,
        "guarantees": guarantees,
    }


def financials_for_business(financials: list[dict[str, Any]], business_id: str) -> list[dict[str, Any]]:
    rows = [row for row in financials if row["business_id"] == business_id]
    return sorted(rows, key=lambda row: row["month"])


def products_by_business(products: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for product in products:
        grouped.setdefault(product["business_id"], []).append(product)
    return grouped


def outgoing_edges(edges: list[dict[str, Any]], business_id: str, product_category: str | None = None) -> list[dict[str, Any]]:
    return [
        edge
        for edge in edges
        if edge["source_id"] == business_id and (product_category is None or edge["product_category"] == product_category)
    ]


def incoming_edges(edges: list[dict[str, Any]], business_id: str, product_category: str | None = None) -> list[dict[str, Any]]:
    return [
        edge
        for edge in edges
        if edge["target_id"] == business_id and (product_category is None or edge["product_category"] == product_category)
    ]
