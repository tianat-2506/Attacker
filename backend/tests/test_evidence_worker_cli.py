from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.request import Request

from backend.app.services.database import Database
from backend.app.services.evidence_workers import EvidenceWorkerService
from backend.app.services.postgres_pilot_service import ObjectStorageSettings
from scripts import run_evidence_workers as worker_cli


ROOT = Path(__file__).resolve().parents[2]


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class EvidenceWorkerCliTests(unittest.TestCase):
    def test_scan_cli_dry_run_then_execute_fails_closed_without_scanner(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "worker-cli.db"
            _seed_pending_evidence(Database(db_path))

            dry_run = _run_worker_cli(db_path, "--mode", "scan")
            executed = _run_worker_cli(db_path, "--mode", "scan", "--execute")

            with closing(Database(db_path).connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-CLI-001",),
                ).fetchone()
                log = connection.execute(
                    """
                    SELECT access_type, access_status, reason, object_key_hash
                    FROM evidence_object_access_logs
                    WHERE evidence_version_id = ?
                    """,
                    ("EVV-CLI-001",),
                ).fetchone()

            self.assertTrue(dry_run["dry_run"])
            self.assertEqual(dry_run["candidates"], 1)
            self.assertEqual(dry_run["processed"], 0)
            self.assertFalse(executed["dry_run"])
            self.assertEqual(executed["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "failed")
            self.assertEqual(log["access_type"], "scan_worker")
            self.assertEqual(log["access_status"], "executed")
            self.assertIn("scanner_not_configured", log["reason"])
            self.assertTrue(log["object_key_hash"])

    def test_scan_cli_unsafe_mark_clean_is_explicit_demo_override(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "worker-cli-clean.db"
            _seed_pending_evidence(Database(db_path))

            result = _run_worker_cli(db_path, "--mode", "scan", "--execute", "--unsafe-mark-clean")

            with closing(Database(db_path).connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-CLI-001",),
                ).fetchone()

            self.assertEqual(result["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "clean")

    def test_scan_cli_local_demo_scanner_reads_persisted_object(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "worker-cli-local.db"
            content = b"clean cli local demo evidence"
            document_hash = hashlib.sha256(content).hexdigest()
            _seed_pending_evidence(Database(db_path), document_hash=document_hash, byte_size=len(content))
            object_path = Path(temp_dir) / "evidence_objects" / "tenant-demo" / "BIZ-009" / f"EVV-CLI-001-{document_hash[:16]}.bin"
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(content)

            result = _run_worker_cli(db_path, "--mode", "scan", "--execute", "--local-demo-scanner")

            with closing(Database(db_path).connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-CLI-001",),
                ).fetchone()

            self.assertEqual(result["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "clean")

    def test_lifecycle_cli_execute_does_not_delete_without_object_backend(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "worker-cli-lifecycle.db"
            _seed_pending_evidence(Database(db_path), retention_status="scheduled_delete")

            result = _run_worker_cli(db_path, "--mode", "lifecycle", "--execute")

            with closing(Database(db_path).connect()) as connection:
                document = connection.execute(
                    "SELECT retention_status FROM evidence_documents WHERE evidence_document_id = ?",
                    ("EVD-CLI-001",),
                ).fetchone()
                log = connection.execute(
                    """
                    SELECT access_type, access_status, reason
                    FROM evidence_object_access_logs
                    WHERE evidence_document_id = ? AND access_type = 'lifecycle_worker'
                    """,
                    ("EVD-CLI-001",),
                ).fetchone()

            self.assertEqual(result["skipped"], 1)
            self.assertEqual(document["retention_status"], "scheduled_delete")
            self.assertEqual(log["access_status"], "skipped")
            self.assertEqual(log["reason"], "object_delete_not_configured")

    def test_lifecycle_s3_minio_delete_marks_metadata_deleted_after_http_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker-cli-s3-delete.db")
            _seed_pending_evidence(database, retention_status="scheduled_delete")
            worker = EvidenceWorkerService(database)
            settings = ObjectStorageSettings(
                endpoint_url="https://minio.example",
                bucket="demo",
                access_key_id="access-key",
                secret_access_key="secret-key",
                region="ap-southeast-1",
            )
            calls: list[Request] = []

            def fake_urlopen(request: Request, timeout: float = 0) -> _FakeResponse:
                calls.append(request)
                return _FakeResponse(204)

            with patch.object(worker_cli, "urlopen", side_effect=fake_urlopen):
                delete_object = worker_cli._build_s3_minio_delete_object(settings=settings, timeout_seconds=0.1)
                result = worker.apply_retention_lifecycle(dry_run=False, delete_object=delete_object)

            with closing(database.connect()) as connection:
                document = connection.execute(
                    "SELECT retention_status FROM evidence_documents WHERE evidence_document_id = ?",
                    ("EVD-CLI-001",),
                ).fetchone()
                log = connection.execute(
                    """
                    SELECT access_status, reason
                    FROM evidence_object_access_logs
                    WHERE evidence_document_id = ? AND access_type = 'lifecycle_worker'
                    """,
                    ("EVD-CLI-001",),
                ).fetchone()

            self.assertEqual(result["processed"], 1)
            self.assertEqual(document["retention_status"], "deleted")
            self.assertEqual(log["access_status"], "executed")
            self.assertEqual(log["reason"], "s3_minio_object_deleted")
            self.assertEqual([request.get_method() for request in calls], ["DELETE"])
            self.assertNotIn("secret-key", calls[0].full_url)

    def test_lifecycle_s3_minio_delete_keeps_metadata_when_storage_delete_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker-cli-s3-delete-fail.db")
            _seed_pending_evidence(database, retention_status="scheduled_delete")
            worker = EvidenceWorkerService(database)
            settings = ObjectStorageSettings(
                endpoint_url="https://minio.example",
                bucket="demo",
                access_key_id="access-key",
                secret_access_key="secret-key",
            )

            def fake_urlopen(request: Request, timeout: float = 0) -> _FakeResponse:
                return _FakeResponse(403)

            with patch.object(worker_cli, "urlopen", side_effect=fake_urlopen):
                delete_object = worker_cli._build_s3_minio_delete_object(settings=settings, timeout_seconds=0.1)
                result = worker.apply_retention_lifecycle(dry_run=False, delete_object=delete_object)

            with closing(database.connect()) as connection:
                document = connection.execute(
                    "SELECT retention_status FROM evidence_documents WHERE evidence_document_id = ?",
                    ("EVD-CLI-001",),
                ).fetchone()
                log = connection.execute(
                    """
                    SELECT access_status, reason
                    FROM evidence_object_access_logs
                    WHERE evidence_document_id = ? AND access_type = 'lifecycle_worker'
                    """,
                    ("EVD-CLI-001",),
                ).fetchone()

            self.assertEqual(result["skipped"], 1)
            self.assertEqual(document["retention_status"], "scheduled_delete")
            self.assertEqual(log["access_status"], "skipped")
            self.assertEqual(log["reason"], "s3_minio_delete_http_403")


def _run_worker_cli(db_path: Path, *args: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts" / "run_evidence_workers.py"),
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


def _seed_pending_evidence(
    database: Database,
    retention_status: str = "active",
    document_hash: str = "sha256:demo-cli",
    byte_size: int = 128,
) -> None:
    database.initialize()
    with closing(database.connect()) as connection:
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
            ("PER-CLI-001", "tenant-demo", "BIZ-009", "month", "2026-09", "2026-09-01", "2026-09-30", "open", 1),
        )
        connection.execute(
            """
            INSERT INTO evidence_documents (
              evidence_document_id, tenant_id, organization_id, reporting_period_id,
              document_type, title, object_key, document_hash, classification, content_type,
              byte_size, uploader_id, malware_scan_status, retention_status, legal_hold,
              source_submission_id, source_record_id, valid_from, valid_to, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                "EVD-CLI-001",
                "tenant-demo",
                "BIZ-009",
                "PER-CLI-001",
                "CERTIFICATE",
                "HACCP",
                "s3://demo/evidence/haccp-cli.pdf",
                document_hash,
                "confidential",
                "application/pdf",
                byte_size,
                "demo-user",
                "pending_scan",
                retention_status,
                0,
                "SUB-CLI-001",
                "ROW-CLI-001",
                "2026-09-01",
                "2026-09-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO evidence_versions (
              evidence_version_id, evidence_document_id, tenant_id, organization_id, object_key,
              object_version, document_hash, content_type, byte_size, malware_scan_status,
              retention_status, legal_hold, uploader_id, supersedes_version_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                "EVV-CLI-001",
                "EVD-CLI-001",
                "tenant-demo",
                "BIZ-009",
                "s3://demo/evidence/haccp-cli.pdf",
                "v1",
                document_hash,
                "application/pdf",
                byte_size,
                "pending_scan",
                "active",
                0,
                "demo-user",
                "2026-09-01T00:00:00+00:00",
            ),
        )
        connection.commit()


if __name__ == "__main__":
    unittest.main()
