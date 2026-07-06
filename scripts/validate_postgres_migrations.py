from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "backend" / "migrations" / "versions" / "0001_trust_foundation_postgres.sql"

REQUIRED_SNIPPETS = [
    "CREATE EXTENSION IF NOT EXISTS postgis",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "CREATE EXTENSION IF NOT EXISTS citext",
    "CREATE OR REPLACE FUNCTION app_try_uuid",
    "current_setting('app.tenant_id'",
    "current_setting('app.organization_ids'",
    "tenants.external_key",
    "organizations.external_business_id",
    "ALTER TABLE financial_snapshots ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE evidence_documents ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE evidence_object_access_logs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE invoice_claims ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE scenario_runs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ruleset_registry ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE analytics_recompute_jobs ENABLE ROW LEVEL SECURITY",
    "CREATE POLICY financials_consent_or_owner",
    "CREATE POLICY evidence_consent_or_owner",
    "CREATE POLICY evidence_object_access_logs_tenant",
    "CREATE POLICY scenario_runs_consent_or_owner",
    "CREATE POLICY model_registry_tenant",
    "CREATE POLICY ruleset_registry_tenant",
    "CREATE POLICY analytics_recompute_jobs_owner",
    "CREATE POLICY invoice_claims_party_or_consent",
    "CREATE TRIGGER audit_logs_append_only",
    "invoice_claim_active_financing_idx",
]


def validate() -> list[str]:
    if not MIGRATION.exists():
        return [f"Missing migration: {MIGRATION}"]
    sql = MIGRATION.read_text(encoding="utf-8")
    errors = [f"Missing required migration snippet: {snippet}" for snippet in REQUIRED_SNIPPETS if snippet not in sql]
    if sql.count("ENABLE ROW LEVEL SECURITY") < 15:
        errors.append("Expected at least 15 RLS-enabled tables in trust foundation migration.")
    if "DROP POLICY" in sql.upper():
        errors.append("Migration should not drop policies in the initial trust foundation artifact.")
    return errors


if __name__ == "__main__":
    errors = validate()
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("PostgreSQL trust migration validation passed.")
