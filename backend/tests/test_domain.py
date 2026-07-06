from __future__ import annotations

import unittest

from backend.app.domain.invoice_verification import double_financing_alert, invoice_hash
from backend.app.domain.risk_scoring import score_from_features, calculate_business_risk
from backend.app.domain.shock_simulation import simulate_shock
from backend.app.domain.supplier_matching import rank_suppliers
from backend.app.services.data_loader import financials_for_business, load_data
from scripts.validate_data import validate


class DataValidationTests(unittest.TestCase):
    def test_generated_data_is_valid(self) -> None:
        self.assertEqual(validate(), [])


class RiskScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_data()

    def test_low_risk_features_are_green(self) -> None:
        result = score_from_features(
            {
                "cashflow_risk": 10,
                "late_payment_risk": 15,
                "inventory_risk": 12,
                "delivery_delay_risk": 8,
                "debt_risk": 20,
                "dependency_risk": 10,
            }
        )
        self.assertEqual(result.level, "green")
        self.assertLess(result.score, 40)

    def test_default_shock_supplier_is_red(self) -> None:
        financials = financials_for_business(self.data["financials"], "BIZ-005")
        result = calculate_business_risk("BIZ-005", financials, self.data["edges"], "beverage")
        self.assertEqual(result.level, "red")
        self.assertGreaterEqual(result.score, 70)
        self.assertTrue(result.drivers)


class ShockSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_data()

    def test_biz005_beverage_shock_affects_at_least_12_retailers(self) -> None:
        result = simulate_shock("BIZ-005", self.data["businesses"], self.data["edges"], "beverage")
        self.assertGreaterEqual(result.impact.affected_sme_count, 12)
        self.assertGreater(result.impact.monthly_volume_at_risk, 70_000)
        self.assertIn("EDGE-055", result.affected_edges)

    def test_upstream_supplier_is_not_affected_when_retailer_shocks(self) -> None:
        result = simulate_shock("BIZ-009", self.data["businesses"], self.data["edges"], "beverage")
        affected_ids = {node.business_id for node in result.affected_nodes}
        self.assertNotIn("BIZ-005", affected_ids)


class SupplierMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_data()

    def test_recommendations_exclude_disrupted_supplier(self) -> None:
        recommendations = rank_suppliers(
            buyer_id="BIZ-009",
            disrupted_supplier_id="BIZ-005",
            product_category="beverage",
            product_specification="UHT, 1L, khong duong",
            required_monthly_volume=12_000,
            businesses=self.data["businesses"],
            products=self.data["products"],
            edges=self.data["edges"],
            top_k=3,
        )
        self.assertEqual(len(recommendations), 3)
        self.assertNotIn("BIZ-005", {item.supplier_id for item in recommendations})
        self.assertGreaterEqual(recommendations[0].match_score, recommendations[-1].match_score)
        self.assertTrue(recommendations[0].reason_codes)


class InvoiceVerificationTests(unittest.TestCase):
    def test_invoice_hash_is_stable(self) -> None:
        invoice = {
            "invoice_id": "INV-TEST",
            "seller_id": "BIZ-002",
            "buyer_id": "BIZ-005",
            "amount": 240_000_000,
            "issue_date": "2026-06-05",
            "due_date": "2026-07-05",
        }
        self.assertEqual(invoice_hash(invoice), invoice_hash(dict(reversed(list(invoice.items())))))

    def test_double_financing_alert_for_existing_funded_invoice(self) -> None:
        invoice = {
            "invoice_id": "INV-TEST",
            "seller_id": "BIZ-002",
            "buyer_id": "BIZ-005",
            "amount": 240_000_000,
            "issue_date": "2026-06-05",
            "due_date": "2026-07-05",
        }
        existing = [{**invoice, "funding_status": "funded"}]
        self.assertTrue(double_financing_alert(invoice, existing))


if __name__ == "__main__":
    unittest.main()
