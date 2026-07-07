from __future__ import annotations

import base64
import binascii
import calendar
import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.services.access_control import AccessDeniedError, PolicyDecision, PolicyService, RequestContext
from backend.app.services.database import Database
from backend.app.services.intake_service import IntakeNotFoundError
from backend.app.services.repositories import AccessPolicyRepository, AuditRepository


TRUST_NOTICE = (
    "Operational decision-support only. This platform does not approve financing, assign a credit score, "
    "confirm fraud, or make legal breach findings without independent review."
)

INVOICE_STATES = {"registered", "verified", "pledged", "financed", "released", "disputed"}
INVOICE_TRANSITIONS = {
    "registered": {"verified", "disputed"},
    "verified": {"pledged", "released", "disputed"},
    "pledged": {"financed", "released", "disputed"},
    "financed": {"released", "disputed"},
    "released": set(),
    "disputed": {"released"},
}
RESTRICTED_FINANCIAL_EVIDENCE_TYPES = {"GUARANTEE", "INVOICE"}


class EvidenceUploadValidationError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _safe_path_segment(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return safe[:90] or "unknown"


def invoice_identity_hash(seller_id: str, buyer_id: str, invoice_hash: str, amount: int, due_date: str) -> str:
    raw = f"{seller_id}|{buyer_id}|{invoice_hash}|{amount}|{due_date}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_evidence_upload_classification(document_type: str, classification: str) -> None:
    if document_type.upper() in RESTRICTED_FINANCIAL_EVIDENCE_TYPES and classification != "restricted_financial":
        raise ValueError(f"{document_type} uploads must use restricted_financial classification.")


class GovernanceService:
    def __init__(self, database: Database, audit: AuditRepository, access_policy: AccessPolicyRepository) -> None:
        self.database = database
        self.audit = audit
        self.access_policy = access_policy

    def _require_access(
        self,
        action: str,
        context: RequestContext,
        *,
        resource_type: str,
        resource_id: str | None,
        resource_organization_id: str | None,
        data_classification: str,
        consent_scope: str | None = None,
    ) -> Any:
        external_allowed = False
        if (
            resource_organization_id
            and resource_organization_id not in context.organization_ids
            and not context.is_demo_actor()
            and consent_scope
        ):
            external_allowed = self.access_policy.has_active_consent(
                tenant_id=context.tenant_id,
                subject_id=resource_organization_id,
                recipient_ids=context.organization_ids,
                scope=consent_scope,
                purpose=context.purpose,
            )
        return PolicyService.require(
            action,
            context,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_organization_id=resource_organization_id,
            data_classification=data_classification,
            external_access_allowed=external_allowed,
        )

    def _require_and_audit(
        self,
        action: str,
        context: RequestContext,
        *,
        resource_type: str,
        resource_id: str | None,
        resource_organization_id: str | None,
        data_classification: str,
        denied_event_type: str,
    ) -> PolicyDecision:
        decision = PolicyService.decide(
            action,
            context,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_organization_id=resource_organization_id,
            data_classification=data_classification,
        )
        self.audit.record_policy_decision(context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                denied_event_type,
                context,
                resource_id or resource_organization_id or resource_type,
                policy_decision=decision,
                payload={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "resource_organization_id": resource_organization_id,
                    "reason": decision.reason,
                },
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        return decision

    def auth_me(self, context: RequestContext) -> dict[str, Any]:
        capabilities = PolicyService.capability_matrix(context)
        return {
            "tenant_id": context.tenant_id,
            "actor_id": context.actor_id,
            "token_subject": context.token_subject,
            "organization_id": context.organization_id,
            "organization_ids": sorted(context.organization_ids),
            "roles": sorted(context.roles),
            "scopes": sorted(context.scopes),
            "purpose": context.purpose,
            "request_id": context.request_id,
            "auth_assurance": context.auth_assurance,
            "app_mode": context.app_mode,
            "capabilities": capabilities,
            "workspace_access": PolicyService.workspace_access(context, capabilities=capabilities),
            "advisory_notice": TRUST_NOTICE,
        }

    def create_consent(
        self,
        *,
        subject_id: str,
        recipient_id: str,
        scope: str,
        purpose: str,
        legal_basis: str,
        expires_at: str | None,
        evidence_reference: str | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        decision = PolicyService.require(
            "create_consent",
            context,
            resource_type="consent",
            resource_id=subject_id,
            resource_organization_id=subject_id,
            data_classification="restricted_financial" if "financial" in scope else "confidential",
        )
        self.audit.record_policy_decision(context, decision)
        now = _now()
        consent_id = _id("CONS")
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO consent_records (
                  consent_id, tenant_id, actor_id, subject_id, recipient_id, scope, purpose,
                  legal_basis, status, expires_at, revoked_at, evidence_reference, version, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'granted', ?, NULL, ?, 1, ?, ?)
                """,
                (
                    consent_id,
                    context.tenant_id,
                    context.actor_id,
                    subject_id,
                    recipient_id,
                    scope,
                    purpose,
                    legal_basis,
                    expires_at,
                    evidence_reference,
                    now,
                    now,
                ),
            )
            connection.commit()
        event_id = self.audit.record_context(
            "CONSENT_GRANTED",
            context,
            consent_id,
            policy_decision=decision,
            payload={"subject_id": subject_id, "recipient_id": recipient_id, "scope": scope, "purpose": purpose},
        )
        return {
            "consent_id": consent_id,
            "subject_id": subject_id,
            "recipient_id": recipient_id,
            "scope": scope,
            "purpose": purpose,
            "legal_basis": legal_basis,
            "status": "granted",
            "expires_at": expires_at,
            "revoked_at": None,
            "version": 1,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": TRUST_NOTICE,
        }

    def revoke_consent(self, consent_id: str, context: RequestContext) -> dict[str, Any]:
        now = _now()
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT * FROM consent_records WHERE consent_id = ?", (consent_id,)).fetchone()
            if row is None:
                raise IntakeNotFoundError(consent_id)
            subject_id = row["subject_id"]
            decision = PolicyService.require(
                "revoke_consent",
                context,
                resource_type="consent",
                resource_id=consent_id,
                resource_organization_id=subject_id,
                data_classification="confidential",
            )
            self.audit.record_policy_decision(context, decision)
            connection.execute(
                """
                UPDATE consent_records
                SET status = 'revoked', revoked_at = ?, version = version + 1, updated_at = ?
                WHERE consent_id = ?
                """,
                (now, now, consent_id),
            )
            connection.commit()
            updated = dict(connection.execute("SELECT * FROM consent_records WHERE consent_id = ?", (consent_id,)).fetchone())
        event_id = self.audit.record_context("CONSENT_REVOKED", context, consent_id, policy_decision=decision)
        return {
            "consent_id": consent_id,
            "subject_id": updated["subject_id"],
            "recipient_id": updated["recipient_id"],
            "scope": updated["scope"],
            "purpose": updated["purpose"],
            "legal_basis": updated["legal_basis"],
            "status": updated["status"],
            "expires_at": updated["expires_at"],
            "revoked_at": updated["revoked_at"],
            "version": updated["version"],
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": TRUST_NOTICE,
        }

    def create_evidence_upload_url(
        self,
        *,
        organization_id: str,
        file_name: str,
        content_type: str,
        byte_size: int,
        classification: str,
        purpose: str,
        context: RequestContext,
        document_type: str = "CERTIFICATION",
        period_key: str | None = None,
    ) -> dict[str, Any]:
        require_evidence_upload_classification(document_type, classification)
        decision = PolicyService.require(
            "create_evidence_upload",
            context,
            resource_type="evidence",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification=classification,
        )
        self.audit.record_policy_decision(context, decision)
        object_key = f"s3://vietsupply-evidence/{context.tenant_id}/{organization_id}/{uuid4().hex}-{file_name}"
        version_id = _id("EVV")
        now = _now()
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO evidence_versions (
                  evidence_version_id, evidence_document_id, tenant_id, organization_id, object_key,
                  period_key, document_type, file_name, classification,
                  object_version, document_hash, content_type, byte_size, malware_scan_status,
                  retention_status, legal_hold, uploader_id, supersedes_version_id, created_at
                )
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 'pending-upload', '', ?, ?, 'pending_upload',
                  'active', 0, ?, NULL, ?)
                """,
                (
                    version_id,
                    context.tenant_id,
                    organization_id,
                    object_key,
                    period_key,
                    document_type,
                    file_name,
                    classification,
                    content_type,
                    byte_size,
                    context.actor_id,
                    now,
                ),
            )
            connection.commit()
        event_id = self.audit.record_context(
            "EVIDENCE_UPLOAD_URL_CREATED",
            context,
            version_id,
            policy_decision=decision,
            payload={
                "organization_id": organization_id,
                "classification": classification,
                "document_type": document_type,
                "period_key": period_key,
                "purpose": purpose,
            },
        )
        return {
            "evidence_version_id": version_id,
            "organization_id": organization_id,
            "period_key": period_key,
            "document_type": document_type,
            "file_name": file_name,
            "content_type": content_type,
            "byte_size": byte_size,
            "classification": classification,
            "upload_url": f"demo-upload-ticket://{version_id}",
            "expires_in_seconds": 900,
            "malware_scan_status": "pending_upload",
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Evidence is not usable until checksum is recorded and malware scan is clean.",
        }

    def list_evidence_upload_tickets(
        self,
        *,
        organization_id: str,
        period_key: str | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        decision = self._require_and_audit(
            "read_evidence",
            context,
            resource_type="evidence_upload_ticket",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
            denied_event_type="EVIDENCE_UPLOAD_TICKETS_VIEW_DENIED",
        )
        params: list[Any] = [context.tenant_id, organization_id]
        period_clause = ""
        if period_key:
            period_clause = " AND period_key = ?"
            params.append(period_key)
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM evidence_versions
                WHERE tenant_id = ?
                  AND organization_id = ?
                  AND object_version = 'pending-upload'
                  AND malware_scan_status IN ('pending_upload', 'pending_scan', 'failed')
                  {period_clause}
                ORDER BY created_at DESC
                LIMIT 100
                """,
                tuple(params),
            ).fetchall()
        tickets = [self._pending_evidence_ticket_payload(dict(row), decision.decision_id) for row in rows]
        event_id = self.audit.record_context(
            "EVIDENCE_UPLOAD_TICKETS_VIEWED",
            context,
            organization_id,
            policy_decision=decision,
            payload={"period_key": period_key, "count": len(tickets)},
        )
        return {
            "organization_id": organization_id,
            "period_key": period_key,
            "tickets": [{**ticket, "audit_event_id": event_id} for ticket in tickets],
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Pending upload tickets are not verified evidence and cannot support approved snapshots until scan/checksum gates pass.",
        }

    def complete_evidence_upload_ticket(
        self,
        *,
        evidence_version_id: str,
        organization_id: str,
        document_hash: str,
        malware_scan_status: str,
        title: str | None,
        context: RequestContext,
        content_base64: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM evidence_versions
                WHERE evidence_version_id = ? AND organization_id = ?
                """,
                (evidence_version_id, organization_id),
            ).fetchone()
        ticket = dict(row) if row is not None else None
        decision = self._require_and_audit(
            "create_evidence_version",
            context,
            resource_type="evidence_upload_ticket",
            resource_id=evidence_version_id,
            resource_organization_id=organization_id,
            data_classification=(ticket.get("classification") if ticket else None) or "confidential",
            denied_event_type="EVIDENCE_UPLOAD_COMPLETE_DENIED",
        )
        if ticket is None:
            self.audit.record_context(
                "EVIDENCE_UPLOAD_TICKET_NOT_FOUND",
                context,
                evidence_version_id,
                policy_decision=decision,
                payload={"organization_id": organization_id, "reason": "not_found_or_not_authorized"},
            )
            raise IntakeNotFoundError(evidence_version_id)
        if ticket.get("evidence_document_id"):
            raise ValueError("Evidence upload ticket is already linked to a document.")
        normalized_hash, object_storage_status = self._verify_and_store_demo_upload_content(
            ticket=ticket,
            expected_document_hash=document_hash,
            content_base64=content_base64,
            decision=decision,
            context=context,
        )
        period_key = ticket.get("period_key") or now[:7]
        document_id = _id("EVD")
        document_title = title or ticket.get("file_name") or f"Evidence upload {evidence_version_id}"
        document_type = ticket.get("document_type") or "SUPPORTING_DOCUMENT"
        classification = ticket.get("classification") or "confidential"
        final_malware_scan_status = "pending_scan"
        with closing(self.database.connect()) as connection:
            period_id, period_start, period_end = self._ensure_upload_period(connection, context.tenant_id, organization_id, period_key)
            connection.execute(
                """
                INSERT INTO evidence_documents (
                  evidence_document_id, tenant_id, organization_id, reporting_period_id,
                  document_type, title, object_key, object_version, document_hash,
                  classification, content_type, byte_size, uploader_id, malware_scan_status,
                  retention_status, legal_hold, supersedes_document_id, source_submission_id,
                  source_record_id, valid_from, valid_to, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded-demo', ?, ?, ?, ?, ?, ?,
                  'active', 0, NULL, ?, ?, ?, NULL, ?)
                """,
                (
                    document_id,
                    context.tenant_id,
                    organization_id,
                    period_id,
                    document_type,
                    document_title,
                    ticket["object_key"],
                    normalized_hash,
                    classification,
                    ticket["content_type"],
                    ticket["byte_size"],
                    context.actor_id,
                    final_malware_scan_status,
                    f"UPLOAD-{evidence_version_id}",
                    evidence_version_id,
                    period_start,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE evidence_versions
                SET evidence_document_id = ?,
                    object_version = 'uploaded-demo',
                    document_hash = ?,
                    malware_scan_status = ?
                WHERE evidence_version_id = ? AND organization_id = ?
                """,
                (document_id, normalized_hash, final_malware_scan_status, evidence_version_id, organization_id),
            )
            connection.commit()
            updated = dict(
                connection.execute(
                    "SELECT * FROM evidence_versions WHERE evidence_version_id = ?",
                    (evidence_version_id,),
                ).fetchone()
            )
        event_id = self.audit.record_context(
            "EVIDENCE_UPLOAD_COMPLETED",
            context,
            evidence_version_id,
            policy_decision=decision,
            payload={
                "organization_id": organization_id,
                "evidence_document_id": document_id,
                "period_key": period_key,
                "malware_scan_status": final_malware_scan_status,
                "object_storage_status": object_storage_status,
                "client_requested_scan_status": malware_scan_status,
            },
        )
        return {
            "evidence_version_id": evidence_version_id,
            "evidence_document_id": document_id,
            "organization_id": organization_id,
            "period_key": period_key,
            "document_type": document_type,
            "title": document_title,
            "object_version": updated["object_version"],
            "document_hash": normalized_hash,
            "malware_scan_status": final_malware_scan_status,
            "object_storage_status": object_storage_status,
            "usable": False,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Evidence object/checksum is recorded. It is not usable for approval until an authorized scanner marks it clean.",
        }

    def _verify_and_store_demo_upload_content(
        self,
        *,
        ticket: dict[str, Any],
        expected_document_hash: str,
        content_base64: str | None,
        decision: PolicyDecision,
        context: RequestContext,
    ) -> tuple[str, str]:
        normalized_hash = expected_document_hash.strip().lower()
        if content_base64 is None:
            return normalized_hash, "metadata_only"

        try:
            encoded = content_base64.split(",", maxsplit=1)[1] if content_base64.startswith("data:") else content_base64
            content = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error) as exc:
            self._record_evidence_upload_rejected(
                ticket=ticket,
                context=context,
                decision=decision,
                reason="invalid_base64_content",
            )
            raise EvidenceUploadValidationError("Uploaded content must be valid base64.") from exc

        expected_size = int(ticket.get("byte_size") or 0)
        if len(content) != expected_size:
            self._record_evidence_upload_rejected(
                ticket=ticket,
                context=context,
                decision=decision,
                reason="byte_size_mismatch",
                details={"expected_byte_size": expected_size, "actual_byte_size": len(content)},
            )
            raise EvidenceUploadValidationError("Uploaded content size does not match the upload ticket.")

        computed_hash = hashlib.sha256(content).hexdigest()
        if computed_hash != normalized_hash:
            self._record_evidence_upload_rejected(
                ticket=ticket,
                context=context,
                decision=decision,
                reason="document_hash_mismatch",
                details={"expected_hash": normalized_hash, "computed_hash": computed_hash},
            )
            raise EvidenceUploadValidationError("Uploaded content hash does not match document_hash.")

        self._persist_demo_evidence_object(ticket, computed_hash, content)
        return computed_hash, "local_demo"

    def _persist_demo_evidence_object(self, ticket: dict[str, Any], document_hash: str, content: bytes) -> None:
        root = (self.database.path.parent / "evidence_objects").resolve()
        target_dir = (
            root
            / _safe_path_segment(str(ticket.get("tenant_id") or "tenant"))
            / _safe_path_segment(str(ticket.get("organization_id") or "organization"))
        ).resolve()
        target_dir.relative_to(root)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = (target_dir / f"{_safe_path_segment(str(ticket['evidence_version_id']))}-{document_hash[:16]}.bin").resolve()
        target.relative_to(root)
        target.write_bytes(content)

    def _record_evidence_upload_rejected(
        self,
        *,
        ticket: dict[str, Any],
        context: RequestContext,
        decision: PolicyDecision,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "organization_id": ticket.get("organization_id"),
            "period_key": ticket.get("period_key"),
            "document_type": ticket.get("document_type"),
            "file_name": ticket.get("file_name"),
            "reason": reason,
            **(details or {}),
        }
        self.audit.record_context(
            "EVIDENCE_UPLOAD_REJECTED",
            context,
            str(ticket["evidence_version_id"]),
            policy_decision=decision,
            payload=payload,
        )
        self._record_object_access_log(
            tenant_id=context.tenant_id,
            evidence_document_id=None,
            evidence_version_id=str(ticket["evidence_version_id"]),
            organization_id=str(ticket.get("organization_id") or ""),
            actor_id=context.actor_id,
            access_type="upload_complete",
            access_status="denied",
            purpose=context.purpose,
            request_id=context.request_id,
            policy_decision_id=decision.decision_id,
            object_storage_status=reason,
            object_key=ticket.get("object_key"),
            reason=reason,
        )

    def get_evidence_document(self, evidence_document_id: str, context: RequestContext) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM evidence_documents WHERE evidence_document_id = ?",
                (evidence_document_id,),
            ).fetchone()
            if row is None:
                self._record_denied_evidence_access(
                    resource_id=evidence_document_id,
                    resource_type="evidence",
                    event_type="EVIDENCE_DOCUMENT_READ_DENIED",
                    action="read_evidence",
                    context=context,
                    reason="not_found_or_not_authorized",
                )
                raise IntakeNotFoundError(evidence_document_id)
            document = dict(row)
            decision = PolicyService.require(
                "read_evidence",
                context,
                resource_type="evidence",
                resource_id=evidence_document_id,
                resource_organization_id=document["organization_id"],
                data_classification=document["classification"],
            )
            self.audit.record_policy_decision(context, decision)
            versions = [
                dict(item)
                for item in connection.execute(
                    "SELECT * FROM evidence_versions WHERE evidence_document_id = ? ORDER BY created_at DESC",
                    (evidence_document_id,),
                ).fetchall()
            ]
            grants = [
                dict(item)
                for item in connection.execute(
                    """
                    SELECT *
                    FROM evidence_access_grants
                    WHERE evidence_document_id = ?
                      AND status = 'active'
                      AND revoked_at IS NULL
                      AND purpose = ?
                    ORDER BY created_at DESC
                    """,
                    (evidence_document_id, context.purpose),
                ).fetchall()
            ]
        safe_versions = [dict(version) for version in versions]
        for version in safe_versions:
            version.pop("object_key", None)
        event_id = self.audit.record_context(
            "EVIDENCE_DOCUMENT_READ",
            context,
            evidence_document_id,
            policy_decision=decision,
            payload={"organization_id": document["organization_id"], "classification": document["classification"]},
        )
        return {
            "evidence_document_id": evidence_document_id,
            "organization_id": document["organization_id"],
            "reporting_period_id": document.get("reporting_period_id"),
            "period_key": None,
            "document_type": document["document_type"],
            "title": document["title"],
            "classification": document["classification"],
            "retention_status": document["retention_status"],
            "legal_hold": bool(document["legal_hold"]),
            "source_submission_id": document.get("source_submission_id"),
            "source_record_id": document.get("source_record_id"),
            "valid_from": document.get("valid_from"),
            "valid_to": document.get("valid_to"),
            "created_at": document.get("created_at"),
            "versions": safe_versions,
            "active_grants": grants,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": TRUST_NOTICE,
        }

    def add_evidence_version(
        self,
        *,
        evidence_document_id: str,
        organization_id: str,
        object_key: str,
        document_hash: str,
        content_type: str,
        byte_size: int,
        malware_scan_status: str,
        supersedes_version_id: str | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM evidence_documents WHERE evidence_document_id = ? AND organization_id = ?",
                (evidence_document_id, organization_id),
            ).fetchone()
        document = dict(row) if row is not None else None
        decision = PolicyService.require(
            "create_evidence_version",
            context,
            resource_type="evidence",
            resource_id=evidence_document_id,
            resource_organization_id=organization_id,
            data_classification=(document.get("classification") if document else None) or "confidential",
        )
        self.audit.record_policy_decision(context, decision)
        if document is None:
            raise IntakeNotFoundError(evidence_document_id)
        version_id = _id("EVV")
        now = _now()
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO evidence_versions (
                  evidence_version_id, evidence_document_id, tenant_id, organization_id, object_key,
                  period_key, document_type, file_name, classification,
                  object_version, document_hash, content_type, byte_size, malware_scan_status,
                  retention_status, legal_hold, uploader_id, supersedes_version_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?)
                """,
                (
                    version_id,
                    evidence_document_id,
                    context.tenant_id,
                    organization_id,
                    object_key,
                    (document.get("valid_from") or now)[:7],
                    document.get("document_type"),
                    document.get("title"),
                    document.get("classification"),
                    version_id,
                    document_hash,
                    content_type,
                    byte_size,
                    malware_scan_status,
                    context.actor_id,
                    supersedes_version_id,
                    now,
                ),
            )
            connection.commit()
        event_id = self.audit.record_context(
            "EVIDENCE_VERSION_RECORDED",
            context,
            evidence_document_id,
            policy_decision=decision,
            payload={"version_id": version_id, "malware_scan_status": malware_scan_status},
        )
        return {
            "evidence_version_id": version_id,
            "evidence_document_id": evidence_document_id,
            "organization_id": organization_id,
            "object_key": object_key,
            "object_version": version_id,
            "document_hash": document_hash,
            "malware_scan_status": malware_scan_status,
            "usable": malware_scan_status == "clean",
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Evidence versions are append-only; clean scan is required before approval workflows can rely on this file.",
        }

    def create_evidence_download_url(self, evidence_version_id: str, context: RequestContext) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                """
                SELECT
                  version.*,
                  COALESCE(document.classification, version.classification, 'confidential') AS policy_classification,
                  COALESCE(document.retention_status, version.retention_status, 'active') AS policy_retention_status
                FROM evidence_versions version
                LEFT JOIN evidence_documents document ON document.evidence_document_id = version.evidence_document_id
                WHERE version.evidence_version_id = ?
                """,
                (evidence_version_id,),
            ).fetchone()
        if row is None:
            self._record_denied_evidence_access(
                resource_id=evidence_version_id,
                resource_type="evidence_version",
                event_type="EVIDENCE_DOWNLOAD_URL_DENIED",
                action="read_evidence",
                context=context,
                reason="not_found_or_not_authorized",
            )
            raise IntakeNotFoundError(evidence_version_id)

        item = dict(row)
        if item["malware_scan_status"] != "clean":
            self._record_denied_evidence_access(
                resource_id=evidence_version_id,
                resource_type="evidence_version",
                event_type="EVIDENCE_DOWNLOAD_URL_DENIED",
                action="read_evidence",
                context=context,
                reason=f"malware_scan_status_{item['malware_scan_status']}_not_downloadable",
                evidence_document_id=item.get("evidence_document_id"),
                evidence_version_id=evidence_version_id,
                organization_id=item.get("organization_id"),
                object_key=item.get("object_key"),
                object_storage_status="not_issued",
                data_classification=item.get("policy_classification") or "confidential",
            )
            raise AccessDeniedError(
                "EVIDENCE_VERSION_NOT_CLEAN",
                "Evidence version is not downloadable until malware scan status is clean.",
                status_code=409,
            )
        retention_status = str(item.get("policy_retention_status") or item.get("retention_status") or "active")
        if retention_status in {"scheduled_delete", "deleted"}:
            self._record_denied_evidence_access(
                resource_id=evidence_version_id,
                resource_type="evidence_version",
                event_type="EVIDENCE_DOWNLOAD_URL_DENIED",
                action="read_evidence",
                context=context,
                reason=f"retention_status_{retention_status}_not_downloadable",
                evidence_document_id=item.get("evidence_document_id"),
                evidence_version_id=evidence_version_id,
                organization_id=item.get("organization_id"),
                object_key=item.get("object_key"),
                object_storage_status="not_issued",
                data_classification=item.get("policy_classification") or "confidential",
            )
            raise AccessDeniedError(
                "EVIDENCE_VERSION_RETIRED",
                "Evidence version is not downloadable while retention status is scheduled_delete or deleted.",
                status_code=409,
            )

        decision = PolicyService.require(
            "read_evidence",
            context,
            resource_type="evidence_version",
            resource_id=evidence_version_id,
            resource_organization_id=item["organization_id"],
            data_classification=item.get("policy_classification") or "confidential",
        )
        self.audit.record_policy_decision(context, decision)
        event_id = self.audit.record_context(
            "EVIDENCE_DOWNLOAD_URL_CREATED",
            context,
            evidence_version_id,
            policy_decision=decision,
            payload={
                "organization_id": item["organization_id"],
                "evidence_document_id": item["evidence_document_id"],
                "object_storage_status": "demo",
            },
        )
        access_id = self._record_object_access_log(
            tenant_id=context.tenant_id,
            evidence_document_id=item.get("evidence_document_id"),
            evidence_version_id=evidence_version_id,
            organization_id=item.get("organization_id"),
            actor_id=context.actor_id,
            access_type="download_ticket",
            access_status="allowed",
            purpose=context.purpose,
            request_id=context.request_id,
            policy_decision_id=decision.decision_id,
            object_storage_status="demo",
            object_key=item.get("object_key"),
            reason=None,
        )
        return {
            "evidence_version_id": evidence_version_id,
            "evidence_document_id": item["evidence_document_id"],
            "organization_id": item["organization_id"],
            "download_url": f"demo-download-ticket://{evidence_version_id}",
            "download_method": "GET",
            "expires_in_seconds": 300,
            "object_storage_status": "demo",
            "object_version": item["object_version"],
            "document_hash": item["document_hash"],
            "content_type": item["content_type"],
            "byte_size": item["byte_size"],
            "malware_scan_status": item["malware_scan_status"],
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "object_access_id": access_id,
            "advisory_notice": "Download tickets are audited and only issued for clean evidence versions.",
        }

    def _record_denied_evidence_access(
        self,
        *,
        resource_id: str,
        resource_type: str,
        event_type: str,
        action: str,
        context: RequestContext,
        reason: str,
        evidence_document_id: str | None = None,
        evidence_version_id: str | None = None,
        organization_id: str | None = None,
        object_key: str | None = None,
        object_storage_status: str | None = None,
        data_classification: str | None = None,
    ) -> None:
        decision = PolicyDecision(
            decision_id=_id("POL"),
            action=action,
            effect="deny",
            reason=reason,
            resource_type=resource_type,
            resource_id=resource_id,
            data_classification=data_classification or "confidential",
        )
        self.audit.record_policy_decision(context, decision)
        self.audit.record_context(
            event_type,
            context,
            resource_id,
            policy_decision=decision,
            payload={"resource_type": resource_type, "reason": reason},
        )
        self._record_object_access_log(
            tenant_id=context.tenant_id,
            evidence_document_id=evidence_document_id,
            evidence_version_id=evidence_version_id,
            organization_id=organization_id,
            actor_id=context.actor_id,
            access_type="metadata_read" if event_type == "EVIDENCE_DOCUMENT_READ_DENIED" else "download_denied",
            access_status="denied",
            purpose=context.purpose,
            request_id=context.request_id,
            policy_decision_id=decision.decision_id,
            object_storage_status=object_storage_status,
            object_key=object_key,
            reason=reason,
        )

    def _record_object_access_log(
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
        policy_decision_id: str | None,
        object_storage_status: str | None,
        object_key: str | None,
        reason: str | None,
    ) -> str:
        access_id = _id("EAL")
        object_key_hash = hashlib.sha256(object_key.encode("utf-8")).hexdigest() if object_key else None
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO evidence_object_access_logs (
                  access_id, tenant_id, evidence_document_id, evidence_version_id, organization_id,
                  actor_id, access_type, access_status, purpose, request_id, policy_decision_id,
                  object_storage_status, object_key_hash, reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    policy_decision_id,
                    object_storage_status,
                    object_key_hash,
                    reason,
                    _now(),
                ),
            )
            connection.commit()
        return access_id

    def record_evidence_scan_result(
        self,
        *,
        evidence_version_id: str,
        organization_id: str,
        malware_scan_status: str,
        scanner_name: str,
        scanner_version: str | None,
        scanned_at: str | None,
        details: str | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                """
                SELECT version.*, COALESCE(document.classification, version.classification, 'confidential') AS policy_classification
                FROM evidence_versions version
                LEFT JOIN evidence_documents document ON document.evidence_document_id = version.evidence_document_id
                WHERE version.evidence_version_id = ? AND version.organization_id = ?
                """,
                (evidence_version_id, organization_id),
            ).fetchone()
        version = dict(row) if row is not None else None
        decision = PolicyService.require(
            "record_malware_scan_result",
            context,
            resource_type="evidence_version",
            resource_id=evidence_version_id,
            resource_organization_id=organization_id,
            data_classification=(version.get("policy_classification") if version else None) or "confidential",
        )
        self.audit.record_policy_decision(context, decision)
        if version is None:
            raise IntakeNotFoundError(evidence_version_id)
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                UPDATE evidence_versions
                SET malware_scan_status = ?
                WHERE evidence_version_id = ? AND organization_id = ?
                """,
                (malware_scan_status, evidence_version_id, organization_id),
            )
            if version["evidence_document_id"]:
                connection.execute(
                    "UPDATE evidence_documents SET malware_scan_status = ? WHERE evidence_document_id = ?",
                    (malware_scan_status, version["evidence_document_id"]),
                )
            if version["evidence_document_id"] and malware_scan_status in {"infected", "failed"}:
                connection.execute(
                    "UPDATE evidence_documents SET retention_status = 'retention_locked' WHERE evidence_document_id = ?",
                    (version["evidence_document_id"],),
                )
            connection.commit()
            updated = dict(
                connection.execute(
                    """
                    SELECT
                      version.*,
                      COALESCE(document.retention_status, version.retention_status, 'active') AS effective_retention_status
                    FROM evidence_versions version
                    LEFT JOIN evidence_documents document ON document.evidence_document_id = version.evidence_document_id
                    WHERE version.evidence_version_id = ?
                    """,
                    (evidence_version_id,),
                ).fetchone()
            )
        event_id = self.audit.record_context(
            "EVIDENCE_SCAN_RESULT_RECORDED",
            context,
            evidence_version_id,
            policy_decision=decision,
            payload={
                "organization_id": organization_id,
                "malware_scan_status": malware_scan_status,
                "scanner_name": scanner_name,
                "scanner_version": scanner_version,
                "scanned_at": scanned_at,
                "details": details,
            },
        )
        retention_status = str(updated.get("effective_retention_status") or updated["retention_status"])
        return {
            "evidence_version_id": evidence_version_id,
            "evidence_document_id": updated["evidence_document_id"],
            "organization_id": organization_id,
            "object_key": updated["object_key"],
            "object_version": updated["object_version"],
            "document_hash": updated["document_hash"],
            "malware_scan_status": malware_scan_status,
            "retention_status": retention_status,
            "usable": malware_scan_status == "clean" and retention_status not in {"scheduled_delete", "deleted"},
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Malware scan results control evidence usability; infected or failed scans stay out of approval workflows.",
        }

    def create_evidence_access_grant(
        self,
        *,
        evidence_document_id: str,
        organization_id: str,
        grantee_organization_id: str,
        scope: str,
        purpose: str,
        expires_at: str | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM evidence_documents WHERE evidence_document_id = ? AND organization_id = ?",
                (evidence_document_id, organization_id),
            ).fetchone()
        document = dict(row) if row is not None else None
        decision = PolicyService.require(
            "grant_evidence_access",
            context,
            resource_type="evidence_access_grant",
            resource_id=evidence_document_id,
            resource_organization_id=organization_id,
            data_classification=(document.get("classification") if document else None) or "confidential",
        )
        self.audit.record_policy_decision(context, decision)
        if document is None:
            raise IntakeNotFoundError(evidence_document_id)
        grant_id = _id("EVG")
        now = _now()
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO evidence_access_grants (
                  grant_id, tenant_id, evidence_document_id, grantee_organization_id,
                  scope, purpose, status, expires_at, created_by, created_at, revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL)
                """,
                (
                    grant_id,
                    context.tenant_id,
                    evidence_document_id,
                    grantee_organization_id,
                    scope,
                    purpose,
                    expires_at,
                    context.actor_id,
                    now,
                ),
            )
            connection.commit()
        event_id = self.audit.record_context(
            "EVIDENCE_ACCESS_GRANTED",
            context,
            grant_id,
            policy_decision=decision,
            payload={
                "evidence_document_id": evidence_document_id,
                "organization_id": organization_id,
                "grantee_organization_id": grantee_organization_id,
                "scope": scope,
                "purpose": purpose,
            },
        )
        return {
            "grant_id": grant_id,
            "evidence_document_id": evidence_document_id,
            "organization_id": organization_id,
            "grantee_organization_id": grantee_organization_id,
            "scope": scope,
            "purpose": purpose,
            "status": "active",
            "expires_at": expires_at,
            "revoked_at": None,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Evidence access grants authorize review only for the stated scope and purpose.",
        }

    def revoke_evidence_access_grant(self, grant_id: str, context: RequestContext) -> dict[str, Any]:
        now = _now()
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                """
                SELECT grant.*, document.organization_id, document.classification
                FROM evidence_access_grants grant
                JOIN evidence_documents document ON document.evidence_document_id = grant.evidence_document_id
                WHERE grant.grant_id = ?
                """,
                (grant_id,),
            ).fetchone()
            if row is None:
                raise IntakeNotFoundError(grant_id)
            grant = dict(row)
            decision = PolicyService.require(
                "revoke_evidence_access",
                context,
                resource_type="evidence_access_grant",
                resource_id=grant_id,
                resource_organization_id=grant["organization_id"],
                data_classification=grant.get("classification") or "confidential",
            )
            self.audit.record_policy_decision(context, decision)
            connection.execute(
                "UPDATE evidence_access_grants SET status = 'revoked', revoked_at = ? WHERE grant_id = ?",
                (now, grant_id),
            )
            connection.commit()
        event_id = self.audit.record_context(
            "EVIDENCE_ACCESS_REVOKED",
            context,
            grant_id,
            policy_decision=decision,
            payload={"evidence_document_id": grant["evidence_document_id"], "scope": grant["scope"]},
        )
        return {
            "grant_id": grant_id,
            "evidence_document_id": grant["evidence_document_id"],
            "organization_id": grant["organization_id"],
            "grantee_organization_id": grant["grantee_organization_id"],
            "scope": grant["scope"],
            "purpose": grant["purpose"],
            "status": "revoked",
            "expires_at": grant["expires_at"],
            "revoked_at": now,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Evidence access grant revoked; future sensitive reads must re-check policy.",
        }

    def update_evidence_retention(
        self,
        *,
        evidence_document_id: str,
        organization_id: str,
        retention_status: str,
        legal_hold: bool,
        reason: str,
        context: RequestContext,
    ) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM evidence_documents WHERE evidence_document_id = ? AND organization_id = ?",
                (evidence_document_id, organization_id),
            ).fetchone()
        document = dict(row) if row is not None else None
        decision = PolicyService.require(
            "update_evidence_retention",
            context,
            resource_type="evidence",
            resource_id=evidence_document_id,
            resource_organization_id=organization_id,
            data_classification=(document.get("classification") if document else None) or "confidential",
        )
        self.audit.record_policy_decision(context, decision)
        if document is None:
            raise IntakeNotFoundError(evidence_document_id)
        with closing(self.database.connect()) as connection:
            if document["legal_hold"] and retention_status == "deleted":
                raise ValueError("Evidence on legal hold cannot be marked deleted.")
            connection.execute(
                """
                UPDATE evidence_documents
                SET retention_status = ?, legal_hold = ?
                WHERE evidence_document_id = ? AND organization_id = ?
                """,
                (retention_status, 1 if legal_hold else 0, evidence_document_id, organization_id),
            )
            connection.commit()
        event_id = self.audit.record_context(
            "EVIDENCE_RETENTION_UPDATED",
            context,
            evidence_document_id,
            policy_decision=decision,
            payload={"organization_id": organization_id, "retention_status": retention_status, "legal_hold": legal_hold, "reason": reason},
        )
        return {
            "evidence_document_id": evidence_document_id,
            "organization_id": organization_id,
            "retention_status": retention_status,
            "legal_hold": legal_hold,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Retention changes are governance metadata; deletion requires separate storage lifecycle enforcement.",
        }

    def create_invoice_claim(
        self,
        *,
        seller_id: str,
        buyer_id: str,
        financier_id: str,
        invoice_hash_value: str,
        amount: int,
        due_date: str,
        invoice_id: str | None,
        issue_date: str | None,
        currency: str,
        idempotency_key: str | None,
        source_evidence_id: str | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        if (
            financier_id not in context.organization_ids
            and not context.has_role("demo_admin", "demo_operator", "system_admin")
            and "policy:override" not in context.scopes
        ):
            denial = PolicyService.deny_decision(
                "register_invoice_claim",
                "Invoice claim financier must match the actor organization or platform operations.",
                resource_type="invoice_claim",
                resource_id=invoice_id,
                data_classification="restricted_financial",
            )
            self.audit.record_policy_decision(context, denial)
            self.audit.record_context(
                "INVOICE_CLAIM_REGISTER_DENIED",
                context,
                invoice_id or seller_id,
                policy_decision=denial,
                payload={"seller_id": seller_id, "buyer_id": buyer_id, "financier_id": financier_id},
            )
            raise AccessDeniedError("POLICY_DENIED", denial.reason, status_code=403)
        decision = self._require_access(
            "register_invoice_claim",
            context,
            resource_type="invoice_claim",
            resource_id=invoice_id,
            resource_organization_id=seller_id,
            data_classification="restricted_financial",
            consent_scope="invoice_claim",
        )
        self.audit.record_policy_decision(context, decision)
        identity = invoice_identity_hash(seller_id, buyer_id, invoice_hash_value, amount, due_date)
        now = _now()
        with closing(self.database.connect()) as connection:
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM invoice_claims WHERE tenant_id = ? AND idempotency_key = ?",
                    (context.tenant_id, idempotency_key),
                ).fetchone()
                if existing:
                    return self._invoice_claim_payload(dict(existing), decision.decision_id, None)
            active = connection.execute(
                """
                SELECT * FROM invoice_claims
                WHERE tenant_id = ? AND invoice_identity_hash = ? AND status IN ('pledged', 'financed')
                """,
                (context.tenant_id, identity),
            ).fetchone()
            if active:
                raise ValueError("Invoice already has an active pledged/financed claim.")
            claim_id = _id("CLM")
            connection.execute(
                """
                INSERT INTO invoice_claims (
                  claim_id, tenant_id, seller_id, buyer_id, financier_id, invoice_id, invoice_hash,
                  invoice_identity_hash, amount, currency, issue_date, due_date, status,
                  idempotency_key, review_status, reviewer_id, source_evidence_id,
                  created_by, created_at, updated_at, released_at, dispute_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'registered', ?, 'pending_review',
                  NULL, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    claim_id,
                    context.tenant_id,
                    seller_id,
                    buyer_id,
                    financier_id,
                    invoice_id,
                    invoice_hash_value,
                    identity,
                    amount,
                    currency,
                    issue_date,
                    due_date,
                    idempotency_key,
                    source_evidence_id,
                    context.actor_id,
                    now,
                    now,
                ),
            )
            self._insert_claim_event(connection, claim_id, context.tenant_id, None, "registered", context.actor_id, "Claim registered.", now)
            connection.commit()
            row = connection.execute("SELECT * FROM invoice_claims WHERE claim_id = ?", (claim_id,)).fetchone()
        event_id = self.audit.record_context(
            "INVOICE_CLAIM_REGISTERED",
            context,
            claim_id,
            policy_decision=decision,
            payload={"seller_id": seller_id, "buyer_id": buyer_id, "amount": amount, "status": "registered"},
        )
        return self._invoice_claim_payload(dict(row), decision.decision_id, event_id)

    def transition_invoice_claim(self, claim_id: str, to_status: str, note: str | None, context: RequestContext) -> dict[str, Any]:
        if to_status not in INVOICE_STATES:
            raise ValueError("Unsupported invoice claim status.")
        now = _now()
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT * FROM invoice_claims WHERE claim_id = ?", (claim_id,)).fetchone()
            if row is None:
                raise IntakeNotFoundError(claim_id)
            claim = dict(row)
            decision = self._require_access(
                "transition_invoice_claim",
                context,
                resource_type="invoice_claim",
                resource_id=claim_id,
                resource_organization_id=claim["seller_id"],
                data_classification="restricted_financial",
                consent_scope="invoice_claim",
            )
            self.audit.record_policy_decision(context, decision)
            allowed = INVOICE_TRANSITIONS.get(claim["status"], set())
            if to_status not in allowed:
                raise ValueError(f"Cannot transition invoice claim from {claim['status']} to {to_status}.")
            if to_status in {"financed", "released"} and not context.has_role("lender", "reviewer", "demo_operator", "demo_admin", "system_admin"):
                raise ValueError("Financing lifecycle transitions require lender/reviewer approval.")
            active = connection.execute(
                """
                SELECT claim_id FROM invoice_claims
                WHERE tenant_id = ? AND invoice_identity_hash = ? AND status IN ('pledged', 'financed') AND claim_id <> ?
                """,
                (claim["tenant_id"], claim["invoice_identity_hash"], claim_id),
            ).fetchone()
            if active and to_status in {"pledged", "financed"}:
                raise ValueError("Invoice already has another active pledged/financed claim.")
            connection.execute(
                """
                UPDATE invoice_claims
                SET status = ?, review_status = ?, reviewer_id = ?, updated_at = ?,
                    released_at = CASE WHEN ? = 'released' THEN ? ELSE released_at END,
                    dispute_reason = CASE WHEN ? = 'disputed' THEN ? ELSE dispute_reason END
                WHERE claim_id = ?
                """,
                (
                    to_status,
                    "reviewed" if to_status in {"verified", "pledged", "financed", "released"} else "disputed",
                    context.actor_id,
                    now,
                    to_status,
                    now,
                    to_status,
                    note,
                    claim_id,
                ),
            )
            self._insert_claim_event(connection, claim_id, claim["tenant_id"], claim["status"], to_status, context.actor_id, note, now)
            connection.commit()
            updated = dict(connection.execute("SELECT * FROM invoice_claims WHERE claim_id = ?", (claim_id,)).fetchone())
        event_id = self.audit.record_context(
            "INVOICE_CLAIM_TRANSITIONED",
            context,
            claim_id,
            policy_decision=decision,
            payload={"from_status": claim["status"], "to_status": to_status},
        )
        return self._invoice_claim_payload(updated, decision.decision_id, event_id)

    def list_risk_runs(self, organization_id: str, period_key: str | None, context: RequestContext) -> dict[str, Any]:
        decision = self._require_access(
            "read_risk_run",
            context,
            resource_type="risk_run",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
            consent_scope="financial_summary",
        )
        self.audit.record_policy_decision(context, decision)
        with closing(self.database.connect()) as connection:
            period = self._period(connection, organization_id, period_key)
            if period is None:
                return self._runs_payload("risk_runs", organization_id, period_key, [], decision)
            rows = connection.execute(
                """
                SELECT rr.*, fs.payload_json AS feature_payload_json
                FROM risk_runs rr
                LEFT JOIN feature_snapshots fs ON fs.feature_snapshot_id = rr.feature_snapshot_id
                WHERE rr.organization_id = ? AND rr.reporting_period_id = ?
                ORDER BY rr.created_at DESC
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchall()
        self.audit.record_context("RISK_RUNS_VIEWED", context, organization_id, policy_decision=decision)
        return self._runs_payload("risk_runs", organization_id, period_key, [dict(row) for row in rows], decision)

    def list_match_runs(self, organization_id: str, period_key: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_match_run",
            context,
            resource_type="match_run",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        self.audit.record_policy_decision(context, decision)
        with closing(self.database.connect()) as connection:
            period = self._period(connection, organization_id, period_key)
            if period is None:
                return self._runs_payload("match_runs", organization_id, period_key, [], decision)
            rows = connection.execute(
                """
                SELECT mr.*
                FROM match_runs mr
                WHERE mr.buyer_organization_id = ? AND mr.reporting_period_id = ?
                ORDER BY mr.created_at DESC
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchall()
            runs = []
            for row in rows:
                run = dict(row)
                candidates = connection.execute(
                    "SELECT * FROM match_candidates WHERE match_run_id = ? ORDER BY rank",
                    (run["match_run_id"],),
                ).fetchall()
                run["candidates"] = [dict(item) for item in candidates]
                runs.append(run)
        self.audit.record_context("MATCH_RUNS_VIEWED", context, organization_id, policy_decision=decision)
        return self._runs_payload("match_runs", organization_id, period_key, runs, decision)

    def list_scenario_runs(self, organization_id: str, period_key: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_scenario_run",
            context,
            resource_type="scenario_run",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        self.audit.record_policy_decision(context, decision)
        with closing(self.database.connect()) as connection:
            period = self._period(connection, organization_id, period_key)
            if period is None:
                return self._runs_payload("scenario_runs", organization_id, period_key, [], decision)
            rows = connection.execute(
                """
                SELECT sr.*
                FROM scenario_runs sr
                WHERE sr.organization_id = ? AND sr.reporting_period_id = ?
                ORDER BY sr.created_at DESC
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchall()
            runs = []
            for row in rows:
                run = dict(row)
                run["payload"] = _loads(run.pop("payload_json", "{}"), {})
                runs.append(run)
        self.audit.record_context("SCENARIO_RUNS_VIEWED", context, organization_id, policy_decision=decision)
        return self._runs_payload("scenario_runs", organization_id, period_key, runs, decision)

    def list_model_registry(self, artifact_type: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_ops",
            context,
            resource_type="model_registry",
            resource_id=artifact_type,
            data_classification="confidential",
        )
        self.audit.record_policy_decision(context, decision)
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM model_registry
                WHERE tenant_id = ?
                  AND (? IS NULL OR artifact_type = ?)
                ORDER BY artifact_type, model_version
                """,
                (context.tenant_id, artifact_type, artifact_type),
            ).fetchall()
        models = []
        for row in rows:
            item = dict(row)
            item["config"] = _loads(item.pop("config_json", "{}"), {})
            models.append(item)
        self.audit.record_context(
            "MODEL_REGISTRY_VIEWED",
            context,
            artifact_type or "all",
            policy_decision=decision,
            payload={"artifact_type": artifact_type, "count": len(models)},
        )
        return {
            "artifact_type": artifact_type,
            "models": models,
            "policy_decision_id": decision.decision_id,
            "advisory_notice": TRUST_NOTICE,
        }

    def list_ruleset_registry(self, artifact_type: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_ops",
            context,
            resource_type="ruleset_registry",
            resource_id=artifact_type,
            data_classification="confidential",
        )
        self.audit.record_policy_decision(context, decision)
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM ruleset_registry
                WHERE tenant_id = ?
                  AND (? IS NULL OR artifact_type = ?)
                ORDER BY artifact_type, ruleset_version
                """,
                (context.tenant_id, artifact_type, artifact_type),
            ).fetchall()
        rulesets = []
        for row in rows:
            item = dict(row)
            item["config"] = _loads(item.pop("config_json", "{}"), {})
            rulesets.append(item)
        self.audit.record_context(
            "RULESET_REGISTRY_VIEWED",
            context,
            artifact_type or "all",
            policy_decision=decision,
            payload={"artifact_type": artifact_type, "count": len(rulesets)},
        )
        return {
            "artifact_type": artifact_type,
            "rulesets": rulesets,
            "policy_decision_id": decision.decision_id,
            "advisory_notice": TRUST_NOTICE,
        }

    def list_recompute_jobs(
        self,
        *,
        organization_id: str | None,
        status: str | None,
        limit: int,
        context: RequestContext,
    ) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_ops",
            context,
            resource_type="analytics_recompute_jobs",
            resource_id=organization_id or status or "all",
            data_classification="confidential",
        )
        self.audit.record_policy_decision(context, decision)
        safe_limit = max(1, min(limit, 100))
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM analytics_recompute_jobs
                WHERE tenant_id = ?
                  AND (? IS NULL OR organization_id = ?)
                  AND (? IS NULL OR status = ?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (context.tenant_id, organization_id, organization_id, status, status, safe_limit),
            ).fetchall()
        jobs = []
        for row in rows:
            item = dict(row)
            item["payload"] = _loads(item.pop("payload_json", "{}"), {})
            jobs.append(item)
        self.audit.record_context(
            "RECOMPUTE_JOBS_VIEWED",
            context,
            organization_id or "all",
            policy_decision=decision,
            payload={"organization_id": organization_id, "status": status, "count": len(jobs)},
        )
        return {
            "organization_id": organization_id,
            "status": status,
            "limit": safe_limit,
            "jobs": jobs,
            "policy_decision_id": decision.decision_id,
            "advisory_notice": TRUST_NOTICE,
        }

    def _period(self, connection: Any, organization_id: str, period_key: str | None) -> dict[str, Any] | None:
        if period_key:
            row = connection.execute(
                "SELECT * FROM reporting_periods WHERE organization_id = ? AND period_key = ?",
                (organization_id, period_key),
            ).fetchone()
            return dict(row) if row else None
        row = connection.execute(
            "SELECT * FROM reporting_periods WHERE organization_id = ? ORDER BY period_start DESC LIMIT 1",
            (organization_id,),
        ).fetchone()
        return dict(row) if row else None

    def _ensure_upload_period(self, connection: Any, tenant_id: str, organization_id: str, period_key: str) -> tuple[str, str, str]:
        year_text, month_text = period_key.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
        period_start = f"{period_key}-01"
        period_end = f"{period_key}-{calendar.monthrange(year, month)[1]:02d}"
        period_id = f"PER-{organization_id}-{period_key}"
        connection.execute(
            """
            INSERT OR IGNORE INTO reporting_periods (
              reporting_period_id, tenant_id, organization_id, period_type, period_key,
              period_start, period_end, status, lock_version
            )
            VALUES (?, ?, ?, 'month', ?, ?, ?, 'open', 1)
            """,
            (period_id, tenant_id, organization_id, period_key, period_start, period_end),
        )
        return period_id, period_start, period_end

    def _runs_payload(self, kind: str, organization_id: str, period_key: str | None, rows: list[dict[str, Any]], decision: Any) -> dict[str, Any]:
        return {
            "organization_id": organization_id,
            "period_key": period_key,
            kind: rows,
            "policy_decision_id": decision.decision_id,
            "advisory_notice": TRUST_NOTICE,
        }

    def _pending_evidence_ticket_payload(self, row: dict[str, Any], policy_decision_id: str) -> dict[str, Any]:
        file_name = row.get("file_name")
        if not file_name:
            file_name = str(row.get("object_key") or row["evidence_version_id"]).rsplit("/", maxsplit=1)[-1]
        return {
            "id": row["evidence_version_id"],
            "evidence_version_id": row["evidence_version_id"],
            "organization_id": row["organization_id"],
            "business_id": row["organization_id"],
            "period_key": row.get("period_key"),
            "document_type": row.get("document_type") or "CERTIFICATION",
            "file_name": file_name,
            "content_type": row["content_type"],
            "byte_size": row["byte_size"],
            "classification": row.get("classification") or "confidential",
            "status": "upload_ticket_created" if row["malware_scan_status"] == "pending_upload" else row["malware_scan_status"],
            "malware_scan_status": row["malware_scan_status"],
            "uploaded_at": row["created_at"],
            "policy_decision_id": policy_decision_id,
            "audit_event_id": None,
            "advisory_notice": "Pending upload ticket only; file is not verified evidence until checksum and malware scan pass.",
        }

    def _invoice_claim_payload(self, row: dict[str, Any], policy_decision_id: str, audit_event_id: str | None) -> dict[str, Any]:
        return {
            **row,
            "policy_decision_id": policy_decision_id,
            "audit_event_id": audit_event_id,
            "advisory_notice": (
                "Invoice claim registry is a control workflow. It does not confirm invoice authenticity, "
                "fraud, double financing, or financing approval; lender/human decision remains required."
            ),
        }

    def _insert_claim_event(
        self,
        connection: Any,
        claim_id: str,
        tenant_id: str,
        from_status: str | None,
        to_status: str,
        actor_id: str,
        note: str | None,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO invoice_claim_events (
              event_id, claim_id, tenant_id, from_status, to_status, actor_id, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_id("ICE"), claim_id, tenant_id, from_status, to_status, actor_id, note, created_at),
        )
