from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from contextlib import closing
from typing import Any
from uuid import uuid4

from backend.app.domain.entities import Business, FinancialSnapshot, InvoiceVerification, Product, SupplyEdge
from backend.app.services.access_control import PolicyDecision, RequestContext
from backend.app.services.database import Database


def _demo_coordinates_for_province(province: str) -> tuple[float, float]:
    coordinates = {
        "Binh Duong": (10.9804, 106.6519),
        "Dong Nai": (10.9453, 106.8246),
        "Lam Dong": (11.5753, 108.1429),
        "TP.HCM": (10.7769, 106.7009),
    }
    return coordinates.get(province, coordinates["TP.HCM"])


def _onboarding_demo_metrics(stakeholder_role: str, scale: str, category: str) -> dict[str, int]:
    role = stakeholder_role.lower()
    scale_value = scale.lower()
    if category == "finance" or "finance" in role:
        return {"monthly_revenue": 3_000_000_000, "capacity": 0, "financial_health_score": 72, "supply_risk_score": 25}
    if "household" in scale_value or "hộ" in scale_value:
        return {"monthly_revenue": 250_000_000, "capacity": 3_000, "financial_health_score": 58, "supply_risk_score": 45}
    if "distributor" in role or "supplier" in role:
        return {"monthly_revenue": 2_000_000_000, "capacity": 60_000, "financial_health_score": 68, "supply_risk_score": 38}
    return {"monthly_revenue": 800_000_000, "capacity": 18_000, "financial_health_score": 68, "supply_risk_score": 38}


class BusinessRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_all(self) -> list[Business]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute("SELECT * FROM businesses ORDER BY business_id").fetchall()
        return [Business.from_mapping(row) for row in rows]

    def get(self, business_id: str) -> Business | None:
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT * FROM businesses WHERE business_id = ?", (business_id,)).fetchone()
        return Business.from_mapping(row) if row else None


class SupplyEdgeRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_all(self) -> list[SupplyEdge]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute("SELECT * FROM supply_edges ORDER BY edge_id").fetchall()
        return [SupplyEdge.from_mapping(row) for row in rows]

    def outgoing(self, business_id: str, product_category: str | None = None) -> list[SupplyEdge]:
        sql = "SELECT * FROM supply_edges WHERE source_id = ?"
        params: tuple[str, ...] = (business_id,)
        if product_category:
            sql += " AND product_category = ?"
            params = (business_id, product_category)
        sql += " ORDER BY edge_id"
        with closing(self.database.connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [SupplyEdge.from_mapping(row) for row in rows]


class FinancialRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def for_business(self, business_id: str) -> list[FinancialSnapshot]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM financial_snapshots WHERE business_id = ? ORDER BY month",
                (business_id,),
            ).fetchall()
        return [FinancialSnapshot.from_mapping(row) for row in rows]


class ProductRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_all(self) -> list[Product]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute("SELECT * FROM products ORDER BY business_id, sku").fetchall()
        return [Product.from_mapping(row) for row in rows]

    def for_business(self, business_id: str) -> list[Product]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM products WHERE business_id = ? ORDER BY sku",
                (business_id,),
            ).fetchall()
        return [Product.from_mapping(row) for row in rows]


class InvoiceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_all(self) -> list[InvoiceVerification]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute("SELECT * FROM invoice_verifications ORDER BY invoice_id").fetchall()
        return [InvoiceVerification.from_mapping(row) for row in rows]

    def get(self, invoice_id: str) -> InvoiceVerification | None:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM invoice_verifications WHERE invoice_id = ?",
                (invoice_id,),
            ).fetchone()
        return InvoiceVerification.from_mapping(row) if row else None


class AuditRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        event_type: str,
        actor_role: str,
        subject_id: str,
        purpose: str,
        actor_id: str = "demo-user",
        *,
        tenant_id: str = "tenant-demo",
        request_id: str | None = None,
        policy_decision_id: str | None = None,
        app_mode: str = "demo",
        auth_assurance: str = "demo-header",
        payload: dict[str, Any] | None = None,
    ) -> str:
        event_id = f"AUD-{uuid4().hex[:12].upper()}"
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        canonical_payload = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with closing(self.database.connect()) as connection:
            previous = connection.execute(
                "SELECT event_hash FROM audit_logs WHERE event_hash IS NOT NULL ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous["event_hash"] if previous else None
            event_hash = self._event_hash(
                {
                    "event_id": event_id,
                    "tenant_id": tenant_id,
                    "event_type": event_type,
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "subject_id": subject_id,
                    "purpose": purpose,
                    "timestamp": timestamp,
                    "request_id": request_id or event_id.lower(),
                    "policy_decision_id": policy_decision_id,
                    "previous_hash": previous_hash,
                    "payload_json": canonical_payload,
                    "app_mode": app_mode,
                    "auth_assurance": auth_assurance,
                }
            )
            connection.execute(
                """
                INSERT INTO audit_logs (
                  event_id, tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                  timestamp, request_id, policy_decision_id, previous_hash, event_hash,
                  payload_json, app_mode, auth_assurance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    tenant_id,
                    event_type,
                    actor_id,
                    actor_role,
                    subject_id,
                    purpose,
                    timestamp,
                    request_id or event_id.lower(),
                    policy_decision_id,
                    previous_hash,
                    event_hash,
                    canonical_payload,
                    app_mode,
                    auth_assurance,
                ),
            )
            connection.commit()
        return event_id

    def record_context(
        self,
        event_type: str,
        context: RequestContext,
        subject_id: str,
        *,
        policy_decision: PolicyDecision | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        return self.record(
            event_type,
            context.actor_role,
            subject_id,
            context.purpose,
            actor_id=context.actor_id,
            tenant_id=context.tenant_id,
            request_id=context.request_id,
            policy_decision_id=policy_decision.decision_id if policy_decision else None,
            app_mode=context.app_mode,
            auth_assurance=context.auth_assurance,
            payload=payload,
        )

    def list_recent(self, limit: int = 30) -> list[dict[str, Any]]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def verify_chain(self) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute("SELECT * FROM audit_logs ORDER BY rowid").fetchall()
        previous_hash = None
        checked = 0
        for row in rows:
            item = dict(row)
            if item.get("event_hash") is None:
                previous_hash = None
                continue
            expected = self._event_hash(
                {
                    "event_id": item["event_id"],
                    "tenant_id": item.get("tenant_id"),
                    "event_type": item["event_type"],
                    "actor_id": item["actor_id"],
                    "actor_role": item["actor_role"],
                    "subject_id": item["subject_id"],
                    "purpose": item["purpose"],
                    "timestamp": item["timestamp"],
                    "request_id": item["request_id"],
                    "policy_decision_id": item.get("policy_decision_id"),
                    "previous_hash": item.get("previous_hash"),
                    "payload_json": item.get("payload_json") or "{}",
                    "app_mode": item.get("app_mode") or "demo",
                    "auth_assurance": item.get("auth_assurance") or "demo-header",
                }
            )
            if item.get("previous_hash") != previous_hash:
                return {"ok": False, "checked": checked, "failed_event_id": item["event_id"], "reason": "previous_hash_mismatch"}
            if item.get("event_hash") != expected:
                return {"ok": False, "checked": checked, "failed_event_id": item["event_id"], "reason": "event_hash_mismatch"}
            previous_hash = item["event_hash"]
            checked += 1
        return {"ok": True, "checked": checked, "failed_event_id": None, "reason": None}

    def record_policy_decision(self, context: RequestContext, decision: PolicyDecision) -> str:
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO policy_decisions (
                  decision_id, tenant_id, actor_id, action, resource_type, resource_id,
                  data_classification, effect, reason, purpose, request_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    context.tenant_id,
                    context.actor_id,
                    decision.action,
                    decision.resource_type,
                    decision.resource_id,
                    decision.data_classification,
                    decision.effect,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    created_at,
                ),
            )
            connection.commit()
        return decision.decision_id

    @staticmethod
    def _event_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AccessPolicyRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def has_active_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        recipient_ids: set[str] | frozenset[str],
        scope: str,
        purpose: str | None = None,
    ) -> bool:
        if not recipient_ids:
            return False
        placeholders = ",".join("?" for _ in recipient_ids)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        params: list[Any] = [tenant_id, subject_id, scope, *sorted(recipient_ids), now]
        sql = f"""
            SELECT 1
            FROM consent_records
            WHERE tenant_id = ?
              AND subject_id = ?
              AND scope = ?
              AND recipient_id IN ({placeholders})
              AND status = 'granted'
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?)
        """
        if purpose:
            sql += " AND (purpose = ? OR purpose = 'all_purposes')"
            params.append(purpose)
        sql += " LIMIT 1"
        with closing(self.database.connect()) as connection:
            return connection.execute(sql, tuple(params)).fetchone() is not None

    def has_active_relationship(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        actor_organization_ids: set[str] | frozenset[str],
        relationship_types: set[str] | frozenset[str] | None = None,
    ) -> bool:
        if not actor_organization_ids:
            return False
        org_placeholders = ",".join("?" for _ in actor_organization_ids)
        params: list[Any] = [tenant_id, subject_id, *sorted(actor_organization_ids), subject_id, *sorted(actor_organization_ids)]
        sql = f"""
            SELECT 1
            FROM organization_relationships
            WHERE tenant_id = ?
              AND status = 'active'
              AND (
                source_organization_id = ? AND target_organization_id IN ({org_placeholders})
                OR target_organization_id = ? AND source_organization_id IN ({org_placeholders})
              )
        """
        if relationship_types:
            type_placeholders = ",".join("?" for _ in relationship_types)
            sql += f" AND relationship_type IN ({type_placeholders})"
            params.extend(sorted(relationship_types))
        sql += " LIMIT 1"
        with closing(self.database.connect()) as connection:
            return connection.execute(sql, tuple(params)).fetchone() is not None

    def has_any_active_relationship(
        self,
        *,
        tenant_id: str,
        actor_organization_ids: set[str] | frozenset[str],
    ) -> bool:
        if not actor_organization_ids:
            return False
        placeholders = ",".join("?" for _ in actor_organization_ids)
        params: list[Any] = [tenant_id, *sorted(actor_organization_ids), *sorted(actor_organization_ids)]
        sql = f"""
            SELECT 1
            FROM organization_relationships
            WHERE tenant_id = ?
              AND status = 'active'
              AND (source_organization_id IN ({placeholders}) OR target_organization_id IN ({placeholders}))
            LIMIT 1
        """
        with closing(self.database.connect()) as connection:
            return connection.execute(sql, tuple(params)).fetchone() is not None


class EvidenceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def contracts_for_business(self, business_id: str) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM contracts WHERE supplier_id = ? OR buyer_id = ? ORDER BY effective_date DESC",
            (business_id, business_id),
        )

    def purchase_orders_for_business(self, business_id: str) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM purchase_orders WHERE supplier_id = ? OR buyer_id = ? ORDER BY order_date DESC",
            (business_id, business_id),
        )

    def delivery_notes_for_business(self, business_id: str) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT * FROM delivery_notes
            WHERE supplier_id = ? OR buyer_id = ? OR logistics_partner_id = ?
            ORDER BY delivery_date DESC
            """,
            (business_id, business_id, business_id),
        )

    def certifications_for_business(self, business_id: str) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM certifications WHERE business_id = ? ORDER BY expiry_date",
            (business_id,),
        )

    def guarantees_for_business(self, business_id: str) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT * FROM guarantees
            WHERE applicant_id = ? OR beneficiary_id = ? OR issuer_id = ?
            ORDER BY effective_date DESC
            """,
            (business_id, business_id, business_id),
        )

    def documents_for_business(self, business_id: str) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT
              document.*,
              (
                SELECT version.evidence_version_id
                FROM evidence_versions version
                WHERE version.evidence_document_id = document.evidence_document_id
                ORDER BY version.created_at DESC
                LIMIT 1
              ) AS latest_evidence_version_id,
              (
                SELECT version.malware_scan_status
                FROM evidence_versions version
                WHERE version.evidence_document_id = document.evidence_document_id
                ORDER BY version.created_at DESC
                LIMIT 1
              ) AS latest_version_malware_scan_status
            FROM evidence_documents document
            WHERE document.organization_id = ?
            ORDER BY document.created_at DESC
            """,
            (business_id,),
        )

    def all_for_business(self, business_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            "contracts": self.contracts_for_business(business_id),
            "purchase_orders": self.purchase_orders_for_business(business_id),
            "delivery_notes": self.delivery_notes_for_business(business_id),
            "certifications": self.certifications_for_business(business_id),
            "guarantees": self.guarantees_for_business(business_id),
            "evidence_documents": self.documents_for_business(business_id),
        }

    def _query(self, sql: str, params: tuple[str, ...]) -> list[dict[str, Any]]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


class ConnectionRequestRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        tenant_id: str,
        buyer_id: str,
        target_supplier_id: str,
        disrupted_supplier_id: str | None,
        purpose: str,
        requester_id: str = "demo-user",
    ) -> dict[str, Any]:
        request_id = f"REQ-{uuid4().hex[:12].upper()}"
        requested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO connection_requests (
                  request_id, tenant_id, requester_id, buyer_id, target_supplier_id, disrupted_supplier_id,
                  purpose, status, consent_status, requested_at, decided_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'awaiting_supplier_consent', ?, NULL)
                """,
                (
                    request_id,
                    tenant_id,
                    requester_id,
                    buyer_id,
                    target_supplier_id,
                    disrupted_supplier_id,
                    purpose,
                    requested_at,
                ),
            )
            connection.commit()
        return self.get(request_id) or {}

    def get(self, request_id: str) -> dict[str, Any] | None:
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT * FROM connection_requests WHERE request_id = ?", (request_id,)).fetchone()
        return dict(row) if row else None

    def set_audit_event(self, request_id: str, audit_event_id: str, policy_decision_id: str | None) -> dict[str, Any] | None:
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                UPDATE connection_requests
                SET audit_event_id = ?, policy_decision_id = ?
                WHERE request_id = ?
                """,
                (audit_event_id, policy_decision_id, request_id),
            )
            connection.commit()
        return self.get(request_id)

    def decide(
        self,
        *,
        request_id: str,
        decision: str,
        actor_id: str,
        note: str | None,
        contract_evidence_id: str | None,
        policy_decision_id: str | None,
    ) -> dict[str, Any] | None:
        current = self.get(request_id)
        if current is None:
            return None
        status_by_decision = {
            "grant_consent": ("pending", "supplier_consented"),
            "reject": ("rejected", "supplier_rejected"),
            "request_changes": ("changes_requested", "changes_requested"),
            "activate_relationship": ("relationship_active", "contract_evidence_recorded"),
        }
        status, consent_status = status_by_decision[decision]
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        relationship_id = current.get("relationship_id")
        relationship_edge_id = current.get("relationship_edge_id")
        with closing(self.database.connect()) as connection:
            if decision == "activate_relationship":
                relationship_id = relationship_id or f"REL-{request_id}"
                relationship_edge_id = relationship_edge_id or f"EDGE-{request_id}"
                supplier = connection.execute(
                    "SELECT product_category FROM businesses WHERE business_id = ?",
                    (current["target_supplier_id"],),
                ).fetchone()
                product_category = supplier["product_category"] if supplier else "general"
                connection.execute(
                    """
                    INSERT OR IGNORE INTO organization_relationships (
                      relationship_id, tenant_id, source_organization_id, target_organization_id,
                      relationship_type, status
                    )
                    VALUES (?, ?, ?, ?, 'supply', 'active')
                    """,
                    (relationship_id, current.get("tenant_id") or "tenant-demo", current["target_supplier_id"], current["buyer_id"]),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO supply_edges (
                      edge_id, source_id, target_id, product, product_category, monthly_volume,
                      lead_time_days, transport_cost, reliability, payment_term_days
                    )
                    VALUES (?, ?, ?, 'Contract-gated supply relationship', ?, 0, 0, 0, 0.0, 0)
                    """,
                    (relationship_edge_id, current["target_supplier_id"], current["buyer_id"], product_category),
                )
            connection.execute(
                """
                UPDATE connection_requests
                SET status = ?,
                    consent_status = ?,
                    decided_at = ?,
                    decided_by = ?,
                    decision_note = ?,
                    contract_evidence_id = COALESCE(?, contract_evidence_id),
                    relationship_id = ?,
                    relationship_edge_id = ?,
                    policy_decision_id = ?,
                    updated_at = ?
                WHERE request_id = ?
                """,
                (
                    status,
                    consent_status,
                    now,
                    actor_id,
                    note,
                    contract_evidence_id,
                    relationship_id,
                    relationship_edge_id,
                    policy_decision_id,
                    now,
                    request_id,
                ),
            )
            connection.commit()
        return self.get(request_id)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM connection_requests ORDER BY requested_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_visible(
        self,
        *,
        tenant_id: str,
        organization_id: str,
        include_review_queue: bool,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with closing(self.database.connect()) as connection:
            if include_review_queue:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM connection_requests
                    WHERE tenant_id = ?
                    ORDER BY requested_at DESC
                    LIMIT ?
                    """,
                    (tenant_id, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM connection_requests
                    WHERE tenant_id = ?
                      AND (buyer_id = ? OR target_supplier_id = ?)
                    ORDER BY requested_at DESC
                    LIMIT ?
                    """,
                    (tenant_id, organization_id, organization_id, safe_limit),
                ).fetchall()
        return [dict(row) for row in rows]


class SupplyMapRegistrationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        context: RequestContext,
        organization_name: str,
        stakeholder_role: str,
        province: str,
        category: str,
        scale: str,
        contact_email: str,
        intended_relationships: list[str],
        data_boundary: str,
        policy_decision_id: str | None,
    ) -> dict[str, Any]:
        registration_id = f"REG-{uuid4().hex[:12].upper()}"
        submitted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        linked_business_id = context.organization_id if context.organization_id.startswith("BIZ-") else None
        map_visibility = "masked_pending_consent" if linked_business_id else "not_on_map"
        advisory_notice = "Submitted for human review; no unmasked graph access is granted by submission alone."
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT INTO supply_map_registrations (
                  registration_id, tenant_id, organization_id, organization_name, requested_by,
                  stakeholder_role, province, category, scale, contact_email, intended_relationships_json,
                  data_boundary, status, review_status, map_visibility, linked_business_id,
                  submitted_at, reviewed_at, reviewer_note, policy_decision_id, audit_event_id, advisory_notice
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', 'in_review', ?, ?, ?, NULL, NULL, ?, NULL, ?)
                """,
                (
                    registration_id,
                    context.tenant_id,
                    context.organization_id,
                    organization_name,
                    context.actor_id,
                    stakeholder_role,
                    province,
                    category,
                    scale,
                    contact_email,
                    json.dumps(intended_relationships, ensure_ascii=False),
                    data_boundary,
                    map_visibility,
                    linked_business_id,
                    submitted_at,
                    policy_decision_id,
                    advisory_notice,
                ),
            )
            connection.commit()
        return self.get(registration_id) or {}

    def list_visible(
        self,
        *,
        tenant_id: str,
        organization_id: str,
        include_review_queue: bool,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with closing(self.database.connect()) as connection:
            if include_review_queue:
                rows = connection.execute(
                    """
                    SELECT * FROM supply_map_registrations
                    WHERE tenant_id = ?
                    ORDER BY submitted_at DESC
                    LIMIT ?
                    """,
                    (tenant_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM supply_map_registrations
                    WHERE tenant_id = ? AND (organization_id = ? OR linked_business_id = ?)
                    ORDER BY submitted_at DESC
                    LIMIT ?
                    """,
                    (tenant_id, organization_id, organization_id, limit),
                ).fetchall()
        return [self._to_api(row) for row in rows]

    def get(self, registration_id: str) -> dict[str, Any] | None:
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM supply_map_registrations WHERE registration_id = ?",
                (registration_id,),
            ).fetchone()
        return self._to_api(row) if row else None

    def decide(
        self,
        *,
        registration_id: str,
        decision: str,
        note: str | None,
        policy_decision_id: str | None,
    ) -> dict[str, Any] | None:
        current = self.get(registration_id)
        if current is None:
            return None
        status = "approved" if decision == "approve" else "rejected" if decision == "reject" else "changes_requested"
        linked_business_id = current.get("linkedBusinessId")
        if status == "approved" and not linked_business_id:
            linked_business_id = f"BIZ-ONB-{uuid4().hex[:8].upper()}"
        map_visibility = "visible_demo_node" if status == "approved" else "masked_pending_consent" if linked_business_id else "not_on_map"
        advisory_notice = (
            "Approved for demo map visibility; unmasked commercial data still requires consent."
            if status == "approved"
            else "Review decision recorded; membership is not active until requirements are satisfied."
        )
        reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                UPDATE supply_map_registrations
                SET status = ?,
                    review_status = ?,
                    map_visibility = ?,
                    linked_business_id = ?,
                    reviewed_at = ?,
                    reviewer_note = ?,
                    policy_decision_id = ?,
                    advisory_notice = ?
                WHERE registration_id = ?
                """,
                (
                    status,
                    "approved" if status == "approved" else "rejected" if status == "rejected" else "changes_requested",
                    map_visibility,
                    linked_business_id,
                    reviewed_at,
                    note,
                    policy_decision_id,
                    advisory_notice,
                    registration_id,
                ),
            )
            connection.commit()
        return self.get(registration_id)

    def set_audit_event(self, registration_id: str, audit_event_id: str) -> dict[str, Any] | None:
        with closing(self.database.connect()) as connection:
            connection.execute(
                "UPDATE supply_map_registrations SET audit_event_id = ? WHERE registration_id = ?",
                (audit_event_id, registration_id),
            )
            connection.commit()
        return self.get(registration_id)

    def materialize_approved_business(self, registration_id: str) -> dict[str, Any] | None:
        current = self.get(registration_id)
        if current is None or current["status"] != "approved" or not current.get("linkedBusinessId"):
            return current
        business_id = current["linkedBusinessId"]
        organization_id = current["organizationId"]
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        lat, lng = _demo_coordinates_for_province(current["province"])
        metrics = _onboarding_demo_metrics(current["stakeholderRole"], current["scale"], current["category"])
        advisory_notice = "Approved and materialized as a demo supply-map node; commercial edges and unmasked data still require consent or contract evidence."
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO businesses (
                  business_id, name, type, industry, product_category, province, lat, lng, scale,
                  monthly_revenue, capacity, financial_health_score, supply_risk_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    business_id,
                    current["organizationName"],
                    current["stakeholderRole"],
                    "Synthetic onboarding profile",
                    current["category"],
                    current["province"],
                    lat,
                    lng,
                    current["scale"],
                    metrics["monthly_revenue"],
                    metrics["capacity"],
                    metrics["financial_health_score"],
                    metrics["supply_risk_score"],
                ),
            )
            existing_org = connection.execute(
                "SELECT organization_id, external_business_id FROM organizations WHERE organization_id = ?",
                (organization_id,),
            ).fetchone()
            if existing_org is None:
                connection.execute(
                    """
                    INSERT INTO organizations (
                      organization_id, tenant_id, external_business_id, name, organization_type, status
                    )
                    VALUES (?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        organization_id,
                        current["tenant_id"] or "tenant-demo",
                        business_id,
                        current["organizationName"],
                        current["stakeholderRole"],
                    ),
                )
            elif not existing_org["external_business_id"]:
                connection.execute(
                    """
                    UPDATE organizations
                    SET external_business_id = ?,
                        name = ?,
                        organization_type = ?,
                        status = 'active'
                    WHERE organization_id = ?
                    """,
                    (business_id, current["organizationName"], current["stakeholderRole"], organization_id),
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO business_profiles (
                  profile_id, tenant_id, organization_id, legal_name, trade_name, business_type,
                  industry, product_category, tax_registration_status, scale, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_demo_kyb', ?, 'active', ?, ?)
                """,
                (
                    f"PROF-{organization_id}",
                    current["tenant_id"] or "tenant-demo",
                    organization_id,
                    current["organizationName"],
                    current["organizationName"],
                    current["stakeholderRole"],
                    "Synthetic onboarding profile",
                    current["category"],
                    current["scale"],
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO facilities (
                  facility_id, tenant_id, organization_id, facility_type, province, address, lat, lng, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    f"FAC-{organization_id}-PRIMARY",
                    current["tenant_id"] or "tenant-demo",
                    organization_id,
                    current["stakeholderRole"],
                    current["province"],
                    f"Onboarding supplied {current['province']} operating site",
                    lat,
                    lng,
                ),
            )
            connection.execute(
                """
                UPDATE supply_map_registrations
                SET advisory_notice = ?
                WHERE registration_id = ?
                """,
                (advisory_notice, registration_id),
            )
            connection.commit()
        return self.get(registration_id)

    def _to_api(self, row: Any) -> dict[str, Any]:
        item = dict(row)
        try:
            intended_relationships = json.loads(item.get("intended_relationships_json") or "[]")
        except json.JSONDecodeError:
            intended_relationships = []
        return {
            "id": item["registration_id"],
            "registration_id": item["registration_id"],
            "tenant_id": item.get("tenant_id"),
            "organizationId": item["organization_id"],
            "organization_id": item["organization_id"],
            "organizationName": item["organization_name"],
            "organization_name": item["organization_name"],
            "requestedBy": item["requested_by"],
            "requested_by": item["requested_by"],
            "stakeholderRole": item["stakeholder_role"],
            "stakeholder_role": item["stakeholder_role"],
            "province": item["province"],
            "category": item["category"],
            "scale": item["scale"],
            "contactEmail": item["contact_email"],
            "contact_email": item["contact_email"],
            "intendedRelationships": intended_relationships,
            "intended_relationships": intended_relationships,
            "dataBoundary": item["data_boundary"],
            "data_boundary": item["data_boundary"],
            "status": item["status"],
            "reviewStatus": item["review_status"],
            "review_status": item["review_status"],
            "mapVisibility": item["map_visibility"],
            "map_visibility": item["map_visibility"],
            "linkedBusinessId": item.get("linked_business_id"),
            "linked_business_id": item.get("linked_business_id"),
            "submittedAt": item["submitted_at"],
            "submitted_at": item["submitted_at"],
            "reviewedAt": item.get("reviewed_at"),
            "reviewed_at": item.get("reviewed_at"),
            "reviewerNote": item.get("reviewer_note"),
            "reviewer_note": item.get("reviewer_note"),
            "policyDecisionId": item.get("policy_decision_id"),
            "policy_decision_id": item.get("policy_decision_id"),
            "auditEventId": item.get("audit_event_id"),
            "audit_event_id": item.get("audit_event_id"),
            "advisoryNotice": item["advisory_notice"],
            "advisory_notice": item["advisory_notice"],
        }
