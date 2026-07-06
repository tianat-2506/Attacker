from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REQUIRED_FILES = {
    "businesses": DATA_DIR / "businesses.csv",
    "supply_edges": DATA_DIR / "supply_edges.csv",
    "financials": DATA_DIR / "financials.csv",
    "products": DATA_DIR / "products.csv",
}
VALID_TYPES = {"manufacturer", "distributor", "wholesaler", "retailer", "logistics_partner", "financial_partner"}
VALID_PROVINCES = {"TP.HCM", "Binh Duong", "Dong Nai", "Lam Dong"}
VALID_CATEGORIES = {"beverage", "packaged_food", "processed_agri", "cold_chain_food", "finance"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def downstream_retailers(shock_id: str, businesses: dict[str, dict[str, str]], edges: list[dict[str, str]], category: str) -> set[str]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge["product_category"] == category:
            adjacency[edge["source_id"]].append(edge["target_id"])

    affected: set[str] = set()
    queue: deque[str] = deque([shock_id])
    visited: set[str] = set()
    while queue:
        source = queue.popleft()
        if source in visited:
            continue
        visited.add(source)
        for target in adjacency.get(source, []):
            business = businesses[target]
            if business["type"] == "retailer":
                affected.add(target)
            if business["type"] in {"distributor", "wholesaler"}:
                queue.append(target)
    return affected


def validate() -> list[str]:
    errors: list[str] = []
    for name, path in REQUIRED_FILES.items():
        if not path.exists():
            fail(errors, f"Missing {name}: {path}")
    if errors:
        return errors

    businesses_rows = read_csv(REQUIRED_FILES["businesses"])
    edges = read_csv(REQUIRED_FILES["supply_edges"])
    financials = read_csv(REQUIRED_FILES["financials"])
    products = read_csv(REQUIRED_FILES["products"])
    businesses = {row["business_id"]: row for row in businesses_rows}

    if len(businesses_rows) != 62:
        fail(errors, f"Expected 62 businesses, got {len(businesses_rows)}")
    if len(edges) != 120:
        fail(errors, f"Expected 120 edges, got {len(edges)}")

    ids = [row["business_id"] for row in businesses_rows]
    if len(ids) != len(set(ids)):
        fail(errors, "business_id values must be unique")

    for row in businesses_rows:
        if row["type"] not in VALID_TYPES:
            fail(errors, f"Invalid type for {row['business_id']}: {row['type']}")
        if row["province"] not in VALID_PROVINCES:
            fail(errors, f"Invalid province for {row['business_id']}: {row['province']}")
        if row["product_category"] not in VALID_CATEGORIES:
            fail(errors, f"Invalid category for {row['business_id']}: {row['product_category']}")
        lat = float(row["lat"])
        lng = float(row["lng"])
        if not (10.4 <= lat <= 12.2 and 106.2 <= lng <= 108.8):
            fail(errors, f"Lat/lng out of MVP bbox for {row['business_id']}")

    edge_ids = [row["edge_id"] for row in edges]
    if len(edge_ids) != len(set(edge_ids)):
        fail(errors, "edge_id values must be unique")

    for edge in edges:
        if edge["source_id"] not in businesses:
            fail(errors, f"Unknown source_id {edge['source_id']}")
        if edge["target_id"] not in businesses:
            fail(errors, f"Unknown target_id {edge['target_id']}")
        if edge["source_id"] == edge["target_id"]:
            fail(errors, f"Self-loop edge {edge['edge_id']}")
        reliability = float(edge["reliability"])
        if not (0 <= reliability <= 1):
            fail(errors, f"Reliability out of range in {edge['edge_id']}")
        if int(edge["monthly_volume"]) <= 0:
            fail(errors, f"monthly_volume must be positive in {edge['edge_id']}")

    months_by_business: dict[str, Counter[str]] = defaultdict(Counter)
    for row in financials:
        if row["business_id"] not in businesses:
            fail(errors, f"Unknown financial business_id {row['business_id']}")
        months_by_business[row["business_id"]][row["month"]] += 1
        for field in ["cash_in", "cash_out", "revenue", "debt", "accounts_receivable", "accounts_payable", "inventory_value"]:
            if int(row[field]) < 0:
                fail(errors, f"{field} negative for {row['business_id']} {row['month']}")
        for field in ["late_payment_rate", "delivery_delay_rate"]:
            value = float(row[field])
            if not (0 <= value <= 1):
                fail(errors, f"{field} out of range for {row['business_id']} {row['month']}")

    for business_id in businesses:
        if len(months_by_business[business_id]) != 12:
            fail(errors, f"{business_id} must have 12 financial months")
        duplicates = [month for month, count in months_by_business[business_id].items() if count > 1]
        if duplicates:
            fail(errors, f"{business_id} duplicate financial months: {duplicates}")

    product_businesses = {row["business_id"] for row in products}
    for business_id, row in businesses.items():
        if row["type"] != "financial_partner" and business_id not in product_businesses:
            fail(errors, f"{business_id} missing product row")
    for row in products:
        if row["business_id"] not in businesses:
            fail(errors, f"Unknown product business_id {row['business_id']}")
        if row["category"] not in VALID_CATEGORIES - {"finance"}:
            fail(errors, f"Invalid product category for {row['business_id']}")
        if int(row["available_capacity"]) <= 0:
            fail(errors, f"available_capacity must be positive for {row['business_id']}")

    affected = downstream_retailers("BIZ-005", businesses, edges, "beverage")
    if len(affected) < 12:
        fail(errors, f"BIZ-005 shock must affect at least 12 beverage retailers, got {len(affected)}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Data validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Data validation passed: 62 businesses, 120 edges, 12 months financials, BIZ-005 shock scenario ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
