from __future__ import annotations

import unittest
import hashlib
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.services.database import Database
from backend.app.services.evidence_workers import EvidenceWorkerService


class _FakeClamAvSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent: list[bytes] = []
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, _: int) -> bytes:
        response = self.response
        self.response = b""
        return response

    def close(self) -> None:
        self.closed = True


class EvidenceWorkerTests(unittest.TestCase):
    def test_scan_worker_dry_run_and_execute_records_access_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker.db")
            self._seed_pending_evidence(database)
            worker = EvidenceWorkerService(database)

            dry_run = worker.scan_pending_versions(dry_run=True)
            executed = worker.scan_pending_versions(
                dry_run=False,
                scanner=lambda row: ("clean", f"test-clean:{row['evidence_version_id']}"),
            )

            with closing(database.connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-001",),
                ).fetchone()
                access_log = connection.execute(
                    """
                    SELECT access_type, access_status, object_key_hash, reason
                    FROM evidence_object_access_logs
                    WHERE evidence_version_id = ?
                    """,
                    ("EVV-001",),
                ).fetchone()

            self.assertEqual(dry_run["candidates"], 1)
            self.assertEqual(dry_run["processed"], 0)
            self.assertEqual(executed["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "clean")
            self.assertEqual(access_log["access_type"], "scan_worker")
            self.assertEqual(access_log["access_status"], "executed")
            self.assertTrue(access_log["object_key_hash"])
            self.assertIn("test-clean", access_log["reason"])

    def test_local_demo_scanner_reads_object_bytes_before_marking_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker.db")
            content = b"clean local demo evidence"
            document_hash = hashlib.sha256(content).hexdigest()
            self._seed_pending_evidence(database, document_hash=document_hash, byte_size=len(content))
            worker = EvidenceWorkerService(database)
            object_path = Path(temp_dir) / "evidence_objects" / "tenant-demo" / "BIZ-009" / f"EVV-001-{document_hash[:16]}.bin"
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(content)

            executed = worker.scan_pending_versions(dry_run=False, scanner=worker.local_demo_scanner)

            with closing(database.connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-001",),
                ).fetchone()
                log = connection.execute(
                    "SELECT reason FROM evidence_object_access_logs WHERE evidence_version_id = ? AND access_type = 'scan_worker'",
                    ("EVV-001",),
                ).fetchone()

            self.assertEqual(executed["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "clean")
            self.assertIn("local_demo_sha256_match", log["reason"])

    def test_scan_worker_filters_pending_versions_by_period(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker-filter.db")
            self._seed_pending_evidence(database)
            self._seed_second_period_pending_evidence(database)
            worker = EvidenceWorkerService(database)

            executed = worker.scan_pending_versions(
                dry_run=False,
                scanner=lambda row: ("clean", f"period-filter:{row['period_key']}"),
                organization_id="BIZ-009",
                period_key="2026-09",
            )

            with closing(database.connect()) as connection:
                versions = {
                    row["evidence_version_id"]: row["malware_scan_status"]
                    for row in connection.execute(
                        "SELECT evidence_version_id, malware_scan_status FROM evidence_versions ORDER BY evidence_version_id"
                    ).fetchall()
                }

            self.assertEqual(executed["candidates"], 1)
            self.assertEqual(executed["processed"], 1)
            self.assertEqual(versions["EVV-001"], "clean")
            self.assertEqual(versions["EVV-002"], "pending_scan")

    def test_local_demo_scanner_marks_demo_threat_marker_infected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker.db")
            content = b"prefix DEMO-MALWARE suffix"
            document_hash = hashlib.sha256(content).hexdigest()
            self._seed_pending_evidence(database, document_hash=document_hash, byte_size=len(content))
            worker = EvidenceWorkerService(database)
            object_path = Path(temp_dir) / "evidence_objects" / "tenant-demo" / "BIZ-009" / f"EVV-001-{document_hash[:16]}.bin"
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(content)

            executed = worker.scan_pending_versions(dry_run=False, scanner=worker.local_demo_scanner)

            with closing(database.connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-001",),
                ).fetchone()
                document = connection.execute(
                    "SELECT malware_scan_status, retention_status FROM evidence_documents WHERE evidence_document_id = ?",
                    ("EVD-001",),
                ).fetchone()

            self.assertEqual(executed["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "infected")
            self.assertEqual(document["malware_scan_status"], "infected")
            self.assertEqual(document["retention_status"], "retention_locked")

    def test_clamav_scanner_marks_clean_when_daemon_returns_ok(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker.db")
            content = b"clean evidence for clamav"
            document_hash = hashlib.sha256(content).hexdigest()
            self._seed_pending_evidence(database, document_hash=document_hash, byte_size=len(content))
            self._write_local_object(Path(temp_dir), "EVV-001", document_hash, content)
            worker = EvidenceWorkerService(database)
            fake_socket = _FakeClamAvSocket(b"stream: OK\0")

            executed = worker.scan_pending_versions(
                dry_run=False,
                scanner=lambda row: worker.clamav_scanner(row, socket_factory=lambda address, timeout: fake_socket),
            )

            with closing(database.connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-001",),
                ).fetchone()
                log = connection.execute(
                    "SELECT reason FROM evidence_object_access_logs WHERE evidence_version_id = ? AND access_type = 'scan_worker'",
                    ("EVV-001",),
                ).fetchone()
            self.assertEqual(executed["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "clean")
            self.assertIn("clamav:stream: OK", log["reason"])
            self.assertEqual(fake_socket.sent[0], b"zINSTREAM\0")
            self.assertEqual(fake_socket.sent[-1], b"\x00\x00\x00\x00")
            self.assertTrue(fake_socket.closed)

    def test_clamav_scanner_marks_infected_when_daemon_returns_found(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker.db")
            content = b"eicar fixture bytes"
            document_hash = hashlib.sha256(content).hexdigest()
            self._seed_pending_evidence(database, document_hash=document_hash, byte_size=len(content))
            self._write_local_object(Path(temp_dir), "EVV-001", document_hash, content)
            worker = EvidenceWorkerService(database)
            fake_socket = _FakeClamAvSocket(b"stream: Eicar-Test-Signature FOUND\0")

            executed = worker.scan_pending_versions(
                dry_run=False,
                scanner=lambda row: worker.clamav_scanner(row, socket_factory=lambda address, timeout: fake_socket),
            )

            with closing(database.connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-001",),
                ).fetchone()
                document = connection.execute(
                    "SELECT retention_status FROM evidence_documents WHERE evidence_document_id = ?",
                    ("EVD-001",),
                ).fetchone()
            self.assertEqual(executed["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "infected")
            self.assertEqual(document["retention_status"], "retention_locked")

    def test_clamav_scanner_fails_closed_when_daemon_is_unavailable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker.db")
            content = b"clean but scanner unavailable"
            document_hash = hashlib.sha256(content).hexdigest()
            self._seed_pending_evidence(database, document_hash=document_hash, byte_size=len(content))
            self._write_local_object(Path(temp_dir), "EVV-001", document_hash, content)
            worker = EvidenceWorkerService(database)

            executed = worker.scan_pending_versions(
                dry_run=False,
                scanner=lambda row: worker.clamav_scanner(row, socket_factory=lambda address, timeout: (_ for _ in ()).throw(OSError("down"))),
            )

            with closing(database.connect()) as connection:
                version = connection.execute(
                    "SELECT malware_scan_status FROM evidence_versions WHERE evidence_version_id = ?",
                    ("EVV-001",),
                ).fetchone()
                log = connection.execute(
                    "SELECT reason FROM evidence_object_access_logs WHERE evidence_version_id = ? AND access_type = 'scan_worker'",
                    ("EVV-001",),
                ).fetchone()
            self.assertEqual(executed["processed"], 1)
            self.assertEqual(version["malware_scan_status"], "failed")
            self.assertIn("clamav_unavailable", log["reason"])

    def test_lifecycle_worker_requires_delete_callback_before_marking_deleted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "worker.db")
            self._seed_pending_evidence(database, retention_status="scheduled_delete")
            worker = EvidenceWorkerService(database)

            skipped = worker.apply_retention_lifecycle(dry_run=False)
            with closing(database.connect()) as connection:
                after_skip = connection.execute(
                    "SELECT retention_status FROM evidence_documents WHERE evidence_document_id = ?",
                    ("EVD-001",),
                ).fetchone()
            deleted = worker.apply_retention_lifecycle(dry_run=False, delete_object=lambda row: True)
            with closing(database.connect()) as connection:
                after_delete = connection.execute(
                    "SELECT retention_status FROM evidence_documents WHERE evidence_document_id = ?",
                    ("EVD-001",),
                ).fetchone()
                lifecycle_logs = connection.execute(
                    """
                    SELECT access_status, reason
                    FROM evidence_object_access_logs
                    WHERE evidence_document_id = ? AND access_type = 'lifecycle_worker'
                    ORDER BY created_at
                    """,
                    ("EVD-001",),
                ).fetchall()

            self.assertEqual(skipped["skipped"], 1)
            self.assertEqual(after_skip["retention_status"], "scheduled_delete")
            self.assertEqual(deleted["processed"], 1)
            self.assertEqual(after_delete["retention_status"], "deleted")
            self.assertEqual([row["access_status"] for row in lifecycle_logs], ["skipped", "executed"])
            self.assertEqual([row["reason"] for row in lifecycle_logs], ["object_delete_not_configured", "object_deleted"])

    def _seed_pending_evidence(
        self,
        database: Database,
        retention_status: str = "active",
        document_hash: str = "sha256:demo",
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
                ("PER-001", "tenant-demo", "BIZ-009", "month", "2026-09", "2026-09-01", "2026-09-30", "open", 1),
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
                    "EVD-001",
                    "tenant-demo",
                    "BIZ-009",
                    "PER-001",
                    "CERTIFICATE",
                    "HACCP",
                    "s3://demo/evidence/haccp.pdf",
                    document_hash,
                    "confidential",
                    "application/pdf",
                    byte_size,
                    "demo-user",
                    "pending_scan",
                    retention_status,
                    0,
                    "SUB-001",
                    "ROW-001",
                    "2026-09-01",
                    "2026-09-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO evidence_versions (
                  evidence_version_id, evidence_document_id, tenant_id, organization_id, object_key,
                  period_key, object_version, document_hash, content_type, byte_size, malware_scan_status,
                  retention_status, legal_hold, uploader_id, supersedes_version_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    "EVV-001",
                    "EVD-001",
                    "tenant-demo",
                    "BIZ-009",
                    "s3://demo/evidence/haccp.pdf",
                    "2026-09",
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

    def _seed_second_period_pending_evidence(self, database: Database) -> None:
        with closing(database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO reporting_periods (
                  reporting_period_id, tenant_id, organization_id, period_type, period_key,
                  period_start, period_end, status, lock_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("PER-002", "tenant-demo", "BIZ-009", "month", "2026-10", "2026-10-01", "2026-10-31", "open", 1),
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
                    "EVD-002",
                    "tenant-demo",
                    "BIZ-009",
                    "PER-002",
                    "GUARANTEE",
                    "Performance guarantee",
                    "s3://demo/evidence/guarantee.pdf",
                    "sha256:demo-2",
                    "confidential",
                    "application/pdf",
                    128,
                    "demo-user",
                    "pending_scan",
                    "active",
                    0,
                    "SUB-002",
                    "ROW-002",
                    "2026-10-01",
                    "2026-10-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO evidence_versions (
                  evidence_version_id, evidence_document_id, tenant_id, organization_id, object_key,
                  period_key, object_version, document_hash, content_type, byte_size, malware_scan_status,
                  retention_status, legal_hold, uploader_id, supersedes_version_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    "EVV-002",
                    "EVD-002",
                    "tenant-demo",
                    "BIZ-009",
                    "s3://demo/evidence/guarantee.pdf",
                    "2026-10",
                    "v1",
                    "sha256:demo-2",
                    "application/pdf",
                    128,
                    "pending_scan",
                    "active",
                    0,
                    "demo-user",
                    "2026-10-01T00:00:00+00:00",
                ),
            )
            connection.commit()

    def _write_local_object(self, temp_dir: Path, evidence_version_id: str, document_hash: str, content: bytes) -> None:
        object_path = temp_dir / "evidence_objects" / "tenant-demo" / "BIZ-009" / f"{evidence_version_id}-{document_hash[:16]}.bin"
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
