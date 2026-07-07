from __future__ import annotations

from typing import Any

from backend.app.schemas import (
    ConnectionRequestCreate,
    ConnectionRequestDecisionCreate,
    ConsentCreate,
    CsvImportBatchCreate,
    DataSubmissionCreate,
    DataSubmissionPatch,
    EvidenceAccessGrantCreate,
    EvidenceRetentionUpdate,
    EvidenceScanJobCreate,
    EvidenceScanResultCreate,
    EvidenceUploadCompleteCreate,
    EvidenceUploadUrlCreate,
    EvidenceVersionCreate,
    InvoiceClaimCreate,
    InvoiceClaimTransitionCreate,
    ReviewDecisionCreate,
    ShockSimulationRequest,
    SupplyMapRegistrationCreate,
    SupplyMapRegistrationDecisionCreate,
    SupplierRecommendationRequest,
)
from backend.app.services.access_control import AccessDeniedError, PolicyService, RequestContext, context_from_headers
from backend.app.services.config import get_settings
from backend.app.services.evidence_workers import EvidenceWorkerService
from backend.app.services.governance_service import EvidenceUploadValidationError
from backend.app.services.intake_service import IntakeNotFoundError
from backend.app.services.postgres_pilot_service import PilotFeatureUnavailableError
from backend.app.services.radar_service import NotFoundError, create_service


try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:  # Domain tests can run before FastAPI is installed.
    Depends = None  # type: ignore[assignment]
    FastAPI = None  # type: ignore[assignment]
    Header = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]
    CORSMiddleware = None  # type: ignore[assignment]


SETTINGS = get_settings()
SETTINGS.validate_runtime()
SERVICE = create_service()


def business_detail_payload(business_id: str, context: RequestContext | None = None) -> dict[str, Any]:
    return SERVICE.business_detail_payload(business_id, context=context)


def graph_payload(masked: bool = True, context: RequestContext | None = None) -> dict[str, Any]:
    return SERVICE.graph_payload(masked=masked, context=context)


if FastAPI is not None:
    app = FastAPI(title="VietSupply Radar API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AccessDeniedError)
    async def access_denied_handler(request: Request, exc: AccessDeniedError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": str(exc), "path": str(request.url.path)}},
        )

    @app.exception_handler(PilotFeatureUnavailableError)
    async def pilot_feature_unavailable_handler(request: Request, exc: PilotFeatureUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": exc.code,
                    "message": str(exc),
                    "feature": exc.feature,
                    "path": str(request.url.path),
                }
            },
        )

    def request_context(
        authorization: str | None = Header(default=None, alias="Authorization"),
        tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
        organization_id: str | None = Header(default=None, alias="X-Organization-Id"),
        actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
        actor_role: str | None = Header(default=None, alias="X-Actor-Role"),
        purpose: str | None = Header(default=None, alias="X-Purpose"),
        scopes: str | None = Header(default=None, alias="X-Demo-Scopes"),
        request_id: str | None = Header(default=None, alias="X-Request-Id"),
    ) -> RequestContext:
        try:
            return context_from_headers(
                authorization=authorization,
                tenant_id=tenant_id,
                organization_id=organization_id,
                actor_id=actor_id,
                actor_role=actor_role,
                purpose=purpose,
                scopes=scopes,
                request_id=request_id,
                app_mode=SETTINGS.app_mode,
            )
        except AccessDeniedError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    def raise_access_denied(exc: AccessDeniedError) -> None:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    def intake_not_found(exc: IntakeNotFoundError) -> None:
        raise HTTPException(status_code=404, detail={"code": "INTAKE_RESOURCE_NOT_FOUND", "id": str(exc)}) from exc

    def organization_from_payload(value: str | None, fallback: str | None) -> str:
        organization_id = value or fallback
        if not organization_id:
            raise HTTPException(status_code=422, detail={"code": "ORGANIZATION_REQUIRED"})
        return organization_id

    def evidence_worker_database():
        intake = getattr(SERVICE, "intake", None)
        database = getattr(intake, "database", None)
        if database is None:
            raise PilotFeatureUnavailableError("evidence_scan_job")
        return database

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        service_health = SERVICE.health_payload() if hasattr(SERVICE, "health_payload") else {}
        return {
            "data": {
                "status": "ok",
                "database": SETTINGS.database_engine,
                "app_mode": SETTINGS.app_mode,
                "adapter_status": service_health.get("adapter_status", "sqlite_demo"),
            },
            "meta": {
                "demo_headers_allowed": SETTINGS.allow_demo_headers and SETTINGS.is_demo,
                "production_database_required": not SETTINGS.is_demo,
                "migration_revisions": service_health.get("migration_revisions", []),
            },
            "errors": [],
        }

    @app.get("/api/v1/auth/me")
    def auth_me(context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        return {"data": SERVICE.governance.auth_me(context), "meta": {"request_id": context.request_id}, "errors": []}

    @app.get("/api/v1/overview")
    def overview(context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        return {"data": SERVICE.overview_payload(), "meta": {"request_id": context.request_id}, "errors": []}

    @app.get("/api/v1/dashboard")
    def dashboard(context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        return {"data": SERVICE.dashboard_payload(), "meta": {"request_id": context.request_id}, "errors": []}

    @app.get("/api/v1/demo/scenario")
    def demo_scenario(context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        payload = SERVICE.scenario_payload()
        return {"data": payload, "meta": {"node_count": payload["node_count"], "request_id": context.request_id}, "errors": []}

    @app.get("/api/v1/businesses")
    def businesses(masked: bool = True, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            payload = SERVICE.businesses_payload(masked=masked, context=context)
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        return {"data": payload, "meta": {"count": len(payload)}, "errors": []}

    @app.get("/api/v1/businesses/{business_id}")
    def business_detail(business_id: str, period: str | None = None, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": business_detail_payload(business_id, context=context, period_key=period), "meta": {"period_key": period}, "errors": []}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND", "field": "business_id"}) from exc

    @app.get("/api/v1/businesses/{business_id}/evidence")
    def business_evidence(business_id: str, period: str | None = None, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.evidence_payload(business_id, context=context, period_key=period), "meta": {"period_key": period}, "errors": []}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND", "field": "business_id"}) from exc

    @app.get("/api/v1/businesses/{business_id}/risk-signal")
    def business_risk_signal(business_id: str, period: str | None = None, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.risk_signal_payload(business_id, context=context, period_key=period), "meta": {"period_key": period}, "errors": []}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND", "field": "business_id"}) from exc

    @app.get("/api/v1/businesses/{business_id}/finance")
    def business_finance(business_id: str, period: str | None = None, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.finance_payload_for_context(business_id, context=context, period_key=period), "meta": {"period_key": period}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND", "field": "business_id"}) from exc

    @app.get("/api/v1/periods")
    def periods(
        organization_id: str | None = None,
        business_id: str | None = None,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        active_organization_id = organization_from_payload(organization_id, business_id)
        return {
            "data": SERVICE.intake.list_periods(active_organization_id, context=context),
            "meta": {"organization_id": active_organization_id, "actor_id": context.actor_id},
            "errors": [],
        }

    @app.post("/api/v1/data-submissions", status_code=201)
    def create_data_submission(
        request: DataSubmissionCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            organization_id = organization_from_payload(request.organization_id, request.business_id)
            payload = SERVICE.intake.create_submission(
                organization_id=organization_id,
                period_key=request.period_key,
                source_type=request.source,
                sections=request.sections,
                context=context,
            )
            return {"data": payload, "meta": {}, "errors": []}
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.get("/api/v1/data-submissions/{submission_id}")
    def data_submission(submission_id: str, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.intake.get_submission(submission_id, context=context), "meta": {"actor_id": context.actor_id}, "errors": []}
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.patch("/api/v1/data-submissions/{submission_id}")
    def update_data_submission(
        submission_id: str,
        request: DataSubmissionPatch,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {"data": SERVICE.intake.update_submission(submission_id, request.sections, context), "meta": {}, "errors": []}
        except IntakeNotFoundError as exc:
            intake_not_found(exc)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "SUBMISSION_LOCKED", "message": str(exc)}) from exc

    @app.post("/api/v1/import-batches", status_code=201)
    def create_import_batch(
        request: CsvImportBatchCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            organization_id = organization_from_payload(request.organization_id, request.business_id)
            payload = SERVICE.intake.create_import_batch(
                organization_id=organization_id,
                period_key=request.period_key,
                dataset=request.dataset,
                file_name=request.file_name,
                csv_text=request.csv_text,
                context=context,
                submission_id=request.submission_id,
            )
            return {"data": payload, "meta": {}, "errors": []}
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/data-submissions/{submission_id}/validate")
    def validate_data_submission(submission_id: str, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.intake.validate_submission(submission_id, context), "meta": {}, "errors": []}
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.get("/api/v1/data-submissions/{submission_id}/error-report")
    def data_submission_error_report(
        submission_id: str,
        format: str = "json",
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        if format not in {"json", "csv"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_REPORT_FORMAT", "message": "format must be json or csv"})
        try:
            return {"data": SERVICE.intake.error_report(submission_id, context, report_format=format), "meta": {}, "errors": []}
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/data-submissions/{submission_id}/submit")
    def submit_data_submission(submission_id: str, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.intake.submit_submission(submission_id, context), "meta": {}, "errors": []}
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.get("/api/v1/review-tasks")
    def review_tasks(
        status: str = "open",
        limit: int = 25,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {"data": SERVICE.intake.list_review_tasks(context, status=status, limit=limit), "meta": {}, "errors": []}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_QUEUE_FILTER", "message": str(exc)}) from exc

    @app.post("/api/v1/review-tasks/{review_task_id}/decision")
    def review_task_decision(
        review_task_id: str,
        request: ReviewDecisionCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.intake.review_decision(review_task_id, request.decision, request.note, context),
                "meta": {},
                "errors": [],
            }
        except IntakeNotFoundError as exc:
            intake_not_found(exc)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_DECISION", "message": str(exc)}) from exc

    @app.get("/api/v1/businesses/{business_id}/periods/{period_key}/snapshot")
    def business_period_snapshot(
        business_id: str,
        period_key: str,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        return {
            "data": SERVICE.intake.period_snapshot(business_id, period_key, context=context),
            "meta": {"business_id": business_id, "period_key": period_key, "actor_id": context.actor_id},
            "errors": [],
        }

    @app.get("/api/v1/graph")
    def graph(masked: bool = True, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            payload = graph_payload(masked, context=context)
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        return {
            "data": payload,
            "meta": {
                "node_count": len(payload["nodes"]),
                "edge_count": len(payload["edges"]),
                "access": payload["access"],
            },
            "errors": [],
        }

    @app.post("/api/v1/simulation/shock")
    def shock(request: ShockSimulationRequest, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        result = SERVICE.shock_payload(
            shock_business_id=request.shock_business_id,
            product_category=request.product_category,
            inventory_coverage_days=request.inventory_coverage_days,
            context=context,
        )
        return {"data": result, "meta": {}, "errors": []}

    @app.post("/api/v1/recommendations/suppliers")
    def recommendations(request: SupplierRecommendationRequest, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            results = SERVICE.recommendations_payload(
                buyer_id=request.buyer_id,
                disrupted_supplier_id=request.disrupted_supplier_id,
                period_key=request.period_key,
                product_category=request.product_category,
                product_specification=request.product_specification,
                required_monthly_volume=request.required_monthly_volume,
                preferred_payment_term_days=request.preferred_payment_term_days,
                max_lead_time_days=request.max_lead_time_days,
                top_k=request.top_k,
                context=context,
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "BUYER_NOT_FOUND", "field": "buyer_id"}) from exc
        return {"data": results, "meta": {"top_k": len(results), "period_key": request.period_key}, "errors": []}

    @app.get("/api/v1/invoices/{invoice_id}/verification")
    def invoice_verification(invoice_id: str, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.invoice_payload(invoice_id, context=context), "meta": {}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "INVOICE_NOT_FOUND", "field": "invoice_id"}) from exc

    @app.post("/api/v1/consents", status_code=201)
    def create_consent(request: ConsentCreate, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.create_consent(
                subject_id=request.subject_id,
                recipient_id=request.recipient_id,
                scope=request.scope,
                purpose=request.purpose,
                legal_basis=request.legal_basis,
                expires_at=request.expires_at,
                evidence_reference=request.evidence_reference,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/consents/{consent_id}/revoke")
    def revoke_consent(consent_id: str, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.revoke_consent(consent_id, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/evidence/upload-url", status_code=201)
    def evidence_upload_url(request: EvidenceUploadUrlCreate, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.create_evidence_upload_url(
                organization_id=request.organization_id,
                file_name=request.file_name,
                document_type=request.document_type,
                period_key=request.period_key,
                content_type=request.content_type,
                byte_size=request.byte_size,
                classification=request.classification,
                purpose=request.purpose,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_CLASSIFICATION", "message": str(exc)}) from exc

    @app.get("/api/v1/evidence/upload-tickets")
    def list_evidence_upload_tickets(
        organization_id: str,
        period_key: str | None = None,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.list_evidence_upload_tickets(
                organization_id=organization_id,
                period_key=period_key,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/evidence/upload-tickets/{evidence_version_id}/complete")
    def complete_evidence_upload_ticket(
        evidence_version_id: str,
        request: EvidenceUploadCompleteCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.complete_evidence_upload_ticket(
                evidence_version_id=evidence_version_id,
                organization_id=request.organization_id,
                document_hash=request.document_hash,
                malware_scan_status=request.malware_scan_status,
                title=request.title,
                content_base64=request.content_base64,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)
        except EvidenceUploadValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": "EVIDENCE_UPLOAD_CONTENT_INVALID", "message": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "EVIDENCE_UPLOAD_TICKET_ALREADY_COMPLETED", "message": str(exc)}) from exc

    @app.get("/api/v1/evidence/{evidence_document_id}")
    def get_evidence_document(evidence_document_id: str, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.get_evidence_document(evidence_document_id, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/evidence/{evidence_document_id}/versions", status_code=201)
    def create_evidence_version(
        evidence_document_id: str,
        request: EvidenceVersionCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.add_evidence_version(
                evidence_document_id=evidence_document_id,
                organization_id=request.organization_id,
                object_key=request.object_key,
                document_hash=request.document_hash,
                content_type=request.content_type,
                byte_size=request.byte_size,
                malware_scan_status=request.malware_scan_status,
                supersedes_version_id=request.supersedes_version_id,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/evidence/versions/{evidence_version_id}/scan-result")
    def record_evidence_scan_result(
        evidence_version_id: str,
        request: EvidenceScanResultCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.record_evidence_scan_result(
                evidence_version_id=evidence_version_id,
                organization_id=request.organization_id,
                malware_scan_status=request.malware_scan_status,
                scanner_name=request.scanner_name,
                scanner_version=request.scanner_version,
                scanned_at=request.scanned_at,
                details=request.details,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/evidence/scan-jobs", status_code=202)
    def run_evidence_scan_job(request: EvidenceScanJobCreate, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            database = evidence_worker_database()
            decision = PolicyService.require(
                "record_malware_scan_result",
                context,
                resource_type="evidence_scan_job",
                resource_id=request.organization_id,
                resource_organization_id=request.organization_id,
                data_classification="confidential",
            )
            SERVICE.governance.audit.record_policy_decision(context, decision)
            worker = EvidenceWorkerService(database, governance=SERVICE.governance)
            scanner = worker.local_demo_scanner if request.scanner == "local_demo" else None
            summary = worker.scan_pending_versions(
                limit=request.limit,
                dry_run=request.dry_run,
                scanner=scanner,
                organization_id=request.organization_id,
                period_key=request.period_key,
            )
            event_id = SERVICE.governance.audit.record_context(
                "EVIDENCE_SCAN_JOB_REQUESTED",
                context,
                request.organization_id,
                policy_decision=decision,
                payload={
                    "organization_id": request.organization_id,
                    "period_key": request.period_key,
                    "limit": request.limit,
                    "scanner": request.scanner,
                    "dry_run": request.dry_run,
                    "candidates": summary["candidates"],
                    "processed": summary["processed"],
                    "skipped": summary["skipped"],
                    "errors": summary["errors"],
                },
            )
            return {
                "data": {
                    **summary,
                    "organization_id": request.organization_id,
                    "period_key": request.period_key,
                    "scanner": request.scanner,
                    "policy_decision_id": decision.decision_id,
                    "audit_event_id": event_id,
                    "advisory_notice": (
                        "Demo scan job checks object bytes for malware markers only; clean scan does not verify "
                        "document authenticity, legal validity or financing eligibility."
                    ),
                },
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/evidence/versions/{evidence_version_id}/download-url")
    def create_evidence_download_url(
        evidence_version_id: str,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.create_evidence_download_url(evidence_version_id, context=context)
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/evidence/{evidence_document_id}/access-grants", status_code=201)
    def create_evidence_access_grant(
        evidence_document_id: str,
        request: EvidenceAccessGrantCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.create_evidence_access_grant(
                evidence_document_id=evidence_document_id,
                organization_id=request.organization_id,
                grantee_organization_id=request.grantee_organization_id,
                scope=request.scope,
                purpose=request.purpose,
                expires_at=request.expires_at,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/evidence/access-grants/{grant_id}/revoke")
    def revoke_evidence_access_grant(grant_id: str, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.revoke_evidence_access_grant(grant_id, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)

    @app.post("/api/v1/evidence/{evidence_document_id}/retention")
    def update_evidence_retention(
        evidence_document_id: str,
        request: EvidenceRetentionUpdate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.update_evidence_retention(
                evidence_document_id=evidence_document_id,
                organization_id=request.organization_id,
                retention_status=request.retention_status,
                legal_hold=request.legal_hold,
                reason=request.reason,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_EVIDENCE_RETENTION", "message": str(exc)}) from exc

    @app.post("/api/v1/invoice-claims", status_code=201)
    def create_invoice_claim(request: InvoiceClaimCreate, context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.create_invoice_claim(
                seller_id=request.seller_id,
                buyer_id=request.buyer_id,
                financier_id=request.financier_id,
                invoice_hash_value=request.invoice_hash,
                amount=request.amount,
                due_date=request.due_date,
                invoice_id=request.invoice_id,
                issue_date=request.issue_date,
                currency=request.currency,
                idempotency_key=request.idempotency_key,
                source_evidence_id=request.source_evidence_id,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "INVOICE_CLAIM_CONFLICT", "message": str(exc)}) from exc

    @app.post("/api/v1/invoice-claims/{claim_id}/transition")
    def transition_invoice_claim(
        claim_id: str,
        request: InvoiceClaimTransitionCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.governance.transition_invoice_claim(claim_id, request.status, request.note, context=context)
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except IntakeNotFoundError as exc:
            intake_not_found(exc)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_INVOICE_CLAIM_TRANSITION", "message": str(exc)}) from exc

    @app.get("/api/v1/risk-runs")
    def risk_runs(
        organization_id: str,
        period: str | None = None,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.list_risk_runs(organization_id, period, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.get("/api/v1/match-runs")
    def match_runs(
        organization_id: str,
        period: str | None = None,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.list_match_runs(organization_id, period, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.get("/api/v1/scenario-runs")
    def scenario_runs(
        organization_id: str,
        period: str | None = None,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.list_scenario_runs(organization_id, period, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.get("/api/v1/admin/model-registry")
    def model_registry(
        artifact_type: str | None = None,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.list_model_registry(artifact_type, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.get("/api/v1/admin/ruleset-registry")
    def ruleset_registry(
        artifact_type: str | None = None,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.list_ruleset_registry(artifact_type, context=context),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.get("/api/v1/admin/recompute-jobs")
    def recompute_jobs(
        organization_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            return {
                "data": SERVICE.governance.list_recompute_jobs(
                    organization_id=organization_id,
                    status=status,
                    limit=limit,
                    context=context,
                ),
                "meta": {"request_id": context.request_id},
                "errors": [],
            }
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/connection-requests", status_code=201)
    def create_connection_request(
        request: ConnectionRequestCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.connection_request_payload(
                buyer_id=request.buyer_id,
                target_supplier_id=request.target_supplier_id,
                disrupted_supplier_id=request.disrupted_supplier_id,
                purpose=request.purpose,
                context=context,
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_NOT_FOUND"}) from exc
        return {"data": payload, "meta": {}, "errors": []}

    @app.get("/api/v1/connection-requests")
    def list_connection_requests(
        limit: int = 100,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.connection_requests_payload(context=context, limit=limit)
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/connection-requests/{connection_request_id}/decision")
    def decide_connection_request(
        connection_request_id: str,
        request: ConnectionRequestDecisionCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.decide_connection_request_payload(
                request_id=connection_request_id,
                decision_value=request.decision,
                note=request.note,
                contract_evidence_id=request.contract_evidence_id,
                context=context,
            )
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "CONNECTION_REQUEST_NOT_FOUND", "id": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "CONNECTION_REQUEST_STATE_INVALID", "message": str(exc)}) from exc
        return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}

    @app.get("/api/v1/supply-map-registrations")
    def list_supply_map_registrations(context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            payload = SERVICE.supply_map_registrations_payload(context=context)
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/supply-map-registrations", status_code=201)
    def create_supply_map_registration(
        request: SupplyMapRegistrationCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.create_supply_map_registration_payload(
                organization_name=request.organization_name,
                stakeholder_role=request.stakeholder_role,
                province=request.province,
                category=request.category,
                scale=request.scale,
                contact_email=request.contact_email,
                intended_relationships=request.intended_relationships,
                data_boundary=request.data_boundary,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)

    @app.post("/api/v1/supply-map-registrations/{registration_id}/decision")
    def decide_supply_map_registration(
        registration_id: str,
        request: SupplyMapRegistrationDecisionCreate,
        context: RequestContext = Depends(request_context),
    ) -> dict[str, Any]:
        try:
            payload = SERVICE.decide_supply_map_registration_payload(
                registration_id=registration_id,
                decision_value=request.decision,
                note=request.note,
                context=context,
            )
            return {"data": payload, "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "SUPPLY_MAP_REGISTRATION_NOT_FOUND"}) from exc

    @app.get("/api/v1/audit")
    def audit(context: RequestContext = Depends(request_context)) -> dict[str, Any]:
        try:
            return {"data": SERVICE.audit_payload(context=context), "meta": {"request_id": context.request_id}, "errors": []}
        except AccessDeniedError as exc:
            raise_access_denied(exc)
else:
    app = None
