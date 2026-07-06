from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.services.access_control import AccessDeniedError, RequestContext, SENSITIVE_GRAPH_SCOPE
from backend.app.services.database import Database
from backend.app.services.radar_service import create_service


class AccessControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "demo.db")
        self.database.seed_from_csv(reset=True)
        self.service = create_service(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_public_actor_cannot_force_unmasked_graph(self) -> None:
        with self.assertRaises(AccessDeniedError):
            self.service.graph_payload(masked=False)
        events = self.service.audit.list_recent()
        denied_event = next(item for item in events if item["event_type"] == "COMMERCIAL_GRAPH_UNMASK_DENIED")

        self.assertEqual(denied_event["actor_id"], "demo-user")
        self.assertTrue(denied_event["policy_decision_id"])

    def test_authorized_scope_can_view_unmasked_graph_for_demo(self) -> None:
        context = RequestContext.authorized_demo()
        graph = self.service.graph_payload(masked=False, context=context)
        node = next(item for item in graph["nodes"] if item["id"] == "BIZ-005")
        edge = next(item for item in graph["edges"] if item["id"] == "EDGE-001")

        self.assertFalse(graph["access"]["masked"])
        self.assertEqual(node["legal_name"], "Dai Tin Distribution")
        self.assertGreater(node["monthly_revenue"], 0)
        self.assertGreater(edge["monthly_volume"], 0)
        self.assertTrue(graph["access"]["policy_decision_id"])
        self.assertTrue(graph["access"]["audit_event_id"])

        events = self.service.audit.list_recent()
        viewed_event = next(item for item in events if item["event_type"] == "COMMERCIAL_GRAPH_UNMASKED_VIEWED")
        self.assertEqual(viewed_event["actor_id"], "demo-admin")
        self.assertEqual(viewed_event["policy_decision_id"], graph["access"]["policy_decision_id"])

    def test_masked_graph_hides_legal_name_and_raw_edge_metrics(self) -> None:
        graph = self.service.graph_payload()
        node = next(item for item in graph["nodes"] if item["id"] == "BIZ-005")
        edge = next(item for item in graph["edges"] if item["id"] == "EDGE-001")

        self.assertTrue(graph["access"]["masked"])
        self.assertIsNone(node["legal_name"])
        self.assertNotEqual(node["name"], "Dai Tin Distribution")
        self.assertEqual(node["monthly_revenue"], 0)
        self.assertEqual(node["risk"], 0)
        self.assertIn("revenue_band", node)
        self.assertEqual(edge["monthly_volume"], 0)
        self.assertEqual(edge["transport_cost"], 0)
        self.assertEqual(edge["payment_term_days"], 0)
        self.assertIn("volume_band", edge)
        self.assertTrue(graph["access"]["policy_decision_id"])
        self.assertTrue(graph["access"]["audit_event_id"])

    def test_unmasked_business_roster_cannot_bypass_graph_policy(self) -> None:
        with self.assertRaises(AccessDeniedError):
            self.service.businesses_payload(masked=False)
        events = self.service.audit.list_recent()
        denied_event = next(item for item in events if item["event_type"] == "BUSINESS_ROSTER_UNMASK_DENIED")

        self.assertEqual(denied_event["actor_id"], "demo-user")
        self.assertTrue(denied_event["policy_decision_id"])

    def test_audit_records_actor_context_not_hardcoded_demo_user(self) -> None:
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-buyer-009",
            actor_role="sme_user",
            purpose="supplier_risk_review",
            scopes=frozenset({"demo:read", SENSITIVE_GRAPH_SCOPE}),
        )
        self.service.business_detail_payload("BIZ-005", context=context)
        events = self.service.audit_payload()["events"]
        event = next(item for item in events if item["event_type"] == "BUSINESS_DETAIL_VIEWED")

        self.assertEqual(event["actor_id"], "user-buyer-009")
        self.assertEqual(event["actor_role"], "sme_user")
        self.assertEqual(event["purpose"], "supplier_risk_review")

    def test_audit_trail_read_requires_audit_policy(self) -> None:
        denied_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="sme-user-009",
            actor_role="sme_user",
            purpose="general_review",
            scopes=frozenset({"demo:read"}),
        )

        with self.assertRaises(AccessDeniedError):
            self.service.audit_payload(context=denied_context)
        denied_events = self.service.audit.list_recent()
        denied_event = next(item for item in denied_events if item["event_type"] == "AUDIT_TRAIL_READ_DENIED")
        self.assertEqual(denied_event["actor_id"], "sme-user-009")
        self.assertTrue(denied_event["policy_decision_id"])

        allowed_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="org-demo",
            actor_id="demo-user",
            actor_role="demo_operator",
            purpose="demo_view",
            scopes=frozenset({"demo:read"}),
        )
        payload = self.service.audit_payload(context=allowed_context)
        viewed_event = next(item for item in payload["events"] if item["event_type"] == "AUDIT_TRAIL_VIEWED")

        self.assertTrue(payload["policy_decision_id"])
        self.assertTrue(payload["audit_event_id"])
        self.assertEqual(viewed_event["actor_id"], "demo-user")


if __name__ == "__main__":
    unittest.main()
