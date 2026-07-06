from __future__ import annotations

import unittest
from pathlib import Path

from scripts.validate_postgres_migrations import MIGRATION, validate


class PostgresMigrationArtifactTests(unittest.TestCase):
    def test_trust_foundation_migration_has_rls_and_postgis_controls(self) -> None:
        self.assertEqual(validate(), [])
        sql = Path(MIGRATION).read_text(encoding="utf-8")

        self.assertIn("CREATE EXTENSION IF NOT EXISTS postgis", sql)
        self.assertGreaterEqual(sql.count("ENABLE ROW LEVEL SECURITY"), 15)
        self.assertIn("CREATE OR REPLACE FUNCTION app_try_uuid", sql)
        self.assertIn("tenants.external_key", sql)
        self.assertIn("organizations.external_business_id", sql)
        self.assertIn("CREATE POLICY financials_consent_or_owner", sql)
        self.assertIn("CREATE TABLE review_tasks", sql)
        self.assertIn("assigned_to uuid REFERENCES user_accounts(user_id)", sql)
        self.assertIn("assignment_reason text", sql)
        self.assertIn("CREATE POLICY review_tasks_via_submission", sql)
        self.assertIn("CREATE TABLE product_capabilities", sql)
        self.assertIn("CREATE POLICY products_consent_or_owner", sql)
        self.assertIn("source_submission_id uuid REFERENCES data_submissions(submission_id)", sql)
        self.assertIn("CREATE TABLE evidence_access_grants", sql)
        self.assertIn("CREATE TABLE evidence_object_access_logs", sql)
        self.assertIn("CREATE OR REPLACE FUNCTION app_has_active_evidence_grant", sql)
        self.assertIn("grant_row.purpose = requested_purpose", sql)
        self.assertIn("cr.purpose = requested_purpose", sql)
        self.assertIn("ALTER TABLE evidence_access_grants ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER TABLE evidence_object_access_logs ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("CREATE POLICY evidence_access_grants_subject_or_grantee", sql)
        self.assertIn("CREATE POLICY evidence_object_access_logs_tenant", sql)
        self.assertIn(
            "app_has_active_evidence_grant(evidence_document_id, 'evidence_review', NULLIF(current_setting('app.purpose', true), ''))",
            sql,
        )
        self.assertIn("CREATE TABLE ingestion_batches", sql)
        self.assertIn("CREATE TABLE raw_records", sql)
        self.assertIn("CREATE TABLE raw_record_errors", sql)
        self.assertIn("CREATE POLICY raw_records_via_batch", sql)
        self.assertIn("CREATE TABLE scenario_runs", sql)
        self.assertIn("CREATE TABLE model_registry", sql)
        self.assertIn("CREATE TABLE ruleset_registry", sql)
        self.assertIn("CREATE TABLE analytics_recompute_jobs", sql)
        self.assertIn("ALTER TABLE scenario_runs ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER TABLE ruleset_registry ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER TABLE analytics_recompute_jobs ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("CREATE POLICY scenario_runs_consent_or_owner", sql)
        self.assertIn("CREATE POLICY model_registry_tenant", sql)
        self.assertIn("CREATE POLICY ruleset_registry_tenant", sql)
        self.assertIn("CREATE POLICY analytics_recompute_jobs_owner", sql)
        self.assertIn("CREATE POLICY invoice_claims_party_or_consent", sql)
        self.assertIn("CREATE TRIGGER audit_logs_append_only", sql)


if __name__ == "__main__":
    unittest.main()
