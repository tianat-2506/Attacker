from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.services.access_control import Membership, RequestContext
from backend.app.services.postgres_migrations import (
    PostgresMigrationError,
    PostgresMigrationRunner,
    executable_migration_sql,
    migration_files,
    normalize_postgres_url,
    rls_session_settings,
)


class PostgresMigrationRunnerTests(unittest.TestCase):
    def test_migration_plan_loads_trust_foundation_revision(self) -> None:
        plan = PostgresMigrationRunner("postgresql://user:pass@localhost:5432/vietsupply").plan()
        self.assertGreaterEqual(len(plan), 1)
        self.assertEqual(plan[0].revision, "0001")
        self.assertTrue(plan[0].path.name.endswith("_trust_foundation_postgres.sql"))

    def test_postgresql_psycopg_url_is_normalized(self) -> None:
        self.assertEqual(
            normalize_postgres_url("postgresql+psycopg://user:pass@localhost/db"),
            "postgresql://user:pass@localhost/db",
        )
        with self.assertRaises(PostgresMigrationError):
            normalize_postgres_url("sqlite:///demo.db")

    def test_executable_migration_sql_strips_embedded_transaction_control(self) -> None:
        self.assertEqual(
            executable_migration_sql("BEGIN;\nSELECT 1;\nCOMMIT;\n"),
            "SELECT 1;\n",
        )

    def test_rls_session_settings_are_derived_from_request_context(self) -> None:
        context = RequestContext(
            tenant_id="tenant-1",
            organization_id="org-a",
            actor_id="user-1",
            actor_role="lender",
            purpose="management_review",
            scopes=frozenset({"invoice:read", "finance:read"}),
            roles=frozenset({"lender"}),
            memberships=(Membership("org-b", "lender"), Membership("org-a", "lender")),
            request_id="req-test",
            auth_assurance="jwt-dev-hs256",
            app_mode="pilot",
        )
        settings = rls_session_settings(context)

        self.assertEqual(settings["app.tenant_id"], "tenant-1")
        self.assertEqual(settings["app.actor_id"], "user-1")
        self.assertEqual(settings["app.organization_ids"], "org-a,org-b")
        self.assertEqual(settings["app.purpose"], "management_review")
        self.assertEqual(settings["app.scopes"], "finance:read invoice:read")

    def test_duplicate_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            (path / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
            (path / "0001_b.sql").write_text("SELECT 2;", encoding="utf-8")
            with self.assertRaises(PostgresMigrationError):
                migration_files(path)


if __name__ == "__main__":
    unittest.main()
