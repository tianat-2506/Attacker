from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.services.access_control import AccessDeniedError, RequestContext
from backend.app.services.database import Database
from backend.app.services.radar_service import create_service


class SupplyMapOnboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "demo.db")
        self.database.seed_from_csv(reset=True)
        self.service = create_service(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seeded_review_queue_and_own_org_filter(self) -> None:
        reviewer = RequestContext(
            tenant_id="tenant-demo",
            organization_id="org-demo",
            actor_id="reviewer-001",
            actor_role="reviewer",
            purpose="onboarding_review",
            scopes=frozenset({"demo:read"}),
        )
        queue = self.service.supply_map_registrations_payload(reviewer)
        queue_ids = {item["id"] for item in queue["registrations"]}

        self.assertIn("REG-BIZ-005", queue_ids)
        self.assertEqual(queue["scope"], "review_queue")
        self.assertTrue(queue["policy_decision_id"])
        self.assertTrue(queue["audit_event_id"])

        submitter = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="sme-biz-009",
            actor_role="sme_submitter",
            purpose="own_membership_review",
            scopes=frozenset({"demo:read"}),
        )
        own = self.service.supply_map_registrations_payload(submitter)
        own_ids = {item["id"] for item in own["registrations"]}

        self.assertIn("REG-BIZ-009", own_ids)
        self.assertNotIn("REG-BIZ-005", own_ids)
        self.assertEqual(own["scope"], "own_organization")

    def test_create_registration_records_policy_and_audit(self) -> None:
        submitter = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="sme-biz-009",
            actor_role="sme_submitter",
            purpose="supply_map_membership_request",
            scopes=frozenset({"demo:read"}),
        )
        registration = self.service.create_supply_map_registration_payload(
            organization_name="Thu Duc Retail Mart",
            stakeholder_role="retailer",
            province="TP.HCM",
            category="beverage",
            scale="SME",
            contact_email="sme-biz-009@demo.vietsupply.local",
            intended_relationships=["supplier_review", "evidence_sharing"],
            data_boundary="masked profile, products, evidence metadata",
            context=submitter,
        )

        self.assertEqual(registration["organizationId"], "BIZ-009")
        self.assertEqual(registration["status"], "submitted")
        self.assertEqual(registration["mapVisibility"], "masked_pending_consent")
        self.assertTrue(registration["policyDecisionId"])
        self.assertTrue(registration["auditEventId"])

    def test_network_analyst_cannot_create_registration(self) -> None:
        analyst = RequestContext(
            tenant_id="tenant-demo",
            organization_id="org-network",
            actor_id="network-analyst-001",
            actor_role="network_analyst",
            purpose="aggregate_graph_review",
            scopes=frozenset({"demo:read"}),
        )

        with self.assertRaises(AccessDeniedError):
            self.service.create_supply_map_registration_payload(
                organization_name="Analyst Created Node",
                stakeholder_role="distributor",
                province="TP.HCM",
                category="beverage",
                scale="SME",
                contact_email="analyst@demo.vietsupply.local",
                intended_relationships=["supplier_review"],
                data_boundary="masked profile only",
                context=analyst,
            )

    def test_reviewer_decision_approves_demo_map_visibility(self) -> None:
        submitter = RequestContext(
            tenant_id="tenant-demo",
            organization_id="org-new-sme",
            actor_id="new-sme-owner",
            actor_role="sme_submitter",
            purpose="supply_map_membership_request",
            scopes=frozenset({"demo:read"}),
        )
        registration = self.service.create_supply_map_registration_payload(
            organization_name="New Demo Household Business",
            stakeholder_role="retailer",
            province="Dong Nai",
            category="beverage",
            scale="Household business",
            contact_email="owner@demo.vietsupply.local",
            intended_relationships=["supplier_shortlist"],
            data_boundary="masked profile and evidence metadata",
            context=submitter,
        )
        reviewer = RequestContext(
            tenant_id="tenant-demo",
            organization_id="org-demo",
            actor_id="reviewer-001",
            actor_role="reviewer",
            purpose="onboarding_review",
            scopes=frozenset({"demo:read"}),
        )

        approved = self.service.decide_supply_map_registration_payload(
            registration_id=registration["id"],
            decision_value="approve",
            note="Approved for demo map membership only.",
            context=reviewer,
        )

        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["mapVisibility"], "visible_demo_node")
        self.assertTrue(approved["linkedBusinessId"].startswith("BIZ-ONB-"))
        self.assertTrue(approved["policyDecisionId"])
        self.assertTrue(approved["auditEventId"])
        self.assertIn("materialized as a demo supply-map node", approved["advisoryNotice"])

        graph = self.service.graph_payload(
            masked=True,
            context=RequestContext(
                tenant_id="tenant-demo",
                organization_id="org-demo",
                actor_id="demo-user",
                actor_role="demo_operator",
                purpose="demo_view",
                scopes=frozenset({"demo:read"}),
            ),
        )
        node = next(item for item in graph["nodes"] if item["id"] == approved["linkedBusinessId"])
        self.assertEqual(node["province"], "Dong Nai")
        self.assertEqual(node["category"], "beverage")

        approved_again = self.service.decide_supply_map_registration_payload(
            registration_id=registration["id"],
            decision_value="approve",
            note="Idempotent second review.",
            context=reviewer,
        )
        self.assertEqual(approved_again["linkedBusinessId"], approved["linkedBusinessId"])
        graph_after_replay = self.service.graph_payload(
            masked=True,
            context=RequestContext(
                tenant_id="tenant-demo",
                organization_id="org-demo",
                actor_id="demo-user",
                actor_role="demo_operator",
                purpose="demo_view",
                scopes=frozenset({"demo:read"}),
            ),
        )
        self.assertEqual(len([item for item in graph_after_replay["nodes"] if item["id"] == approved["linkedBusinessId"]]), 1)

        self.database.seed_from_csv(reset=False)
        restarted_service = create_service(self.database)
        restarted_graph = restarted_service.graph_payload(
            masked=True,
            context=RequestContext(
                tenant_id="tenant-demo",
                organization_id="org-demo",
                actor_id="demo-user",
                actor_role="demo_operator",
                purpose="demo_view",
                scopes=frozenset({"demo:read"}),
            ),
        )
        self.assertEqual(len([item for item in restarted_graph["nodes"] if item["id"] == approved["linkedBusinessId"]]), 1)

    def test_connection_request_requires_buyer_role_and_organization(self) -> None:
        buyer_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="buyer-admin-009",
            actor_role="buyer_admin",
            purpose="supplier_risk_review",
            scopes=frozenset({"demo:read"}),
        )
        request = self.service.connection_request_payload(
            buyer_id="BIZ-009",
            target_supplier_id="BIZ-007",
            disrupted_supplier_id="BIZ-005",
            purpose="alternative_supplier_review",
            context=buyer_admin,
        )
        self.assertEqual(request["requester_id"], "buyer-admin-009")
        self.assertTrue(request["policy_decision_id"])
        self.assertTrue(request["audit_event_id"])

        supplier_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-005",
            actor_id="supplier-admin-005",
            actor_role="supplier_admin",
            purpose="evidence_management",
            scopes=frozenset({"demo:read"}),
        )
        with self.assertRaises(AccessDeniedError):
            self.service.connection_request_payload(
                buyer_id="BIZ-009",
                target_supplier_id="BIZ-007",
                disrupted_supplier_id="BIZ-005",
                purpose="alternative_supplier_review",
                context=supplier_admin,
            )

        analyst = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="network-analyst-001",
            actor_role="network_analyst",
            purpose="supplier_shortlist_review",
            scopes=frozenset({"demo:read"}),
        )
        with self.assertRaises(AccessDeniedError):
            self.service.connection_request_payload(
                buyer_id="BIZ-009",
                target_supplier_id="BIZ-007",
                disrupted_supplier_id="BIZ-005",
                purpose="alternative_supplier_review",
                context=analyst,
            )

    def test_connection_request_requires_supplier_consent_and_contract_before_edge(self) -> None:
        buyer_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="buyer-admin-009",
            actor_role="buyer_admin",
            purpose="supplier_risk_review",
            scopes=frozenset({"demo:read"}),
        )
        supplier_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-007",
            actor_id="supplier-admin-007",
            actor_role="supplier_admin",
            purpose="supplier_introduction_review",
            scopes=frozenset({"demo:read"}),
        )
        reviewer = RequestContext(
            tenant_id="tenant-demo",
            organization_id="org-demo",
            actor_id="reviewer-001",
            actor_role="reviewer",
            purpose="relationship_review",
            scopes=frozenset({"demo:read"}),
        )

        request = self.service.connection_request_payload(
            buyer_id="BIZ-009",
            target_supplier_id="BIZ-007",
            disrupted_supplier_id="BIZ-005",
            purpose="alternative_supplier_review",
            context=buyer_admin,
        )
        with self.assertRaises(AccessDeniedError):
            self.service.decide_connection_request_payload(
                request_id=request["request_id"],
                decision_value="grant_consent",
                note="Buyer cannot grant supplier consent.",
                contract_evidence_id=None,
                context=buyer_admin,
            )

        consented = self.service.decide_connection_request_payload(
            request_id=request["request_id"],
            decision_value="grant_consent",
            note="Supplier consents to introduction only.",
            contract_evidence_id=None,
            context=supplier_admin,
        )
        self.assertEqual(consented["consent_status"], "supplier_consented")
        self.assertIsNone(consented["relationship_edge_id"])
        with closing(self.database.connect()) as connection:
            no_edge = connection.execute(
                "SELECT COUNT(*) AS count FROM supply_edges WHERE edge_id = ?",
                (f"EDGE-{request['request_id']}",),
            ).fetchone()
        self.assertEqual(no_edge["count"], 0)

        with self.assertRaisesRegex(ValueError, "contract_evidence_id"):
            self.service.decide_connection_request_payload(
                request_id=request["request_id"],
                decision_value="activate_relationship",
                note="Missing contract evidence.",
                contract_evidence_id=None,
                context=reviewer,
            )

        activated = self.service.decide_connection_request_payload(
            request_id=request["request_id"],
            decision_value="activate_relationship",
            note="Contract evidence reviewed for demo relationship basis.",
            contract_evidence_id="EVD-CONTRACT-007-009",
            context=reviewer,
        )
        self.assertEqual(activated["status"], "relationship_active")
        self.assertEqual(activated["consent_status"], "contract_evidence_recorded")
        self.assertEqual(activated["contract_evidence_id"], "EVD-CONTRACT-007-009")
        self.assertEqual(activated["relationship_edge_id"], f"EDGE-{request['request_id']}")
        self.assertTrue(activated["policy_decision_id"])
        self.assertTrue(activated["audit_event_id"])
        with closing(self.database.connect()) as connection:
            edge = connection.execute(
                "SELECT monthly_volume, payment_term_days FROM supply_edges WHERE edge_id = ?",
                (activated["relationship_edge_id"],),
            ).fetchone()
            relationship = connection.execute(
                "SELECT status FROM organization_relationships WHERE relationship_id = ?",
                (activated["relationship_id"],),
            ).fetchone()
        self.assertEqual(edge["monthly_volume"], 0)
        self.assertEqual(edge["payment_term_days"], 0)
        self.assertEqual(relationship["status"], "active")

    def test_connection_request_inbox_is_scoped_by_stakeholder_role(self) -> None:
        buyer_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="buyer-admin-009",
            actor_role="buyer_admin",
            purpose="supplier_risk_review",
            scopes=frozenset({"demo:read"}),
        )
        supplier_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-007",
            actor_id="supplier-admin-007",
            actor_role="supplier_admin",
            purpose="supplier_introduction_review",
            scopes=frozenset({"demo:read"}),
        )
        unrelated_supplier = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-005",
            actor_id="supplier-admin-005",
            actor_role="supplier_admin",
            purpose="supplier_introduction_review",
            scopes=frozenset({"demo:read"}),
        )
        reviewer = RequestContext(
            tenant_id="tenant-demo",
            organization_id="org-demo",
            actor_id="reviewer-001",
            actor_role="reviewer",
            purpose="relationship_review",
            scopes=frozenset({"demo:read"}),
        )
        request = self.service.connection_request_payload(
            buyer_id="BIZ-009",
            target_supplier_id="BIZ-007",
            disrupted_supplier_id="BIZ-005",
            purpose="alternative_supplier_review",
            context=buyer_admin,
        )

        buyer_inbox = self.service.connection_requests_payload(context=buyer_admin)
        supplier_inbox = self.service.connection_requests_payload(context=supplier_admin)
        unrelated_inbox = self.service.connection_requests_payload(context=unrelated_supplier)
        reviewer_queue = self.service.connection_requests_payload(context=reviewer)
        analyst = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="network-analyst-001",
            actor_role="network_analyst",
            purpose="supplier_shortlist_review",
            scopes=frozenset({"demo:read"}),
        )

        self.assertIn(request["request_id"], {item["request_id"] for item in buyer_inbox["connection_requests"]})
        self.assertIn(request["request_id"], {item["request_id"] for item in supplier_inbox["connection_requests"]})
        self.assertNotIn(request["request_id"], {item["request_id"] for item in unrelated_inbox["connection_requests"]})
        self.assertIn(request["request_id"], {item["request_id"] for item in reviewer_queue["connection_requests"]})
        self.assertEqual(buyer_inbox["scope"], "own_organization")
        self.assertEqual(reviewer_queue["scope"], "review_queue")
        with self.assertRaises(AccessDeniedError):
            self.service.connection_requests_payload(context=analyst)

    def test_buyer_and_supplier_admin_have_distinct_capabilities(self) -> None:
        buyer_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="buyer-admin-009",
            actor_role="buyer_admin",
            purpose="supplier_risk_review",
            scopes=frozenset({"demo:read"}),
        )
        supplier_admin = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-005",
            actor_id="supplier-admin-005",
            actor_role="supplier_admin",
            purpose="evidence_management",
            scopes=frozenset({"demo:read"}),
        )

        graph = self.service.graph_payload(masked=True, context=buyer_admin)
        self.assertTrue(graph["access"]["masked"])

        with self.assertRaises(AccessDeniedError):
            self.service.intake.create_submission(
                organization_id="BIZ-009",
                period_key="2026-08",
                source_type="manual",
                sections={"financials": {"revenue": 1}},
                context=buyer_admin,
            )

        submission = self.service.intake.create_submission(
            organization_id="BIZ-005",
            period_key="2026-08",
            source_type="manual",
            sections={"financials": {"revenue": 1}},
            context=supplier_admin,
        )
        self.assertEqual(submission["organization_id"], "BIZ-005")

        with self.assertRaises(AccessDeniedError):
            self.service.connection_request_payload(
                buyer_id="BIZ-009",
                target_supplier_id="BIZ-007",
                disrupted_supplier_id="BIZ-005",
                purpose="alternative_supplier_review",
                context=supplier_admin,
            )


if __name__ == "__main__":
    unittest.main()
