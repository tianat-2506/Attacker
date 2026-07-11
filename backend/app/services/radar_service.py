from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import uuid4

from backend.app.domain.invoice_verification import double_financing_alert, invoice_hash
from backend.app.domain.risk_scoring import calculate_business_risk
from backend.app.domain.shock_simulation import simulate_shock
from backend.app.domain.supplier_matching import rank_suppliers
from backend.app.services.access_control import AccessDeniedError, PolicyDecision, PolicyService, RequestContext
from backend.app.services.config import get_settings
from backend.app.services.database import Database, ensure_database
from backend.app.services.governance_service import GovernanceService
from backend.app.services.intake_service import PeriodicIntakeService
from backend.app.services.postgres_pilot_service import PostgresPilotService
from backend.app.services.repositories import (
    AccessPolicyRepository,
    AuditRepository,
    BusinessRepository,
    ConnectionRequestRepository,
    EvidenceRepository,
    FinancialRepository,
    InvoiceRepository,
    ProductRepository,
    SupplyEdgeRepository,
    SupplyMapRegistrationRepository,
)


class NotFoundError(KeyError):
    pass


def _context(context: RequestContext | None) -> RequestContext:
    return context or RequestContext.demo()


def _month_key(value: Any) -> str | None:
    text = str(value or "")
    return text[:7] if len(text) >= 7 and text[4:5] == "-" else None


def _matches_period_window(item: dict[str, Any], period_key: str | None) -> bool:
    if not period_key:
        return True
    item_period = _month_key(item.get("period_key"))
    if item_period:
        return item_period == period_key
    effective_month = _month_key(item.get("effective_date"))
    expiry_month = _month_key(item.get("expiry_date"))
    if effective_month and effective_month > period_key:
        return False
    if expiry_month and expiry_month < period_key:
        return False
    return True


DENIED_RESOURCE_EVENTS = {
    "read_business": "BUSINESS_DETAIL_READ_DENIED",
    "read_evidence": "EVIDENCE_READ_DENIED",
    "read_financials": "FINANCIALS_READ_DENIED",
    "read_invoice": "INVOICE_READ_DENIED",
    "read_risk_run": "RISK_SIGNAL_READ_DENIED",
}


class VietSupplyRadarService:
    def __init__(
        self,
        businesses: BusinessRepository,
        edges: SupplyEdgeRepository,
        financials: FinancialRepository,
        products: ProductRepository,
        invoices: InvoiceRepository,
        audit: AuditRepository,
        intake: PeriodicIntakeService,
        evidence: EvidenceRepository,
        connection_requests: ConnectionRequestRepository,
        supply_map_registrations: SupplyMapRegistrationRepository,
        governance: GovernanceService,
        access_policy: AccessPolicyRepository,
    ) -> None:
        self.businesses = businesses
        self.edges = edges
        self.financials = financials
        self.products = products
        self.invoices = invoices
        self.audit = audit
        self.intake = intake
        self.evidence = evidence
        self.connection_requests = connection_requests
        self.supply_map_registrations = supply_map_registrations
        self.governance = governance
        self.access_policy = access_policy

    def overview_payload(self) -> dict[str, Any]:
        businesses = self.businesses.list_all()
        edges = self.edges.list_all()
        active_companies = len(businesses)
        at_risk_nodes = len([business for business in businesses if business.supply_risk_score >= 70])
        supply_health = round(sum(business.financial_health_score for business in businesses) / max(1, active_companies))
        monthly_volume = sum(edge.monthly_volume for edge in edges)
        return {
            "active_companies": active_companies,
            "at_risk_nodes": at_risk_nodes,
            "affected_smes": 0,
            "supply_health_score": supply_health,
            "monthly_network_volume": monthly_volume,
            "advisory_notice": "Decision-support signal only; commercial and financial actions require consent and human approval.",
        }

    def _require_resource_access(
        self,
        action: str,
        context: RequestContext,
        *,
        resource_type: str,
        resource_id: str | None,
        resource_organization_id: str | None,
        data_classification: str,
        consent_scope: str | None = None,
        allow_relationship: bool = False,
        denied_event_type: str | None = None,
    ) -> Any:
        external_allowed = False
        if (
            resource_organization_id
            and resource_organization_id not in context.organization_ids
            and not context.is_demo_actor()
        ):
            if consent_scope:
                external_allowed = self.access_policy.has_active_consent(
                    tenant_id=context.tenant_id,
                    subject_id=resource_organization_id,
                    recipient_ids=context.organization_ids,
                    scope=consent_scope,
                    purpose=context.purpose,
                )
            if not external_allowed and allow_relationship:
                external_allowed = self.access_policy.has_active_relationship(
                    tenant_id=context.tenant_id,
                    subject_id=resource_organization_id,
                    actor_organization_ids=context.organization_ids,
                )
        decision = PolicyService.decide(
            action,
            context,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_organization_id=resource_organization_id,
            data_classification=data_classification,
            external_access_allowed=external_allowed,
        )
        if decision.effect != "allow":
            self.audit.record_policy_decision(context, decision)
            self.audit.record_context(
                denied_event_type or DENIED_RESOURCE_EVENTS.get(action, "RESOURCE_ACCESS_DENIED"),
                context,
                resource_id or resource_organization_id or resource_type,
                policy_decision=decision,
                payload={
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "resource_organization_id": resource_organization_id,
                    "data_classification": data_classification,
                    "reason": decision.reason,
                },
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        return decision

    @staticmethod
    def _access_scope_for_context(context: RequestContext, resource_organization_id: str | None) -> str:
        if context.has_role("demo_operator", "demo_admin", "system_admin"):
            return "platform_demo_scope" if context.app_mode == "demo" else "platform_admin_scope"
        if resource_organization_id and resource_organization_id in context.organization_ids:
            return "own_organization"
        return "consented_external"

    def dashboard_payload(self) -> dict[str, Any]:
        businesses = self.businesses.list_all()
        edges = self.edges.list_all()
        by_id = {business.business_id: business for business in businesses}
        regional_flow: dict[str, int] = {}
        for edge in edges:
            source = by_id.get(edge.source_id)
            if source:
                regional_flow[source.province] = regional_flow.get(source.province, 0) + edge.monthly_volume
        total_flow = sum(regional_flow.values()) or 1
        risky = sorted(businesses, key=lambda item: item.supply_risk_score, reverse=True)[:5]
        return {
            "overview": self.overview_payload(),
            "disruption_trend": [
                {"month": "Dec", "total": 18, "high_critical": 4},
                {"month": "Jan", "total": 23, "high_critical": 6},
                {"month": "Feb", "total": 21, "high_critical": 5},
                {"month": "Mar", "total": 31, "high_critical": 8},
                {"month": "Apr", "total": 27, "high_critical": 6},
                {"month": "May", "total": 24, "high_critical": 7},
            ],
            "regional_flow": [
                {
                    "region": province,
                    "volume": volume,
                    "share": round(volume / total_flow * 100, 1),
                }
                for province, volume in sorted(regional_flow.items(), key=lambda item: item[1], reverse=True)
            ],
            "recent_alerts": [
                {
                    "id": "ALT-001",
                    "severity": "high",
                    "title": "Delivery risk signal at Dai Tin Distribution",
                    "detail": "3 reviewed purchase-order records exceeded the contracted delivery SLA.",
                    "age": "27 min",
                    "business_id": "BIZ-005",
                },
                {
                    "id": "ALT-002",
                    "severity": "medium",
                    "title": "Certificate expiry window",
                    "detail": "HACCP evidence enters the 30-day review window.",
                    "age": "1 hr",
                    "business_id": "BIZ-005",
                },
                {
                    "id": "ALT-003",
                    "severity": "medium",
                    "title": "Negative operating cash-flow trend",
                    "detail": "Three consecutive demo snapshots show cash out above cash in.",
                    "age": "3 hr",
                    "business_id": "BIZ-005",
                },
                {
                    "id": "ALT-004",
                    "severity": "info",
                    "title": "Alternative supplier pilot signal",
                    "detail": "An Phu FMCG Hub completed one on-time sample delivery.",
                    "age": "5 hr",
                    "business_id": "BIZ-007",
                },
            ],
            "risky_businesses": [business.to_api_node(masked=False) for business in risky],
            "data_scope": "Synthetic demonstration dataset; business relationships and risk signals are not claims about real companies.",
        }

    def scenario_payload(self) -> dict[str, Any]:
        scenario_ids = [
            "BIZ-002",
            "BIZ-005",
            "BIZ-007",
            "BIZ-009",
            "BIZ-011",
            "BIZ-013",
            "BIZ-017",
            "BIZ-022",
            "BIZ-061",
            "BIZ-062",
        ]
        business_map = {business.business_id: business for business in self.businesses.list_all()}
        nodes = [business_map[business_id].to_api_node(masked=False) for business_id in scenario_ids]
        edges = [
            edge.to_api_edge()
            for edge in self.edges.list_all()
            if edge.source_id in scenario_ids and edge.target_id in scenario_ids
        ]
        edges.extend(
            [
                {
                    "id": "REL-LOG-001",
                    "edge_id": "REL-LOG-001",
                    "sourceId": "BIZ-017",
                    "targetId": "BIZ-005",
                    "source_id": "BIZ-017",
                    "target_id": "BIZ-005",
                    "product": "Cold-chain delivery evidence",
                    "category": "logistics",
                    "product_category": "logistics",
                    "volume": 12_700,
                    "monthly_volume": 12_700,
                    "leadTimeDays": 1,
                    "lead_time_days": 1,
                    "transport_cost": 8_400_000,
                    "reliability": 0.94,
                    "payment_term_days": 15,
                    "relation_type": "logistics",
                },
                {
                    "id": "REL-GUA-001",
                    "edge_id": "REL-GUA-001",
                    "sourceId": "BIZ-061",
                    "targetId": "BIZ-005",
                    "source_id": "BIZ-061",
                    "target_id": "BIZ-005",
                    "product": "Performance guarantee",
                    "category": "finance",
                    "product_category": "finance",
                    "volume": 0,
                    "monthly_volume": 0,
                    "leadTimeDays": 0,
                    "lead_time_days": 0,
                    "transport_cost": 0,
                    "reliability": 1.0,
                    "payment_term_days": 0,
                    "relation_type": "guarantee",
                },
                {
                    "id": "REL-FIN-001",
                    "edge_id": "REL-FIN-001",
                    "sourceId": "BIZ-062",
                    "targetId": "BIZ-009",
                    "source_id": "BIZ-062",
                    "target_id": "BIZ-009",
                    "product": "Invoice verification channel",
                    "category": "finance",
                    "product_category": "finance",
                    "volume": 0,
                    "monthly_volume": 0,
                    "leadTimeDays": 0,
                    "lead_time_days": 0,
                    "transport_cost": 0,
                    "reliability": 1.0,
                    "payment_term_days": 0,
                    "relation_type": "finance",
                },
            ]
        )
        return {
            "scenario_id": "DEMO-BEVERAGE-BD-01",
            "name": "Binh Duong beverage disruption",
            "nodes": nodes,
            "edges": edges,
            "role_coverage": {
                "supplier": ["BIZ-002", "BIZ-007", "BIZ-013"],
                "distributor": ["BIZ-005", "BIZ-022"],
                "sme": ["BIZ-009", "BIZ-011"],
                "logistics": ["BIZ-017"],
                "finance": ["BIZ-061", "BIZ-062"],
            },
            "node_count": len(nodes),
            "data_scope": "All names, relationships, documents and risk events in this scenario are synthetic.",
        }

    def _authorize_graph_access(
        self,
        *,
        masked: bool,
        context: RequestContext,
        denied_event_type: str,
    ) -> tuple[bool, PolicyDecision]:
        action = "read_graph" if masked else "unmask_graph"
        decision = PolicyService.decide(
            action,
            context,
            resource_type="commercial_graph",
            resource_id="network",
            data_classification="confidential" if masked else "restricted_commercial",
        )
        self.audit.record_policy_decision(context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                denied_event_type,
                context,
                "commercial_graph",
                policy_decision=decision,
                payload={"masked": masked, "reason": decision.reason},
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        return masked, decision

    def _require_unmasked_graph_basis(
        self,
        context: RequestContext,
        *,
        denied_event_type: str,
    ) -> None:
        if context.is_demo_actor():
            return
        has_network_basis = self.access_policy.has_any_active_relationship(
            tenant_id=context.tenant_id,
            actor_organization_ids=context.organization_ids,
        )
        has_network_consent = self.access_policy.has_active_consent(
            tenant_id=context.tenant_id,
            subject_id=context.organization_id,
            recipient_ids=context.organization_ids,
            scope="commercial_graph",
            purpose=context.purpose,
        )
        if has_network_basis or has_network_consent:
            return
        decision = PolicyService.deny_decision(
            "unmask_graph",
            "Unmasked commercial graph requires an active relationship or consent basis.",
            resource_type="commercial_graph",
            resource_id="network",
            data_classification="restricted_commercial",
        )
        self.audit.record_policy_decision(context, decision)
        self.audit.record_context(
            denied_event_type,
            context,
            "commercial_graph",
            policy_decision=decision,
            payload={"masked": False, "reason": decision.reason},
        )
        raise AccessDeniedError("COMMERCIAL_GRAPH_RELATIONSHIP_REQUIRED", decision.reason)

    def businesses_payload(self, masked: bool = True, context: RequestContext | None = None) -> list[dict[str, Any]]:
        active_context = _context(context)
        effective_masked, decision = self._authorize_graph_access(
            masked=masked,
            context=active_context,
            denied_event_type="BUSINESS_ROSTER_READ_DENIED" if masked else "BUSINESS_ROSTER_UNMASK_DENIED",
        )
        if not effective_masked:
            self._require_unmasked_graph_basis(active_context, denied_event_type="BUSINESS_ROSTER_UNMASK_DENIED")
        self.audit.record_context(
            "BUSINESS_ROSTER_VIEWED" if effective_masked else "BUSINESS_ROSTER_UNMASKED_VIEWED",
            active_context,
            "commercial_graph",
            policy_decision=decision,
            payload={"masked": effective_masked},
        )
        return [business.to_api_node(masked=effective_masked) for business in self.businesses.list_all()]

    def graph_payload(self, masked: bool = True, context: RequestContext | None = None) -> dict[str, Any]:
        active_context = _context(context)
        effective_masked, decision = self._authorize_graph_access(
            masked=masked,
            context=active_context,
            denied_event_type="COMMERCIAL_GRAPH_READ_DENIED" if masked else "COMMERCIAL_GRAPH_UNMASK_DENIED",
        )
        if not effective_masked:
            self._require_unmasked_graph_basis(active_context, denied_event_type="COMMERCIAL_GRAPH_UNMASK_DENIED")
        event_id = self.audit.record_context(
            "COMMERCIAL_GRAPH_VIEWED" if effective_masked else "COMMERCIAL_GRAPH_UNMASKED_VIEWED",
            active_context,
            "commercial_graph",
            policy_decision=decision,
            payload={"masked": effective_masked},
        )
        nodes = [business.to_api_node(masked=effective_masked) for business in self.businesses.list_all()]
        edges = [edge.to_api_edge(masked=effective_masked) for edge in self.edges.list_all()]
        return {
            "nodes": nodes,
            "edges": edges,
            "access": {
                "masked": effective_masked,
                "tenant_id": active_context.tenant_id,
                "actor_id": active_context.actor_id,
                "purpose": active_context.purpose,
                "policy_decision_id": decision.decision_id,
                "audit_event_id": event_id,
            },
        }

    def business_detail_payload(self, business_id: str, context: RequestContext | None = None, period_key: str | None = None) -> dict[str, Any]:
        active_context = _context(context)
        decision = self._require_resource_access(
            "read_business",
            active_context,
            resource_type="business",
            resource_id=business_id,
            resource_organization_id=business_id,
            data_classification="confidential",
            consent_scope="business_profile",
            allow_relationship=True,
        )
        self.audit.record_policy_decision(active_context, decision)
        business = self.businesses.get(business_id)
        if business is None:
            raise NotFoundError(business_id)

        financial_rows = [row.to_domain() for row in self.financials.for_business(business_id)]
        if period_key:
            risk_financial_rows = [row for row in financial_rows if _month_key(row.get("month")) and str(row["month"]) <= period_key]
            financial_summary = next((row for row in financial_rows if row.get("month") == period_key), None)
        else:
            risk_financial_rows = financial_rows
            financial_summary = financial_rows[-1] if financial_rows else None
        edge_rows = [edge.to_domain() for edge in self.edges.list_all()]
        risk = calculate_business_risk(business_id, risk_financial_rows, edge_rows, business.product_category)
        downstream = self.edges.outgoing(business_id)
        evidence_groups = self.evidence.all_for_business(business_id)
        filtered_evidence_groups: dict[str, list[dict[str, Any]]] = {}
        evidence_date_fields = {
            "contracts": ("effective_date", "expiry_date"),
            "purchase_orders": ("order_date", "expected_delivery_date"),
            "delivery_notes": ("delivery_date", None),
            "certifications": ("effective_date", "expiry_date"),
            "guarantees": ("effective_date", "expiry_date"),
            "evidence_documents": ("valid_from", "valid_to"),
        }
        for group_name, rows in evidence_groups.items():
            start_field, end_field = evidence_date_fields[group_name]
            filtered_evidence_groups[group_name] = [
                row for row in rows
                if _matches_period_window(
                    {
                        "effective_date": row.get(start_field),
                        "expiry_date": row.get(end_field) if end_field else None,
                        "period_key": row.get("period_key"),
                    },
                    period_key,
                )
            ]
        self.audit.record_context(
            "BUSINESS_DETAIL_VIEWED",
            active_context,
            business_id,
            policy_decision=decision,
        )
        return {
            "business": business.to_api_node(masked=False),
            "products": [product.to_domain() for product in self.products.for_business(business_id)],
            "risk": {
                "score": risk.score,
                "level": risk.level,
                "formula_version": risk.formula_version,
                "drivers": [asdict(driver) for driver in risk.drivers],
                "explanation": risk.explanation,
                "advisory_notice": "Supply Risk Signal only; not credit approval, default probability or legal breach finding.",
            },
            "financial_summary": financial_summary,
            "dependency_summary": {
                "downstream_business_count": len({edge.target_id for edge in downstream}),
                "monthly_volume_supplied": sum(edge.monthly_volume for edge in downstream),
            },
            "evidence_summary": {
                "total": sum(len(rows) for rows in filtered_evidence_groups.values()),
                "by_type": {name: len(rows) for name, rows in filtered_evidence_groups.items()},
                "verified": sum(
                    1
                    for rows in filtered_evidence_groups.values()
                    for row in rows
                    if row.get("verification_status") == "VERIFIED" or row.get("status") == "VERIFIED"
                ),
            },
            "period_key": period_key,
            "advisory_notice": (
                f"Selected period {period_key}; financial summary requires an exact month match and evidence is filtered by validity window."
                if period_key
                else "Latest synthetic profile context."
            ),
        }

    def evidence_payload(self, business_id: str, context: RequestContext | None = None, period_key: str | None = None) -> dict[str, Any]:
        active_context = _context(context)
        decision = self._require_resource_access(
            "read_evidence",
            active_context,
            resource_type="evidence",
            resource_id=business_id,
            resource_organization_id=business_id,
            data_classification="confidential",
            consent_scope="evidence_review",
        )
        self.audit.record_policy_decision(active_context, decision)
        if self.businesses.get(business_id) is None:
            raise NotFoundError(business_id)
        groups = self.evidence.all_for_business(business_id)
        documents: list[dict[str, Any]] = []
        for row in groups["contracts"]:
            documents.append(
                {
                    "id": row["contract_id"],
                    "type": "CONTRACT",
                    "title": f"Supply contract {row['contract_id']}",
                    "status": row["status"],
                    "verification_status": row["verification_status"],
                    "effective_date": row["effective_date"],
                    "expiry_date": row["expiry_date"],
                    "source": row["source_label"],
                    "hash": row["document_hash"],
                    "facts": [
                        f"Net {row['payment_term_days']} payment term",
                        f"{row['sla_lead_time_days']}-day delivery SLA",
                        "Backup supplier clause present" if row["has_backup_supplier_clause"] else "No backup supplier clause recorded",
                    ],
                }
            )
        for row in groups["purchase_orders"]:
            documents.append(
                {
                    "id": row["po_id"],
                    "type": "PURCHASE_ORDER",
                    "title": f"Purchase order {row['po_id']}",
                    "status": row["status"],
                    "verification_status": row["verification_status"],
                    "effective_date": row["order_date"],
                    "expiry_date": row["expected_delivery_date"],
                    "source": "Synthetic procurement register",
                    "hash": row["document_hash"],
                    "facts": [
                        f"Quantity {row['quantity']:,}",
                        f"Value VND {row['value']:,}",
                        f"Expected {row['expected_delivery_date']}",
                    ],
                }
            )
        for row in groups["delivery_notes"]:
            documents.append(
                {
                    "id": row["delivery_note_id"],
                    "type": "DELIVERY_NOTE",
                    "title": f"Delivery note {row['delivery_note_id']}",
                    "status": row["status"],
                    "verification_status": "VERIFIED" if row["verified_by_buyer"] and row["logistics_confirmed"] else "PENDING_REVIEW",
                    "effective_date": row["delivery_date"],
                    "expiry_date": None,
                    "source": "Buyer and logistics confirmations",
                    "hash": row["document_hash"],
                    "facts": [
                        f"Linked PO {row['po_id']}",
                        f"Delivered {row['delivered_quantity']:,}",
                        f"Delay {row['delay_days']} days",
                    ],
                }
            )
        for row in groups["certifications"]:
            documents.append(
                {
                    "id": row["certification_id"],
                    "type": "CERTIFICATION",
                    "title": row["certification_type"],
                    "status": row["status"],
                    "verification_status": row["verification_status"],
                    "effective_date": row["effective_date"],
                    "expiry_date": row["expiry_date"],
                    "source": row["issuer"],
                    "hash": row["document_hash"],
                    "facts": [f"Issuer {row['issuer']}", f"Expires {row['expiry_date']}"],
                }
            )
        for row in groups["guarantees"]:
            documents.append(
                {
                    "id": row["guarantee_id"],
                    "type": "GUARANTEE",
                    "title": row["guarantee_type"].replace("_", " ").title(),
                    "status": row["status"],
                    "verification_status": row["verification_status"],
                    "effective_date": row["effective_date"],
                    "expiry_date": row["expiry_date"],
                    "source": f"Issuer {row['issuer_id']}",
                    "hash": row["document_hash"],
                    "facts": [f"Amount VND {row['amount']:,}", f"Beneficiary {row['beneficiary_id']}"],
                }
            )
        for row in groups["evidence_documents"]:
            scan_status = row["malware_scan_status"]
            retention_status = str(row.get("retention_status") or "active")
            retired = retention_status in {"scheduled_delete", "deleted"}
            if retired:
                verification_status = "REJECTED"
            elif scan_status == "clean":
                verification_status = "VERIFIED"
            elif scan_status in {"infected", "failed"}:
                verification_status = "REJECTED"
            else:
                verification_status = "PENDING_REVIEW"
            documents.append(
                {
                    "id": row["evidence_document_id"],
                    "type": row["document_type"],
                    "title": row["title"],
                    "status": row["retention_status"].upper(),
                    "verification_status": verification_status,
                    "effective_date": row["valid_from"],
                    "expiry_date": row["valid_to"],
                    "period_key": row.get("period_key"),
                    "source": "Evidence intake upload ticket",
                    "hash": row["document_hash"],
                    "evidence_version_id": row.get("latest_evidence_version_id"),
                    "downloadable": scan_status == "clean" and not retired and bool(row.get("latest_evidence_version_id")),
                    "facts": [
                        f"Classification {row['classification']}",
                        f"Malware scan {scan_status}",
                        f"Retention {retention_status}",
                        f"Content type {row['content_type']}",
                    ],
                }
            )
        invoices = [
            invoice.to_domain()
            for invoice in self.invoices.list_all()
            if invoice.seller_id == business_id or invoice.buyer_id == business_id
        ]
        for row in invoices:
            documents.append(
                {
                    "id": row["invoice_id"],
                    "type": "INVOICE",
                    "title": f"E-invoice {row['invoice_id']}",
                    "status": row["funding_status"].upper(),
                    "verification_status": "VERIFIED" if "buyer" in row["confirmed_by"] and "seller" in row["confirmed_by"] else "PENDING_REVIEW",
                    "effective_date": row["issue_date"],
                    "expiry_date": row["due_date"],
                    "source": "Synthetic e-invoice register",
                    "hash": row["invoice_hash"],
                    "facts": [f"Amount VND {row['amount']:,}", f"Confirmed by {row['confirmed_by']}"] ,
                }
            )
        self.audit.record_context(
            "EVIDENCE_VAULT_VIEWED",
            active_context,
            business_id,
            policy_decision=decision,
        )
        documents = [item for item in documents if _matches_period_window(item, period_key)]
        documents.sort(key=lambda item: (item["effective_date"] or ""), reverse=True)
        return {
            "business_id": business_id,
            "period_key": period_key,
            "documents": documents,
            "summary": {
                "total": len(documents),
                "verified": len([item for item in documents if item["verification_status"] == "VERIFIED"]),
                "needs_review": len([item for item in documents if item["verification_status"] != "VERIFIED"]),
            },
            "data_scope": (
                f"Evidence is filtered for selected period {period_key} by validity window or upload period; synthetic demo only."
                if period_key
                else "Evidence is synthetic and demonstrates provenance, integrity and access-control patterns only."
            ),
        }

    def risk_signal_payload(self, business_id: str, context: RequestContext | None = None, period_key: str | None = None) -> dict[str, Any]:
        active_context = _context(context)
        decision = self._require_resource_access(
            "read_risk_run",
            active_context,
            resource_type="risk_signal",
            resource_id=business_id,
            resource_organization_id=business_id,
            data_classification="partner_visible",
            consent_scope="risk_signal",
            allow_relationship=True,
            denied_event_type="RISK_SIGNAL_READ_DENIED",
        )
        self.audit.record_policy_decision(active_context, decision)
        business = self.businesses.get(business_id)
        if business is None:
            raise NotFoundError(business_id)
        evidence_scope = "linked_evidence_visible"
        try:
            evidence = self.evidence_payload(business_id, context=active_context, period_key=period_key)["documents"]
        except AccessDeniedError:
            evidence_scope = "evidence_blocked_by_policy"
            evidence = []
        if evidence_scope == "evidence_blocked_by_policy":
            score = business.supply_risk_score
            level = "HIGH" if score >= 70 else "MEDIUM" if score >= 40 else "LOW"
            event_id = self.audit.record_context(
                "RISK_SIGNAL_VIEWED",
                active_context,
                business_id,
                policy_decision=decision,
                payload={"period_key": period_key, "evidence_scope": evidence_scope},
            )
            return {
                "signal_id": f"RISK-{business_id}-HIGH-LEVEL",
                "business_id": business_id,
                "period_key": period_key,
                "risk_type": "HIGH_LEVEL_SUPPLY_RISK",
                "level": level,
                "confidence": 52,
                "summary": "High-level supply risk indicator is visible, but linked evidence and commercial details are blocked by policy for this account.",
                "triggers": [
                    {
                        "rule": "Supply risk band",
                        "observed": score,
                        "threshold": 70,
                        "result": "triggered" if score >= 70 else "not_triggered",
                    }
                ],
                "evidence_ids": [],
                "evidence": [],
                "suggested_actions": [
                    "Request consented evidence access before operational decisions.",
                    "Use this as a review prompt only; do not treat it as a legal or finance conclusion.",
                    "Escalate to a reviewer when supplier introduction or financial action is required.",
                ],
                "formula_version": "risk-signal-rules-v1.1",
                "policy_decision_id": decision.decision_id,
                "audit_event_id": event_id,
                "evidence_scope": evidence_scope,
                "disclaimer": (
                    f"Advisory high-level signal for selected period {period_key}; linked evidence is not visible under this account scope. It is not a legal breach finding, credit decision or instruction to replace a supplier."
                    if period_key
                    else "Advisory high-level signal; linked evidence is not visible under this account scope. It is not a legal breach finding, credit decision or instruction to replace a supplier."
                ),
            }
        late_orders = [item for item in evidence if item["type"] == "PURCHASE_ORDER" and "LATE" in item["status"]]
        overdue_orders = [item for item in evidence if item["type"] == "PURCHASE_ORDER" and "OVERDUE" in item["status"]]
        delayed_notes = [
            item
            for item in evidence
            if item["type"] == "DELIVERY_NOTE" and any(fact.startswith("Delay ") and fact != "Delay 0 days" for fact in item["facts"])
        ]
        expiring_certificates = [item for item in evidence if item["type"] == "CERTIFICATION" and item["status"] == "EXPIRING_SOON"]
        evidence_ids = [item["id"] for item in late_orders + overdue_orders + delayed_notes + expiring_certificates]
        event_id = self.audit.record_context(
            "RISK_SIGNAL_VIEWED",
            active_context,
            business_id,
            policy_decision=decision,
            payload={"period_key": period_key, "evidence_scope": evidence_scope},
        )
        return {
            "signal_id": f"RISK-{business_id}-DELIVERY",
            "business_id": business_id,
            "period_key": period_key,
            "risk_type": "DELIVERY_AND_COMPLIANCE",
            "level": "HIGH" if len(late_orders) >= 3 else "MEDIUM",
            "confidence": 86 if len(late_orders) >= 3 else 67,
            "summary": f"{len(late_orders)} delivered orders exceeded SLA; {len(overdue_orders)} order remains overdue and {len(expiring_certificates)} certificate needs review.",
            "triggers": [
                {"rule": "Late PO in rolling review window", "observed": len(late_orders), "threshold": 3, "result": "triggered" if len(late_orders) >= 3 else "not_triggered"},
                {"rule": "Overdue in-transit PO", "observed": len(overdue_orders), "threshold": 1, "result": "triggered" if overdue_orders else "not_triggered"},
                {"rule": "Certificate expires within review window", "observed": len(expiring_certificates), "threshold": 1, "result": "triggered" if expiring_certificates else "not_triggered"},
            ],
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "evidence": [item for item in evidence if item["id"] in evidence_ids],
            "suggested_actions": [
                "Request updated delivery status and supporting documents.",
                "Review qualified alternative suppliers and contract constraints.",
                "Require a human approver before any commercial action.",
            ],
            "formula_version": "risk-signal-rules-v1.1",
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "evidence_scope": evidence_scope,
            "disclaimer": (
                f"Advisory signal for selected period {period_key} based on synthetic evidence. It is not a legal breach finding, credit decision or instruction to replace a supplier."
                if period_key
                else "Advisory signal based on synthetic evidence. It is not a legal breach finding, credit decision or instruction to replace a supplier."
            ),
        }

    def finance_payload(self, business_id: str) -> dict[str, Any]:
        return self.finance_payload_for_context(business_id, RequestContext.demo())

    def finance_payload_for_context(self, business_id: str, context: RequestContext | None = None, period_key: str | None = None) -> dict[str, Any]:
        active_context = _context(context)
        decision = self._require_resource_access(
            "read_financials",
            active_context,
            resource_type="financials",
            resource_id=business_id,
            resource_organization_id=business_id,
            data_classification="restricted_financial",
            consent_scope="financial_summary",
        )
        self.audit.record_policy_decision(active_context, decision)
        business = self.businesses.get(business_id)
        if business is None:
            raise NotFoundError(business_id)
        snapshots = [row.to_domain() for row in self.financials.for_business(business_id)]
        series = []
        for row in snapshots:
            revenue = max(1, row["revenue"])
            net_cash_flow = row["cash_in"] - row["cash_out"]
            series.append(
                {
                    **row,
                    "net_cash_flow": net_cash_flow,
                    "working_capital": row["accounts_receivable"] + row["inventory_value"] - row["accounts_payable"],
                    "cashflow_margin": round(net_cash_flow / revenue * 100, 1),
                    "receivable_days_proxy": round(row["accounts_receivable"] / revenue * 30, 1),
                    "inventory_days_proxy": round(row["inventory_value"] / revenue * 30, 1),
                    "debt_to_monthly_revenue": round(row["debt"] / revenue, 2),
                }
            )
        if period_key:
            visible_series = [row for row in series if row.get("month") <= period_key]
            latest = next((row for row in series if row.get("month") == period_key), None)
            previous_candidates = [row for row in series if row.get("month") < period_key]
            previous = previous_candidates[-1] if previous_candidates else None
        else:
            visible_series = series
            latest = series[-1] if series else None
            previous = series[-2] if len(series) > 1 else latest
        cashflow_component = max(0, min(100, 50 + (latest["cashflow_margin"] if latest else 0) * 2))
        payment_component = max(0, round(100 - (latest["late_payment_rate"] if latest else 0) * 220))
        delivery_component = max(0, round(100 - (latest["delivery_delay_rate"] if latest else 0) * 250))
        leverage_component = max(0, round(100 - (latest["debt_to_monthly_revenue"] if latest else 0) * 80))
        components = {
            "operating_cashflow": round(cashflow_component),
            "payment_discipline": payment_component,
            "delivery_reliability": delivery_component,
            "leverage_pressure": leverage_component,
        }
        if period_key and latest is None:
            components = {key: 0 for key in components}
        health = round(sum(components.values()) / len(components))
        return {
            "business": business.to_api_node(masked=False),
            "health": {
                "score": health,
                "level": "no_period_data" if period_key and latest is None else "watch" if health < 60 else "stable" if health < 80 else "strong",
                "components": components,
                "formula_version": "financial-health-v1.0-demo",
                "explanation": "Weighted operational indicators from cash flow, payment delays, delivery delays and debt pressure; not a regulated credit score.",
            },
            "latest": latest,
            "previous": previous,
            "series": visible_series,
            "access_scope": self._access_scope_for_context(active_context, business_id),
            "data_scope": "restricted_financial",
            "period_key": period_key,
            "advisory_notice": (
                f"Synthetic management indicators for selected period {period_key}. No exact month row means no latest period snapshot is returned; independent financial and legal review is required."
                if period_key
                else "Synthetic management indicators only. Lenders and businesses must perform independent financial and legal review."
            ),
            "policy_decision_id": decision.decision_id,
        }

    def connection_request_payload(
        self,
        buyer_id: str,
        target_supplier_id: str,
        disrupted_supplier_id: str | None,
        purpose: str,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        active_context = _context(context)
        if self.businesses.get(buyer_id) is None:
            raise NotFoundError(buyer_id)
        if self.businesses.get(target_supplier_id) is None:
            raise NotFoundError(target_supplier_id)
        decision = PolicyService.decide(
            "create_connection_request",
            active_context,
            resource_type="connection_request",
            resource_id=target_supplier_id,
            resource_organization_id=buyer_id,
            data_classification="partner_visible",
            external_access_allowed=True,
        )
        if (
            decision.effect == "allow"
            and buyer_id not in active_context.organization_ids
            and not active_context.has_role("demo_admin", "demo_operator", "system_admin")
        ):
            decision = PolicyService.deny_decision(
                "create_connection_request",
                "Connection requests must be created by the buyer organization or platform operations.",
                resource_type="connection_request",
                resource_id=target_supplier_id,
                data_classification="partner_visible",
            )
        self.audit.record_policy_decision(active_context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                "CONNECTION_REQUEST_CREATE_DENIED",
                active_context,
                target_supplier_id,
                policy_decision=decision,
                payload={"buyer_id": buyer_id, "target_supplier_id": target_supplier_id},
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        request = self.connection_requests.create(
            tenant_id=active_context.tenant_id,
            buyer_id=buyer_id,
            target_supplier_id=target_supplier_id,
            disrupted_supplier_id=disrupted_supplier_id,
            purpose=purpose,
            requester_id=active_context.actor_id,
        )
        event_id = self.audit.record_context(
            "CONNECTION_REQUEST_CREATED",
            active_context,
            target_supplier_id,
            policy_decision=decision,
            payload={"buyer_id": buyer_id, "target_supplier_id": target_supplier_id},
        )
        persisted = self.connection_requests.set_audit_event(request["request_id"], event_id, decision.decision_id) or request
        return {
            **persisted,
            "audit_event_id": event_id,
            "policy_decision_id": decision.decision_id,
            "next_step": "Supplier consent and commercial review are required before contact details are released.",
            "advisory_notice": "This request does not amend a contract, move an order or commit either business.",
        }

    def connection_requests_payload(self, context: RequestContext | None = None, limit: int = 100) -> dict[str, Any]:
        active_context = _context(context)
        decision = PolicyService.decide(
            "read_connection_request",
            active_context,
            resource_type="connection_request",
            resource_id=active_context.organization_id,
            resource_organization_id=active_context.organization_id,
            data_classification="partner_visible",
        )
        self.audit.record_policy_decision(active_context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                "CONNECTION_REQUESTS_READ_DENIED",
                active_context,
                active_context.organization_id,
                policy_decision=decision,
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        include_review_queue = active_context.has_role("demo_admin", "demo_operator", "reviewer", "system_admin")
        requests = self.connection_requests.list_visible(
            tenant_id=active_context.tenant_id,
            organization_id=active_context.organization_id,
            include_review_queue=include_review_queue,
            limit=limit,
        )
        event_id = self.audit.record_context(
            "CONNECTION_REQUESTS_VIEWED",
            active_context,
            active_context.organization_id,
            policy_decision=decision,
            payload={"count": len(requests), "scope": "review_queue" if include_review_queue else "own_organization"},
        )
        return {
            "connection_requests": requests,
            "scope": "review_queue" if include_review_queue else "own_organization",
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Connection requests are consent and contract-gated; they do not create supply relationships by themselves.",
        }

    def decide_connection_request_payload(
        self,
        *,
        request_id: str,
        decision_value: str,
        note: str | None,
        contract_evidence_id: str | None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        active_context = _context(context)
        existing = self.connection_requests.get(request_id)
        if existing is None:
            raise NotFoundError(request_id)
        if (existing.get("tenant_id") or "tenant-demo") != active_context.tenant_id:
            raise NotFoundError(request_id)
        resource_organization_id = existing["target_supplier_id"] if decision_value != "activate_relationship" else existing["buyer_id"]
        decision = PolicyService.decide(
            "decide_connection_request",
            active_context,
            resource_type="connection_request",
            resource_id=request_id,
            resource_organization_id=resource_organization_id,
            data_classification="partner_visible",
            external_access_allowed=active_context.has_role("demo_admin", "demo_operator", "reviewer", "system_admin"),
        )
        explicit_denial: str | None = None
        if decision.effect == "allow" and decision_value in {"grant_consent", "reject"}:
            if (
                existing["target_supplier_id"] not in active_context.organization_ids
                and not active_context.has_role("demo_admin", "demo_operator", "system_admin")
            ):
                explicit_denial = "Supplier consent decisions must be made by the target supplier organization or platform operations."
        if decision.effect == "allow" and decision_value == "request_changes":
            if (
                existing["target_supplier_id"] not in active_context.organization_ids
                and not active_context.has_role("demo_admin", "demo_operator", "reviewer", "system_admin")
            ):
                explicit_denial = "Change requests require supplier, reviewer, or platform operations context."
        if decision.effect == "allow" and decision_value == "activate_relationship":
            if not active_context.has_role("demo_admin", "demo_operator", "reviewer", "system_admin"):
                explicit_denial = "Relationship activation requires reviewer or platform operations approval."
            elif existing["consent_status"] != "supplier_consented":
                raise ValueError("Supplier consent is required before a relationship can be activated.")
            elif not contract_evidence_id:
                raise ValueError("contract_evidence_id is required to activate a supply relationship.")
        if decision.effect == "allow" and decision_value == "grant_consent" and existing["consent_status"] not in {"awaiting_supplier_consent", "changes_requested"}:
            raise ValueError("Supplier consent can only be granted for pending or changes-requested connection requests.")
        if decision.effect == "allow" and decision_value in {"reject", "request_changes"} and existing["status"] == "relationship_active":
            raise ValueError("Active relationship requests cannot be changed through this workflow.")
        if decision.effect == "allow" and existing["status"] == "relationship_active" and decision_value != "activate_relationship":
            raise ValueError("Active relationship requests cannot be changed through this workflow.")
        if explicit_denial:
            decision = PolicyService.deny_decision(
                "decide_connection_request",
                explicit_denial,
                resource_type="connection_request",
                resource_id=request_id,
                data_classification="partner_visible",
            )
        self.audit.record_policy_decision(active_context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                "CONNECTION_REQUEST_DECISION_DENIED",
                active_context,
                request_id,
                policy_decision=decision,
                payload={"decision": decision_value, "buyer_id": existing["buyer_id"], "target_supplier_id": existing["target_supplier_id"]},
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        consent_id: str | None = None
        if decision_value == "grant_consent":
            consent = self.governance.create_consent(
                subject_id=existing["target_supplier_id"],
                recipient_id=existing["buyer_id"],
                scope="supplier_introduction",
                purpose=existing["purpose"],
                legal_basis="supplier_explicit_consent",
                expires_at=None,
                evidence_reference=None,
                context=active_context,
            )
            consent_id = consent["consent_id"]
        updated = self.connection_requests.decide(
            request_id=request_id,
            decision=decision_value,
            actor_id=active_context.actor_id,
            note=note,
            contract_evidence_id=contract_evidence_id,
            policy_decision_id=decision.decision_id,
        )
        if updated is None:
            raise NotFoundError(request_id)
        event_id = self.audit.record_context(
            "CONNECTION_REQUEST_DECIDED",
            active_context,
            request_id,
            policy_decision=decision,
            payload={
                "decision": decision_value,
                "buyer_id": existing["buyer_id"],
                "target_supplier_id": existing["target_supplier_id"],
                "contract_evidence_id": contract_evidence_id,
                "relationship_id": updated.get("relationship_id"),
                "relationship_edge_id": updated.get("relationship_edge_id"),
                "consent_id": consent_id,
            },
        )
        updated = self.connection_requests.set_audit_event(request_id, event_id, decision.decision_id) or updated
        next_steps = {
            "supplier_consented": "Contract evidence and reviewer approval are required before a supply relationship edge is created.",
            "supplier_rejected": "No relationship or contact release is allowed unless a new request is submitted.",
            "changes_requested": "Requester must resolve supplier/reviewer changes before consent can be granted.",
            "contract_evidence_recorded": "Relationship basis recorded; the demo graph edge is visible but commercial terms remain masked unless policy allows unmasking.",
        }
        return {
            **updated,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "next_step": next_steps.get(updated["consent_status"], "Human review is required before downstream use."),
            "advisory_notice": (
                "Connection workflow records consent and contract evidence for decision support only; it does not "
                "amend contracts, verify legal enforceability, or automatically replace suppliers."
            ),
        }

    def supply_map_registrations_payload(self, context: RequestContext | None = None) -> dict[str, Any]:
        active_context = _context(context)
        decision = PolicyService.decide(
            "read_supply_map_registration",
            active_context,
            resource_type="supply_map_registration",
            resource_id=active_context.organization_id,
            data_classification="partner_visible",
        )
        self.audit.record_policy_decision(active_context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                "SUPPLY_MAP_REGISTRATIONS_READ_DENIED",
                active_context,
                active_context.organization_id,
                policy_decision=decision,
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        include_review_queue = active_context.has_role("demo_admin", "demo_operator", "reviewer", "system_admin")
        registrations = self.supply_map_registrations.list_visible(
            tenant_id=active_context.tenant_id,
            organization_id=active_context.organization_id,
            include_review_queue=include_review_queue,
        )
        event_id = self.audit.record_context(
            "SUPPLY_MAP_REGISTRATIONS_VIEWED",
            active_context,
            active_context.organization_id,
            policy_decision=decision,
            payload={"count": len(registrations), "scope": "review_queue" if include_review_queue else "own_organization"},
        )
        return {
            "registrations": registrations,
            "scope": "review_queue" if include_review_queue else "own_organization",
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Supply map membership is review-gated and does not grant unmasked commercial data access.",
        }

    def create_supply_map_registration_payload(
        self,
        *,
        organization_name: str,
        stakeholder_role: str,
        province: str,
        category: str,
        scale: str,
        contact_email: str,
        intended_relationships: list[str],
        data_boundary: str,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        active_context = _context(context)
        decision = PolicyService.decide(
            "create_supply_map_registration",
            active_context,
            resource_type="supply_map_registration",
            resource_id=active_context.organization_id,
            resource_organization_id=active_context.organization_id,
            data_classification="partner_visible",
        )
        self.audit.record_policy_decision(active_context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                "SUPPLY_MAP_REGISTRATION_CREATE_DENIED",
                active_context,
                active_context.organization_id,
                policy_decision=decision,
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        registration = self.supply_map_registrations.create(
            context=active_context,
            organization_name=organization_name,
            stakeholder_role=stakeholder_role,
            province=province,
            category=category,
            scale=scale,
            contact_email=contact_email,
            intended_relationships=intended_relationships,
            data_boundary=data_boundary,
            policy_decision_id=decision.decision_id,
        )
        event_id = self.audit.record_context(
            "SUPPLY_MAP_REGISTRATION_SUBMITTED",
            active_context,
            registration["id"],
            policy_decision=decision,
            payload={"organization_id": registration["organizationId"], "stakeholder_role": registration["stakeholderRole"]},
        )
        return self.supply_map_registrations.set_audit_event(registration["id"], event_id) or registration

    def decide_supply_map_registration_payload(
        self,
        *,
        registration_id: str,
        decision_value: str,
        note: str | None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        active_context = _context(context)
        existing = self.supply_map_registrations.get(registration_id)
        if existing is None:
            raise NotFoundError(registration_id)
        decision = PolicyService.decide(
            "review_supply_map_registration",
            active_context,
            resource_type="supply_map_registration",
            resource_id=registration_id,
            resource_organization_id=existing["organizationId"],
            data_classification="partner_visible",
            external_access_allowed=True,
        )
        self.audit.record_policy_decision(active_context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                "SUPPLY_MAP_REGISTRATION_REVIEW_DENIED",
                active_context,
                registration_id,
                policy_decision=decision,
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        registration = self.supply_map_registrations.decide(
            registration_id=registration_id,
            decision=decision_value,
            note=note,
            policy_decision_id=decision.decision_id,
        )
        if registration is None:
            raise NotFoundError(registration_id)
        if decision_value == "approve":
            registration = self.supply_map_registrations.materialize_approved_business(registration_id) or registration
        event_id = self.audit.record_context(
            "SUPPLY_MAP_REGISTRATION_REVIEWED",
            active_context,
            registration_id,
            policy_decision=decision,
            payload={"decision": decision_value, "organization_id": registration["organizationId"]},
        )
        return self.supply_map_registrations.set_audit_event(registration_id, event_id) or registration

    def audit_payload(self, context: RequestContext | None = None) -> dict[str, Any]:
        active_context = _context(context)
        decision = PolicyService.decide(
            "read_audit",
            active_context,
            resource_type="audit_log",
            resource_id=active_context.tenant_id,
            data_classification="restricted_audit",
        )
        self.audit.record_policy_decision(active_context, decision)
        if decision.effect != "allow":
            self.audit.record_context(
                "AUDIT_TRAIL_READ_DENIED",
                active_context,
                active_context.tenant_id,
                policy_decision=decision,
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        event_id = self.audit.record_context(
            "AUDIT_TRAIL_VIEWED",
            active_context,
            active_context.tenant_id,
            policy_decision=decision,
        )
        return {
            "events": self.audit.list_recent(),
            "connection_requests": self.connection_requests.list_recent(),
            "data_scope": "Demo audit trail; production records require immutable retention controls and role-based access.",
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
        }

    def shock_payload(
        self,
        shock_business_id: str = "BIZ-005",
        product_category: str = "beverage",
        inventory_coverage_days: int = 5,
        period_key: str | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        active_context = _context(context)
        decision = PolicyService.decide(
            "simulate_shock",
            active_context,
            resource_type="supply_shock_scenario",
            resource_id=shock_business_id,
            resource_organization_id=shock_business_id,
            data_classification="partner_visible",
            external_access_allowed=True,
        )
        if decision.effect != "allow":
            self.audit.record_policy_decision(active_context, decision)
            self.audit.record_context(
                "SUPPLY_SHOCK_SIMULATION_DENIED",
                active_context,
                shock_business_id,
                policy_decision=decision,
                payload={
                    "action": "simulate_shock",
                    "period_key": period_key,
                    "product_category": product_category,
                    "reason": decision.reason,
                },
            )
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        self.audit.record_policy_decision(active_context, decision)
        businesses = {business.business_id: business.to_domain() for business in self.businesses.list_all()}
        edges = [edge.to_domain() for edge in self.edges.list_all()]
        result = simulate_shock(shock_business_id, businesses, edges, product_category, inventory_coverage_days)
        event_id = self.audit.record_context(
            "SUPPLY_SHOCK_SIMULATED",
            active_context,
            shock_business_id,
            policy_decision=decision,
            payload={
                "period_key": period_key,
                "product_category": product_category,
                "inventory_coverage_days": inventory_coverage_days,
                "result_source": "current_demo_graph" if active_context.app_mode == "demo" else "current_commercial_graph",
            },
        )
        payload = asdict(result)
        payload.update(
            {
                "period_key": period_key,
                "scenario_run_id": f"SCN-{uuid4().hex[:12].upper()}",
                "ruleset_version": "shock-rules-v1.0",
                "model_version": "deterministic-adjacency-v1.0",
                "policy_decision_id": decision.decision_id,
                "audit_event_id": event_id,
                "result_source": "current_demo_graph" if active_context.app_mode == "demo" else "current_commercial_graph",
                "advisory_notice": "Hypothetical decision-support scenario only; it is not a forecast, legal finding, credit assessment or automatic supplier replacement instruction.",
            }
        )
        return payload

    def recommendations_payload(
        self,
        buyer_id: str,
        disrupted_supplier_id: str = "BIZ-005",
        period_key: str | None = None,
        product_category: str = "beverage",
        product_specification: str | None = None,
        required_monthly_volume: int = 10_000,
        preferred_payment_term_days: int = 30,
        max_lead_time_days: int = 4,
        top_k: int = 3,
        context: RequestContext | None = None,
    ) -> list[dict[str, Any]]:
        active_context = _context(context)
        business_map = {business.business_id: business.to_domain() for business in self.businesses.list_all()}
        if buyer_id not in business_map:
            raise NotFoundError(buyer_id)
        results = rank_suppliers(
            buyer_id=buyer_id,
            disrupted_supplier_id=disrupted_supplier_id,
            product_category=product_category,
            product_specification=product_specification,
            required_monthly_volume=required_monthly_volume,
            preferred_payment_term_days=preferred_payment_term_days,
            max_lead_time_days=max_lead_time_days,
            top_k=top_k,
            businesses=business_map,
            products=[product.to_domain() for product in self.products.list_all()],
            edges=[edge.to_domain() for edge in self.edges.list_all()],
        )
        self.audit.record(
            "SUPPLIER_SHORTLIST_GENERATED",
            active_context.actor_role,
            buyer_id,
            active_context.purpose,
            actor_id=active_context.actor_id,
            payload={"period_key": period_key, "disrupted_supplier_id": disrupted_supplier_id},
        )
        return [
            {
                **asdict(result),
                "period_key": period_key,
                "advisory_notice": (
                    f"Suggested alternative for selected period {period_key} only; contact reveal and commercial action require mutual consent and human approval."
                    if period_key
                    else "Suggested alternative only; contact reveal and commercial action require mutual consent and human approval."
                ),
            }
            for result in results
        ]

    def invoice_payload(self, invoice_id: str, context: RequestContext | None = None) -> dict[str, Any]:
        active_context = _context(context)
        invoice = self.invoices.get(invoice_id)
        if invoice is None:
            raise NotFoundError(invoice_id)
        if invoice.seller_id in active_context.organization_ids:
            resource_organization_id = invoice.seller_id
            access_scope = "seller_party"
        elif invoice.buyer_id in active_context.organization_ids:
            resource_organization_id = invoice.buyer_id
            access_scope = "buyer_party"
        elif active_context.has_role("demo_operator", "demo_admin", "system_admin"):
            resource_organization_id = invoice.seller_id
            access_scope = "platform_demo_scope" if active_context.app_mode == "demo" else "platform_admin_scope"
        else:
            resource_organization_id = invoice.seller_id
            access_scope = "consented_external"
        decision = self._require_resource_access(
            "read_invoice",
            active_context,
            resource_type="invoice",
            resource_id=invoice_id,
            resource_organization_id=resource_organization_id,
            data_classification="restricted_financial",
            consent_scope="invoice_claim",
        )
        self.audit.record_policy_decision(active_context, decision)
        invoice_row = invoice.to_domain()
        existing = [row.to_domain() for row in self.invoices.list_all() if row.invoice_id != invoice_id]
        computed_hash = invoice_hash(invoice_row)
        payload = {
            **invoice_row,
            "computed_hash": computed_hash,
            "double_financing_alert": double_financing_alert(invoice_row, existing),
            "access_scope": access_scope,
            "data_scope": "restricted_financial",
            "policy_decision_id": decision.decision_id,
            "advisory_notice": "Hash match is a registry signal; raw invoice authenticity still requires buyer/seller confirmation and partner review.",
        }
        self.audit.record_context(
            "INVOICE_VERIFICATION_VIEWED",
            active_context,
            invoice_id,
            policy_decision=decision,
        )
        return payload


def create_service(database: Database | None = None) -> VietSupplyRadarService | PostgresPilotService:
    if database is None:
        settings = get_settings()
        settings.validate_runtime()
        if settings.database_engine == "postgresql":
            return PostgresPilotService(settings.database_url, settings.app_mode)
        if settings.database_engine != "sqlite":
            raise RuntimeError("Unsupported DATABASE_URL engine.")
        db = ensure_database(settings.sqlite_path)
    else:
        db = database
    audit = AuditRepository(db)
    access_policy = AccessPolicyRepository(db)
    governance = GovernanceService(db, audit, access_policy)
    return VietSupplyRadarService(
        businesses=BusinessRepository(db),
        edges=SupplyEdgeRepository(db),
        financials=FinancialRepository(db),
        products=ProductRepository(db),
        invoices=InvoiceRepository(db),
        audit=audit,
        intake=PeriodicIntakeService(db, audit),
        evidence=EvidenceRepository(db),
        connection_requests=ConnectionRequestRepository(db),
        supply_map_registrations=SupplyMapRegistrationRepository(db),
        governance=governance,
        access_policy=access_policy,
    )
