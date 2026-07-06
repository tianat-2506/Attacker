from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.services.access_control import RequestContext
from backend.app.services.database import Database
from backend.app.services.radar_service import create_service


class DatabaseServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "demo.db")
        self.database.seed_from_csv(reset=True)
        self.service = create_service(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seeded_sqlite_database_has_demo_graph(self) -> None:
        graph = self.service.graph_payload(masked=False, context=RequestContext.authorized_demo())
        self.assertEqual(len(graph["nodes"]), 62)
        self.assertEqual(len(graph["edges"]), 120)
        self.assertEqual(graph["nodes"][4]["id"], "BIZ-005")

    def test_business_detail_uses_database_and_domain_risk_signal(self) -> None:
        detail = self.service.business_detail_payload("BIZ-005")
        self.assertEqual(detail["business"]["name"], "Dai Tin Distribution")
        self.assertEqual(detail["risk"]["level"], "red")
        self.assertGreaterEqual(detail["risk"]["score"], 70)
        self.assertIn("advisory_notice", detail["risk"])

    def test_recommendations_are_shortlist_not_disrupted_supplier(self) -> None:
        recommendations = self.service.recommendations_payload(
            buyer_id="BIZ-009",
            disrupted_supplier_id="BIZ-005",
            period_key="2026-05",
            product_category="beverage",
            product_specification="UHT, 1L, khong duong",
            required_monthly_volume=12_000,
            top_k=3,
        )
        self.assertEqual(len(recommendations), 3)
        self.assertNotIn("BIZ-005", {item["supplier_id"] for item in recommendations})
        self.assertEqual({item["period_key"] for item in recommendations}, {"2026-05"})
        self.assertIn("selected period 2026-05", recommendations[0]["advisory_notice"])
        self.assertIn("advisory_notice", recommendations[0])

    def test_focused_scenario_has_ten_nodes_and_all_demo_roles(self) -> None:
        scenario = self.service.scenario_payload()
        self.assertEqual(scenario["node_count"], 10)
        self.assertEqual(set(scenario["role_coverage"]), {"supplier", "distributor", "sme", "logistics", "finance"})
        self.assertTrue(all(scenario["role_coverage"].values()))

    def test_risk_signal_is_backed_by_procurement_evidence(self) -> None:
        signal = self.service.risk_signal_payload("BIZ-005")
        self.assertEqual(signal["level"], "HIGH")
        self.assertEqual(len([item for item in signal["evidence"] if item["type"] == "PURCHASE_ORDER"]), 4)
        self.assertIn("not a legal breach finding", signal["disclaimer"])

    def test_finance_payload_explains_health_without_credit_claim(self) -> None:
        payload = self.service.finance_payload("BIZ-005")
        self.assertEqual(len(payload["series"]), 12)
        self.assertIn("not a regulated credit score", payload["health"]["explanation"])
        self.assertIn("net_cash_flow", payload["latest"])

    def test_connection_request_requires_human_consent_and_is_audited(self) -> None:
        request = self.service.connection_request_payload(
            buyer_id="BIZ-009",
            target_supplier_id="BIZ-007",
            disrupted_supplier_id="BIZ-005",
            purpose="alternative_supplier_review",
        )
        self.assertEqual(request["status"], "pending")
        self.assertEqual(request["consent_status"], "awaiting_supplier_consent")
        audit = self.service.audit_payload()
        self.assertTrue(any(event["event_type"] == "CONNECTION_REQUEST_CREATED" for event in audit["events"]))


if __name__ == "__main__":
    unittest.main()
