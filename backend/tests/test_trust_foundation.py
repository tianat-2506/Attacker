from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import threading
import time
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from backend.app.services.access_control import (
    AccessDeniedError,
    JwtVerificationError,
    context_from_headers,
    issue_dev_jwt,
)
from backend.app.services.database import Database
from backend.app.services.intake_service import IntakeNotFoundError
from backend.app.services.radar_service import create_service


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class _JwksHandler(BaseHTTPRequestHandler):
    jwks: dict[str, object] = {"keys": []}

    def do_GET(self) -> None:
        body = json.dumps(self.jwks).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class TrustFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "demo.db")
        self.database.seed_from_csv(reset=True)
        self.service = create_service(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dev_jwt_maps_actor_tenant_roles_and_rejects_bad_audience(self) -> None:
        token = issue_dev_jwt(
            subject="user-biz-009",
            organization_id="BIZ-009",
            roles=["sme_submitter"],
            scopes=["intake:write", "graph:read"],
        )
        context = context_from_headers(authorization=f"Bearer {token}", app_mode="demo")

        self.assertEqual(context.actor_id, "user-biz-009")
        self.assertEqual(context.tenant_id, "tenant-demo")
        self.assertIn("BIZ-009", context.organization_ids)
        self.assertIn("sme_submitter", context.roles)
        self.assertEqual(context.auth_assurance, "jwt-dev-hs256")

        bad_token = issue_dev_jwt(audience="wrong-audience")
        with self.assertRaises(JwtVerificationError):
            context_from_headers(authorization=f"Bearer {bad_token}", app_mode="demo")

    def test_demo_headers_are_disabled_outside_demo_mode(self) -> None:
        with self.assertRaises(JwtVerificationError):
            context_from_headers(actor_id="spoofed-user", actor_role="system_admin", app_mode="pilot")

    def test_auth_me_exposes_role_capability_matrix(self) -> None:
        sme_context = context_from_headers(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="sme-biz-009",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes="demo:read intake:write",
            app_mode="demo",
        )
        buyer_context = context_from_headers(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="buyer-admin-009",
            actor_role="buyer_admin",
            purpose="supplier_risk_review",
            scopes="demo:read buyer:intro",
            app_mode="demo",
        )
        reviewer_context = context_from_headers(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="reviewer-001",
            actor_role="reviewer",
            purpose="submission_review",
            scopes="demo:read",
            app_mode="demo",
        )

        sme_me = self.service.governance.auth_me(sme_context)
        buyer_me = self.service.governance.auth_me(buyer_context)
        reviewer_me = self.service.governance.auth_me(reviewer_context)
        sme = sme_me["capabilities"]
        buyer = buyer_me["capabilities"]
        reviewer = reviewer_me["capabilities"]

        self.assertTrue(sme["can_create_submission"])
        self.assertTrue(sme["can_create_evidence_upload"])
        self.assertTrue(sme["can_read_supply_map_registration"])
        self.assertFalse(sme["can_review_submission"])
        self.assertFalse(sme["can_create_connection_request"])
        self.assertIn("create_submission", sme["allowed_actions"])
        self.assertIn("intake", sme_me["workspace_access"]["allowed_views"])
        self.assertIn("companies", sme_me["workspace_access"]["allowed_views"])
        self.assertEqual(sme_me["workspace_access"]["default_view"], "intake")

        self.assertTrue(buyer["can_read_graph"])
        self.assertTrue(buyer["can_create_connection_request"])
        self.assertFalse(buyer["can_create_submission"])
        self.assertFalse(buyer["can_read_evidence"])
        self.assertIn("map", buyer_me["workspace_access"]["allowed_views"])
        self.assertIn("matching", buyer_me["workspace_access"]["allowed_views"])
        self.assertNotIn("intake", buyer_me["workspace_access"]["allowed_views"])
        self.assertEqual(buyer_me["workspace_access"]["default_view"], "overview")

        self.assertTrue(reviewer["can_review_submission"])
        self.assertTrue(reviewer["can_review_supply_map_registration"])
        self.assertFalse(reviewer["can_create_evidence_upload"])
        self.assertIn("intake", reviewer_me["workspace_access"]["allowed_views"])
        self.assertIn("onboarding", reviewer_me["workspace_access"]["allowed_views"])
        self.assertNotIn("overview", reviewer_me["workspace_access"]["allowed_views"])
        self.assertEqual(reviewer_me["workspace_access"]["default_view"], "intake")

    def test_risk_signal_can_be_high_level_without_evidence_access(self) -> None:
        buyer_context = context_from_headers(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="buyer-admin-009",
            actor_role="buyer_admin",
            purpose="supplier_risk_review",
            scopes="demo:read buyer:intro",
            app_mode="demo",
        )

        signal = self.service.risk_signal_payload("BIZ-005", context=buyer_context, period_key="2026-06")

        self.assertEqual(signal["business_id"], "BIZ-005")
        self.assertEqual(signal["risk_type"], "HIGH_LEVEL_SUPPLY_RISK")
        self.assertEqual(signal["evidence_scope"], "evidence_blocked_by_policy")
        self.assertEqual(signal["evidence"], [])
        self.assertIn("not a legal breach finding", signal["disclaimer"])
        self.assertTrue(any(event["event_type"] == "RISK_SIGNAL_VIEWED" for event in self.service.audit_payload()["events"]))

    def test_oidc_provider_does_not_fallback_to_dev_jwt_without_jwks(self) -> None:
        token = issue_dev_jwt(subject="user-biz-009", organization_id="BIZ-009", roles=["sme_submitter"])
        with patch.dict("os.environ", {"AUTH_PROVIDER": "oidc"}, clear=False):
            with self.assertRaisesRegex(JwtVerificationError, "AUTH_JWKS_URL"):
                context_from_headers(authorization=f"Bearer {token}", app_mode="pilot")

    def test_oidc_jwks_token_maps_provisioned_actor_context(self) -> None:
        try:
            import jwt  # type: ignore[import-not-found]
            from cryptography.hazmat.primitives.asymmetric import rsa  # type: ignore[import-not-found]
        except ImportError as exc:
            self.skipTest(f"OIDC crypto dependencies are not installed: {exc}")

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()
        kid = "test-oidc-key-1"
        _JwksHandler.jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": kid,
                    "alg": "RS256",
                    "n": _base64url_uint(public_numbers.n),
                    "e": _base64url_uint(public_numbers.e),
                }
            ]
        }

        server = HTTPServer(("127.0.0.1", 0), _JwksHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            now = int(time.time())
            token = jwt.encode(
                {
                    "iss": "https://issuer.example/",
                    "aud": "vietsupply-api",
                    "sub": "oidc-user-009",
                    "tenant_id": "tenant-demo",
                    "organization_id": "BIZ-009",
                    "roles": ["org_admin", "sme_submitter"],
                    "scopes": ["finance:read", "intake:write"],
                    "purpose": "periodic_intake",
                    "memberships": [
                        {"organization_id": "BIZ-009", "role": "org_admin", "status": "active"},
                        {"organization_id": "BIZ-062", "role": "lender", "status": "active"},
                    ],
                    "iat": now,
                    "nbf": now - 5,
                    "exp": now + 300,
                },
                private_key,
                algorithm="RS256",
                headers={"kid": kid, "typ": "JWT"},
            )
            with patch.dict(
                "os.environ",
                {
                    "AUTH_PROVIDER": "oidc",
                    "AUTH_JWKS_URL": f"http://127.0.0.1:{server.server_port}/jwks.json",
                    "AUTH_JWT_ISSUER": "https://issuer.example/",
                    "AUTH_JWT_AUDIENCE": "vietsupply-api",
                },
                clear=False,
            ):
                context = context_from_headers(
                    authorization=f"Bearer {token}",
                    app_mode="pilot",
                    request_id="req-oidc",
                )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertEqual(context.actor_id, "oidc-user-009")
        self.assertEqual(context.token_subject, "oidc-user-009")
        self.assertEqual(context.tenant_id, "tenant-demo")
        self.assertEqual(context.organization_id, "BIZ-009")
        self.assertEqual(context.auth_assurance, "oidc-jwks")
        self.assertEqual(context.app_mode, "pilot")
        self.assertEqual(context.request_id, "req-oidc")
        self.assertEqual(context.purpose, "periodic_intake")
        self.assertIn("org_admin", context.roles)
        self.assertIn("sme_submitter", context.roles)
        self.assertIn("finance:read", context.scopes)
        self.assertIn("intake:write", context.scopes)
        self.assertIn("BIZ-009", context.organization_ids)
        self.assertIn("BIZ-062", context.organization_ids)

    def test_cross_org_intake_write_is_denied_for_jwt_actor(self) -> None:
        token = issue_dev_jwt(subject="user-biz-009", organization_id="BIZ-009", roles=["sme_submitter"])
        context = context_from_headers(authorization=f"Bearer {token}", app_mode="demo")

        with self.assertRaises(AccessDeniedError):
            self.service.intake.create_submission(
                organization_id="BIZ-010",
                period_key="2026-07",
                source_type="manual",
                sections={"financials": {"revenue": 1, "cash_in": 1, "cash_out": 1}},
                context=context,
            )

    def test_invoice_claim_idempotency_and_active_duplicate_guard(self) -> None:
        context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='lender-001', organization_id='BIZ-062', roles=['lender'])}",
            purpose="invoice_financing_review",
            app_mode="demo",
        )
        seller_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='seller-owner-005', organization_id='BIZ-005', roles=['org_admin'])}",
            app_mode="demo",
        )
        self.service.governance.create_consent(
            subject_id="BIZ-005",
            recipient_id="BIZ-062",
            scope="invoice_claim",
            purpose="invoice_financing_review",
            legal_basis="explicit_invoice_financing_consent",
            expires_at="2026-12-31T23:59:59Z",
            evidence_reference=None,
            context=seller_context,
        )
        first = self.service.governance.create_invoice_claim(
            seller_id="BIZ-005",
            buyer_id="BIZ-009",
            financier_id="BIZ-062",
            invoice_hash_value="abc1234567890def",
            amount=68_000_000,
            due_date="2026-07-08",
            invoice_id="INV-TRUST-001",
            issue_date="2026-06-08",
            currency="VND",
            idempotency_key="idem-001",
            source_evidence_id=None,
            context=context,
        )
        with self.assertRaises(AccessDeniedError):
            self.service.governance.create_invoice_claim(
                seller_id="BIZ-005",
                buyer_id="BIZ-009",
                financier_id="BIZ-999",
                invoice_hash_value="abc1234567890def-mismatch",
                amount=68_000_000,
                due_date="2026-07-08",
                invoice_id="INV-TRUST-001-MISMATCH",
                issue_date="2026-06-08",
                currency="VND",
                idempotency_key="idem-mismatch",
                source_evidence_id=None,
                context=context,
            )
        replay = self.service.governance.create_invoice_claim(
            seller_id="BIZ-005",
            buyer_id="BIZ-009",
            financier_id="BIZ-062",
            invoice_hash_value="abc1234567890def",
            amount=68_000_000,
            due_date="2026-07-08",
            invoice_id="INV-TRUST-001",
            issue_date="2026-06-08",
            currency="VND",
            idempotency_key="idem-001",
            source_evidence_id=None,
            context=context,
        )
        self.assertEqual(first["claim_id"], replay["claim_id"])

        verified = self.service.governance.transition_invoice_claim(first["claim_id"], "verified", "Counterparties matched.", context)
        pledged = self.service.governance.transition_invoice_claim(verified["claim_id"], "pledged", "Lender review hold.", context)
        self.assertEqual(pledged["status"], "pledged")

        with self.assertRaises(ValueError):
            self.service.governance.create_invoice_claim(
                seller_id="BIZ-005",
                buyer_id="BIZ-009",
                financier_id="BIZ-062",
                invoice_hash_value="abc1234567890def",
                amount=68_000_000,
                due_date="2026-07-08",
                invoice_id="INV-TRUST-001-COPY",
                issue_date="2026-06-08",
                currency="VND",
                idempotency_key="idem-002",
                source_evidence_id=None,
                context=context,
            )

    def test_audit_hash_chain_detects_tamper(self) -> None:
        self.service.business_detail_payload("BIZ-005")
        self.assertTrue(self.service.audit.verify_chain()["ok"])

        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT event_id FROM audit_logs WHERE event_hash IS NOT NULL ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            connection.execute("UPDATE audit_logs SET subject_id = 'BIZ-TAMPERED' WHERE event_id = ?", (row["event_id"],))
            connection.commit()

        result = self.service.audit.verify_chain()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "event_hash_mismatch")

    def test_audit_hash_chain_uses_insertion_order_for_rapid_events(self) -> None:
        for index in range(5):
            self.service.audit.record(
                "RAPID_AUDIT_EVENT",
                "demo_operator",
                f"BIZ-{index:03d}",
                "chain_order_test",
                actor_id="rapid-auditor",
                tenant_id="tenant-demo",
                request_id=f"req-rapid-{index}",
            )

        result = self.service.audit.verify_chain()
        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["checked"], 5)

    def test_external_finance_read_requires_active_consent_and_revoke_blocks(self) -> None:
        lender_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='lender-062', organization_id='BIZ-062', roles=['lender'])}",
            app_mode="demo",
        )
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='owner-005', organization_id='BIZ-005', roles=['org_admin'])}",
            app_mode="demo",
        )

        with self.assertRaises(AccessDeniedError):
            self.service.finance_payload_for_context("BIZ-005", lender_context)
        finance_denied = next(
            item for item in self.service.audit.list_recent() if item["event_type"] == "FINANCIALS_READ_DENIED"
        )
        self.assertEqual(finance_denied["actor_id"], "lender-062")
        self.assertEqual(finance_denied["subject_id"], "BIZ-005")
        self.assertTrue(finance_denied["policy_decision_id"])

        consent = self.service.governance.create_consent(
            subject_id="BIZ-005",
            recipient_id="BIZ-062",
            scope="financial_summary",
            purpose="management_review",
            legal_basis="explicit_sme_consent",
            expires_at="2026-12-31T23:59:59Z",
            evidence_reference=None,
            context=owner_context,
        )
        payload = self.service.finance_payload_for_context("BIZ-005", lender_context)
        self.assertIn("policy_decision_id", payload)

        self.service.governance.revoke_consent(consent["consent_id"], owner_context)
        with self.assertRaises(AccessDeniedError):
            self.service.finance_payload_for_context("BIZ-005", lender_context)

    def test_sensitive_read_denials_are_audited_for_evidence_and_invoice(self) -> None:
        lender_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='lender-062', organization_id='BIZ-062', roles=['lender'])}",
            app_mode="demo",
        )

        with self.assertRaises(AccessDeniedError):
            self.service.evidence_payload("BIZ-005", lender_context)
        with self.assertRaises(AccessDeniedError):
            self.service.invoice_payload("INV-0242", lender_context)

        events = self.service.audit.list_recent()
        evidence_denied = next(item for item in events if item["event_type"] == "EVIDENCE_READ_DENIED")
        invoice_denied = next(item for item in events if item["event_type"] == "INVOICE_READ_DENIED")

        self.assertEqual(evidence_denied["actor_id"], "lender-062")
        self.assertEqual(evidence_denied["subject_id"], "BIZ-005")
        self.assertTrue(evidence_denied["policy_decision_id"])
        self.assertEqual(invoice_denied["actor_id"], "lender-062")
        self.assertEqual(invoice_denied["subject_id"], "INV-0242")
        self.assertTrue(invoice_denied["policy_decision_id"])

    def test_demo_read_scope_does_not_bypass_external_finance_or_invoice(self) -> None:
        lender_demo_context = context_from_headers(
            tenant_id="tenant-demo",
            organization_id="BIZ-062",
            actor_id="lender-062",
            actor_role="lender",
            purpose="invoice_financing_review",
            scopes="demo:read invoice:read",
            app_mode="demo",
        )
        buyer_demo_context = context_from_headers(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="buyer-admin-009",
            actor_role="buyer_admin",
            purpose="supplier_risk_review",
            scopes="demo:read",
            app_mode="demo",
        )

        with self.assertRaises(AccessDeniedError):
            self.service.finance_payload_for_context("BIZ-005", lender_demo_context)
        with self.assertRaises(AccessDeniedError):
            self.service.invoice_payload("INV-0242", lender_demo_context)

        buyer_invoice = self.service.invoice_payload("INV-0242", buyer_demo_context)
        self.assertEqual(buyer_invoice["access_scope"], "buyer_party")
        self.assertEqual(buyer_invoice["policy_decision_id"][:4], "POL-")

    def test_selected_period_context_does_not_silently_fallback_for_finance_or_evidence(self) -> None:
        owner_context = context_from_headers(
            tenant_id="tenant-demo",
            organization_id="BIZ-005",
            actor_id="supplier-admin-005",
            actor_role="supplier_admin",
            purpose="period_review",
            scopes="finance:read evidence:read",
            app_mode="demo",
        )

        may_finance = self.service.finance_payload_for_context("BIZ-005", owner_context, period_key="2026-05")
        july_finance = self.service.finance_payload_for_context("BIZ-005", owner_context, period_key="2026-07")

        self.assertEqual(may_finance["latest"]["month"], "2026-05")
        self.assertIsNone(july_finance["latest"])
        self.assertEqual(july_finance["health"]["level"], "no_period_data")
        self.assertIn("No exact month row", july_finance["advisory_notice"])

        may_evidence = self.service.evidence_payload("BIZ-005", owner_context, period_key="2026-05")
        evidence_ids = {item["id"] for item in may_evidence["documents"]}

        self.assertIn("PO-260501", evidence_ids)
        self.assertNotIn("PO-260601", evidence_ids)
        self.assertEqual(may_evidence["period_key"], "2026-05")

    def test_pending_evidence_upload_tickets_are_persisted_and_listed_without_object_key(self) -> None:
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-005', organization_id='BIZ-005', roles=['supplier_admin'])}",
            app_mode="demo",
        )

        created = self.service.governance.create_evidence_upload_url(
            organization_id="BIZ-005",
            file_name="guarantee-2026-07.pdf",
            document_type="GUARANTEE",
            period_key="2026-07",
            content_type="application/pdf",
            byte_size=2048,
            classification="restricted_financial",
            purpose="evidence_intake",
            context=owner_context,
        )
        listed = self.service.governance.list_evidence_upload_tickets(
            organization_id="BIZ-005",
            period_key="2026-07",
            context=owner_context,
        )

        self.assertEqual(created["document_type"], "GUARANTEE")
        self.assertEqual(created["period_key"], "2026-07")
        self.assertEqual(listed["tickets"][0]["evidence_version_id"], created["evidence_version_id"])
        self.assertEqual(listed["tickets"][0]["document_type"], "GUARANTEE")
        self.assertEqual(listed["tickets"][0]["period_key"], "2026-07")
        self.assertEqual(listed["tickets"][0]["file_name"], "guarantee-2026-07.pdf")
        self.assertNotIn("object_key", listed["tickets"][0])
        self.assertTrue(listed["policy_decision_id"])
        self.assertTrue(listed["audit_event_id"])

    def test_financial_evidence_upload_requires_restricted_financial_classification(self) -> None:
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-005', organization_id='BIZ-005', roles=['supplier_admin'])}",
            app_mode="demo",
        )

        with self.assertRaises(ValueError):
            self.service.governance.create_evidence_upload_url(
                organization_id="BIZ-005",
                file_name="guarantee-2026-07.pdf",
                document_type="GUARANTEE",
                period_key="2026-07",
                content_type="application/pdf",
                byte_size=2048,
                classification="confidential",
                purpose="evidence_intake",
                context=owner_context,
            )

    def test_cross_org_cannot_list_or_complete_evidence_upload_ticket(self) -> None:
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-005', organization_id='BIZ-005', roles=['supplier_admin'])}",
            app_mode="demo",
        )
        cross_org_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-062', organization_id='BIZ-062', roles=['supplier_admin'])}",
            app_mode="demo",
        )
        created = self.service.governance.create_evidence_upload_url(
            organization_id="BIZ-005",
            file_name="private-ticket.pdf",
            document_type="CERTIFICATION",
            period_key="2026-07",
            content_type="application/pdf",
            byte_size=128,
            classification="confidential",
            purpose="evidence_intake",
            context=owner_context,
        )

        with self.assertRaises(AccessDeniedError):
            self.service.governance.list_evidence_upload_tickets(
                organization_id="BIZ-005",
                period_key="2026-07",
                context=cross_org_context,
            )
        with self.assertRaises(AccessDeniedError):
            self.service.governance.complete_evidence_upload_ticket(
                evidence_version_id=created["evidence_version_id"],
                organization_id="BIZ-005",
                document_hash="c" * 64,
                malware_scan_status="pending_scan",
                title="Cross org attempt",
                context=cross_org_context,
            )
        with self.assertRaises(IntakeNotFoundError):
            self.service.governance.complete_evidence_upload_ticket(
                evidence_version_id=created["evidence_version_id"],
                organization_id="BIZ-062",
                document_hash="d" * 64,
                malware_scan_status="pending_scan",
                title="Wrong org attempt",
                context=cross_org_context,
            )

        listed = self.service.governance.list_evidence_upload_tickets(
            organization_id="BIZ-005",
            period_key="2026-07",
            context=owner_context,
        )
        with closing(self.database.connect()) as connection:
            version = dict(
                connection.execute(
                    "SELECT evidence_document_id, object_version, malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    (created["evidence_version_id"],),
                ).fetchone()
            )
            denied_events = connection.execute(
                """
                SELECT event_type, actor_id, subject_id, policy_decision_id
                FROM audit_logs
                WHERE event_type IN ('EVIDENCE_UPLOAD_TICKETS_VIEW_DENIED', 'EVIDENCE_UPLOAD_COMPLETE_DENIED', 'EVIDENCE_UPLOAD_TICKET_NOT_FOUND')
                ORDER BY rowid
                """
            ).fetchall()

        self.assertEqual(listed["tickets"][0]["evidence_version_id"], created["evidence_version_id"])
        self.assertNotIn("object_key", listed["tickets"][0])
        self.assertIsNone(version["evidence_document_id"])
        self.assertEqual(version["object_version"], "pending-upload")
        self.assertEqual(version["malware_scan_status"], "pending_upload")
        self.assertEqual([row["event_type"] for row in denied_events], ["EVIDENCE_UPLOAD_TICKETS_VIEW_DENIED", "EVIDENCE_UPLOAD_COMPLETE_DENIED", "EVIDENCE_UPLOAD_TICKET_NOT_FOUND"])
        self.assertTrue(all(row["policy_decision_id"] for row in denied_events))
        self.assertTrue(all(row["actor_id"] == "supplier-admin-062" for row in denied_events))

    def test_completed_evidence_upload_ticket_appears_in_vault_as_pending_review(self) -> None:
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-005', organization_id='BIZ-005', roles=['supplier_admin'])}",
            app_mode="demo",
        )
        created = self.service.governance.create_evidence_upload_url(
            organization_id="BIZ-005",
            file_name="certificate-2026-07.pdf",
            document_type="CERTIFICATION",
            period_key="2026-07",
            content_type="application/pdf",
            byte_size=4096,
            classification="confidential",
            purpose="evidence_intake",
            context=owner_context,
        )
        completed = self.service.governance.complete_evidence_upload_ticket(
            evidence_version_id=created["evidence_version_id"],
            organization_id="BIZ-005",
            document_hash="b" * 64,
            malware_scan_status="pending_scan",
            title="HACCP certificate July upload",
            context=owner_context,
        )
        vault = self.service.evidence_payload("BIZ-005", context=owner_context)
        document = next(item for item in vault["documents"] if item["id"] == completed["evidence_document_id"])

        self.assertEqual(completed["document_type"], "CERTIFICATION")
        self.assertFalse(completed["usable"])
        self.assertEqual(document["verification_status"], "PENDING_REVIEW")
        self.assertEqual(document["hash"], "b" * 64)
        self.assertEqual(document["evidence_version_id"], created["evidence_version_id"])
        self.assertFalse(document["downloadable"])
        self.assertIn("Malware scan pending_scan", document["facts"])
        with self.assertRaises(AccessDeniedError):
            self.service.governance.create_evidence_download_url(created["evidence_version_id"], context=owner_context)

        scanner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='scanner-001', organization_id='BIZ-005', roles=['evidence_scanner'])}",
            app_mode="demo",
        )
        self.service.governance.record_evidence_scan_result(
            evidence_version_id=created["evidence_version_id"],
            organization_id="BIZ-005",
            malware_scan_status="clean",
            scanner_name="demo-scanner",
            scanner_version="0.1",
            scanned_at=None,
            details="Synthetic clean result for test.",
            context=scanner_context,
        )
        refreshed = self.service.evidence_payload("BIZ-005", context=owner_context)
        clean_document = next(item for item in refreshed["documents"] if item["id"] == completed["evidence_document_id"])
        self.assertEqual(clean_document["verification_status"], "VERIFIED")
        self.assertEqual(clean_document["evidence_version_id"], created["evidence_version_id"])
        self.assertTrue(clean_document["downloadable"])
        self.assertIn("Malware scan clean", clean_document["facts"])
        ticket = self.service.governance.create_evidence_download_url(created["evidence_version_id"], context=owner_context)
        self.assertEqual(ticket["download_method"], "GET")
        self.assertEqual(ticket["malware_scan_status"], "clean")
        self.assertTrue(ticket["policy_decision_id"])
        self.assertTrue(ticket["audit_event_id"])
        self.assertTrue(ticket["object_access_id"])
        self.assertNotIn("object_key", ticket)

    def test_evidence_upload_content_is_persisted_and_forced_to_pending_scan(self) -> None:
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-005', organization_id='BIZ-005', roles=['supplier_admin'])}",
            app_mode="demo",
        )
        content = b"demo evidence object bytes"
        document_hash = hashlib.sha256(content).hexdigest()
        created = self.service.governance.create_evidence_upload_url(
            organization_id="BIZ-005",
            file_name="guarantee-bytes.pdf",
            document_type="GUARANTEE",
            period_key="2026-07",
            content_type="application/pdf",
            byte_size=len(content),
            classification="restricted_financial",
            purpose="evidence_intake",
            context=owner_context,
        )

        completed = self.service.governance.complete_evidence_upload_ticket(
            evidence_version_id=created["evidence_version_id"],
            organization_id="BIZ-005",
            document_hash=document_hash,
            malware_scan_status="clean",
            title="Performance guarantee byte upload",
            context=owner_context,
            content_base64=base64.b64encode(content).decode("ascii"),
        )

        self.assertNotIn("object_key", created)
        self.assertNotIn("object_key", completed)
        self.assertEqual(completed["document_hash"], document_hash)
        self.assertEqual(completed["malware_scan_status"], "pending_scan")
        self.assertFalse(completed["usable"])
        self.assertEqual(completed["object_storage_status"], "local_demo")
        object_files = [path for path in (self.database.path.parent / "evidence_objects").rglob("*") if path.is_file()]
        self.assertEqual(len(object_files), 1)
        self.assertEqual(object_files[0].read_bytes(), content)
        with closing(self.database.connect()) as connection:
            completion_policy = connection.execute(
                "SELECT data_classification FROM policy_decisions WHERE decision_id = ?",
                (completed["policy_decision_id"],),
            ).fetchone()
        self.assertEqual(completion_policy["data_classification"], "restricted_financial")

    def test_restricted_evidence_governance_actions_preserve_classification(self) -> None:
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-005', organization_id='BIZ-005', roles=['supplier_admin'])}",
            app_mode="demo",
        )
        scanner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='scanner-001', organization_id='BIZ-005', roles=['evidence_scanner'])}",
            app_mode="demo",
        )
        created = self.service.governance.create_evidence_upload_url(
            organization_id="BIZ-005",
            file_name="restricted-guarantee.pdf",
            document_type="GUARANTEE",
            period_key="2026-07",
            content_type="application/pdf",
            byte_size=4096,
            classification="restricted_financial",
            purpose="evidence_intake",
            context=owner_context,
        )
        completed = self.service.governance.complete_evidence_upload_ticket(
            evidence_version_id=created["evidence_version_id"],
            organization_id="BIZ-005",
            document_hash="d" * 64,
            malware_scan_status="pending_scan",
            title="Restricted financial guarantee",
            context=owner_context,
        )

        with self.assertRaises(AccessDeniedError):
            self.service.governance.create_evidence_download_url(created["evidence_version_id"], context=owner_context)
        scan = self.service.governance.record_evidence_scan_result(
            evidence_version_id=created["evidence_version_id"],
            organization_id="BIZ-005",
            malware_scan_status="clean",
            scanner_name="demo-scanner",
            scanner_version="0.1",
            scanned_at=None,
            details="Synthetic clean result for test.",
            context=scanner_context,
        )
        version = self.service.governance.add_evidence_version(
            evidence_document_id=completed["evidence_document_id"],
            organization_id="BIZ-005",
            object_key="s3://vietsupply-evidence/tenant-demo/BIZ-005/restricted-guarantee-v2.pdf",
            document_hash="e" * 64,
            content_type="application/pdf",
            byte_size=2048,
            malware_scan_status="pending_scan",
            supersedes_version_id=created["evidence_version_id"],
            context=owner_context,
        )
        grant = self.service.governance.create_evidence_access_grant(
            evidence_document_id=completed["evidence_document_id"],
            organization_id="BIZ-005",
            grantee_organization_id="BIZ-062",
            scope="evidence_review",
            purpose="management_review",
            expires_at="2026-12-31T23:59:59Z",
            context=owner_context,
        )
        revoked = self.service.governance.revoke_evidence_access_grant(grant["grant_id"], context=owner_context)
        retention = self.service.governance.update_evidence_retention(
            evidence_document_id=completed["evidence_document_id"],
            organization_id="BIZ-005",
            retention_status="retention_locked",
            legal_hold=True,
            reason="restricted financial evidence retention test",
            context=owner_context,
        )

        tracked_decision_ids = [
            completed["policy_decision_id"],
            scan["policy_decision_id"],
            version["policy_decision_id"],
            grant["policy_decision_id"],
            revoked["policy_decision_id"],
            retention["policy_decision_id"],
        ]
        placeholders = ", ".join("?" for _ in tracked_decision_ids)
        with closing(self.database.connect()) as connection:
            classifications = {
                row["decision_id"]: row["data_classification"]
                for row in connection.execute(
                    f"SELECT decision_id, data_classification FROM policy_decisions WHERE decision_id IN ({placeholders})",
                    tuple(tracked_decision_ids),
                ).fetchall()
            }
            download_denial = connection.execute(
                """
                SELECT data_classification
                FROM policy_decisions
                WHERE action = 'read_evidence'
                  AND resource_id = ?
                  AND effect = 'deny'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (created["evidence_version_id"],),
            ).fetchone()
            stored_version = connection.execute(
                """
                SELECT classification, document_type, period_key
                FROM evidence_versions
                WHERE evidence_version_id = ?
                """,
                (version["evidence_version_id"],),
            ).fetchone()

        self.assertEqual(set(classifications), set(tracked_decision_ids))
        self.assertTrue(all(value == "restricted_financial" for value in classifications.values()))
        self.assertEqual(download_denial["data_classification"], "restricted_financial")
        self.assertEqual(stored_version["classification"], "restricted_financial")
        self.assertEqual(stored_version["document_type"], "GUARANTEE")
        self.assertEqual(stored_version["period_key"], "2026-07")

    def test_evidence_upload_hash_mismatch_rejects_without_materializing_document(self) -> None:
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='supplier-admin-005', organization_id='BIZ-005', roles=['supplier_admin'])}",
            app_mode="demo",
        )
        content = b"not the claimed file"
        created = self.service.governance.create_evidence_upload_url(
            organization_id="BIZ-005",
            file_name="mismatch.pdf",
            document_type="CERTIFICATION",
            period_key="2026-07",
            content_type="application/pdf",
            byte_size=len(content),
            classification="confidential",
            purpose="evidence_intake",
            context=owner_context,
        )

        with self.assertRaises(Exception) as raised:
            self.service.governance.complete_evidence_upload_ticket(
                evidence_version_id=created["evidence_version_id"],
                organization_id="BIZ-005",
                document_hash="0" * 64,
                malware_scan_status="pending_scan",
                title="Mismatch upload",
                context=owner_context,
                content_base64=base64.b64encode(content).decode("ascii"),
            )

        self.assertIn("hash", str(raised.exception).lower())
        with closing(self.database.connect()) as connection:
            version = dict(
                connection.execute(
                    "SELECT evidence_document_id, object_version, document_hash, malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    (created["evidence_version_id"],),
                ).fetchone()
            )
            documents = connection.execute(
                "SELECT COUNT(*) AS count FROM evidence_documents WHERE source_record_id = ?",
                (created["evidence_version_id"],),
            ).fetchone()
            rejected_events = connection.execute(
                "SELECT COUNT(*) AS count FROM audit_logs WHERE event_type = 'EVIDENCE_UPLOAD_REJECTED'",
            ).fetchone()
            access_logs = connection.execute(
                "SELECT access_type, access_status, object_key_hash, reason FROM evidence_object_access_logs WHERE evidence_version_id = ? ORDER BY created_at DESC LIMIT 1",
                (created["evidence_version_id"],),
            ).fetchone()
        self.assertIsNone(version["evidence_document_id"])
        self.assertEqual(version["object_version"], "pending-upload")
        self.assertEqual(version["document_hash"], "")
        self.assertEqual(version["malware_scan_status"], "pending_upload")
        self.assertEqual(documents["count"], 0)
        self.assertGreaterEqual(rejected_events["count"], 1)
        self.assertEqual(access_logs["access_type"], "upload_complete")
        self.assertEqual(access_logs["access_status"], "denied")
        self.assertTrue(access_logs["object_key_hash"])
        self.assertEqual(access_logs["reason"], "document_hash_mismatch")

    def test_external_invoice_claim_requires_invoice_consent(self) -> None:
        lender_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='lender-062', organization_id='BIZ-062', roles=['lender'])}",
            app_mode="demo",
        )
        owner_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='owner-005', organization_id='BIZ-005', roles=['org_admin'])}",
            app_mode="demo",
        )

        with self.assertRaises(AccessDeniedError):
            self.service.governance.create_invoice_claim(
                seller_id="BIZ-005",
                buyer_id="BIZ-009",
                financier_id="BIZ-062",
                invoice_hash_value="feed1234567890abc",
                amount=68_000_000,
                due_date="2026-07-08",
                invoice_id="INV-CONSENT-001",
                issue_date="2026-06-08",
                currency="VND",
                idempotency_key="external-denied",
                source_evidence_id=None,
                context=lender_context,
            )

        self.service.governance.create_consent(
            subject_id="BIZ-005",
            recipient_id="BIZ-062",
            scope="invoice_claim",
            purpose="management_review",
            legal_basis="explicit_invoice_financing_consent",
            expires_at="2026-12-31T23:59:59Z",
            evidence_reference=None,
            context=owner_context,
        )
        claim = self.service.governance.create_invoice_claim(
            seller_id="BIZ-005",
            buyer_id="BIZ-009",
            financier_id="BIZ-062",
            invoice_hash_value="feed1234567890abc",
            amount=68_000_000,
            due_date="2026-07-08",
            invoice_id="INV-CONSENT-001",
            issue_date="2026-06-08",
            currency="VND",
            idempotency_key="external-allowed",
            source_evidence_id=None,
            context=lender_context,
        )
        self.assertEqual(claim["status"], "registered")


if __name__ == "__main__":
    unittest.main()
