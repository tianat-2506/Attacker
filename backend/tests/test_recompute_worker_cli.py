from __future__ import annotations

import json
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.services.database import Database


ROOT = Path(__file__).resolve().parents[2]


class RecomputeWorkerCliTests(unittest.TestCase):
    def test_recompute_cli_dry_run_then_execute_skips_without_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "recompute.db"
            _seed_recompute_job(Database(db_path))

            dry_run = _run_recompute_cli(db_path)
            executed = _run_recompute_cli(db_path, "--execute")

            with closing(Database(db_path).connect()) as connection:
                job = connection.execute(
                    "SELECT status, attempts, last_error FROM analytics_recompute_jobs WHERE job_id = ?",
                    ("JOB-CLI-001",),
                ).fetchone()

            self.assertTrue(dry_run["dry_run"])
            self.assertEqual(dry_run["candidates"], 1)
            self.assertEqual(dry_run["processed"], 0)
            self.assertFalse(executed["dry_run"])
            self.assertEqual(executed["skipped"], 1)
            self.assertEqual(job["status"], "skipped")
            self.assertEqual(job["attempts"], 1)
            self.assertEqual(job["last_error"], "recompute_handler_not_configured")

    def test_recompute_cli_unsafe_mark_succeeded_is_explicit_demo_override(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "recompute-success.db"
            _seed_recompute_job(Database(db_path))

            result = _run_recompute_cli(db_path, "--execute", "--unsafe-mark-succeeded")

            with closing(Database(db_path).connect()) as connection:
                job = connection.execute(
                    "SELECT status, attempts, last_error FROM analytics_recompute_jobs WHERE job_id = ?",
                    ("JOB-CLI-001",),
                ).fetchone()

            self.assertEqual(result["processed"], 1)
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["attempts"], 1)
            self.assertEqual(job["last_error"], "unsafe_demo_mark_succeeded")


def _run_recompute_cli(db_path: Path, *args: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts" / "run_recompute_jobs.py"),
            "--sqlite-path",
            str(db_path),
            *args,
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def _seed_recompute_job(database: Database) -> None:
    database.initialize()
    with closing(database.connect()) as connection:
        now = "2026-01-01T00:00:00+00:00"
        connection.execute(
            "INSERT INTO tenants (tenant_id, name, status) VALUES (?, ?, ?)",
            ("tenant-demo", "Tenant", "active"),
        )
        connection.execute(
            """
            INSERT INTO organizations (organization_id, tenant_id, external_business_id, name, organization_type, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("BIZ-009", "tenant-demo", None, "Owner SME", "sme", "active"),
        )
        connection.execute(
            """
            INSERT INTO reporting_periods (
              reporting_period_id, tenant_id, organization_id, period_type, period_key,
              period_start, period_end, status, lock_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("PER-CLI-001", "tenant-demo", "BIZ-009", "month", "2026-09", "2026-09-01", "2026-09-30", "approved", 1),
        )
        connection.execute(
            """
            INSERT INTO analytics_recompute_jobs (
              job_id, tenant_id, organization_id, reporting_period_id, source_submission_id,
              job_type, status, idempotency_key, payload_json, attempts, max_attempts,
              last_error, created_by, created_at, updated_at, available_at, started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                "JOB-CLI-001",
                "tenant-demo",
                "BIZ-009",
                "PER-CLI-001",
                "SUB-CLI-001",
                "analytics_recompute",
                "queued",
                "analytics:SUB-CLI-001",
                json.dumps({"period_key": "2026-09"}, sort_keys=True),
                0,
                3,
                "demo-user",
                now,
                now,
                now,
            ),
        )
        connection.commit()


if __name__ == "__main__":
    unittest.main()
