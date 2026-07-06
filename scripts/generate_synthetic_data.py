from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MONTHS = [
    "2025-06",
    "2025-07",
    "2025-08",
    "2025-09",
    "2025-10",
    "2025-11",
    "2025-12",
    "2026-01",
    "2026-02",
    "2026-03",
    "2026-04",
    "2026-05",
]


@dataclass(frozen=True)
class BusinessSeed:
    business_id: str
    name: str
    type: str
    province: str
    product_category: str
    scale: str
    lat: float
    lng: float


BUSINESSES: list[BusinessSeed] = [
    BusinessSeed("BIZ-001", "Highland Agri Foods", "manufacturer", "Lam Dong", "processed_agri", "large", 11.9404, 108.4583),
    BusinessSeed("BIZ-002", "Saigon NutriDrink", "manufacturer", "TP.HCM", "beverage", "large", 10.7769, 106.7009),
    BusinessSeed("BIZ-003", "Dong Nai Packaged Food", "manufacturer", "Dong Nai", "packaged_food", "large", 10.9574, 106.8427),
    BusinessSeed("BIZ-004", "Binh Duong Cold Chain Foods", "manufacturer", "Binh Duong", "cold_chain_food", "medium", 10.9804, 106.6519),
    BusinessSeed("BIZ-005", "Dai Tin Distribution", "distributor", "Binh Duong", "beverage", "medium", 10.9951, 106.6792),
    BusinessSeed("BIZ-006", "Mekong Fresh Distributor", "distributor", "TP.HCM", "processed_agri", "medium", 10.8231, 106.6297),
    BusinessSeed("BIZ-007", "An Phu FMCG Hub", "distributor", "Dong Nai", "beverage", "medium", 10.9467, 106.8243),
    BusinessSeed("BIZ-008", "Dalat Pure Foods", "distributor", "Lam Dong", "processed_agri", "small", 11.9333, 108.4210),
    BusinessSeed("BIZ-009", "Thu Duc Retail Mart", "retailer", "TP.HCM", "beverage", "small", 10.8494, 106.7537),
    BusinessSeed("BIZ-010", "Bien Hoa Mini Market", "retailer", "Dong Nai", "packaged_food", "micro", 10.9576, 106.8426),
    BusinessSeed("BIZ-011", "Di An Convenience", "retailer", "Binh Duong", "beverage", "small", 10.9068, 106.7694),
    BusinessSeed("BIZ-012", "Bao Loc Specialty Store", "retailer", "Lam Dong", "processed_agri", "micro", 11.5481, 107.8077),
    BusinessSeed("BIZ-013", "Gia Dinh Beverage Supply", "distributor", "TP.HCM", "beverage", "medium", 10.8032, 106.6960),
    BusinessSeed("BIZ-014", "Tan Uyen FMCG Distribution", "distributor", "Binh Duong", "packaged_food", "medium", 11.0636, 106.7897),
    BusinessSeed("BIZ-015", "Xuan Loc Agri Trade", "distributor", "Dong Nai", "processed_agri", "small", 10.9397, 107.2452),
    BusinessSeed("BIZ-016", "Duc Trong Food Link", "distributor", "Lam Dong", "processed_agri", "small", 11.7356, 108.3681),
    BusinessSeed("BIZ-017", "Song Than Cold Logistics", "logistics_partner", "Binh Duong", "cold_chain_food", "medium", 10.9041, 106.7450),
    BusinessSeed("BIZ-018", "Nha Be Grocery Supply", "distributor", "TP.HCM", "packaged_food", "medium", 10.6956, 106.7404),
    BusinessSeed("BIZ-019", "Trang Bom Beverage Link", "distributor", "Dong Nai", "beverage", "small", 10.9537, 107.0067),
    BusinessSeed("BIZ-020", "Da Lat Dairy Route", "distributor", "Lam Dong", "cold_chain_food", "small", 11.9400, 108.4380),
    BusinessSeed("BIZ-021", "Cho Lon Wholesale Foods", "wholesaler", "TP.HCM", "packaged_food", "small", 10.7521, 106.6635),
    BusinessSeed("BIZ-022", "Go Vap Beverage Agent", "wholesaler", "TP.HCM", "beverage", "small", 10.8387, 106.6653),
    BusinessSeed("BIZ-023", "Thu Duc Agri Agent", "wholesaler", "TP.HCM", "processed_agri", "small", 10.8442, 106.7684),
    BusinessSeed("BIZ-024", "Ben Cat FMCG Wholesale", "wholesaler", "Binh Duong", "packaged_food", "small", 11.1517, 106.6070),
    BusinessSeed("BIZ-025", "Thuan An Beverage Agent", "wholesaler", "Binh Duong", "beverage", "small", 10.9316, 106.7110),
    BusinessSeed("BIZ-026", "Bau Bang Cold Agent", "wholesaler", "Binh Duong", "cold_chain_food", "micro", 11.2673, 106.6248),
    BusinessSeed("BIZ-027", "Long Thanh Food Wholesale", "wholesaler", "Dong Nai", "packaged_food", "small", 10.7895, 106.9490),
    BusinessSeed("BIZ-028", "Nhon Trach Beverage Agent", "wholesaler", "Dong Nai", "beverage", "small", 10.6952, 106.8831),
    BusinessSeed("BIZ-029", "Tan Phu Agri Wholesale", "wholesaler", "Dong Nai", "processed_agri", "micro", 11.1086, 107.4076),
    BusinessSeed("BIZ-030", "Da Lat Specialty Agent", "wholesaler", "Lam Dong", "processed_agri", "small", 11.9345, 108.4252),
    BusinessSeed("BIZ-031", "Bao Loc Coffee Agent", "wholesaler", "Lam Dong", "processed_agri", "micro", 11.5491, 107.8070),
    BusinessSeed("BIZ-032", "Duc Trong Dairy Agent", "wholesaler", "Lam Dong", "cold_chain_food", "small", 11.7351, 108.3730),
    BusinessSeed("BIZ-033", "Phu Nhuan Snack Agent", "wholesaler", "TP.HCM", "packaged_food", "micro", 10.7992, 106.6804),
    BusinessSeed("BIZ-034", "Bien Hoa Cold Chain Agent", "wholesaler", "Dong Nai", "cold_chain_food", "small", 10.9658, 106.8345),
    BusinessSeed("BIZ-035", "District 1 Mini Mart", "retailer", "TP.HCM", "beverage", "micro", 10.7758, 106.7004),
    BusinessSeed("BIZ-036", "District 7 Family Store", "retailer", "TP.HCM", "packaged_food", "micro", 10.7356, 106.7218),
    BusinessSeed("BIZ-037", "Binh Thanh Organic Shop", "retailer", "TP.HCM", "processed_agri", "micro", 10.8106, 106.7091),
    BusinessSeed("BIZ-038", "Tan Phu Convenience", "retailer", "TP.HCM", "beverage", "micro", 10.7902, 106.6282),
    BusinessSeed("BIZ-039", "Hoc Mon Grocery", "retailer", "TP.HCM", "packaged_food", "micro", 10.8835, 106.5864),
    BusinessSeed("BIZ-040", "Thu Duc Milk Corner", "retailer", "TP.HCM", "cold_chain_food", "micro", 10.8482, 106.7721),
    BusinessSeed("BIZ-041", "Thuan An Family Mart", "retailer", "Binh Duong", "beverage", "micro", 10.9330, 106.7122),
    BusinessSeed("BIZ-042", "Ben Cat Grocery", "retailer", "Binh Duong", "packaged_food", "micro", 11.1535, 106.6074),
    BusinessSeed("BIZ-043", "Tan Uyen Organic Store", "retailer", "Binh Duong", "processed_agri", "micro", 11.0638, 106.7906),
    BusinessSeed("BIZ-044", "Di An Milk Store", "retailer", "Binh Duong", "cold_chain_food", "micro", 10.9061, 106.7707),
    BusinessSeed("BIZ-045", "Bau Bang Mini Mart", "retailer", "Binh Duong", "packaged_food", "micro", 11.2651, 106.6266),
    BusinessSeed("BIZ-046", "Thu Dau Mot Beverage Shop", "retailer", "Binh Duong", "beverage", "small", 10.9801, 106.6555),
    BusinessSeed("BIZ-047", "Bien Hoa Family Foods", "retailer", "Dong Nai", "packaged_food", "micro", 10.9580, 106.8449),
    BusinessSeed("BIZ-048", "Long Khanh Coffee Store", "retailer", "Dong Nai", "processed_agri", "micro", 10.9459, 107.2437),
    BusinessSeed("BIZ-049", "Nhon Trach Mini Mart", "retailer", "Dong Nai", "beverage", "micro", 10.6957, 106.8844),
    BusinessSeed("BIZ-050", "Long Thanh Cold Foods", "retailer", "Dong Nai", "cold_chain_food", "micro", 10.7900, 106.9502),
    BusinessSeed("BIZ-051", "Trang Bom Grocery", "retailer", "Dong Nai", "packaged_food", "micro", 10.9544, 107.0078),
    BusinessSeed("BIZ-052", "Xuan Loc Agri Shop", "retailer", "Dong Nai", "processed_agri", "micro", 10.9401, 107.2461),
    BusinessSeed("BIZ-053", "Da Lat Farm Mart", "retailer", "Lam Dong", "processed_agri", "small", 11.9399, 108.4335),
    BusinessSeed("BIZ-054", "Bao Loc Coffee Corner", "retailer", "Lam Dong", "processed_agri", "micro", 11.5475, 107.8088),
    BusinessSeed("BIZ-055", "Duc Trong Family Store", "retailer", "Lam Dong", "packaged_food", "micro", 11.7344, 108.3712),
    BusinessSeed("BIZ-056", "Lam Ha Beverage Shop", "retailer", "Lam Dong", "beverage", "micro", 11.8010, 108.2388),
    BusinessSeed("BIZ-057", "Don Duong Dairy Store", "retailer", "Lam Dong", "cold_chain_food", "micro", 11.8058, 108.5763),
    BusinessSeed("BIZ-058", "Da Huoai Specialty Mart", "retailer", "Lam Dong", "processed_agri", "micro", 11.4168, 107.6425),
    BusinessSeed("BIZ-059", "Cat Tien Grocery", "retailer", "Lam Dong", "packaged_food", "micro", 11.5875, 107.3932),
    BusinessSeed("BIZ-060", "Lac Duong Farm Goods", "retailer", "Lam Dong", "processed_agri", "micro", 12.0032, 108.4018),
    BusinessSeed("BIZ-061", "VietWorking Capital Partner", "financial_partner", "TP.HCM", "finance", "medium", 10.7810, 106.7050),
    BusinessSeed("BIZ-062", "Saigon Invoice Finance", "financial_partner", "TP.HCM", "finance", "medium", 10.7860, 106.7040),
]


PRODUCTS = {
    "beverage": ("SKU-BEV-1L", "Sua hat dong hop 1L", "UHT, 1L, khong duong", "mid", "HACCP;ISO 22000"),
    "packaged_food": ("SKU-PKG-SNACK", "Snack ngu coc 120g", "Goi 120g, shelf-stable", "mid", "HACCP"),
    "processed_agri": ("SKU-AGR-COFFEE", "Ca phe rang xay 500g", "Arabica/Robusta blend, 500g", "premium", "VietGAP;ISO 22000"),
    "cold_chain_food": ("SKU-COLD-YOGURT", "Sua chua lanh 100g", "2-6C, han dung 21 ngay", "mid", "HACCP;Cold Chain"),
}


def scale_revenue(scale: str, index: int) -> int:
    base = {
        "micro": 360_000_000,
        "small": 780_000_000,
        "medium": 3_000_000_000,
        "large": 6_200_000_000,
    }[scale]
    return base + (index % 9) * base // 12


def scale_capacity(seed: BusinessSeed, index: int) -> int:
    if seed.type == "financial_partner":
        return 0
    base = {
        "micro": 7_000,
        "small": 28_000,
        "medium": 90_000,
        "large": 180_000,
    }[seed.scale]
    return base + (index % 7) * 2_500


def base_health(seed: BusinessSeed, index: int) -> int:
    if seed.business_id == "BIZ-005":
        return 43
    if seed.type == "financial_partner":
        return 88
    base = {"micro": 62, "small": 69, "medium": 73, "large": 79}[seed.scale]
    return min(94, base + (index % 8) - 3)


def base_risk(seed: BusinessSeed, index: int) -> int:
    if seed.business_id == "BIZ-005":
        return 78
    if seed.type == "financial_partner":
        return 18
    return max(12, 100 - base_health(seed, index) + (index % 5) * 2)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stable_hash(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def contract_rows() -> list[dict[str, object]]:
    rows = [
        ("CON-001", "BIZ-002", "BIZ-005", "beverage", "ACTIVE", "2026-01-01", "2026-12-31", 30, 3, False, True, "VERIFIED", "Demo contract register"),
        ("CON-002", "BIZ-005", "BIZ-009", "beverage", "ACTIVE", "2026-01-15", "2026-12-31", 30, 2, False, True, "VERIFIED", "Demo contract register"),
        ("CON-003", "BIZ-005", "BIZ-011", "beverage", "ACTIVE", "2026-02-01", "2026-11-30", 30, 2, False, False, "VERIFIED", "Demo contract register"),
        ("CON-004", "BIZ-007", "BIZ-009", "beverage", "PILOT", "2026-06-01", "2026-09-30", 15, 3, False, True, "VERIFIED", "Demo supplier qualification"),
    ]
    return [
        {
            "contract_id": row[0],
            "supplier_id": row[1],
            "buyer_id": row[2],
            "product_category": row[3],
            "status": row[4],
            "effective_date": row[5],
            "expiry_date": row[6],
            "payment_term_days": row[7],
            "sla_lead_time_days": row[8],
            "has_exclusivity": str(row[9]).lower(),
            "has_backup_supplier_clause": str(row[10]).lower(),
            "verification_status": row[11],
            "source_label": row[12],
            "document_hash": stable_hash(*row),
        }
        for row in rows
    ]


def purchase_order_rows() -> list[dict[str, object]]:
    rows = [
        ("PO-260501", "CON-002", "BIZ-005", "BIZ-009", "SKU-BEV-1L-BIZ-005", "2026-05-01", "2026-05-04", "2026-05-08", 4200, 126_000_000, "DELIVERED_LATE", "VERIFIED"),
        ("PO-260515", "CON-002", "BIZ-005", "BIZ-009", "SKU-BEV-1L-BIZ-005", "2026-05-15", "2026-05-18", "2026-05-23", 3900, 117_000_000, "DELIVERED_LATE", "VERIFIED"),
        ("PO-260601", "CON-002", "BIZ-005", "BIZ-009", "SKU-BEV-1L-BIZ-005", "2026-06-01", "2026-06-04", "2026-06-10", 4600, 138_000_000, "DELIVERED_LATE", "VERIFIED"),
        ("PO-260612", "CON-002", "BIZ-005", "BIZ-009", "SKU-BEV-1L-BIZ-005", "2026-06-12", "2026-06-16", "", 5000, 150_000_000, "OVERDUE_IN_TRANSIT", "PENDING_REVIEW"),
        ("PO-ALT-001", "CON-004", "BIZ-007", "BIZ-009", "SKU-BEV-1L-BIZ-007", "2026-06-03", "2026-06-06", "2026-06-06", 1200, 37_200_000, "DELIVERED_ON_TIME", "VERIFIED"),
    ]
    return [
        {
            "po_id": row[0],
            "contract_id": row[1],
            "supplier_id": row[2],
            "buyer_id": row[3],
            "sku": row[4],
            "order_date": row[5],
            "expected_delivery_date": row[6],
            "actual_delivery_date": row[7],
            "quantity": row[8],
            "value": row[9],
            "status": row[10],
            "verification_status": row[11],
            "document_hash": stable_hash(*row),
        }
        for row in rows
    ]


def delivery_note_rows() -> list[dict[str, object]]:
    rows = [
        ("DN-260508", "PO-260501", "BIZ-005", "BIZ-009", "BIZ-017", "2026-05-08", 4200, 4, True, True, "VERIFIED"),
        ("DN-260523", "PO-260515", "BIZ-005", "BIZ-009", "BIZ-017", "2026-05-23", 3900, 5, True, True, "VERIFIED"),
        ("DN-260610", "PO-260601", "BIZ-005", "BIZ-009", "BIZ-017", "2026-06-10", 4600, 6, True, True, "VERIFIED"),
        ("DN-ALT-001", "PO-ALT-001", "BIZ-007", "BIZ-009", "BIZ-017", "2026-06-06", 1200, 0, True, True, "VERIFIED"),
    ]
    return [
        {
            "delivery_note_id": row[0],
            "po_id": row[1],
            "supplier_id": row[2],
            "buyer_id": row[3],
            "logistics_partner_id": row[4],
            "delivery_date": row[5],
            "delivered_quantity": row[6],
            "delay_days": row[7],
            "verified_by_buyer": str(row[8]).lower(),
            "logistics_confirmed": str(row[9]).lower(),
            "status": row[10],
            "document_hash": stable_hash(*row),
        }
        for row in rows
    ]


def certification_rows() -> list[dict[str, object]]:
    rows = [
        ("CERT-005-HACCP", "BIZ-005", "HACCP", "Demo Food Safety Board", "2025-07-06", "2026-07-05", "EXPIRING_SOON", "VERIFIED"),
        ("CERT-002-ISO", "BIZ-002", "ISO 22000", "Demo Quality Registry", "2026-01-01", "2027-12-31", "VALID", "VERIFIED"),
        ("CERT-007-HACCP", "BIZ-007", "HACCP", "Demo Food Safety Board", "2026-02-01", "2027-02-01", "VALID", "VERIFIED"),
        ("CERT-017-COLD", "BIZ-017", "Cold Chain Handling", "Demo Logistics Registry", "2026-01-10", "2027-01-10", "VALID", "VERIFIED"),
    ]
    return [
        {
            "certification_id": row[0],
            "business_id": row[1],
            "certification_type": row[2],
            "issuer": row[3],
            "effective_date": row[4],
            "expiry_date": row[5],
            "status": row[6],
            "verification_status": row[7],
            "document_hash": stable_hash(*row),
        }
        for row in rows
    ]


def guarantee_rows() -> list[dict[str, object]]:
    rows = [
        ("GUA-001", "BIZ-005", "BIZ-009", "BIZ-061", "PERFORMANCE_GUARANTEE", 350_000_000, "2026-01-15", "2026-09-30", "ACTIVE", "VERIFIED"),
        ("GUA-002", "BIZ-009", "BIZ-002", "BIZ-062", "INVOICE_PAYMENT_GUARANTEE", 180_000_000, "2026-06-01", "2026-10-31", "ACTIVE", "VERIFIED"),
    ]
    return [
        {
            "guarantee_id": row[0],
            "applicant_id": row[1],
            "beneficiary_id": row[2],
            "issuer_id": row[3],
            "guarantee_type": row[4],
            "amount": row[5],
            "effective_date": row[6],
            "expiry_date": row[7],
            "status": row[8],
            "verification_status": row[9],
            "document_hash": stable_hash(*row),
        }
        for row in rows
    ]


def business_rows() -> list[dict[str, object]]:
    rows = []
    for idx, seed in enumerate(BUSINESSES, start=1):
        rows.append(
            {
                "business_id": seed.business_id,
                "name": seed.name,
                "type": seed.type,
                "industry": "F&B/FMCG" if seed.type != "financial_partner" else "Finance",
                "product_category": seed.product_category,
                "province": seed.province,
                "lat": f"{seed.lat:.6f}",
                "lng": f"{seed.lng:.6f}",
                "scale": seed.scale,
                "monthly_revenue": scale_revenue(seed.scale, idx),
                "capacity": scale_capacity(seed, idx),
                "financial_health_score": base_health(seed, idx),
                "supply_risk_score": base_risk(seed, idx),
            }
        )
    return rows


def product_rows() -> list[dict[str, object]]:
    rows = []
    for idx, seed in enumerate(BUSINESSES, start=1):
        if seed.type == "financial_partner":
            continue
        sku, product, spec, price, certs = PRODUCTS[seed.product_category]
        capacity = scale_capacity(seed, idx)
        rows.append(
            {
                "business_id": seed.business_id,
                "sku": f"{sku}-{seed.business_id}",
                "product_name": product,
                "category": seed.product_category,
                "specification": spec,
                "available_capacity": max(1_500, capacity - (idx % 5) * 3_000),
                "min_order_value": {"micro": 8_000_000, "small": 25_000_000, "medium": 60_000_000, "large": 120_000_000}[seed.scale],
                "price_range": price,
                "certifications": certs,
            }
        )
    return rows


def edge(source: str, target: str, product_category: str, volume: int, lead: int, cost: int, reliability: float, term: int, idx: int) -> dict[str, object]:
    product_name = PRODUCTS[product_category][1]
    return {
        "edge_id": f"EDGE-{idx:03d}",
        "source_id": source,
        "target_id": target,
        "product": product_name,
        "product_category": product_category,
        "monthly_volume": volume,
        "lead_time_days": lead,
        "transport_cost": cost,
        "reliability": f"{reliability:.2f}",
        "payment_term_days": term,
    }


def edge_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    idx = 1

    manufacturer_to_distributors = [
        ("BIZ-001", ["BIZ-006", "BIZ-008", "BIZ-015", "BIZ-016", "BIZ-023", "BIZ-030"], "processed_agri"),
        ("BIZ-002", ["BIZ-005", "BIZ-007", "BIZ-013", "BIZ-019", "BIZ-022", "BIZ-025"], "beverage"),
        ("BIZ-003", ["BIZ-014", "BIZ-018", "BIZ-021", "BIZ-024", "BIZ-027", "BIZ-033"], "packaged_food"),
        ("BIZ-004", ["BIZ-017", "BIZ-020", "BIZ-026", "BIZ-032", "BIZ-034", "BIZ-040"], "cold_chain_food"),
    ]
    for source, targets, category in manufacturer_to_distributors:
        for target in targets:
            rows.append(edge(source, target, category, 22_000 + idx * 900, 2 + idx % 3, 9_000_000 + idx * 150_000, 0.93 - (idx % 4) * 0.02, 30, idx))
            idx += 1

    distributor_to_wholesalers = {
        "BIZ-005": ["BIZ-022", "BIZ-025", "BIZ-028"],
        "BIZ-006": ["BIZ-023", "BIZ-030", "BIZ-031"],
        "BIZ-007": ["BIZ-022", "BIZ-028"],
        "BIZ-008": ["BIZ-030", "BIZ-031"],
        "BIZ-013": ["BIZ-022", "BIZ-028"],
        "BIZ-014": ["BIZ-021", "BIZ-024", "BIZ-033"],
        "BIZ-015": ["BIZ-029", "BIZ-031"],
        "BIZ-016": ["BIZ-030", "BIZ-031"],
        "BIZ-017": ["BIZ-026", "BIZ-032", "BIZ-034"],
        "BIZ-018": ["BIZ-021", "BIZ-027", "BIZ-033"],
        "BIZ-019": ["BIZ-025", "BIZ-028"],
        "BIZ-020": ["BIZ-032", "BIZ-034"],
    }
    categories = {seed.business_id: seed.product_category for seed in BUSINESSES}
    for source, targets in distributor_to_wholesalers.items():
        for target in targets:
            category = categories[source]
            rows.append(edge(source, target, category, 9_000 + idx * 220, 1 + idx % 4, 3_000_000 + idx * 90_000, 0.91 - (idx % 5) * 0.02, 15 + (idx % 3) * 15, idx))
            idx += 1

    # Default shock scenario: BIZ-005 supplies 12 SME retailers directly.
    shock_targets = ["BIZ-009", "BIZ-011", "BIZ-035", "BIZ-036", "BIZ-038", "BIZ-039", "BIZ-041", "BIZ-042", "BIZ-046", "BIZ-047", "BIZ-049", "BIZ-056"]
    for position, target in enumerate(shock_targets):
        rows.append(edge("BIZ-005", target, "beverage", 5_200 + position * 430, 2 + position % 3, 2_400_000 + position * 120_000, 0.86 - (position % 4) * 0.03, 30, idx))
        idx += 1

    distributor_to_retailers = {
        "BIZ-006": ["BIZ-012", "BIZ-037", "BIZ-043", "BIZ-048", "BIZ-052", "BIZ-053", "BIZ-054", "BIZ-058", "BIZ-060"],
        "BIZ-007": ["BIZ-009", "BIZ-011", "BIZ-035", "BIZ-038", "BIZ-041", "BIZ-046", "BIZ-049", "BIZ-056"],
        "BIZ-013": ["BIZ-009", "BIZ-035", "BIZ-038", "BIZ-041", "BIZ-046", "BIZ-049"],
        "BIZ-014": ["BIZ-010", "BIZ-036", "BIZ-039", "BIZ-042", "BIZ-045", "BIZ-047", "BIZ-051", "BIZ-055", "BIZ-059"],
        "BIZ-017": ["BIZ-040", "BIZ-044", "BIZ-050", "BIZ-057"],
    }
    for source, targets in distributor_to_retailers.items():
        for target in targets:
            category = categories[source]
            rows.append(edge(source, target, category, 3_800 + idx * 80, 1 + idx % 4, 1_500_000 + idx * 50_000, 0.94 - (idx % 5) * 0.015, 30 if idx % 2 else 15, idx))
            idx += 1

    wholesaler_to_retailers = {
        "BIZ-021": ["BIZ-036", "BIZ-039", "BIZ-047", "BIZ-051", "BIZ-055"],
        "BIZ-022": ["BIZ-009", "BIZ-035", "BIZ-038", "BIZ-041"],
        "BIZ-023": ["BIZ-037", "BIZ-043", "BIZ-052"],
        "BIZ-024": ["BIZ-042", "BIZ-045"],
        "BIZ-025": ["BIZ-011", "BIZ-046"],
        "BIZ-028": ["BIZ-049", "BIZ-056"],
        "BIZ-030": ["BIZ-012", "BIZ-053", "BIZ-054", "BIZ-058", "BIZ-060"],
        "BIZ-032": ["BIZ-057", "BIZ-040"],
        "BIZ-034": ["BIZ-044", "BIZ-050"],
    }
    for source, targets in wholesaler_to_retailers.items():
        for target in targets:
            category = categories[source]
            rows.append(edge(source, target, category, 1_800 + idx * 55, 1 + idx % 3, 700_000 + idx * 35_000, 0.92 - (idx % 4) * 0.02, 15, idx))
            idx += 1

    while len(rows) < 120:
        source = ["BIZ-013", "BIZ-007", "BIZ-019", "BIZ-018", "BIZ-015"][len(rows) % 5]
        target_candidates = [seed.business_id for seed in BUSINESSES if seed.type == "retailer" and seed.product_category == categories[source]]
        target = target_candidates[len(rows) % len(target_candidates)]
        rows.append(edge(source, target, categories[source], 2_500 + len(rows) * 60, 2 + len(rows) % 3, 1_000_000 + len(rows) * 40_000, 0.90 - (len(rows) % 5) * 0.01, 30, idx))
        idx += 1

    return rows[:120]


def financial_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, seed in enumerate(BUSINESSES, start=1):
        revenue = scale_revenue(seed.scale, idx)
        for month_idx, month in enumerate(MONTHS):
            if seed.type == "financial_partner":
                cash_in = 0
                cash_out = 0
                debt = 0
                ar = 0
                ap = 0
                inventory = 0
                late_rate = 0.01
                delay_rate = 0.00
            else:
                seasonal = 1 + ((month_idx % 4) - 1.5) * 0.025
                shock_decay = 1
                late_rate = 0.06 + (idx % 5) * 0.012
                delay_rate = 0.04 + (idx % 4) * 0.01
                if seed.business_id == "BIZ-005" and month_idx >= 9:
                    shock_decay = [0.90, 0.84, 0.76][month_idx - 9]
                    late_rate = [0.14, 0.19, 0.24][month_idx - 9]
                    delay_rate = [0.09, 0.12, 0.16][month_idx - 9]
                cash_in = int(revenue * seasonal * shock_decay)
                cash_out = int(revenue * (0.82 + (idx % 4) * 0.035))
                if seed.business_id == "BIZ-005" and month_idx >= 9:
                    cash_out = int(revenue * 0.96)
                debt = int(revenue * (0.22 + (idx % 6) * 0.035))
                if seed.business_id == "BIZ-005":
                    debt = int(revenue * (0.52 + month_idx * 0.012))
                ar = int(revenue * (0.18 + late_rate))
                ap = int(revenue * (0.12 + (idx % 5) * 0.02))
                inventory = int(revenue * (0.15 + (idx % 7) * 0.018))
                if seed.business_id == "BIZ-005" and month_idx >= 9:
                    inventory = int(revenue * (0.29 + (month_idx - 9) * 0.03))

            rows.append(
                {
                    "business_id": seed.business_id,
                    "month": month,
                    "cash_in": cash_in,
                    "cash_out": cash_out,
                    "revenue": revenue,
                    "debt": debt,
                    "accounts_receivable": ar,
                    "accounts_payable": ap,
                    "inventory_value": inventory,
                    "late_payment_rate": f"{late_rate:.3f}",
                    "delivery_delay_rate": f"{delay_rate:.3f}",
                }
            )
    return rows


def invoice_rows() -> list[dict[str, object]]:
    return [
        {
            "invoice_id": "INV-0241",
            "seller_id": "BIZ-002",
            "buyer_id": "BIZ-005",
            "amount": 240_000_000,
            "issue_date": "2026-06-05",
            "due_date": "2026-07-05",
            "invoice_hash": "generated-by-domain-module",
            "funding_status": "funded",
            "confirmed_by": "buyer;seller",
        },
        {
            "invoice_id": "INV-0242",
            "seller_id": "BIZ-005",
            "buyer_id": "BIZ-009",
            "amount": 68_000_000,
            "issue_date": "2026-06-08",
            "due_date": "2026-07-08",
            "invoice_hash": "generated-by-domain-module",
            "funding_status": "unfunded",
            "confirmed_by": "buyer;seller",
        },
    ]


def main() -> None:
    write_csv(
        DATA_DIR / "businesses.csv",
        [
            "business_id",
            "name",
            "type",
            "industry",
            "product_category",
            "province",
            "lat",
            "lng",
            "scale",
            "monthly_revenue",
            "capacity",
            "financial_health_score",
            "supply_risk_score",
        ],
        business_rows(),
    )
    write_csv(
        DATA_DIR / "supply_edges.csv",
        [
            "edge_id",
            "source_id",
            "target_id",
            "product",
            "product_category",
            "monthly_volume",
            "lead_time_days",
            "transport_cost",
            "reliability",
            "payment_term_days",
        ],
        edge_rows(),
    )
    write_csv(
        DATA_DIR / "financials.csv",
        [
            "business_id",
            "month",
            "cash_in",
            "cash_out",
            "revenue",
            "debt",
            "accounts_receivable",
            "accounts_payable",
            "inventory_value",
            "late_payment_rate",
            "delivery_delay_rate",
        ],
        financial_rows(),
    )
    write_csv(
        DATA_DIR / "products.csv",
        [
            "business_id",
            "sku",
            "product_name",
            "category",
            "specification",
            "available_capacity",
            "min_order_value",
            "price_range",
            "certifications",
        ],
        product_rows(),
    )
    write_csv(
        DATA_DIR / "invoice_verifications.csv",
        [
            "invoice_id",
            "seller_id",
            "buyer_id",
            "amount",
            "issue_date",
            "due_date",
            "invoice_hash",
            "funding_status",
            "confirmed_by",
        ],
        invoice_rows(),
    )
    write_csv(
        DATA_DIR / "contracts.csv",
        [
            "contract_id", "supplier_id", "buyer_id", "product_category", "status",
            "effective_date", "expiry_date", "payment_term_days", "sla_lead_time_days",
            "has_exclusivity", "has_backup_supplier_clause", "verification_status",
            "source_label", "document_hash",
        ],
        contract_rows(),
    )
    write_csv(
        DATA_DIR / "purchase_orders.csv",
        [
            "po_id", "contract_id", "supplier_id", "buyer_id", "sku", "order_date",
            "expected_delivery_date", "actual_delivery_date", "quantity", "value",
            "status", "verification_status", "document_hash",
        ],
        purchase_order_rows(),
    )
    write_csv(
        DATA_DIR / "delivery_notes.csv",
        [
            "delivery_note_id", "po_id", "supplier_id", "buyer_id", "logistics_partner_id",
            "delivery_date", "delivered_quantity", "delay_days", "verified_by_buyer",
            "logistics_confirmed", "status", "document_hash",
        ],
        delivery_note_rows(),
    )
    write_csv(
        DATA_DIR / "certifications.csv",
        [
            "certification_id", "business_id", "certification_type", "issuer",
            "effective_date", "expiry_date", "status", "verification_status", "document_hash",
        ],
        certification_rows(),
    )
    write_csv(
        DATA_DIR / "guarantees.csv",
        [
            "guarantee_id", "applicant_id", "beneficiary_id", "issuer_id", "guarantee_type",
            "amount", "effective_date", "expiry_date", "status", "verification_status", "document_hash",
        ],
        guarantee_rows(),
    )
    print("Generated synthetic VietSupply Radar data in data/.")


if __name__ == "__main__":
    main()
