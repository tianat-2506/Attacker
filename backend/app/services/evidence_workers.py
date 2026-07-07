from __future__ import annotations

import hashlib
import socket
import struct
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from backend.app.services.access_control import Membership, RequestContext
from backend.app.services.database import Database
from backend.app.services.governance_service import GovernanceService
from backend.app.services.repositories import AccessPolicyRepository, AuditRepository


ScanDecision = Callable[[dict[str, Any]], tuple[str, str]]
DeleteObjectResult = bool | tuple[bool, str]
DeleteObject = Callable[[dict[str, Any]], DeleteObjectResult]
SocketFactory = Callable[[tuple[str, int], float], Any]
DEMO_THREAT_MARKERS = (
    b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE",
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR",
    b"DEMO-MALWARE",
)


def _safe_path_segment(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return safe[:90] or "unknown"


@dataclass(frozen=True)
class WorkerSummary:
    mode: str
    dry_run: bool
    candidates: int
    processed: int
    skipped: int
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dry_run": self.dry_run,
            "candidates": self.candidates,
            "processed": self.processed,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class EvidenceWorkerService:
    """Local worker skeleton for evidence scan and retention jobs.

    The default scanner is deliberately conservative: it never marks files clean.
    A real scanner integration must pass a ScanDecision callback that returns
    clean/infected/failed based on an actual object scan.
    """

    def __init__(self, database: Database, governance: GovernanceService | None = None) -> None:
        self.database = database
        self.governance = governance or GovernanceService(
            database,
            AuditRepository(database),
            AccessPolicyRepository(database),
        )

    def scan_pending_versions(
        self,
        *,
        limit: int = 20,
        dry_run: bool = True,
        scanner: ScanDecision | None = None,
        organization_id: str | None = None,
        period_key: str | None = None,
    ) -> dict[str, Any]:
        rows = self._pending_scan_rows(limit, organization_id=organization_id, period_key=period_key)
        processed = 0
        skipped = 0
        errors: list[str] = []
        if dry_run:
            return WorkerSummary("scan_pending_versions", True, len(rows), 0, len(rows), []).as_dict()

        for row in rows:
            try:
                status, details = scanner(dict(row)) if scanner else ("failed", "scanner_not_configured")
                if status not in {"clean", "infected", "failed"}:
                    raise ValueError(f"unsupported_scan_status:{status}")
                context = self._scanner_context(row["tenant_id"], row["organization_id"])
                self.governance.record_evidence_scan_result(
                    evidence_version_id=row["evidence_version_id"],
                    organization_id=row["organization_id"],
                    malware_scan_status=status,
                    scanner_name="evidence-worker",
                    scanner_version="skeleton-v1",
                    scanned_at=_now(),
                    details=details,
                    context=context,
                )
                self._record_worker_access(
                    tenant_id=row["tenant_id"],
                    evidence_document_id=row["evidence_document_id"],
                    evidence_version_id=row["evidence_version_id"],
                    organization_id=row["organization_id"],
                    actor_id=context.actor_id,
                    access_type="scan_worker",
                    access_status="executed",
                    purpose=context.purpose,
                    request_id=context.request_id,
                    object_key=row["object_key"],
                    reason=status if details is None else f"{status}:{details}",
                )
                processed += 1
            except Exception as exc:  # Worker keeps batch progress and reports row failures.
                errors.append(f"{row['evidence_version_id']}:{exc}")
                skipped += 1
        return WorkerSummary("scan_pending_versions", False, len(rows), processed, skipped, errors).as_dict()

    def apply_retention_lifecycle(
        self,
        *,
        limit: int = 20,
        dry_run: bool = True,
        delete_object: DeleteObject | None = None,
    ) -> dict[str, Any]:
        rows = self._scheduled_delete_rows(limit)
        processed = 0
        skipped = 0
        errors: list[str] = []
        if dry_run:
            return WorkerSummary("apply_retention_lifecycle", True, len(rows), 0, len(rows), []).as_dict()

        for row in rows:
            try:
                context = self._lifecycle_context(row["tenant_id"], row["organization_id"])
                if row["legal_hold"]:
                    self._record_worker_access(
                        tenant_id=row["tenant_id"],
                        evidence_document_id=row["evidence_document_id"],
                        evidence_version_id=None,
                        organization_id=row["organization_id"],
                        actor_id=context.actor_id,
                        access_type="lifecycle_worker",
                        access_status="skipped",
                        purpose=context.purpose,
                        request_id=context.request_id,
                        object_key=row["object_key"],
                        reason="legal_hold_active",
                    )
                    skipped += 1
                    continue
                deleted, delete_reason = self._delete_decision(delete_object, row)
                if not deleted:
                    self._record_worker_access(
                        tenant_id=row["tenant_id"],
                        evidence_document_id=row["evidence_document_id"],
                        evidence_version_id=None,
                        organization_id=row["organization_id"],
                        actor_id=context.actor_id,
                        access_type="lifecycle_worker",
                        access_status="skipped",
                        purpose=context.purpose,
                        request_id=context.request_id,
                        object_key=row["object_key"],
                        reason=delete_reason,
                    )
                    skipped += 1
                    continue
                with closing(self.database.connect()) as connection:
                    connection.execute(
                        """
                        UPDATE evidence_documents
                        SET retention_status = 'deleted', valid_to = ?
                        WHERE evidence_document_id = ? AND retention_status = 'scheduled_delete'
                        """,
                        (_now(), row["evidence_document_id"]),
                    )
                    connection.commit()
                self._record_worker_access(
                    tenant_id=row["tenant_id"],
                    evidence_document_id=row["evidence_document_id"],
                    evidence_version_id=None,
                    organization_id=row["organization_id"],
                    actor_id=context.actor_id,
                    access_type="lifecycle_worker",
                    access_status="executed",
                    purpose=context.purpose,
                    request_id=context.request_id,
                    object_key=row["object_key"],
                    reason=delete_reason,
                )
                processed += 1
            except Exception as exc:
                errors.append(f"{row['evidence_document_id']}:{exc}")
                skipped += 1
        return WorkerSummary("apply_retention_lifecycle", False, len(rows), processed, skipped, errors).as_dict()

    def _delete_decision(self, delete_object: DeleteObject | None, row: dict[str, Any]) -> tuple[bool, str]:
        if delete_object is None:
            return False, "object_delete_not_configured"
        result = delete_object(dict(row))
        if isinstance(result, tuple):
            deleted, reason = result
            return bool(deleted), reason or ("object_deleted" if deleted else "object_delete_failed")
        return bool(result), "object_deleted" if result else "object_delete_failed"

    def local_demo_scanner(self, row: dict[str, Any]) -> tuple[str, str]:
        """Deterministic local-demo scanner; not a production antivirus integration."""

        content, failure = self._read_verified_local_demo_object(row)
        if failure:
            return "failed", failure
        if any(marker in content for marker in DEMO_THREAT_MARKERS):
            return "infected", "local_demo_threat_marker_detected"
        return "clean", "local_demo_sha256_match_no_demo_marker"

    def clamav_scanner(
        self,
        row: dict[str, Any],
        *,
        host: str = "127.0.0.1",
        port: int = 3310,
        timeout: float = 10.0,
        socket_factory: SocketFactory | None = None,
    ) -> tuple[str, str]:
        """Scan the locally persisted evidence object through ClamAV INSTREAM."""

        content, failure = self._read_verified_local_demo_object(row)
        if failure:
            return "failed", f"clamav_input_{failure}"
        try:
            factory = socket_factory or socket.create_connection
            client = factory((host, port), timeout)
            try:
                client.sendall(b"zINSTREAM\0")
                chunk_size = 1024 * 1024
                for index in range(0, len(content), chunk_size):
                    chunk = content[index : index + chunk_size]
                    client.sendall(struct.pack(">I", len(chunk)))
                    client.sendall(chunk)
                client.sendall(struct.pack(">I", 0))
                response_parts: list[bytes] = []
                while True:
                    part = client.recv(4096)
                    if not part:
                        break
                    response_parts.append(part)
                    if b"\0" in part or b"\n" in part:
                        break
            finally:
                client.close()
        except OSError as exc:
            return "failed", f"clamav_unavailable:{exc.__class__.__name__}"
        response = b"".join(response_parts).decode("utf-8", errors="replace").strip("\0\r\n ")
        if " FOUND" in response:
            return "infected", f"clamav:{response}"
        if response.endswith("OK") or " OK" in response:
            return "clean", f"clamav:{response}"
        return "failed", f"clamav_unrecognized_response:{response[:120]}"

    def _read_verified_local_demo_object(self, row: dict[str, Any]) -> tuple[bytes, str | None]:
        object_path = self._local_demo_object_path(row)
        if not object_path.exists():
            return b"", "local_demo_object_missing"
        content = object_path.read_bytes()
        expected_size = int(row.get("byte_size") or 0)
        if len(content) != expected_size:
            return b"", f"local_demo_byte_size_mismatch:{len(content)}:{expected_size}"
        computed_hash = hashlib.sha256(content).hexdigest()
        if computed_hash != str(row.get("document_hash") or "").lower():
            return b"", "local_demo_hash_mismatch"
        return content, None

    def _local_demo_object_path(self, row: dict[str, Any]) -> Path:
        root = (self.database.path.parent / "evidence_objects").resolve()
        path = (
            root
            / _safe_path_segment(str(row.get("tenant_id") or "tenant"))
            / _safe_path_segment(str(row.get("organization_id") or "organization"))
            / f"{_safe_path_segment(str(row['evidence_version_id']))}-{str(row.get('document_hash') or '')[:16]}.bin"
        ).resolve()
        path.relative_to(root)
        return path

    def _pending_scan_rows(
        self,
        limit: int,
        *,
        organization_id: str | None = None,
        period_key: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["version.malware_scan_status = 'pending_scan'", "version.evidence_document_id IS NOT NULL"]
        params: list[Any] = []
        if organization_id:
            clauses.append("version.organization_id = ?")
            params.append(organization_id)
        if period_key:
            clauses.append("version.period_key = ?")
            params.append(period_key)
        params.append(max(1, min(limit, 500)))
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT version.*
                FROM evidence_versions version
                WHERE {" AND ".join(clauses)}
                ORDER BY version.created_at ASC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def _scheduled_delete_rows(self, limit: int) -> list[dict[str, Any]]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM evidence_documents
                WHERE retention_status = 'scheduled_delete'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def _record_worker_access(
        self,
        *,
        tenant_id: str,
        evidence_document_id: str | None,
        evidence_version_id: str | None,
        organization_id: str | None,
        actor_id: str,
        access_type: str,
        access_status: str,
        purpose: str,
        request_id: str,
        object_key: str | None,
        reason: str,
    ) -> str:
        access_id = f"EAL-{uuid4().hex[:12].upper()}"
        object_key_hash = hashlib.sha256(object_key.encode("utf-8")).hexdigest() if object_key else None
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO evidence_object_access_logs (
                  access_id, tenant_id, evidence_document_id, evidence_version_id, organization_id,
                  actor_id, access_type, access_status, purpose, request_id, policy_decision_id,
                  object_storage_status, object_key_hash, reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    access_id,
                    tenant_id,
                    evidence_document_id,
                    evidence_version_id,
                    organization_id,
                    actor_id,
                    access_type,
                    access_status,
                    purpose,
                    request_id,
                    "worker",
                    object_key_hash,
                    reason,
                    _now(),
                ),
            )
            connection.commit()
        return access_id

    def _scanner_context(self, tenant_id: str, organization_id: str) -> RequestContext:
        return RequestContext(
            tenant_id=tenant_id,
            organization_id=organization_id,
            actor_id="evidence-worker",
            actor_role="evidence_scanner",
            purpose="malware_scan",
            scopes=frozenset({"evidence:scan"}),
            roles=frozenset({"evidence_scanner"}),
            memberships=(Membership(organization_id, "evidence_scanner"),),
            request_id=f"evidence-scan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            auth_assurance="worker",
            app_mode="demo",
        )

    def _lifecycle_context(self, tenant_id: str, organization_id: str) -> RequestContext:
        return RequestContext(
            tenant_id=tenant_id,
            organization_id=organization_id,
            actor_id="evidence-lifecycle-worker",
            actor_role="system_admin",
            purpose="retention_lifecycle",
            scopes=frozenset({"evidence:lifecycle"}),
            roles=frozenset({"system_admin"}),
            memberships=(Membership(organization_id, "system_admin"),),
            request_id=f"evidence-lifecycle-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            auth_assurance="worker",
            app_mode="demo",
        )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
