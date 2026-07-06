from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ShockSimulationRequest(BaseModel):
    shock_business_id: str = "BIZ-005"
    product_category: str = "beverage"
    inventory_coverage_days: int = Field(default=5, ge=0, le=365)


class SupplierRecommendationRequest(BaseModel):
    buyer_id: str
    disrupted_supplier_id: str = "BIZ-005"
    period_key: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    product_category: str = "beverage"
    product_specification: str | None = None
    required_monthly_volume: int = Field(default=10_000, gt=0)
    preferred_payment_term_days: int = Field(default=30, ge=0, le=365)
    max_lead_time_days: int = Field(default=4, gt=0, le=365)
    top_k: int = Field(default=3, ge=1, le=10)


class ConnectionRequestCreate(BaseModel):
    buyer_id: str
    target_supplier_id: str
    disrupted_supplier_id: str | None = "BIZ-005"
    purpose: str = Field(default="alternative_supplier_review", min_length=3, max_length=120)


class ConnectionRequestDecisionCreate(BaseModel):
    decision: Literal["grant_consent", "reject", "request_changes", "activate_relationship"]
    note: str | None = Field(default=None, max_length=500)
    contract_evidence_id: str | None = Field(default=None, max_length=120)


class SupplyMapRegistrationCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=180)
    stakeholder_role: Literal["manufacturer", "distributor", "wholesaler", "retailer", "logistics_partner", "financial_partner"]
    province: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=2, max_length=80)
    scale: str = Field(min_length=2, max_length=80)
    contact_email: str = Field(min_length=5, max_length=180)
    intended_relationships: list[str] = Field(default_factory=list, max_length=12)
    data_boundary: str = Field(min_length=3, max_length=240)


class SupplyMapRegistrationDecisionCreate(BaseModel):
    decision: Literal["approve", "reject", "request_changes"]
    note: str | None = Field(default=None, max_length=500)


class DataSubmissionCreate(BaseModel):
    business_id: str | None = None
    organization_id: str | None = None
    period_key: str = Field(pattern=r"^\d{4}-\d{2}$")
    source: Literal["manual", "csv"] = "manual"
    sections: dict[str, Any] | None = None


class DataSubmissionPatch(BaseModel):
    sections: dict[str, Any] = Field(default_factory=dict)


class CsvImportBatchCreate(BaseModel):
    submission_id: str | None = None
    business_id: str | None = None
    organization_id: str | None = None
    period_key: str = Field(pattern=r"^\d{4}-\d{2}$")
    dataset: Literal["financials", "products", "evidence"]
    file_name: str = Field(min_length=3, max_length=180)
    csv_text: str = Field(min_length=1)


class ReviewDecisionCreate(BaseModel):
    decision: Literal["approve", "reject", "request_changes"]
    note: str | None = Field(default=None, max_length=500)


class ConsentCreate(BaseModel):
    subject_id: str
    recipient_id: str
    scope: str = Field(min_length=3, max_length=120)
    purpose: str = Field(min_length=3, max_length=120)
    legal_basis: str = Field(default="contract_or_explicit_consent", min_length=3, max_length=160)
    expires_at: str | None = None
    evidence_reference: str | None = Field(default=None, max_length=240)


class EvidenceUploadUrlCreate(BaseModel):
    organization_id: str
    file_name: str = Field(min_length=3, max_length=180)
    document_type: Literal["CERTIFICATION", "GUARANTEE", "INVOICE", "PURCHASE_ORDER", "DELIVERY_NOTE", "CONTRACT"] = "CERTIFICATION"
    period_key: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    content_type: str = Field(default="application/octet-stream", min_length=3, max_length=120)
    byte_size: int = Field(gt=0, le=50_000_000)
    classification: Literal["public", "partner_visible", "confidential", "restricted_financial"] = "confidential"
    purpose: str = Field(default="evidence_intake", min_length=3, max_length=120)


class EvidenceVersionCreate(BaseModel):
    organization_id: str
    object_key: str = Field(min_length=3, max_length=500)
    document_hash: str = Field(min_length=16, max_length=128)
    content_type: str = Field(default="application/octet-stream", min_length=3, max_length=120)
    byte_size: int = Field(gt=0, le=50_000_000)
    malware_scan_status: Literal["pending_scan", "clean", "infected", "failed"] = "pending_scan"
    supersedes_version_id: str | None = None


class EvidenceUploadCompleteCreate(BaseModel):
    organization_id: str
    document_hash: str = Field(min_length=16, max_length=128)
    malware_scan_status: Literal["pending_scan", "clean", "infected", "failed"] = "pending_scan"
    title: str | None = Field(default=None, max_length=180)
    content_base64: str | None = Field(default=None, max_length=70_000_000)


class EvidenceAccessGrantCreate(BaseModel):
    organization_id: str
    grantee_organization_id: str
    scope: Literal["evidence_review", "invoice_claim", "financial_summary", "audit_support"] = "evidence_review"
    purpose: str = Field(min_length=3, max_length=120)
    expires_at: str | None = None


class EvidenceRetentionUpdate(BaseModel):
    organization_id: str
    retention_status: Literal["active", "retention_locked", "scheduled_delete", "deleted"]
    legal_hold: bool = False
    reason: str = Field(min_length=3, max_length=240)


class EvidenceScanResultCreate(BaseModel):
    organization_id: str
    malware_scan_status: Literal["clean", "infected", "failed"]
    scanner_name: str = Field(min_length=2, max_length=120)
    scanner_version: str | None = Field(default=None, max_length=80)
    scanned_at: str | None = None
    details: str | None = Field(default=None, max_length=500)


class EvidenceScanJobCreate(BaseModel):
    organization_id: str
    period_key: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    limit: int = Field(default=20, ge=1, le=100)
    scanner: Literal["local_demo", "fail_closed"] = "local_demo"
    dry_run: bool = False


class InvoiceClaimCreate(BaseModel):
    seller_id: str
    buyer_id: str
    financier_id: str
    invoice_hash: str = Field(min_length=16, max_length=128)
    amount: int = Field(gt=0)
    due_date: str
    invoice_id: str | None = None
    issue_date: str | None = None
    currency: str = Field(default="VND", min_length=3, max_length=3)
    idempotency_key: str | None = Field(default=None, max_length=120)
    source_evidence_id: str | None = Field(default=None, max_length=120)


class InvoiceClaimTransitionCreate(BaseModel):
    status: Literal["verified", "pledged", "financed", "released", "disputed"]
    note: str | None = Field(default=None, max_length=500)
