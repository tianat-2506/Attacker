from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.access_control import Membership, RequestContext
from backend.app.services.postgres_migrations import PostgresMigrationRunner, set_rls_session


def _database_url(cli_value: str | None) -> str:
    value = cli_value or os.getenv("POSTGRES_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise SystemExit("Set --database-url or POSTGRES_TEST_DATABASE_URL for the RLS smoke test.")
    return value


def _one(connection: Any, statement: str, params: tuple[Any, ...] = ()) -> Any:
    row = connection.execute(statement, params).fetchone()
    return row[0] if row else None


def _request_context(tenant_key: str, organization_key: str, purpose: str = "management_review") -> RequestContext:
    return RequestContext(
        tenant_id=tenant_key,
        organization_id=organization_key,
        actor_id="postgres-rls-smoke-user",
        actor_role="sme_submitter",
        purpose=purpose,
        scopes=frozenset({"finance:read", "evidence:read"}),
        roles=frozenset({"sme_submitter"}),
        memberships=(Membership(organization_key, "sme_submitter"),),
        request_id=f"rls-smoke-{secrets.token_hex(4)}",
        auth_assurance="integration-test",
        app_mode="pilot",
    )


def run(database_url: str) -> None:
    try:
        import psycopg  # type: ignore[import-not-found]
        from psycopg import sql  # type: ignore[import-not-found]
        from psycopg.types.json import Jsonb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("Install backend requirements with psycopg before running this smoke test.") from exc

    applied = PostgresMigrationRunner(database_url).apply()
    suffix = secrets.token_hex(5)
    tenant_key = f"tenant-rls-smoke-{suffix}"
    owner_key = f"BIZ-RLS-OWNER-{suffix}"
    other_key = f"BIZ-RLS-OTHER-{suffix}"
    outside_tenant_key = f"tenant-rls-outside-{suffix}"
    outside_org_key = f"BIZ-RLS-OUTSIDE-{suffix}"
    role_name = f"vietsupply_rls_smoke_{suffix}"

    with psycopg.connect(database_url, autocommit=False) as connection:
        with connection.transaction():
            current_user = _one(connection, "SELECT current_user")
            bypasses_rls = _one(connection, "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            if bypasses_rls:
                print(f"Connected as {current_user}; assertions will run under non-bypass role {role_name}.")

            connection.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role_name)))
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role_name)))
            connection.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role_name)))

            tenant_id = _one(
                connection,
                "INSERT INTO tenants (external_key, name) VALUES (%s, %s) RETURNING tenant_id",
                (tenant_key, "RLS smoke tenant"),
            )
            owner_org_id = _one(
                connection,
                """
                INSERT INTO organizations (tenant_id, external_business_id, name, organization_type)
                VALUES (%s, %s, %s, %s)
                RETURNING organization_id
                """,
                (tenant_id, owner_key, "RLS owner SME", "sme"),
            )
            other_org_id = _one(
                connection,
                """
                INSERT INTO organizations (tenant_id, external_business_id, name, organization_type)
                VALUES (%s, %s, %s, %s)
                RETURNING organization_id
                """,
                (tenant_id, other_key, "RLS other SME", "sme"),
            )
            outside_tenant_id = _one(
                connection,
                "INSERT INTO tenants (external_key, name) VALUES (%s, %s) RETURNING tenant_id",
                (outside_tenant_key, "RLS outside tenant"),
            )
            outside_org_id = _one(
                connection,
                """
                INSERT INTO organizations (tenant_id, external_business_id, name, organization_type)
                VALUES (%s, %s, %s, %s)
                RETURNING organization_id
                """,
                (outside_tenant_id, outside_org_key, "RLS outside SME", "sme"),
            )
            user_id = _one(
                connection,
                """
                INSERT INTO user_accounts (tenant_id, external_subject, display_name)
                VALUES (%s, %s, %s)
                RETURNING user_id
                """,
                (tenant_id, f"rls-user-{suffix}", "RLS Smoke User"),
            )
            connection.execute(
                "INSERT INTO roles (role_id, description) VALUES (%s, %s) ON CONFLICT (role_id) DO NOTHING",
                ("sme_submitter", "SME data submitter"),
            )
            connection.execute(
                """
                INSERT INTO memberships (tenant_id, organization_id, user_id, role_id)
                VALUES (%s, %s, %s, %s)
                """,
                (tenant_id, owner_org_id, user_id, "sme_submitter"),
            )

            owner_period_id = _one(
                connection,
                """
                INSERT INTO reporting_periods (tenant_id, organization_id, period_key, period_start, period_end)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING reporting_period_id
                """,
                (tenant_id, owner_org_id, "2026-06", "2026-06-01", "2026-06-30"),
            )
            other_period_id = _one(
                connection,
                """
                INSERT INTO reporting_periods (tenant_id, organization_id, period_key, period_start, period_end)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING reporting_period_id
                """,
                (tenant_id, other_org_id, "2026-06", "2026-06-01", "2026-06-30"),
            )
            outside_period_id = _one(
                connection,
                """
                INSERT INTO reporting_periods (tenant_id, organization_id, period_key, period_start, period_end)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING reporting_period_id
                """,
                (outside_tenant_id, outside_org_id, "2026-06", "2026-06-01", "2026-06-30"),
            )

            owner_submission_id = _one(
                connection,
                """
                INSERT INTO data_submissions (
                  tenant_id, organization_id, reporting_period_id, source_type, status, version, submitted_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING submission_id
                """,
                (tenant_id, owner_org_id, owner_period_id, "manual", "approved", 1, user_id),
            )
            other_submission_id = _one(
                connection,
                """
                INSERT INTO data_submissions (
                  tenant_id, organization_id, reporting_period_id, source_type, status, version, submitted_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING submission_id
                """,
                (tenant_id, other_org_id, other_period_id, "manual", "approved", 1, user_id),
            )
            outside_submission_id = _one(
                connection,
                """
                INSERT INTO data_submissions (
                  tenant_id, organization_id, reporting_period_id, source_type, status, version, submitted_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING submission_id
                """,
                (outside_tenant_id, outside_org_id, outside_period_id, "manual", "approved", 1, user_id),
            )

            for org_id, period_id, submission_id, source_record_id, revenue in (
                (owner_org_id, owner_period_id, owner_submission_id, "owner-row", 100),
                (other_org_id, other_period_id, other_submission_id, "other-row", 200),
                (outside_org_id, outside_period_id, outside_submission_id, "outside-row", 300),
            ):
                connection.execute(
                    """
                    INSERT INTO financial_snapshots (
                      tenant_id, organization_id, reporting_period_id, statement_type, version, metrics,
                      source_submission_id, source_record_id, valid_from
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tenant_id if org_id != outside_org_id else outside_tenant_id,
                        org_id,
                        period_id,
                        "management",
                        1,
                        Jsonb({"revenue": revenue}),
                        submission_id,
                        source_record_id,
                        "2026-06-01",
                    ),
                )

            evidence_ids: dict[str, Any] = {}
            for label, tenant_for_row, org_id, period_id, submission_id in (
                ("owner", tenant_id, owner_org_id, owner_period_id, owner_submission_id),
                ("other", tenant_id, other_org_id, other_period_id, other_submission_id),
                ("outside", outside_tenant_id, outside_org_id, outside_period_id, outside_submission_id),
            ):
                evidence_document_id = _one(
                    connection,
                    """
                    INSERT INTO evidence_documents (
                      tenant_id, organization_id, reporting_period_id, document_type, title,
                      classification, source_submission_id, source_record_id, valid_from
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING evidence_document_id
                    """,
                    (
                        tenant_for_row,
                        org_id,
                        period_id,
                        "CERTIFICATE",
                        f"{label} RLS certificate",
                        "confidential",
                        submission_id,
                        f"{label}-evidence-row",
                        "2026-06-01",
                    ),
                )
                evidence_ids[label] = evidence_document_id
                connection.execute(
                    """
                    INSERT INTO evidence_versions (
                      evidence_document_id, tenant_id, organization_id, object_key, object_version,
                      document_hash, content_type, byte_size, malware_scan_status, uploader_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        evidence_document_id,
                        tenant_for_row,
                        org_id,
                        f"s3://rls-smoke/{tenant_for_row}/{label}.pdf",
                        f"{label}-v1",
                        f"sha256:{label}-{suffix}",
                        "application/pdf",
                        1024,
                        "clean",
                        user_id,
                    ),
                )

            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role_name)))
            set_rls_session(connection, _request_context(tenant_key, owner_key))
            owner_only_count = _one(connection, "SELECT count(*) FROM financial_snapshots")
            if owner_only_count != 1:
                raise AssertionError(f"Expected owner-only RLS count 1, got {owner_only_count}.")
            evidence_owner_only_count = _one(connection, "SELECT count(*) FROM evidence_documents")
            if evidence_owner_only_count != 1:
                raise AssertionError(f"Expected owner-only evidence RLS count 1, got {evidence_owner_only_count}.")
            connection.execute("RESET ROLE")

            connection.execute(
                """
                INSERT INTO consent_records (
                  tenant_id, actor_id, subject_organization_id, recipient_organization_id,
                  scope, purpose, legal_basis
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, user_id, other_org_id, owner_org_id, "financial_summary", "management_review", "explicit_consent"),
            )

            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role_name)))
            set_rls_session(connection, _request_context(tenant_key, owner_key))
            consent_count = _one(connection, "SELECT count(*) FROM financial_snapshots")
            if consent_count != 2:
                raise AssertionError(f"Expected consent-expanded RLS count 2, got {consent_count}.")
            outside_visible = _one(
                connection,
                """
                SELECT count(*)
                FROM financial_snapshots fs
                JOIN organizations org ON org.organization_id = fs.organization_id
                WHERE org.external_business_id = %s
                """,
                (outside_org_key,),
            )
            if outside_visible != 0:
                raise AssertionError(f"Cross-tenant financial row leaked through RLS: {outside_visible}.")
            connection.execute("RESET ROLE")

            grant_id = _one(
                connection,
                """
                INSERT INTO evidence_access_grants (
                  tenant_id, evidence_document_id, subject_organization_id, grantee_organization_id,
                  scope, purpose, status, granted_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING grant_id
                """,
                (
                    tenant_id,
                    evidence_ids["other"],
                    other_org_id,
                    owner_org_id,
                    "evidence_review",
                    "management_review",
                    "active",
                    user_id,
                ),
            )

            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role_name)))
            set_rls_session(connection, _request_context(tenant_key, owner_key))
            evidence_grant_count = _one(connection, "SELECT count(*) FROM evidence_documents")
            if evidence_grant_count != 2:
                raise AssertionError(f"Expected evidence grant-expanded RLS count 2, got {evidence_grant_count}.")
            set_rls_session(connection, _request_context(tenant_key, owner_key, purpose="credit_decision"))
            evidence_wrong_purpose_count = _one(connection, "SELECT count(*) FROM evidence_documents")
            if evidence_wrong_purpose_count != 1:
                raise AssertionError(
                    f"Expected wrong-purpose evidence grant denial count 1, got {evidence_wrong_purpose_count}."
                )
            outside_evidence_visible = _one(
                connection,
                """
                SELECT count(*)
                FROM evidence_documents document
                JOIN organizations org ON org.organization_id = document.organization_id
                WHERE org.external_business_id = %s
                """,
                (outside_org_key,),
            )
            if outside_evidence_visible != 0:
                raise AssertionError(f"Cross-tenant evidence row leaked through RLS: {outside_evidence_visible}.")
            connection.execute("RESET ROLE")

            connection.execute(
                "UPDATE evidence_access_grants SET status = 'revoked', revoked_at = now() WHERE grant_id = %s",
                (grant_id,),
            )
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role_name)))
            set_rls_session(connection, _request_context(tenant_key, owner_key))
            evidence_revoked_count = _one(connection, "SELECT count(*) FROM evidence_documents")
            if evidence_revoked_count != 1:
                raise AssertionError(f"Expected revoked evidence grant denial count 1, got {evidence_revoked_count}.")
            connection.execute("RESET ROLE")

    print(
        "PostgreSQL RLS smoke passed: "
        f"applied={applied or 'already-current'}, owner_only=1, consent_visible=2, "
        "evidence_grant_visible=2, evidence_wrong_purpose=1, evidence_revoked=1, cross_tenant=0"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply trust migration and run DB-level RLS smoke assertions.")
    parser.add_argument("--database-url", help="PostgreSQL test database URL. Defaults to POSTGRES_TEST_DATABASE_URL or DATABASE_URL.")
    args = parser.parse_args()
    run(_database_url(args.database_url))


if __name__ == "__main__":
    main()
