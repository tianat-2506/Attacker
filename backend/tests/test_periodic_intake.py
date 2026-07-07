from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.services.access_control import AccessDeniedError, RequestContext
from backend.app.services.database import Database
from backend.app.services.radar_service import create_service


class PeriodicIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "demo.db")
        self.database.seed_from_csv(reset=True)
        self.service = create_service(self.database)
        self.context = RequestContext.authorized_demo()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seeded_monthly_periods_are_queryable(self) -> None:
        periods = self.service.intake.list_periods("BIZ-009")

        self.assertGreaterEqual(len(periods), 12)
        self.assertEqual(periods[0]["period_type"], "month")
        self.assertRegex(periods[0]["period_key"], r"^\d{4}-\d{2}$")

    def test_draft_validate_submit_approve_materializes_period_snapshot(self) -> None:
        submission = self.service.intake.create_submission(
            organization_id="BIZ-009",
            period_key="2026-07",
            source_type="manual",
            sections={
                "financials": {
                    "revenue": 790_000_000,
                    "cash_in": 810_000_000,
                    "cash_out": 730_000_000,
                    "debt": 180_000_000,
                    "accounts_receivable": 120_000_000,
                    "accounts_payable": 90_000_000,
                    "inventory_value": 160_000_000,
                    "late_payment_rate": 0.04,
                    "delivery_delay_rate": 0.02,
                },
                "products": [
                    {
                        "sku": "SME-BEV-330",
                        "product_name": "Ready drink 330ml",
                        "category": "beverage",
                        "specification": "330ml can",
                        "available_capacity": 12_000,
                        "min_order_value": 5_000_000,
                        "price_range": "mid",
                        "certifications": "HACCP",
                    }
                ],
                "evidence": [
                    {
                        "document_type": "CERTIFICATION",
                        "title": "HACCP July certificate",
                        "document_hash": "hash-july-haccp",
                        "classification": "confidential",
                        "malware_scan_status": "clean",
                    }
                ],
            },
            context=self.context,
        )

        validated = self.service.intake.validate_submission(submission["id"], self.context)
        self.assertEqual(validated["status"], "ready")
        self.assertEqual(validated["validation_summary"]["errors"], 0)

        submitted = self.service.intake.submit_submission(submission["id"], self.context)
        self.assertEqual(submitted["status"], "in_review")
        self.assertIsNotNone(submitted["review_task"])

        approved = self.service.intake.review_decision(
            submitted["review_task"]["id"],
            "approve",
            "Accepted for July demo period.",
            self.context,
        )
        self.assertEqual(approved["status"], "approved")

        snapshot = self.service.intake.period_snapshot("BIZ-009", "2026-07")
        self.assertEqual(snapshot["approved_version"], 1)
        self.assertEqual(snapshot["latest_submission_status"], "approved")
        self.assertEqual(snapshot["financials"][0]["revenue"], 790_000_000)
        self.assertEqual(snapshot["products"][0]["sku"], "SME-BEV-330")
        self.assertEqual(snapshot["evidence"][0]["document_hash"], "hash-july-haccp")
        self.assertIn(submission["id"], snapshot["source_submission_ids"])

        risk_runs = self.service.governance.list_risk_runs("BIZ-009", "2026-07", self.context)
        match_runs = self.service.governance.list_match_runs("BIZ-009", "2026-07", self.context)
        scenario_runs = self.service.governance.list_scenario_runs("BIZ-009", "2026-07", self.context)
        self.assertEqual(risk_runs["risk_runs"][0]["feature_snapshot_id"], f"FS-{submission['id']}")
        self.assertEqual(match_runs["match_runs"][0]["review_status"], "pending_human_review")
        self.assertEqual(scenario_runs["scenario_runs"][0]["input_snapshot_id"], f"FS-{submission['id']}")
        self.assertEqual(scenario_runs["scenario_runs"][0]["review_status"], "pending_human_review")
        self.assertIn("human review", scenario_runs["scenario_runs"][0]["payload"]["guardrail"])
        with closing(self.database.connect()) as connection:
            model_count = connection.execute("SELECT COUNT(*) AS count FROM model_registry").fetchone()["count"]
            ruleset_count = connection.execute("SELECT COUNT(*) AS count FROM ruleset_registry").fetchone()["count"]
            recompute_job = connection.execute(
                "SELECT * FROM analytics_recompute_jobs WHERE idempotency_key = ?",
                (f"analytics:{submission['id']}",),
            ).fetchone()
        self.assertGreaterEqual(model_count, 2)
        self.assertGreaterEqual(ruleset_count, 4)
        self.assertEqual(recompute_job["status"], "queued")
        self.assertIn("approved_intake_materialized", recompute_job["payload_json"])
        model_registry = self.service.governance.list_model_registry("risk", self.context)
        ruleset_registry = self.service.governance.list_ruleset_registry("risk", self.context)
        recompute_jobs = self.service.governance.list_recompute_jobs(
            organization_id="BIZ-009",
            status="queued",
            limit=10,
            context=self.context,
        )
        self.assertEqual(model_registry["models"][0]["artifact_type"], "risk")
        self.assertEqual(ruleset_registry["rulesets"][0]["artifact_type"], "risk")
        self.assertEqual(recompute_jobs["jobs"][0]["idempotency_key"], f"analytics:{submission['id']}")

    def test_uploaded_clean_evidence_is_counted_and_sourced_in_approved_snapshot(self) -> None:
        upload = self.service.governance.create_evidence_upload_url(
            organization_id="BIZ-009",
            file_name="performance-guarantee-2026-12.pdf",
            document_type="GUARANTEE",
            period_key="2026-12",
            content_type="application/pdf",
            byte_size=4096,
            classification="restricted_financial",
            purpose="evidence_intake",
            context=self.context,
        )
        completed = self.service.governance.complete_evidence_upload_ticket(
            evidence_version_id=upload["evidence_version_id"],
            organization_id="BIZ-009",
            document_hash="f" * 64,
            malware_scan_status="pending_scan",
            title="Performance guarantee December",
            context=self.context,
        )
        self.service.governance.record_evidence_scan_result(
            evidence_version_id=upload["evidence_version_id"],
            organization_id="BIZ-009",
            malware_scan_status="clean",
            scanner_name="demo-scanner",
            scanner_version="0.1",
            scanned_at=None,
            details="Synthetic clean result for intake snapshot provenance.",
            context=self.context,
        )
        submission = self.service.intake.create_submission(
            organization_id="BIZ-009",
            period_key="2026-12",
            source_type="manual",
            sections={"financials": {"revenue": 12_000, "cash_in": 12_500, "cash_out": 9_000}},
            context=self.context,
        )
        submitted = self.service.intake.submit_submission(submission["id"], self.context)

        self.service.intake.review_decision(submitted["review_task"]["id"], "approve", "Clean uploaded guarantee present.", self.context)
        snapshot = self.service.intake.period_snapshot("BIZ-009", "2026-12")
        guarantee = next(item for item in snapshot["evidence"] if item["evidence_document_id"] == completed["evidence_document_id"])

        self.assertEqual(snapshot["sections"]["evidence"]["count"], 1)
        self.assertIn(submission["id"], snapshot["source_submission_ids"])
        self.assertIn(f"UPLOAD-{upload['evidence_version_id']}", snapshot["source_submission_ids"])
        self.assertEqual(guarantee["source_submission_id"], f"UPLOAD-{upload['evidence_version_id']}")
        self.assertEqual(guarantee["source_record_id"], upload["evidence_version_id"])
        self.assertEqual(guarantee["classification"], "restricted_financial")
        self.assertEqual(guarantee["malware_scan_status"], "clean")

    def test_reviewer_queue_lists_open_submissions_and_closes_after_decision(self) -> None:
        submission = self.service.intake.create_submission(
            organization_id="BIZ-009",
            period_key="2026-07",
            source_type="manual",
            sections={
                "financials": {"revenue": 100, "cash_in": 120, "cash_out": 90},
                "products": [{"sku": "QUEUE-SKU", "product_name": "Queue product", "available_capacity": 1}],
            },
            context=self.context,
        )
        submitted = self.service.intake.submit_submission(submission["id"], self.context)
        reviewer_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="reviewer-001",
            actor_role="reviewer",
            purpose="submission_review",
            roles=frozenset({"reviewer"}),
            memberships=(),
        )

        queue = self.service.intake.list_review_tasks(reviewer_context)
        item = next(row for row in queue["review_tasks"] if row["submission_id"] == submission["id"])

        self.assertEqual(item["review_task_id"], submitted["review_task"]["id"])
        self.assertEqual(item["review_status"], "open")
        self.assertEqual(item["submission_status"], "in_review")
        self.assertEqual(item["organization_name"], "Thu Duc Retail Mart")
        self.assertEqual(item["period_key"], "2026-07")
        self.assertEqual(item["assigned_to"], "reviewer-001")
        self.assertEqual(item["assignment_reason"], "auto_assigned_primary_org_reviewer")
        self.assertEqual(item["validation_summary"]["errors"], 0)
        self.assertEqual(item["evidence_review"]["total"], 0)
        self.assertFalse(item["evidence_review"]["approval_blocked"])
        self.assertTrue(queue["policy_decision_id"])
        self.assertTrue(queue["audit_event_id"])

        submitter_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="submitter-001",
            actor_role="sme_submitter",
            purpose="data_intake",
            roles=frozenset({"sme_submitter"}),
            memberships=(),
        )
        other_reviewer_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-001",
            actor_id="reviewer-002",
            actor_role="reviewer",
            purpose="submission_review",
            roles=frozenset({"reviewer"}),
            memberships=(),
        )
        same_org_other_reviewer_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="reviewer-002",
            actor_role="reviewer",
            purpose="submission_review",
            roles=frozenset({"reviewer"}),
            memberships=(),
        )

        with self.assertRaises(AccessDeniedError):
            self.service.intake.list_review_tasks(submitter_context)
        scoped_queue = self.service.intake.list_review_tasks(other_reviewer_context)
        self.assertNotIn(submission["id"], [row["submission_id"] for row in scoped_queue["review_tasks"]])
        assigned_queue = self.service.intake.list_review_tasks(same_org_other_reviewer_context)
        self.assertNotIn(submission["id"], [row["submission_id"] for row in assigned_queue["review_tasks"]])
        with self.assertRaises(AccessDeniedError):
            self.service.intake.review_decision(submitted["review_task"]["id"], "request_changes", "Wrong reviewer.", same_org_other_reviewer_context)

        self.service.intake.review_decision(submitted["review_task"]["id"], "request_changes", "Need product detail.", reviewer_context)
        refreshed = self.service.intake.list_review_tasks(reviewer_context)
        self.assertNotIn(submission["id"], [row["submission_id"] for row in refreshed["review_tasks"]])

    def test_csv_import_replay_is_idempotent(self) -> None:
        csv_text = "\n".join(
            [
                "revenue,cash_in,cash_out,debt,accounts_receivable,accounts_payable,inventory_value,late_payment_rate,delivery_delay_rate",
                "620000000,640000000,590000000,140000000,80000000,70000000,120000000,0.03,0.01",
            ]
        )
        first = self.service.intake.create_import_batch(
            organization_id="BIZ-009",
            period_key="2026-08",
            dataset="financials",
            file_name="financials-2026-08.csv",
            csv_text=csv_text,
            context=self.context,
        )
        second = self.service.intake.create_import_batch(
            organization_id="BIZ-009",
            period_key="2026-08",
            dataset="financials",
            file_name="financials-2026-08.csv",
            csv_text=csv_text,
            context=self.context,
            submission_id=first["submission_id"],
        )

        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["idempotent_replay"])
        submission = self.service.intake.validate_submission(first["submission_id"], self.context)
        self.assertEqual(submission["validation_summary"]["errors"], 0)

    def test_csv_raw_records_link_to_approved_canonical_rows(self) -> None:
        financials_csv = "\n".join(
            [
                "revenue,cash_in,cash_out,debt,accounts_receivable,accounts_payable,inventory_value,late_payment_rate,delivery_delay_rate",
                "720000000,740000000,690000000,130000000,70000000,60000000,110000000,0.02,0.01",
            ]
        )
        products_csv = "\n".join(
            [
                "sku,product_name,category,available_capacity,min_order_value",
                "CSV-SKU-A,CSV product A,beverage,1200,5000000",
                "CSV-SKU-B,CSV product B,beverage,800,3000000",
            ]
        )
        financials_batch = self.service.intake.create_import_batch(
            organization_id="BIZ-009",
            period_key="2026-04",
            dataset="financials",
            file_name="financials-2026-04.csv",
            csv_text=financials_csv,
            context=self.context,
        )
        products_batch = self.service.intake.create_import_batch(
            organization_id="BIZ-009",
            period_key="2026-04",
            dataset="products",
            file_name="products-2026-04.csv",
            csv_text=products_csv,
            context=self.context,
            submission_id=financials_batch["submission_id"],
        )
        validated = self.service.intake.validate_submission(financials_batch["submission_id"], self.context)
        submitted = self.service.intake.submit_submission(validated["id"], self.context)

        self.service.intake.review_decision(submitted["review_task"]["id"], "approve", "CSV raw lineage accepted.", self.context)
        snapshot = self.service.intake.period_snapshot("BIZ-009", "2026-04")

        with closing(self.database.connect()) as connection:
            financial_raw = connection.execute(
                "SELECT raw_record_id FROM raw_records WHERE batch_id = ? ORDER BY row_number",
                (financials_batch["id"],),
            ).fetchone()
            product_raw_rows = connection.execute(
                "SELECT raw_record_id FROM raw_records WHERE batch_id = ? ORDER BY row_number",
                (products_batch["id"],),
            ).fetchall()

        products_by_sku = {item["sku"]: item for item in snapshot["products"]}
        self.assertEqual(snapshot["financials"][0]["source_record_id"], financial_raw["raw_record_id"])
        self.assertEqual(products_by_sku["CSV-SKU-A"]["source_record_id"], product_raw_rows[0]["raw_record_id"])
        self.assertEqual(products_by_sku["CSV-SKU-B"]["source_record_id"], product_raw_rows[1]["raw_record_id"])
        self.assertIn(financials_batch["submission_id"], snapshot["source_submission_ids"])

    def test_csv_validation_errors_quarantine_batch_and_export_error_report(self) -> None:
        csv_text = "\n".join(
            [
                "sku,product_name,category,available_capacity",
                ",Missing SKU,beverage,120",
                "SKU-NEG,Negative capacity,beverage,-10",
            ]
        )
        batch = self.service.intake.create_import_batch(
            organization_id="BIZ-009",
            period_key="2026-11",
            dataset="products",
            file_name="products-2026-11.csv",
            csv_text=csv_text,
            context=self.context,
        )
        submission = self.service.intake.validate_submission(batch["submission_id"], self.context)
        report = self.service.intake.error_report(batch["submission_id"], self.context, report_format="csv")

        self.assertGreaterEqual(submission["validation_summary"]["errors"], 2)
        self.assertEqual(report["summary"]["errors"], 4)
        self.assertIn("SKU_REQUIRED", report["csv"])
        self.assertIn("NEGATIVE_CAPACITY", report["csv"])

        with closing(self.database.connect()) as connection:
            stored_batch = connection.execute("SELECT status FROM ingestion_batches WHERE batch_id = ?", (batch["id"],)).fetchone()
            raw_error_count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM raw_record_errors rre
                JOIN raw_records rr ON rr.raw_record_id = rre.raw_record_id
                WHERE rr.batch_id = ?
                """,
                (batch["id"],),
            ).fetchone()["count"]

        self.assertEqual(stored_batch["status"], "quarantined")
        self.assertGreaterEqual(raw_error_count, 2)

    def test_financial_evidence_metadata_requires_restricted_financial_classification(self) -> None:
        submission = self.service.intake.create_submission(
            organization_id="BIZ-009",
            period_key="2026-12",
            source_type="manual",
            sections={
                "evidence": [
                    {
                        "document_type": "GUARANTEE",
                        "title": "Performance guarantee",
                        "document_hash": "hash-guarantee-demo",
                        "classification": "confidential",
                        "malware_scan_status": "clean",
                    }
                ]
            },
            context=self.context,
        )

        validated = self.service.intake.validate_submission(submission["id"], self.context)

        self.assertEqual(validated["validation_summary"]["errors"], 1)
        self.assertEqual(validated["issues"][0]["code"], "RESTRICTED_FINANCIAL_CLASSIFICATION_REQUIRED")

    def test_rejected_submission_does_not_materialize_snapshot(self) -> None:
        submission = self.service.intake.create_submission(
            organization_id="BIZ-009",
            period_key="2026-09",
            source_type="manual",
            sections={"financials": {"revenue": 1, "cash_in": 1, "cash_out": 1}},
            context=self.context,
        )
        submitted = self.service.intake.submit_submission(submission["id"], self.context)
        rejected = self.service.intake.review_decision(
            submitted["review_task"]["id"],
            "reject",
            "Not enough supporting data.",
            self.context,
        )

        self.assertEqual(rejected["status"], "rejected")
        snapshot = self.service.intake.period_snapshot("BIZ-009", "2026-09")
        self.assertIsNone(snapshot["approved_version"])
        self.assertEqual(snapshot["latest_submission_status"], "rejected")

    def test_pending_scan_evidence_blocks_approval(self) -> None:
        submission = self.service.intake.create_submission(
            organization_id="BIZ-009",
            period_key="2026-10",
            source_type="manual",
            sections={
                "financials": {"revenue": 10, "cash_in": 10, "cash_out": 9},
                "evidence": [
                    {
                        "document_type": "CERTIFICATION",
                        "title": "Pending scan certificate",
                        "document_hash": "hash-pending-scan",
                        "classification": "confidential",
                        "malware_scan_status": "pending_scan",
                    }
                ],
            },
            context=self.context,
        )
        submitted = self.service.intake.submit_submission(submission["id"], self.context)
        queue = self.service.intake.list_review_tasks(self.context)
        item = next(row for row in queue["review_tasks"] if row["submission_id"] == submission["id"])

        self.assertEqual(item["evidence_review"]["total"], 1)
        self.assertEqual(item["evidence_review"]["pending"], 1)
        self.assertTrue(item["evidence_review"]["approval_blocked"])
        requirements = {requirement["document_type"]: requirement for requirement in item["evidence_review"]["requirements"]}
        self.assertEqual(requirements["CERTIFICATION"]["status"], "pending")
        self.assertEqual(requirements["CERTIFICATION"]["pending"], 1)
        self.assertFalse(requirements["CERTIFICATION"]["satisfied"])
        self.assertEqual(requirements["GUARANTEE"]["status"], "missing")
        with self.assertRaises(ValueError):
            self.service.intake.review_decision(submitted["review_task"]["id"], "approve", "Clean financials only.", self.context)
        snapshot = self.service.intake.period_snapshot("BIZ-009", "2026-10")

        self.assertIsNone(snapshot["approved_version"])
        self.assertEqual(snapshot["latest_submission_status"], "in_review")
        self.assertEqual(snapshot["evidence"], [])


if __name__ == "__main__":
    unittest.main()
