from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from backend.app.services.access_control import AccessDeniedError, Membership, RequestContext
from backend.app.services.config import AppSettings, get_settings
from backend.app.services.postgres_pilot_service import ObjectStorageSettings, PilotFeatureUnavailableError, PostgresPilotService
from backend.app.services.radar_service import create_service


class _FakeCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


def _invoice_claim_fixture(
    *,
    claim_id: str = "3cb3a2f6-e597-48cf-99fd-0a7c2f4b6001",
    seller_id: str = "BIZ-005",
    buyer_id: str = "BIZ-009",
    financier_id: str = "BIZ-062",
    invoice_id: str | None = "INV-PG-001",
    invoice_hash: str = "abc1234567890def",
    invoice_identity_hash: str = "invoice-identity-hash",
    amount: int = 68_000_000,
    currency: str = "VND",
    issue_date: str | None = "2026-06-08",
    due_date: str = "2026-07-08",
    status: str = "registered",
    idempotency_key: str | None = "idem-pg-001",
    review_status: str = "pending_review",
    reviewer_id: str | None = None,
    audit_event_id: str | None = "3e337c27-3226-4d87-883d-273bce306001",
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "seller_id": seller_id,
        "buyer_id": buyer_id,
        "financier_id": financier_id,
        "invoice_id": invoice_id,
        "invoice_hash": invoice_hash,
        "invoice_identity_hash": invoice_identity_hash,
        "amount": amount,
        "currency": currency,
        "issue_date": issue_date,
        "due_date": due_date,
        "status": status,
        "idempotency_key": idempotency_key,
        "review_status": review_status,
        "reviewer_id": reviewer_id,
        "source_evidence_id": None,
        "created_by": "user-oidc-1",
        "created_at": "2026-09-01T00:20:00+00:00",
        "updated_at": "2026-09-01T00:20:00+00:00",
        "released_at": None,
        "dispute_reason": None,
        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a6001",
        "audit_event_id": audit_event_id,
    }


class _FakePostgresConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.commits = 0

    def __enter__(self) -> "_FakePostgresConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> _FakeCursor:
        self.calls.append((statement, params))
        if "DATA_SUBMISSION_DRAFT_CREATED" in statement:
            sections = json.loads(str(params[13]))
            return _FakeCursor(
                [
                    {
                        "submission_id": "5f6fd6e2-6a25-46e1-8197-f117487e4001",
                        "tenant_id": "tenant-demo",
                        "organization_id": "BIZ-009",
                        "id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                        "period_type": "month",
                        "period_key": params[4],
                        "period_start": params[5],
                        "period_end": params[6],
                        "status": "open",
                        "lock_version": 1,
                        "source_type": params[12],
                        "submission_status": "draft",
                        "version": 1,
                        "submitted_by": params[0],
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "updated_at": "2026-09-01T00:00:00+00:00",
                        "submitted_at": None,
                        "validated_at": None,
                        "canonicalized_at": None,
                        "sections": [
                            {
                                "section_name": item["section_name"],
                                "status": "draft",
                                "payload": item["payload"],
                                "updated_at": "2026-09-01T00:00:00+00:00",
                            }
                            for item in sections
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a4001",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce304001",
                    }
                ]
            )
        if (
            "ds.submission_id::text AS submission_id" in statement
            and "FROM data_submissions ds" in statement
            and "policy_decisions" not in statement
        ):
            row = self.rows[0] if self.rows else {}
            return _FakeCursor(
                [
                    {
                        "submission_id": params[0],
                        "organization_id": row.get("organization_id", "BIZ-009"),
                        "status": row.get("existing_status", row.get("submission_status", "draft")),
                        "sections": row.get(
                            "sections",
                            [
                                {
                                    "section_name": "financials",
                                    "payload": {
                                        "revenue": 810_000_000,
                                        "cash_in": 820_000_000,
                                        "cash_out": 760_000_000,
                                        "debt": 120_000_000,
                                        "accounts_receivable": 90_000_000,
                                        "accounts_payable": 70_000_000,
                                        "inventory_value": 150_000_000,
                                        "late_payment_rate": 0.02,
                                        "delivery_delay_rate": 0.01,
                                    },
                                }
                            ],
                        ),
                    }
                ]
            )
        if "DATA_SUBMISSION_READ" in statement:
            row = self.rows[0] if self.rows else {}
            return _FakeCursor(
                [
                    {
                        "submission_id": params[2],
                        "tenant_id": row.get("tenant_id", "tenant-demo"),
                        "organization_id": row.get("organization_id", "BIZ-009"),
                        "id": row.get("id", "6a44b8dd-e8e4-4067-a870-2c7c10c74001"),
                        "period_type": row.get("period_type", "month"),
                        "period_key": row.get("period_key", "2026-09"),
                        "period_start": row.get("period_start", "2026-09-01"),
                        "period_end": row.get("period_end", "2026-09-30"),
                        "status": row.get("status", "open"),
                        "lock_version": row.get("lock_version", 1),
                        "source_type": row.get("source_type", "manual"),
                        "submission_status": row.get("submission_status", "draft"),
                        "version": row.get("version", 1),
                        "submitted_by": row.get("submitted_by", "user-oidc-1"),
                        "created_at": row.get("created_at", "2026-09-01T00:00:00+00:00"),
                        "updated_at": row.get("updated_at", "2026-09-01T00:00:00+00:00"),
                        "submitted_at": None,
                        "validated_at": None,
                        "canonicalized_at": None,
                        "sections": row.get(
                            "sections",
                            [{"section_name": "financials", "status": "draft", "payload": {"revenue": 810_000_000}}],
                        ),
                        "issues": row.get("issues", []),
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a4002",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce304002",
                    }
                ]
            )
        if "DATA_SUBMISSION_DRAFT_UPDATED" in statement:
            sections = json.loads(str(params[8]))
            return _FakeCursor(
                [
                    {
                        "submission_id": params[2],
                        "tenant_id": "tenant-demo",
                        "organization_id": "BIZ-009",
                        "id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                        "period_type": "month",
                        "period_key": "2026-09",
                        "period_start": "2026-09-01",
                        "period_end": "2026-09-30",
                        "status": "open",
                        "lock_version": 1,
                        "source_type": "manual",
                        "submission_status": "draft",
                        "version": 1,
                        "submitted_by": "user-oidc-1",
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "updated_at": "2026-09-01T00:05:00+00:00",
                        "submitted_at": None,
                        "validated_at": None,
                        "canonicalized_at": None,
                        "sections": [
                            {
                                "section_name": item["section_name"],
                                "status": "draft",
                                "payload": item["payload"],
                                "updated_at": "2026-09-01T00:05:00+00:00",
                            }
                            for item in sections
                        ],
                        "issues": [],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a4003",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce304003",
                    }
                ]
            )
        if "CSV_IMPORT_BATCH_PARSED" in statement:
            raw_rows = json.loads(str(params[15]))
            return _FakeCursor(
                [
                    {
                        "batch_id": "fa3ee8f7-cf90-4830-b87f-0c2eeacd5001",
                        "submission_id": params[2],
                        "dataset": params[8],
                        "file_name": params[11],
                        "row_count": params[10],
                        "status": "parsed",
                        "checksum": params[9],
                        "preview_rows": [row["payload"] for row in raw_rows[:20]],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a5001",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce305001",
                    }
                ]
            )
        if "DATA_SUBMISSION_VALIDATED" in statement:
            status = params[11]
            issue_payload = json.loads(str(params[8]))
            return _FakeCursor(
                [
                    {
                        "submission_id": params[2],
                        "tenant_id": "tenant-demo",
                        "organization_id": "BIZ-009",
                        "id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                        "period_type": "month",
                        "period_key": "2026-09",
                        "period_start": "2026-09-01",
                        "period_end": "2026-09-30",
                        "status": "open",
                        "lock_version": 1,
                        "source_type": "manual",
                        "submission_status": status,
                        "version": 1,
                        "submitted_by": "user-oidc-1",
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "updated_at": "2026-09-01T00:06:00+00:00",
                        "submitted_at": None,
                        "validated_at": "2026-09-01T00:06:00+00:00",
                        "canonicalized_at": None,
                        "sections": [
                            {
                                "section_name": "financials",
                                "status": params[9],
                                "payload": {
                                    "revenue": 810_000_000,
                                    "cash_in": 820_000_000,
                                    "cash_out": 760_000_000,
                                    "debt": 120_000_000,
                                    "accounts_receivable": 90_000_000,
                                    "accounts_payable": 70_000_000,
                                    "inventory_value": 150_000_000,
                                    "late_payment_rate": 0.02,
                                    "delivery_delay_rate": 0.01,
                                },
                                "updated_at": "2026-09-01T00:06:00+00:00",
                            }
                        ],
                        "issues": [
                            {
                                "issue_id": f"f1a82bb1-7c9a-44ff-9928-8ecaa7a44{index:03d}",
                                "section_name": issue["section"],
                                "path": issue["path"],
                                "row_number": issue.get("row_number"),
                                "column_name": issue.get("column_name"),
                                "code": issue["code"],
                                "severity": issue["severity"],
                                "message": issue["message"],
                                "suggestion": issue.get("suggestion"),
                            }
                            for index, issue in enumerate(issue_payload, start=1)
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a4004",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce304004",
                    }
                ]
            )
        if "DATA_SUBMISSION_ERROR_REPORT_VIEWED" in statement:
            return _FakeCursor(
                [
                    {
                        "rows": [
                            {
                                "source": "validation_issue",
                                "batch_id": "fa3ee8f7-cf90-4830-b87f-0c2eeacd5001",
                                "dataset": "products",
                                "file_name": "products.csv",
                                "raw_record_id": "0c8db0e4-5b13-4de6-a046-58b76d925001",
                                "row": 1,
                                "column": None,
                                "path": "sku",
                                "code": "SKU_REQUIRED",
                                "severity": "error",
                                "message": "SKU is required.",
                                "suggestion": None,
                                "payload": {"sku": "", "available_capacity": "10"},
                            },
                            {
                                "source": "raw_record_error",
                                "batch_id": "fa3ee8f7-cf90-4830-b87f-0c2eeacd5001",
                                "dataset": "products",
                                "file_name": "products.csv",
                                "raw_record_id": "0c8db0e4-5b13-4de6-a046-58b76d925001",
                                "row": 1,
                                "column": None,
                                "path": None,
                                "code": "SKU_REQUIRED",
                                "severity": "error",
                                "message": "SKU is required.",
                                "suggestion": None,
                                "payload": {"sku": "", "available_capacity": "10"},
                            },
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a5002",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce305002",
                    }
                ]
            )
        if "DATA_SUBMISSION_SUBMITTED" in statement:
            return _FakeCursor(
                [
                    {
                        "submission_id": params[2],
                        "tenant_id": "tenant-demo",
                        "organization_id": "BIZ-009",
                        "id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                        "period_type": "month",
                        "period_key": "2026-09",
                        "period_start": "2026-09-01",
                        "period_end": "2026-09-30",
                        "status": "open",
                        "lock_version": 1,
                        "source_type": "manual",
                        "submission_status": "in_review",
                        "version": 1,
                        "submitted_by": "user-oidc-1",
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "updated_at": "2026-09-01T00:07:00+00:00",
                        "submitted_at": "2026-09-01T00:07:00+00:00",
                        "validated_at": "2026-09-01T00:06:00+00:00",
                        "canonicalized_at": None,
                        "sections": [
                            {
                                "section_name": "financials",
                                "status": "ready",
                                "payload": {"revenue": 810_000_000},
                                "updated_at": "2026-09-01T00:06:00+00:00",
                            }
                        ],
                        "issues": [],
                        "review_task": {
                            "review_task_id": "68f2c69b-c245-48cc-bec9-89cbbce45001",
                            "status": "open",
                            "assigned_role": "reviewer",
                            "assigned_to": "reviewer-oidc-1",
                            "assignment_reason": "auto_assigned_primary_org_reviewer",
                            "assigned_at": "2026-09-01T00:07:00+00:00",
                            "decided_by": None,
                            "decision": None,
                            "decision_note": None,
                            "created_at": "2026-09-01T00:07:00+00:00",
                            "decided_at": None,
                        },
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a4005",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce304005",
                    }
                ]
            )
        if "DATA_SUBMISSION_REVIEW_DECIDED" in statement:
            review_decision = params[12]
            submission_status = params[14]
            approved = review_decision == "approve"
            return _FakeCursor(
                [
                    {
                        "submission_id": "5f6fd6e2-6a25-46e1-8197-f117487e4001",
                        "tenant_id": "tenant-demo",
                        "organization_id": "BIZ-009",
                        "id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                        "period_type": "month",
                        "period_key": "2026-09",
                        "period_start": "2026-09-01",
                        "period_end": "2026-09-30",
                        "status": "approved" if approved else "open",
                        "lock_version": 2 if approved else 1,
                        "source_type": "manual",
                        "submission_status": submission_status,
                        "version": 1,
                        "submitted_by": "user-oidc-1",
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "updated_at": "2026-09-01T00:10:00+00:00",
                        "submitted_at": "2026-09-01T00:07:00+00:00",
                        "validated_at": "2026-09-01T00:06:00+00:00",
                        "canonicalized_at": "2026-09-01T00:10:00+00:00" if approved else None,
                        "sections": [
                            {
                                "section_name": "financials",
                                "status": "ready",
                                "payload": {"revenue": 810_000_000},
                                "updated_at": "2026-09-01T00:06:00+00:00",
                            },
                            {
                                "section_name": "products",
                                "status": "ready",
                                "payload": [{"sku": "SME-BEV-330", "available_capacity": 12_000}],
                                "updated_at": "2026-09-01T00:06:00+00:00",
                            },
                            {
                                "section_name": "evidence",
                                "status": "ready",
                                "payload": [
                                    {
                                        "title": "HACCP certificate",
                                        "document_hash": "sha256:6a0b4e33f78d9a18",
                                        "malware_scan_status": "clean",
                                    }
                                ],
                                "updated_at": "2026-09-01T00:06:00+00:00",
                            },
                        ],
                        "issues": [],
                        "review_task": {
                            "review_task_id": params[2],
                            "status": "closed",
                            "assigned_role": "reviewer",
                            "assigned_to": "reviewer-oidc-1",
                            "assignment_reason": "auto_assigned_primary_org_reviewer",
                            "assigned_at": "2026-09-01T00:07:00+00:00",
                            "decided_by": "reviewer-oidc-1",
                            "decision": review_decision,
                            "decision_note": params[13],
                            "created_at": "2026-09-01T00:07:00+00:00",
                            "decided_at": "2026-09-01T00:10:00+00:00",
                        },
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a4006",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce304006",
                    }
                ]
            )
        if (
            "review.review_task_id::text AS review_task_id" in statement
            and "FROM review_tasks review" in statement
            and "policy_decisions" not in statement
        ):
            return _FakeCursor(
                [
                    {
                        "review_task_id": params[0],
                        "submission_id": "5f6fd6e2-6a25-46e1-8197-f117487e4001",
                        "organization_id": "BIZ-009",
                        "assigned_to": "reviewer-oidc-1",
                    }
                ]
            )
        if "RISK_RUNS_VIEWED" in statement:
            no_period = bool(self.rows and self.rows[0].get("analytics_no_period"))
            risk_runs = [] if no_period else [
                {
                    "risk_run_id": "1f676e4e-c460-40d8-bfcb-7811a3d27001",
                    "organization_id": "BIZ-009",
                    "reporting_period_id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                    "period_key": params[5],
                    "feature_snapshot_id": "1a77f087-29d8-4a45-afd1-fcb8af827001",
                    "model_version": "rules-v1",
                    "ruleset_version": "risk-rules-v1",
                    "score": 72,
                    "level": "watch",
                    "explanation": "Late-payment and cash buffer advisory signal.",
                    "review_status": "pending_review",
                    "created_at": "2026-09-01T00:30:00+00:00",
                    "feature_payload": {"period_key": params[5], "revenue": 810_000_000},
                }
            ]
            return _FakeCursor(
                [
                    {
                        "organization_id": params[2],
                        "period_key": params[5],
                        "risk_runs": risk_runs,
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a7001",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce307001",
                    }
                ]
            )
        if "MATCH_RUNS_VIEWED" in statement:
            no_period = bool(self.rows and self.rows[0].get("analytics_no_period"))
            match_runs = [] if no_period else [
                {
                    "match_run_id": "c6e63255-5fbe-467b-bb0c-a74e2e798001",
                    "buyer_organization_id": "BIZ-009",
                    "reporting_period_id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                    "period_key": params[5],
                    "disrupted_supplier_id": "BIZ-005",
                    "product_category": "beverages",
                    "ruleset_version": "matching-rules-v1",
                    "review_status": "pending_review",
                    "created_at": "2026-09-01T00:31:00+00:00",
                    "candidates": [
                        {
                            "candidate_id": "9b0692f1-d49e-4a9a-acf4-fcc7ca618001",
                            "supplier_organization_id": "BIZ-018",
                            "rank": 1,
                            "score": 88,
                            "explanation": {"capacity_fit": "strong", "distance": "nearby"},
                            "consent_status": "not_requested",
                        }
                    ],
                }
            ]
            return _FakeCursor(
                [
                    {
                        "organization_id": params[2],
                        "period_key": params[5],
                        "match_runs": match_runs,
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a7002",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce307002",
                    }
                ]
            )
        if "SCENARIO_RUNS_VIEWED" in statement:
            no_period = bool(self.rows and self.rows[0].get("analytics_no_period"))
            scenario_runs = [] if no_period else [
                {
                    "scenario_run_id": "53c47064-f6de-4828-95d6-497d4e3f8001",
                    "organization_id": "BIZ-009",
                    "reporting_period_id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                    "period_key": params[5],
                    "input_snapshot_id": "1a77f087-29d8-4a45-afd1-fcb8af827001",
                    "shock_organization_id": None,
                    "product_category": "beverages",
                    "ruleset_version": "scenario-rules-v0.1",
                    "model_version": "deterministic-postgres-v0.1",
                    "payload": {
                        "period_key": params[5],
                        "guardrail": "Scenario output is decision-support only and requires human review before operational action.",
                    },
                    "review_status": "pending_human_review",
                    "created_at": "2026-09-01T00:32:00+00:00",
                }
            ]
            return _FakeCursor(
                [
                    {
                        "organization_id": params[2],
                        "period_key": params[5],
                        "scenario_runs": scenario_runs,
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a7003",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce307003",
                    }
                ]
            )
        if "FROM model_registry item" in statement:
            return _FakeCursor(
                [
                    {
                        "models": [
                            {
                                "artifact_type": "risk",
                                "model_version": "deterministic-postgres-v0.1",
                                "status": "active",
                                "approval_status": "approved",
                                "config": {"purpose": "risk decision-support"},
                                "checksum": "sha256:model",
                                "created_by": "user-oidc-1",
                                "created_at": "2026-09-01T00:33:00+00:00",
                            }
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a8001",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce308001",
                    }
                ]
            )
        if "FROM ruleset_registry item" in statement:
            return _FakeCursor(
                [
                    {
                        "rulesets": [
                            {
                                "artifact_type": "risk",
                                "ruleset_version": "intake-risk-rules-v0.1",
                                "status": "active",
                                "approval_status": "approved",
                                "config": {"inputs": ["cashflow", "debt"]},
                                "checksum": "sha256:ruleset",
                                "created_by": "user-oidc-1",
                                "created_at": "2026-09-01T00:33:00+00:00",
                            }
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a8002",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce308002",
                    }
                ]
            )
        if "RECOMPUTE_JOBS_VIEWED" in statement:
            return _FakeCursor(
                [
                    {
                        "jobs": [
                            {
                                "job_id": "db357ba4-f9cf-42f1-8351-aceef3da8003",
                                "organization_id": "BIZ-009",
                                "reporting_period_id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                                "source_submission_id": "5f6fd6e2-6a25-46e1-8197-f117487e4001",
                                "job_type": "analytics_recompute",
                                "status": "queued",
                                "idempotency_key": "analytics:5f6fd6e2-6a25-46e1-8197-f117487e4001",
                                "payload": {"reason": "approved_intake_materialized"},
                                "attempts": 0,
                                "max_attempts": 3,
                                "last_error": None,
                                "created_at": "2026-09-01T00:34:00+00:00",
                            }
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a8003",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce308003",
                    }
                ]
            )
        if "PERIOD_SNAPSHOT_READ" in statement:
            return _FakeCursor(self.rows)
        if "FROM reporting_periods" in statement:
            return _FakeCursor(self.rows)
        if "INSERT INTO consent_records" in statement:
            return _FakeCursor(
                [
                    {
                        "consent_id": "2fd99db8-a305-42fa-8230-7b8c148e1001",
                        "subject_id": "BIZ-009",
                        "recipient_id": "BIZ-062",
                        "scope": "financial_summary",
                        "purpose": "management_review",
                        "legal_basis": "explicit_consent",
                        "status": "granted",
                        "expires_at": None,
                        "revoked_at": None,
                        "version": 1,
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a1001",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce301001",
                    }
                ]
            )
        if "SELECT" in statement and "FROM consent_records consent" in statement and "UPDATE consent_records" not in statement:
            return _FakeCursor([{"consent_id": params[0], "subject_id": "BIZ-009"}])
        if "UPDATE consent_records" in statement:
            return _FakeCursor(
                [
                    {
                        "consent_id": params[2],
                        "subject_id": "BIZ-009",
                        "recipient_id": "BIZ-062",
                        "scope": "financial_summary",
                        "purpose": "management_review",
                        "legal_basis": "explicit_consent",
                        "status": "revoked",
                        "expires_at": None,
                        "revoked_at": "2026-06-30T12:00:00+00:00",
                        "version": 2,
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a1002",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce301002",
                    }
                ]
            )
        if "EVIDENCE_DOCUMENT_READ" in statement:
            return _FakeCursor(
                [
                    {
                        "evidence_document_id": params[2],
                        "organization_id": "BIZ-009",
                        "reporting_period_id": "6a44b8dd-e8e4-4067-a870-2c7c10c74001",
                        "period_key": "2026-09",
                        "document_type": "CERTIFICATE",
                        "title": "HACCP certificate",
                        "classification": "confidential",
                        "retention_status": "active",
                        "legal_hold": False,
                        "source_submission_id": "5f6fd6e2-6a25-46e1-8197-f117487e4001",
                        "source_record_id": "SECTION-5f6fd6e2-6a25-46e1-8197-f117487e4001-EVIDENCE-1",
                        "valid_from": "2026-09-01",
                        "valid_to": None,
                        "created_at": "2026-09-01T00:40:00+00:00",
                        "versions": [
                            {
                                "evidence_version_id": "77bb9f91-e46e-4d4b-9bf2-5c4d857e2002",
                                "object_key": "s3://vietsupply-evidence/tenant-demo/BIZ-009/haccp.pdf",
                                "object_version": "6db69845-ed08-4324-92f5-47b0577e2002",
                                "document_hash": "sha256:6a0b4e33f78d9a18",
                                "content_type": "application/pdf",
                                "byte_size": 4096,
                                "malware_scan_status": "clean",
                                "usable": True,
                            }
                        ],
                        "active_grants": [
                            {
                                "grant_id": "45cf900c-0a22-48a4-8e7f-4aa2891e3001",
                                "grantee_organization_id": "BIZ-062",
                                "scope": "evidence_review",
                                "purpose": "lender_review",
                                "status": "active",
                            }
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a2004",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce302004",
                    }
                ]
            )
        if (
            "FROM evidence_versions version" in statement
            and "version.evidence_version_id = app_try_uuid(%s)" in statement
            and "policy_decisions" not in statement
        ):
            status = str(self.rows[0].get("evidence_download_status", "clean")) if self.rows else "clean"
            return _FakeCursor(
                [
                    {
                        "evidence_version_id": params[0],
                        "evidence_document_id": "9c292401-4679-4491-9f18-4908743e2001",
                        "tenant_id": "73af1c04-6e83-47cc-ae19-47a66c8f2001",
                        "organization_uuid": "79d1fc8b-ae41-4e47-8f1a-1f2f8d3c9009",
                        "organization_id": "BIZ-009",
                        "object_key": "s3://vietsupply-evidence/tenant-demo/BIZ-009/haccp.pdf",
                        "object_version": "6db69845-ed08-4324-92f5-47b0577e2002",
                        "document_hash": "sha256:6a0b4e33f78d9a18",
                        "content_type": "application/pdf",
                        "byte_size": 4096,
                        "malware_scan_status": status,
                        "classification": "confidential",
                    }
                ]
            )
        if "EVIDENCE_DOWNLOAD_URL_CREATED" in statement:
            return _FakeCursor(
                [
                    {
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a2005",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce302005",
                        "object_access_id": "ef7e7cc2-67f1-4270-86f9-14457df82005",
                    }
                ]
            )
        if "EVIDENCE_DOWNLOAD_URL_DENIED" in statement or "EVIDENCE_DOCUMENT_READ_DENIED" in statement:
            return _FakeCursor([])
        if "EVIDENCE_UPLOAD_TICKETS_VIEWED" in statement:
            return _FakeCursor(
                [
                    {
                        "organization_id": params[4],
                        "period_key": params[6],
                        "tickets": [
                            {
                                "id": "77bb9f91-e46e-4d4b-9bf2-5c4d857e2001",
                                "evidence_version_id": "77bb9f91-e46e-4d4b-9bf2-5c4d857e2001",
                                "organization_id": params[4],
                                "business_id": params[4],
                                "period_key": params[6],
                                "document_type": "CERTIFICATION",
                                "file_name": "haccp.pdf",
                                "content_type": "application/pdf",
                                "byte_size": 2048,
                                "classification": "confidential",
                                "status": "pending_scan",
                                "malware_scan_status": "pending_scan",
                                "uploaded_at": "2026-09-01T00:35:00+00:00",
                                "advisory_notice": "Pending only.",
                            }
                        ],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a2006",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce302006",
                    }
                ]
            )
        if "EVIDENCE_UPLOAD_COMPLETED" in statement:
            return _FakeCursor(
                [
                    {
                        "evidence_version_id": params[6],
                        "evidence_document_id": "9c292401-4679-4491-9f18-4908743e2001",
                        "organization_id": params[4],
                        "period_key": "2026-09",
                        "document_type": "CERTIFICATION",
                        "title": params[7] or "haccp.pdf",
                        "object_key": "s3://vietsupply-evidence/tenant-demo/BIZ-009/haccp.pdf",
                        "object_version": params[6],
                        "document_hash": params[8],
                        "malware_scan_status": "pending_scan",
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a2007",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce302007",
                    }
                ]
            )
        if "INSERT INTO evidence_documents" in statement:
            object_key = next((str(item) for item in params if isinstance(item, str) and item.startswith("s3://")), "s3://demo/missing-object")
            return _FakeCursor(
                [
                    {
                        "evidence_version_id": "77bb9f91-e46e-4d4b-9bf2-5c4d857e2001",
                        "evidence_document_id": "9c292401-4679-4491-9f18-4908743e2001",
                        "organization_id": "BIZ-009",
                        "period_key": params[6],
                        "document_type": params[15],
                        "file_name": params[16],
                        "content_type": params[19],
                        "byte_size": params[20],
                        "classification": params[17],
                        "object_key": object_key,
                        "object_version": "pending-upload",
                        "document_hash": "pending-upload",
                        "malware_scan_status": "pending_scan",
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a2001",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce302001",
                    }
                ]
            )
        if "EVIDENCE_VERSION_RECORDED" in statement:
            return _FakeCursor(
                [
                    {
                        "evidence_version_id": "77bb9f91-e46e-4d4b-9bf2-5c4d857e2002",
                        "evidence_document_id": params[2],
                        "organization_id": "BIZ-009",
                        "object_key": params[10],
                        "object_version": "6db69845-ed08-4324-92f5-47b0577e2002",
                        "document_hash": params[11],
                        "malware_scan_status": params[14],
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a2002",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce302002",
                    }
                ]
            )
        if "EVIDENCE_SCAN_RESULT_RECORDED" in statement:
            status = params[9]
            return _FakeCursor(
                [
                    {
                        "evidence_version_id": params[2],
                        "evidence_document_id": "9c292401-4679-4491-9f18-4908743e2001",
                        "organization_id": params[3],
                        "object_key": "s3://vietsupply-evidence/tenant-demo/BIZ-009/haccp.pdf",
                        "object_version": "6db69845-ed08-4324-92f5-47b0577e2002",
                        "document_hash": "sha256:6a0b4e33f78d9a18",
                        "malware_scan_status": status,
                        "retention_status": "retention_locked" if status in {"infected", "failed"} else "active",
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a2003",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce302003",
                    }
                ]
            )
        if "EVIDENCE_ACCESS_GRANTED" in statement:
            return _FakeCursor(
                [
                    {
                        "grant_id": "45cf900c-0a22-48a4-8e7f-4aa2891e3001",
                        "evidence_document_id": params[2],
                        "organization_id": params[3],
                        "grantee_organization_id": params[5],
                        "scope": params[11],
                        "purpose": params[12],
                        "status": "active",
                        "expires_at": params[13],
                        "revoked_at": None,
                        "created_at": "2026-09-01T00:40:00+00:00",
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a3001",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce303001",
                    }
                ]
            )
        if (
            "FROM evidence_access_grants grant" in statement
            and "JOIN organizations subject" in statement
            and "policy_decisions" not in statement
        ):
            return _FakeCursor(
                [
                    {
                        "grant_id": params[0],
                        "evidence_document_id": "9c292401-4679-4491-9f18-4908743e2001",
                        "organization_id": "BIZ-009",
                    }
                ]
            )
        if "EVIDENCE_ACCESS_REVOKED" in statement:
            return _FakeCursor(
                [
                    {
                        "grant_id": params[2],
                        "evidence_document_id": "9c292401-4679-4491-9f18-4908743e2001",
                        "organization_id": "BIZ-009",
                        "grantee_organization_id": "BIZ-062",
                        "scope": "evidence_review",
                        "purpose": "lender_review",
                        "status": "revoked",
                        "expires_at": "2026-12-31T23:59:59Z",
                        "revoked_at": "2026-09-01T00:45:00+00:00",
                        "created_at": "2026-09-01T00:40:00+00:00",
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a3002",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce303002",
                    }
                ]
            )
        if (
            "document.legal_hold" in statement
            and "FROM evidence_documents document" in statement
            and "policy_decisions" not in statement
        ):
            row = self.rows[0] if self.rows else {}
            return _FakeCursor(
                [
                    {
                        "evidence_document_id": params[0],
                        "legal_hold": row.get("evidence_legal_hold", False),
                        "organization_id": params[1],
                    }
                ]
            )
        if "EVIDENCE_RETENTION_UPDATED" in statement:
            return _FakeCursor(
                [
                    {
                        "evidence_document_id": params[5],
                        "organization_id": "BIZ-009",
                        "retention_status": params[2],
                        "legal_hold": params[3],
                        "valid_to": "2026-09-01" if params[2] == "deleted" else None,
                        "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a3003",
                        "audit_event_id": "3e337c27-3226-4d87-883d-273bce303003",
                    }
                ]
            )
        if "claim.idempotency_key = %s" in statement and "FROM invoice_claims claim" in statement:
            row = self.rows[0] if self.rows and self.rows[0].get("idempotent_invoice_claim") else None
            return _FakeCursor([_invoice_claim_fixture(idempotency_key=params[0])] if row else [])
        if (
            "FROM invoice_claims" in statement
            and "invoice_identity_hash = %s" in statement
            and "status IN ('pledged', 'financed')" in statement
        ):
            row = self.rows[0] if self.rows and self.rows[0].get("active_invoice_conflict") else None
            return _FakeCursor([{"claim_id": "3cb3a2f6-e597-48cf-99fd-0a7c2f4b6999"}] if row else [])
        if "claim.claim_id = app_try_uuid(%s)" in statement and "FROM invoice_claims claim" in statement and "policy_decisions" not in statement:
            row = self.rows[0] if self.rows else {}
            return _FakeCursor(
                [
                    _invoice_claim_fixture(
                        claim_id=params[0],
                        status=str(row.get("invoice_claim_status", "registered")),
                        review_status=str(row.get("invoice_claim_review_status", "pending_review")),
                    )
                ]
            )
        if "INVOICE_CLAIM_REGISTERED" in statement:
            return _FakeCursor(
                [
                    _invoice_claim_fixture(
                        seller_id=params[2],
                        buyer_id=params[4],
                        financier_id=params[6],
                        invoice_id=params[17],
                        invoice_hash=params[18],
                        invoice_identity_hash=params[19],
                        amount=params[20],
                        currency=params[21],
                        issue_date=params[22],
                        due_date=params[23],
                        idempotency_key=params[24],
                        audit_event_id="3e337c27-3226-4d87-883d-273bce306001",
                    )
                ]
            )
        if "INVOICE_CLAIM_TRANSITIONED" in statement:
            review_status = "reviewed" if params[8] in {"verified", "pledged", "financed", "released"} else "disputed"
            return _FakeCursor(
                [
                    _invoice_claim_fixture(
                        claim_id=params[2],
                        status=params[8],
                        review_status=review_status,
                        reviewer_id=params[0],
                        audit_event_id="3e337c27-3226-4d87-883d-273bce306002",
                    )
                ]
            )
        return _FakeCursor([])

    def commit(self) -> None:
        self.commits += 1


class _FakePostgresConnector:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.connection = _FakePostgresConnection(rows)

    def connect(self) -> _FakePostgresConnection:
        return self.connection


class RuntimeConfigTests(unittest.TestCase):
    def test_demo_runtime_allows_sqlite_and_dev_jwt(self) -> None:
        settings = AppSettings(app_mode="demo", database_url="sqlite:///demo.db", allow_demo_headers=True, auth_provider="dev_jwt")
        settings.validate_runtime()

    def test_pilot_requires_postgres_oidc_and_no_demo_headers(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "ALLOW_DEMO_HEADERS=false"):
            AppSettings(
                app_mode="pilot",
                database_url="postgresql://user:pass@localhost/db",
                allow_demo_headers=True,
                auth_provider="oidc",
                jwks_url="https://idp.example/.well-known/jwks.json",
            ).validate_runtime()

        with self.assertRaisesRegex(RuntimeError, "AUTH_PROVIDER=oidc"):
            AppSettings(
                app_mode="pilot",
                database_url="postgresql://user:pass@localhost/db",
                allow_demo_headers=False,
                auth_provider="dev_jwt",
            ).validate_runtime()

        with self.assertRaisesRegex(RuntimeError, "AUTH_JWKS_URL"):
            AppSettings(
                app_mode="pilot",
                database_url="postgresql://user:pass@localhost/db",
                allow_demo_headers=False,
                auth_provider="oidc",
            ).validate_runtime()

        AppSettings(
            app_mode="pilot",
            database_url="postgresql://user:pass@localhost/db",
            allow_demo_headers=False,
            auth_provider="oidc",
            jwks_url="https://idp.example/.well-known/jwks.json",
        ).validate_runtime()

    def test_get_settings_reads_oidc_environment(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "APP_MODE": "pilot",
                "DATABASE_URL": "postgresql://user:pass@localhost/db",
                "ALLOW_DEMO_HEADERS": "false",
                "AUTH_PROVIDER": "oidc",
                "AUTH_JWKS_URL": "https://idp.example/.well-known/jwks.json",
                "AUTH_JWT_ISSUER": "https://idp.example/",
                "AUTH_JWT_AUDIENCE": "vietsupply-api",
            },
            clear=False,
        ):
            settings = get_settings()

        self.assertEqual(settings.app_mode, "pilot")
        self.assertEqual(settings.database_engine, "postgresql")
        self.assertEqual(settings.auth_provider, "oidc")
        self.assertEqual(settings.jwks_url, "https://idp.example/.well-known/jwks.json")

    def test_create_service_uses_sqlite_database_url_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "configured-demo.db"
            with patch.dict(
                "os.environ",
                {
                    "APP_MODE": "demo",
                    "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                    "ALLOW_DEMO_HEADERS": "true",
                    "AUTH_PROVIDER": "dev_jwt",
                },
                clear=False,
            ):
                settings = get_settings()
                service = create_service()
                self.assertEqual(settings.sqlite_path, db_path)

            self.assertTrue(db_path.exists())
            self.assertEqual(service.overview_payload()["active_companies"], 62)

    def test_create_service_boots_postgres_pilot_boundary_without_demo_data(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "APP_MODE": "pilot",
                "DATABASE_URL": "postgresql://user:pass@localhost/db",
                "ALLOW_DEMO_HEADERS": "false",
                "AUTH_PROVIDER": "oidc",
                "AUTH_JWKS_URL": "https://idp.example/.well-known/jwks.json",
            },
            clear=False,
        ):
            service = create_service()

        self.assertIsInstance(service, PostgresPilotService)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="management_review",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )
        self.assertEqual(service.governance.auth_me(context)["adapter_status"], "pilot_boot_boundary")
        self.assertEqual(service.health_payload()["migration_revisions"], ["0001"])
        with self.assertRaisesRegex(PilotFeatureUnavailableError, "PostgreSQL pilot adapter"):
            service.overview_payload()

    def test_postgres_pilot_period_lookup_sets_rls_session_and_returns_periods(self) -> None:
        connector = _FakePostgresConnector(
            [
                {
                    "id": "6a44b8dd-e8e4-4067-a870-2c7c10c73001",
                    "tenant_id": "tenant-demo",
                    "organization_id": "BIZ-009",
                    "period_type": "month",
                    "period_key": "2026-07",
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-31",
                    "status": "approved",
                    "lock_version": 2,
                    "latest_submission_status": "approved",
                }
            ]
        )
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="management_review",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-periods",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        periods = service.intake.list_periods("BIZ-009", context=context)

        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        reporting_query = next(call for call in connector.connection.calls if "FROM reporting_periods" in call[0])
        self.assertEqual(periods[0]["period_key"], "2026-07")
        self.assertEqual(periods[0]["organization_id"], "BIZ-009")
        self.assertEqual(periods[0]["latest_submission_status"], "approved")
        self.assertEqual(len(set_config_calls), 5)
        self.assertIn("app.tenant_id", set_config_calls[0][1])
        self.assertEqual(reporting_query[1], ("BIZ-009", "BIZ-009"))
        with self.assertRaisesRegex(PilotFeatureUnavailableError, "intake.delete_submission"):
            service.intake.delete_submission("submission-id", context)

    def test_postgres_pilot_create_submission_ensures_period_sections_policy_and_audit(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-create-submission",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.create_submission(
            organization_id="BIZ-009",
            period_key="2026-09",
            source_type="manual",
            sections={"financials": {"revenue": 810_000_000}},
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        create_call = next(call for call in connector.connection.calls if "DATA_SUBMISSION_DRAFT_CREATED" in call[0])
        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        self.assertEqual(submission["organization_id"], "BIZ-009")
        self.assertEqual(submission["period"]["period_key"], "2026-09")
        self.assertEqual(submission["period"]["period_start"], "2026-09-01")
        self.assertEqual(submission["period"]["period_end"], "2026-09-30")
        self.assertEqual(submission["status"], "draft")
        self.assertEqual(submission["source"], "manual")
        self.assertEqual(submission["version"], 1)
        self.assertEqual(submission["sections"]["financials"]["payload"]["revenue"], 810_000_000)
        self.assertEqual(submission["validation_summary"], {"errors": 0, "warnings": 0, "infos": 0})
        self.assertTrue(submission["policy_decision_id"])
        self.assertTrue(submission["audit_event_id"])
        self.assertGreaterEqual(len(set_config_calls), 5)
        self.assertIn("INSERT INTO reporting_periods", sql_text)
        self.assertIn("ON CONFLICT (tenant_id, organization_id, period_type, period_key)", sql_text)
        self.assertIn("INSERT INTO data_submissions", sql_text)
        self.assertIn("INSERT INTO submission_sections", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("DATA_SUBMISSION_DRAFT_CREATED", sql_text)
        self.assertEqual(create_call[1][4], "2026-09")
        self.assertEqual(create_call[1][12], "manual")
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_get_submission_reads_sections_issues_policy_and_audit(self) -> None:
        connector = _FakePostgresConnector(
            [
                {
                    "sections": [
                        {
                            "section_name": "financials",
                            "status": "draft",
                            "payload": {"revenue": 810_000_000},
                            "updated_at": "2026-09-01T00:00:00+00:00",
                        }
                    ],
                    "issues": [
                        {
                            "issue_id": "f1a82bb1-7c9a-44ff-9928-8ecaa7a44001",
                            "section_name": "financials",
                            "path": "revenue",
                            "row_number": None,
                            "column_name": None,
                            "code": "REVIEW_WARNING",
                            "severity": "warning",
                            "message": "Revenue should be reviewed.",
                            "suggestion": "Check monthly ledger.",
                        }
                    ],
                }
            ]
        )
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-get-submission",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.get_submission("5f6fd6e2-6a25-46e1-8197-f117487e4001", context=context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(submission["sections"]["financials"]["payload"]["revenue"], 810_000_000)
        self.assertEqual(submission["validation_summary"], {"errors": 0, "warnings": 1, "infos": 0})
        self.assertEqual(submission["issues"][0]["code"], "REVIEW_WARNING")
        self.assertTrue(submission["policy_decision_id"])
        self.assertTrue(submission["audit_event_id"])
        self.assertIn("DATA_SUBMISSION_READ", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_update_submission_autosaves_sections_policy_and_audit(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-update-submission",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.update_submission(
            "5f6fd6e2-6a25-46e1-8197-f117487e4001",
            {"financials": {"revenue": 830_000_000, "cash_in": 820_000_000}},
            context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        update_call = next(call for call in connector.connection.calls if "DATA_SUBMISSION_DRAFT_UPDATED" in call[0])
        self.assertEqual(submission["status"], "draft")
        self.assertEqual(submission["sections"]["financials"]["payload"]["revenue"], 830_000_000)
        self.assertEqual(submission["sections"]["financials"]["payload"]["cash_in"], 820_000_000)
        self.assertIsNone(submission["validated_at"])
        self.assertTrue(submission["policy_decision_id"])
        self.assertTrue(submission["audit_event_id"])
        self.assertIn("ON CONFLICT (submission_id, section_name)", sql_text)
        self.assertIn("DATA_SUBMISSION_DRAFT_UPDATED", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(update_call[1][8].count("financials"), 1)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_update_submission_rejects_locked_status(self) -> None:
        connector = _FakePostgresConnector([{"existing_status": "approved"}])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-update-locked",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        with self.assertRaisesRegex(ValueError, "Locked submission"):
            service.intake.update_submission(
                "5f6fd6e2-6a25-46e1-8197-f117487e4001",
                {"financials": {"revenue": 1}},
                context,
            )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertNotIn("DATA_SUBMISSION_DRAFT_UPDATED", sql_text)
        self.assertEqual(connector.connection.commits, 0)

    def test_postgres_pilot_csv_import_records_raw_rows_section_policy_and_audit(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-csv",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        batch = service.intake.create_import_batch(
            organization_id="BIZ-009",
            period_key="2026-09",
            dataset="products",
            file_name="products.csv",
            csv_text="sku,product_name,available_capacity\nSME-BEV-330,Ready drink,12000\n",
            context=context,
            submission_id="5f6fd6e2-6a25-46e1-8197-f117487e4001",
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        import_call = next(call for call in connector.connection.calls if "CSV_IMPORT_BATCH_PARSED" in call[0])
        self.assertEqual(batch["dataset"], "products")
        self.assertEqual(batch["file_name"], "products.csv")
        self.assertEqual(batch["row_count"], 1)
        self.assertEqual(batch["status"], "parsed")
        self.assertFalse(batch["idempotent_replay"])
        self.assertEqual(batch["preview_rows"][0]["sku"], "SME-BEV-330")
        self.assertTrue(batch["policy_decision_id"])
        self.assertTrue(batch["audit_event_id"])
        self.assertIn("INSERT INTO ingestion_batches", sql_text)
        self.assertIn("INSERT INTO raw_file_objects", sql_text)
        self.assertIn("INSERT INTO raw_records", sql_text)
        self.assertIn("INSERT INTO submission_sections", sql_text)
        self.assertIn("CSV_IMPORT_BATCH_PARSED", sql_text)
        self.assertEqual(import_call[1][8], "products")
        self.assertEqual(import_call[1][10], 1)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_error_report_returns_validation_and_raw_rows_with_csv(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-error-report",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        report = service.intake.error_report(
            "5f6fd6e2-6a25-46e1-8197-f117487e4001",
            context,
            report_format="csv",
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(report["format"], "csv")
        self.assertEqual(report["summary"], {"errors": 2, "warnings": 0, "infos": 0, "rows": 2})
        self.assertEqual(report["rows"][0]["source"], "validation_issue")
        self.assertEqual(report["rows"][1]["source"], "raw_record_error")
        self.assertIn("source,batch_id,dataset,file_name,row,column,path,code,severity,message,suggestion", report["csv"])
        self.assertTrue(report["policy_decision_id"])
        self.assertTrue(report["audit_event_id"])
        self.assertIn("DATA_SUBMISSION_ERROR_REPORT_VIEWED", sql_text)
        self.assertIn("raw_record_errors", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_validate_submission_records_issues_and_ready_status(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-validate",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.validate_submission("5f6fd6e2-6a25-46e1-8197-f117487e4001", context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        validate_call = next(call for call in connector.connection.calls if "DATA_SUBMISSION_VALIDATED" in call[0])
        self.assertEqual(submission["status"], "ready")
        self.assertEqual(submission["sections"]["financials"]["status"], "ready")
        self.assertEqual(submission["validation_summary"], {"errors": 0, "warnings": 0, "infos": 0})
        self.assertTrue(submission["validated_at"])
        self.assertTrue(submission["policy_decision_id"])
        self.assertTrue(submission["audit_event_id"])
        self.assertIn("DELETE FROM validation_issues", sql_text)
        self.assertIn("INSERT INTO validation_issues", sql_text)
        self.assertIn("DATA_SUBMISSION_VALIDATED", sql_text)
        self.assertEqual(json.loads(validate_call[1][8]), [])
        self.assertEqual(validate_call[1][9], "ready")
        self.assertEqual(validate_call[1][10], "validated")
        self.assertEqual(validate_call[1][11], "ready")
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_validate_submission_rejects_low_classification_financial_evidence(self) -> None:
        connector = _FakePostgresConnector(
            [
                {
                    "sections": [
                        {
                            "section_name": "evidence",
                            "payload": [
                                {
                                    "document_type": "GUARANTEE",
                                    "title": "Performance guarantee",
                                    "document_hash": "sha256:6a0b4e33f78d9a18",
                                    "classification": "confidential",
                                    "malware_scan_status": "clean",
                                }
                            ],
                        }
                    ]
                }
            ]
        )
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-validate-evidence-classification",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.validate_submission("5f6fd6e2-6a25-46e1-8197-f117487e4001", context)

        validate_call = next(call for call in connector.connection.calls if "DATA_SUBMISSION_VALIDATED" in call[0])
        issues = json.loads(validate_call[1][8])
        self.assertEqual(submission["status"], "draft")
        self.assertEqual(submission["validation_summary"]["errors"], 1)
        self.assertEqual(issues[0]["code"], "RESTRICTED_FINANCIAL_CLASSIFICATION_REQUIRED")
        self.assertEqual(validate_call[1][9], "has_errors")
        self.assertEqual(validate_call[1][10], "quarantined")
        self.assertEqual(validate_call[1][11], "draft")

    def test_postgres_pilot_submit_submission_validates_and_creates_review_task(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-submit",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.submit_submission("5f6fd6e2-6a25-46e1-8197-f117487e4001", context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(submission["status"], "in_review")
        self.assertIsNotNone(submission["submitted_at"])
        self.assertEqual(submission["review_task"]["status"], "open")
        self.assertEqual(submission["review_task"]["assigned_role"], "reviewer")
        self.assertEqual(submission["review_task"]["assigned_to"], "reviewer-oidc-1")
        self.assertEqual(submission["review_task"]["assignment_reason"], "auto_assigned_primary_org_reviewer")
        self.assertIn("DATA_SUBMISSION_VALIDATED", sql_text)
        self.assertIn("DATA_SUBMISSION_SUBMITTED", sql_text)
        self.assertIn("INSERT INTO review_tasks", sql_text)
        self.assertIn("assigned_to", sql_text)
        self.assertIn("assignment_reason", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 2)

    def test_postgres_pilot_submit_submission_stops_when_validation_has_errors(self) -> None:
        connector = _FakePostgresConnector(
            [
                {
                    "sections": [
                        {
                            "section_name": "financials",
                            "payload": {
                                "revenue": -1,
                                "cash_in": 1,
                                "cash_out": 1,
                                "debt": 0,
                                "accounts_receivable": 0,
                                "accounts_payable": 0,
                                "inventory_value": 0,
                            },
                        }
                    ]
                }
            ]
        )
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="sme_submitter",
            purpose="periodic_intake",
            scopes=frozenset({"finance:write"}),
            roles=frozenset({"sme_submitter"}),
            memberships=(Membership("BIZ-009", "sme_submitter"),),
            request_id="req-pilot-submit-errors",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.submit_submission("5f6fd6e2-6a25-46e1-8197-f117487e4001", context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(submission["status"], "draft")
        self.assertEqual(submission["validation_summary"]["errors"], 1)
        self.assertEqual(submission["issues"][0]["code"], "NEGATIVE_VALUE")
        self.assertNotIn("DATA_SUBMISSION_SUBMITTED", sql_text)
        self.assertNotIn("INSERT INTO review_tasks", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_review_approve_materializes_canonical_rows(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="reviewer-oidc-1",
            actor_role="reviewer",
            purpose="management_review",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"reviewer"}),
            memberships=(Membership("BIZ-009", "reviewer"),),
            request_id="req-pilot-review-approve",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.review_decision(
            "68f2c69b-c245-48cc-bec9-89cbbce45001",
            "approve",
            "Approved for pilot canonical snapshot.",
            context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        review_call = next(call for call in connector.connection.calls if "DATA_SUBMISSION_REVIEW_DECIDED" in call[0])
        self.assertEqual(submission["status"], "approved")
        self.assertEqual(submission["period"]["status"], "approved")
        self.assertEqual(submission["period"]["lock_version"], 2)
        self.assertTrue(submission["canonicalized_at"])
        self.assertEqual(submission["review_task"]["status"], "closed")
        self.assertEqual(submission["review_task"]["decision"], "approve")
        self.assertIn("INSERT INTO financial_snapshots", sql_text)
        self.assertIn("INSERT INTO product_capabilities", sql_text)
        self.assertIn("INSERT INTO evidence_documents", sql_text)
        self.assertIn("INSERT INTO evidence_versions", sql_text)
        self.assertIn("INSERT INTO feature_snapshots", sql_text)
        self.assertIn("INSERT INTO risk_runs", sql_text)
        self.assertIn("INSERT INTO match_runs", sql_text)
        self.assertIn("INSERT INTO match_candidates", sql_text)
        self.assertIn("INSERT INTO scenario_runs", sql_text)
        self.assertIn("scenario-rules-v0.1", sql_text)
        self.assertIn("INSERT INTO model_registry", sql_text)
        self.assertIn("INSERT INTO ruleset_registry", sql_text)
        self.assertIn("INSERT INTO analytics_recompute_jobs", sql_text)
        self.assertIn("approved_intake_materialized", sql_text)
        self.assertIn("pending_human_review", sql_text)
        self.assertIn("UPDATE reporting_periods", sql_text)
        self.assertIn("DATA_SUBMISSION_REVIEW_DECIDED", sql_text)
        self.assertEqual(review_call[1][12], "approve")
        self.assertEqual(review_call[1][14], "approved")
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_review_reject_does_not_approve_period_or_canonicalize(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="reviewer-oidc-1",
            actor_role="reviewer",
            purpose="management_review",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"reviewer"}),
            memberships=(Membership("BIZ-009", "reviewer"),),
            request_id="req-pilot-review-reject",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        submission = service.intake.review_decision(
            "68f2c69b-c245-48cc-bec9-89cbbce45001",
            "reject",
            "Rejected for missing support.",
            context,
        )

        review_call = next(call for call in connector.connection.calls if "DATA_SUBMISSION_REVIEW_DECIDED" in call[0])
        self.assertEqual(submission["status"], "rejected")
        self.assertEqual(submission["period"]["status"], "open")
        self.assertEqual(submission["period"]["lock_version"], 1)
        self.assertIsNone(submission["canonicalized_at"])
        self.assertEqual(submission["review_task"]["status"], "closed")
        self.assertEqual(submission["review_task"]["decision"], "reject")
        self.assertEqual(review_call[1][12], "reject")
        self.assertEqual(review_call[1][14], "rejected")
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_period_snapshot_reads_selected_approved_period(self) -> None:
        connector = _FakePostgresConnector(
            [
                {
                    "id": "6a44b8dd-e8e4-4067-a870-2c7c10c73001",
                    "tenant_id": "tenant-demo",
                    "organization_id": "BIZ-009",
                    "period_type": "month",
                    "period_key": "2026-07",
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-31",
                    "status": "approved",
                    "lock_version": 3,
                    "latest_submission_status": "approved",
                    "approved_version": 2,
                    "approved_at": "2026-07-31T10:00:00+00:00",
                    "review_decision": {
                        "review_task_id": "rev-2026-07",
                        "assigned_to": "reviewer-001",
                        "assignment_reason": "auto_assigned_primary_org_reviewer",
                        "decided_by": "reviewer-001",
                        "decision": "approve",
                        "decision_note": "Approved for pilot snapshot.",
                        "decided_at": "2026-07-31T10:00:00+00:00",
                    },
                    "financials": [{"version": 2, "revenue": 790_000_000, "source_submission_id": "sub-2026-07"}],
                    "evidence": [{"title": "HACCP July certificate", "malware_scan_status": "clean"}],
                    "source_submission_ids": ["sub-2026-07"],
                    "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a3001",
                    "audit_event_id": "3e337c27-3226-4d87-883d-273bce303001",
                }
            ]
        )
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="management_review",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-snapshot",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        snapshot = service.intake.period_snapshot("BIZ-009", "2026-07", context=context)

        snapshot_query = next(call for call in connector.connection.calls if "PERIOD_SNAPSHOT_READ" in call[0])
        self.assertEqual(snapshot["period"]["period_key"], "2026-07")
        self.assertEqual(snapshot["approved_version"], 2)
        self.assertEqual(snapshot["review_decision"]["review_task_id"], "rev-2026-07")
        self.assertEqual(snapshot["review_decision"]["decision_note"], "Approved for pilot snapshot.")
        self.assertEqual(snapshot["financials"][0]["revenue"], 790_000_000)
        self.assertEqual(snapshot["evidence"][0]["malware_scan_status"], "clean")
        self.assertNotIn("object_key", snapshot["evidence"][0])
        self.assertEqual(snapshot["products"], [])
        self.assertEqual(snapshot["source_submission_ids"], ["sub-2026-07"])
        self.assertTrue(snapshot["policy_decision_id"])
        self.assertTrue(snapshot["audit_event_id"])
        self.assertEqual(snapshot_query[1][4], "2026-07")
        self.assertIn("financial_snapshots", snapshot_query[0])
        self.assertIn("PERIOD_SNAPSHOT_READ", snapshot_query[0])
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_period_snapshot_does_not_fallback_without_approved_data(self) -> None:
        connector = _FakePostgresConnector(
            [
                {
                    "id": "6a44b8dd-e8e4-4067-a870-2c7c10c73002",
                    "tenant_id": "tenant-demo",
                    "organization_id": "BIZ-009",
                    "period_type": "month",
                    "period_key": "2026-08",
                    "period_start": "2026-08-01",
                    "period_end": "2026-08-31",
                    "status": "open",
                    "lock_version": 1,
                    "latest_submission_status": "in_review",
                    "approved_version": None,
                    "approved_at": None,
                    "financials": [],
                    "evidence": [],
                    "source_submission_ids": [],
                    "policy_decision_id": "43151c93-7528-4655-9b9f-4ec1ad2a3002",
                    "audit_event_id": "3e337c27-3226-4d87-883d-273bce303002",
                }
            ]
        )
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="management_review",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-snapshot-empty",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        snapshot = service.intake.period_snapshot("BIZ-009", "2026-08", context=context)

        snapshot_query = next(call for call in connector.connection.calls if "PERIOD_SNAPSHOT_READ" in call[0])
        self.assertEqual(snapshot["period"]["period_key"], "2026-08")
        self.assertIsNone(snapshot["approved_version"])
        self.assertIsNone(snapshot["review_decision"])
        self.assertEqual(snapshot["latest_submission_status"], "in_review")
        self.assertEqual(snapshot["financials"], [])
        self.assertEqual(snapshot["products"], [])
        self.assertEqual(snapshot["evidence"], [])
        self.assertEqual(snapshot["source_submission_ids"], [])
        self.assertEqual(snapshot_query[1][4], "2026-08")
        self.assertNotEqual(snapshot_query[1][4], "2026-07")
        self.assertTrue(snapshot["policy_decision_id"])
        self.assertTrue(snapshot["audit_event_id"])
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_consent_grant_and_revoke_use_db_policy_and_audit(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="management_review",
            scopes=frozenset({"finance:read"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-consent",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        granted = service.governance.create_consent(
            subject_id="BIZ-009",
            recipient_id="BIZ-062",
            scope="financial_summary",
            purpose="management_review",
            legal_basis="explicit_consent",
            expires_at=None,
            evidence_reference=None,
            context=context,
        )
        revoked = service.governance.revoke_consent(granted["consent_id"], context=context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        self.assertEqual(granted["status"], "granted")
        self.assertEqual(granted["subject_id"], "BIZ-009")
        self.assertEqual(granted["recipient_id"], "BIZ-062")
        self.assertTrue(granted["policy_decision_id"])
        self.assertTrue(granted["audit_event_id"])
        self.assertEqual(revoked["status"], "revoked")
        self.assertEqual(revoked["version"], 2)
        self.assertGreaterEqual(len(set_config_calls), 10)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 2)

    def test_postgres_pilot_evidence_upload_reserves_document_version_policy_and_audit(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="evidence_intake",
            scopes=frozenset({"evidence:write"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        ticket = service.governance.create_evidence_upload_url(
            organization_id="BIZ-009",
            file_name="haccp.pdf",
            content_type="application/pdf",
            byte_size=2048,
            classification="confidential",
            purpose="evidence_intake",
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        self.assertEqual(ticket["organization_id"], "BIZ-009")
        self.assertEqual(ticket["malware_scan_status"], "pending_scan")
        self.assertTrue(ticket["object_key"].endswith("-haccp.pdf"))
        self.assertTrue(ticket["upload_url"].startswith("object-storage-not-configured://"))
        self.assertEqual(ticket["object_storage_status"], "not_configured")
        self.assertEqual(ticket["upload_method"], "PUT")
        self.assertTrue(ticket["policy_decision_id"])
        self.assertTrue(ticket["audit_event_id"])
        self.assertGreaterEqual(len(set_config_calls), 5)
        self.assertIn("INSERT INTO evidence_documents", sql_text)
        self.assertIn("INSERT INTO evidence_versions", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_financial_evidence_upload_requires_restricted_classification(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="evidence_intake",
            scopes=frozenset({"evidence:write"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence-finance-classification",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        with self.assertRaisesRegex(ValueError, "restricted_financial"):
            service.governance.create_evidence_upload_url(
                organization_id="BIZ-009",
                file_name="guarantee.pdf",
                content_type="application/pdf",
                byte_size=2048,
                classification="confidential",
                purpose="evidence_intake",
                context=context,
                document_type="GUARANTEE",
            )

        self.assertEqual(connector.connection.calls, [])
        self.assertEqual(connector.connection.commits, 0)

    def test_postgres_pilot_evidence_upload_uses_s3_minio_presigned_url_when_configured(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService(
            "postgresql://user:pass@localhost/db",
            "pilot",
            connector=connector,
            object_storage=ObjectStorageSettings(
                endpoint_url="http://minio.local:9000",
                bucket="pilot-evidence",
                access_key_id="AKIA_TEST",
                secret_access_key="SECRET_TEST",
                region="ap-southeast-1",
                upload_ttl_seconds=600,
            ),
        )
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="evidence_intake",
            scopes=frozenset({"evidence:write"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence-signed",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        ticket = service.governance.create_evidence_upload_url(
            organization_id="BIZ-009",
            file_name="haccp.pdf",
            content_type="application/pdf",
            byte_size=2048,
            classification="confidential",
            purpose="evidence_intake",
            context=context,
        )

        parsed = urlsplit(ticket["upload_url"])
        query = parse_qs(parsed.query)
        self.assertEqual(ticket["object_storage_status"], "configured")
        self.assertEqual(ticket["expires_in_seconds"], 600)
        self.assertEqual(ticket["upload_method"], "PUT")
        self.assertTrue(ticket["object_key"].startswith("s3://pilot-evidence/tenant-demo/BIZ-009/"))
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.netloc, "minio.local:9000")
        self.assertTrue(parsed.path.startswith("/pilot-evidence/tenant-demo/BIZ-009/"))
        self.assertEqual(query["X-Amz-Algorithm"], ["AWS4-HMAC-SHA256"])
        self.assertEqual(query["X-Amz-Expires"], ["600"])
        self.assertEqual(query["X-Amz-SignedHeaders"], ["host"])
        self.assertIn("/ap-southeast-1/s3/aws4_request", query["X-Amz-Credential"][0])
        self.assertIn("X-Amz-Signature", query)
        self.assertNotIn("SECRET_TEST", ticket["upload_url"])

    def test_postgres_pilot_evidence_upload_ticket_list_and_complete_are_audited(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="evidence_intake",
            scopes=frozenset({"evidence:write"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence-ticket-lifecycle",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        listed = service.governance.list_evidence_upload_tickets(
            organization_id="BIZ-009",
            period_key="2026-09",
            context=context,
        )
        completed = service.governance.complete_evidence_upload_ticket(
            evidence_version_id="77bb9f91-e46e-4d4b-9bf2-5c4d857e2001",
            organization_id="BIZ-009",
            document_hash="sha256:6a0b4e33f78d9a18",
            malware_scan_status="clean",
            title="HACCP certificate upload",
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(listed["organization_id"], "BIZ-009")
        self.assertEqual(listed["period_key"], "2026-09")
        self.assertEqual(listed["tickets"][0]["evidence_version_id"], "77bb9f91-e46e-4d4b-9bf2-5c4d857e2001")
        self.assertNotIn("object_key", listed["tickets"][0])
        self.assertTrue(listed["policy_decision_id"])
        self.assertTrue(listed["audit_event_id"])
        self.assertEqual(completed["document_hash"], "sha256:6a0b4e33f78d9a18")
        self.assertEqual(completed["malware_scan_status"], "pending_scan")
        self.assertEqual(completed["object_storage_status"], "metadata_recorded")
        self.assertFalse(completed["usable"])
        self.assertNotIn("object_key", completed)
        self.assertIn("EVIDENCE_UPLOAD_TICKETS_VIEWED", sql_text)
        self.assertIn("EVIDENCE_UPLOAD_COMPLETED", sql_text)
        self.assertIn("UPDATE evidence_documents", sql_text)
        self.assertIn("UPDATE evidence_versions", sql_text)
        self.assertIn("ticket.evidence_version_id::text, ticket.classification", sql_text)
        self.assertIn("object_key_hash", sql_text)
        self.assertEqual(connector.connection.commits, 2)

        with self.assertRaises(PilotFeatureUnavailableError):
            service.governance.complete_evidence_upload_ticket(
                evidence_version_id="77bb9f91-e46e-4d4b-9bf2-5c4d857e2001",
                organization_id="BIZ-009",
                document_hash="sha256:6a0b4e33f78d9a18",
                malware_scan_status="pending_scan",
                title="base64 should not be used in pilot",
                context=context,
                content_base64="ZGVtbw==",
            )

    def test_postgres_pilot_evidence_version_records_hash_as_pending_scan(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="evidence_intake",
            scopes=frozenset({"evidence:write"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence-version",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        version = service.governance.add_evidence_version(
            evidence_document_id="9c292401-4679-4491-9f18-4908743e2001",
            organization_id="BIZ-009",
            object_key="s3://vietsupply-evidence/tenant-demo/BIZ-009/haccp.pdf",
            document_hash="sha256:6a0b4e33f78d9a18",
            content_type="application/pdf",
            byte_size=4096,
            malware_scan_status="clean",
            supersedes_version_id=None,
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        self.assertEqual(version["evidence_document_id"], "9c292401-4679-4491-9f18-4908743e2001")
        self.assertEqual(version["organization_id"], "BIZ-009")
        self.assertEqual(version["document_hash"], "sha256:6a0b4e33f78d9a18")
        self.assertEqual(version["malware_scan_status"], "pending_scan")
        self.assertFalse(version["usable"])
        self.assertTrue(version["policy_decision_id"])
        self.assertTrue(version["audit_event_id"])
        self.assertGreaterEqual(len(set_config_calls), 5)
        self.assertIn("INSERT INTO evidence_versions", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("EVIDENCE_VERSION_RECORDED", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_evidence_scan_result_requires_scanner_role_and_audits_status(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        uploader_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="owner-oidc-1",
            actor_role="org_admin",
            purpose="evidence_intake",
            scopes=frozenset({"evidence:write"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence-scan-denied",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )
        scanner_context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="scanner-oidc-1",
            actor_role="evidence_scanner",
            purpose="malware_scan",
            scopes=frozenset({"evidence:scan"}),
            roles=frozenset({"evidence_scanner"}),
            memberships=(Membership("BIZ-009", "evidence_scanner"),),
            request_id="req-pilot-evidence-scan",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        with self.assertRaises(AccessDeniedError):
            service.governance.record_evidence_scan_result(
                evidence_version_id="77bb9f91-e46e-4d4b-9bf2-5c4d857e2002",
                organization_id="BIZ-009",
                malware_scan_status="clean",
                scanner_name="local-clamav",
                scanner_version="1.4.3",
                scanned_at="2026-09-01T00:30:00Z",
                details=None,
                context=uploader_context,
            )

        result = service.governance.record_evidence_scan_result(
            evidence_version_id="77bb9f91-e46e-4d4b-9bf2-5c4d857e2002",
            organization_id="BIZ-009",
            malware_scan_status="clean",
            scanner_name="local-clamav",
            scanner_version="1.4.3",
            scanned_at="2026-09-01T00:30:00Z",
            details="Signature database current.",
            context=scanner_context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(result["malware_scan_status"], "clean")
        self.assertTrue(result["usable"])
        self.assertEqual(result["retention_status"], "active")
        self.assertTrue(result["policy_decision_id"])
        self.assertTrue(result["audit_event_id"])
        self.assertIn("UPDATE evidence_versions", sql_text)
        self.assertIn("EVIDENCE_SCAN_RESULT_RECORDED", sql_text)
        self.assertIn("scanner_name", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 1)

        infected = service.governance.record_evidence_scan_result(
            evidence_version_id="77bb9f91-e46e-4d4b-9bf2-5c4d857e2002",
            organization_id="BIZ-009",
            malware_scan_status="infected",
            scanner_name="local-clamav",
            scanner_version="1.4.3",
            scanned_at="2026-09-01T00:31:00Z",
            details="Malware signature matched.",
            context=scanner_context,
        )
        self.assertFalse(infected["usable"])
        self.assertEqual(infected["retention_status"], "retention_locked")

    def test_postgres_pilot_evidence_read_uses_policy_audit_and_grant_aware_query(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-062",
            actor_id="lender-oidc-1",
            actor_role="lender",
            purpose="lender_review",
            scopes=frozenset({"evidence:read"}),
            roles=frozenset({"lender"}),
            memberships=(Membership("BIZ-062", "lender"),),
            request_id="req-pilot-evidence-read",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        document = service.governance.get_evidence_document(
            "9c292401-4679-4491-9f18-4908743e2001",
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        self.assertEqual(document["evidence_document_id"], "9c292401-4679-4491-9f18-4908743e2001")
        self.assertEqual(document["organization_id"], "BIZ-009")
        self.assertEqual(document["versions"][0]["malware_scan_status"], "clean")
        self.assertNotIn("object_key", document["versions"][0])
        self.assertEqual(document["active_grants"][0]["grantee_organization_id"], "BIZ-062")
        self.assertEqual(document["active_grants"][0]["purpose"], "lender_review")
        self.assertTrue(document["policy_decision_id"])
        self.assertTrue(document["audit_event_id"])
        self.assertGreaterEqual(len(set_config_calls), 5)
        self.assertIn("EVIDENCE_DOCUMENT_READ", sql_text)
        self.assertIn("FROM evidence_access_grants grant_row", sql_text)
        self.assertIn("grant_row.purpose = %s", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("Evidence reads are metadata-only", document["advisory_notice"])
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_evidence_download_url_is_audited_get_ticket_without_object_key(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService(
            "postgresql://user:pass@localhost/db",
            "pilot",
            connector=connector,
            object_storage=ObjectStorageSettings(
                endpoint_url="http://minio.local:9000",
                bucket="pilot-evidence",
                access_key_id="AKIA_TEST",
                secret_access_key="SECRET_TEST",
                region="ap-southeast-1",
                upload_ttl_seconds=600,
                download_ttl_seconds=120,
            ),
        )
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-062",
            actor_id="lender-oidc-1",
            actor_role="lender",
            purpose="lender_review",
            scopes=frozenset({"evidence:read"}),
            roles=frozenset({"lender"}),
            memberships=(Membership("BIZ-062", "lender"),),
            request_id="req-pilot-evidence-download",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        ticket = service.governance.create_evidence_download_url(
            "77bb9f91-e46e-4d4b-9bf2-5c4d857e2002",
            context=context,
        )

        parsed = urlsplit(ticket["download_url"])
        query = parse_qs(parsed.query)
        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(ticket["download_method"], "GET")
        self.assertEqual(ticket["object_storage_status"], "configured")
        self.assertEqual(ticket["expires_in_seconds"], 120)
        self.assertEqual(ticket["malware_scan_status"], "clean")
        self.assertTrue(ticket["object_access_id"])
        self.assertNotIn("object_key", ticket)
        self.assertEqual(query["X-Amz-Algorithm"], ["AWS4-HMAC-SHA256"])
        self.assertEqual(query["X-Amz-Expires"], ["120"])
        self.assertIn("X-Amz-Signature", query)
        self.assertNotIn("SECRET_TEST", ticket["download_url"])
        self.assertIn("EVIDENCE_DOWNLOAD_URL_CREATED", sql_text)
        self.assertIn("INSERT INTO evidence_object_access_logs", sql_text)
        self.assertIn("object_key_hash", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_evidence_download_denies_pending_scan_and_audits(self) -> None:
        connector = _FakePostgresConnector([{"evidence_download_status": "pending_scan"}])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-062",
            actor_id="lender-oidc-1",
            actor_role="lender",
            purpose="lender_review",
            scopes=frozenset({"evidence:read"}),
            roles=frozenset({"lender"}),
            memberships=(Membership("BIZ-062", "lender"),),
            request_id="req-pilot-evidence-download-denied",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        with self.assertRaisesRegex(AccessDeniedError, "not downloadable"):
            service.governance.create_evidence_download_url(
                "77bb9f91-e46e-4d4b-9bf2-5c4d857e2002",
                context=context,
            )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        params_text = "\n".join(str(params) for _, params in connector.connection.calls)
        self.assertIn("EVIDENCE_DOWNLOAD_URL_DENIED", params_text)
        self.assertIn("INSERT INTO evidence_object_access_logs", sql_text)
        self.assertIn("download_denied", params_text)
        self.assertIn("'deny'", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_evidence_access_grant_and_revoke_use_policy_audit_and_scope(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="owner-oidc-1",
            actor_role="org_admin",
            purpose="evidence_access_review",
            scopes=frozenset({"evidence:admin"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence-grant",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        grant = service.governance.create_evidence_access_grant(
            evidence_document_id="9c292401-4679-4491-9f18-4908743e2001",
            organization_id="BIZ-009",
            grantee_organization_id="BIZ-062",
            scope="evidence_review",
            purpose="lender_review",
            expires_at="2026-12-31T23:59:59Z",
            context=context,
        )
        revoked = service.governance.revoke_evidence_access_grant(grant["grant_id"], context=context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        self.assertEqual(grant["status"], "active")
        self.assertEqual(grant["organization_id"], "BIZ-009")
        self.assertEqual(grant["grantee_organization_id"], "BIZ-062")
        self.assertEqual(grant["scope"], "evidence_review")
        self.assertEqual(revoked["status"], "revoked")
        self.assertTrue(grant["policy_decision_id"])
        self.assertTrue(grant["audit_event_id"])
        self.assertTrue(revoked["policy_decision_id"])
        self.assertTrue(revoked["audit_event_id"])
        self.assertGreaterEqual(len(set_config_calls), 10)
        self.assertIn("INSERT INTO evidence_access_grants", sql_text)
        self.assertIn("UPDATE evidence_access_grants", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("EVIDENCE_ACCESS_GRANTED", sql_text)
        self.assertIn("EVIDENCE_ACCESS_REVOKED", sql_text)
        self.assertEqual(connector.connection.commits, 2)

    def test_postgres_pilot_evidence_retention_updates_metadata_and_blocks_legal_hold_delete(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="owner-oidc-1",
            actor_role="org_admin",
            purpose="retention_review",
            scopes=frozenset({"evidence:admin"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-evidence-retention",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        retention = service.governance.update_evidence_retention(
            evidence_document_id="9c292401-4679-4491-9f18-4908743e2001",
            organization_id="BIZ-009",
            retention_status="retention_locked",
            legal_hold=True,
            reason="Active lender review.",
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(retention["retention_status"], "retention_locked")
        self.assertTrue(retention["legal_hold"])
        self.assertTrue(retention["policy_decision_id"])
        self.assertTrue(retention["audit_event_id"])
        self.assertIn("UPDATE evidence_documents", sql_text)
        self.assertIn("EVIDENCE_RETENTION_UPDATED", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 1)

        held_connector = _FakePostgresConnector([{"evidence_legal_hold": True}])
        held_service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=held_connector)
        with self.assertRaisesRegex(ValueError, "legal hold"):
            held_service.governance.update_evidence_retention(
                evidence_document_id="9c292401-4679-4491-9f18-4908743e2001",
                organization_id="BIZ-009",
                retention_status="deleted",
                legal_hold=False,
                reason="Retention period elapsed.",
                context=context,
            )

    def test_postgres_pilot_invoice_claim_registration_uses_policy_audit_and_duplicate_guard(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-062",
            actor_id="user-oidc-1",
            actor_role="lender",
            purpose="invoice_financing_review",
            scopes=frozenset({"invoice:write"}),
            roles=frozenset({"lender"}),
            memberships=(Membership("BIZ-062", "lender"),),
            request_id="req-pilot-invoice-claim",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        claim = service.governance.create_invoice_claim(
            seller_id="BIZ-005",
            buyer_id="BIZ-009",
            financier_id="BIZ-062",
            invoice_hash_value="abc1234567890def",
            amount=68_000_000,
            due_date="2026-07-08",
            invoice_id="INV-PG-001",
            issue_date="2026-06-08",
            currency="VND",
            idempotency_key="idem-pg-001",
            source_evidence_id=None,
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        set_config_calls = [call for call in connector.connection.calls if "set_config" in call[0]]
        self.assertEqual(claim["seller_id"], "BIZ-005")
        self.assertEqual(claim["buyer_id"], "BIZ-009")
        self.assertEqual(claim["financier_id"], "BIZ-062")
        self.assertEqual(claim["status"], "registered")
        self.assertEqual(claim["review_status"], "pending_review")
        self.assertEqual(claim["amount"], 68_000_000)
        self.assertTrue(claim["policy_decision_id"])
        self.assertTrue(claim["audit_event_id"])
        self.assertIn("does not confirm invoice authenticity", claim["advisory_notice"])
        self.assertGreaterEqual(len(set_config_calls), 5)
        self.assertIn("INSERT INTO invoice_claims", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("INVOICE_CLAIM_REGISTERED", sql_text)
        self.assertIn("status IN ('pledged', 'financed')", sql_text)
        self.assertEqual(connector.connection.commits, 1)

        conflict_connector = _FakePostgresConnector([{"active_invoice_conflict": True}])
        conflict_service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=conflict_connector)
        with self.assertRaisesRegex(ValueError, "active pledged/financed"):
            conflict_service.governance.create_invoice_claim(
                seller_id="BIZ-005",
                buyer_id="BIZ-009",
                financier_id="BIZ-062",
                invoice_hash_value="abc1234567890def",
                amount=68_000_000,
                due_date="2026-07-08",
                invoice_id="INV-PG-001",
                issue_date="2026-06-08",
                currency="VND",
                idempotency_key="idem-pg-conflict",
                source_evidence_id=None,
                context=context,
            )

    def test_postgres_pilot_invoice_claim_transition_uses_state_machine_and_review_gate(self) -> None:
        connector = _FakePostgresConnector([{"invoice_claim_status": "registered"}])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-005",
            actor_id="user-oidc-1",
            actor_role="lender",
            purpose="invoice_financing_review",
            scopes=frozenset({"invoice:write"}),
            roles=frozenset({"lender"}),
            memberships=(Membership("BIZ-005", "lender"),),
            request_id="req-pilot-invoice-transition",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        with self.assertRaisesRegex(ValueError, "Cannot transition invoice claim from registered to financed"):
            service.governance.transition_invoice_claim(
                "3cb3a2f6-e597-48cf-99fd-0a7c2f4b6001",
                "financed",
                "Cannot skip verification.",
                context=context,
            )

        updated = service.governance.transition_invoice_claim(
            "3cb3a2f6-e597-48cf-99fd-0a7c2f4b6001",
            "verified",
            "Counterparty details reviewed.",
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        self.assertEqual(updated["status"], "verified")
        self.assertEqual(updated["review_status"], "reviewed")
        self.assertEqual(updated["reviewer_id"], "user-oidc-1")
        self.assertTrue(updated["policy_decision_id"])
        self.assertTrue(updated["audit_event_id"])
        self.assertIn("INVOICE_CLAIM_TRANSITIONED", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_risk_runs_read_selected_period_with_policy_audit_and_provenance(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="user-oidc-1",
            actor_role="org_admin",
            purpose="risk_review",
            scopes=frozenset({"risk:read"}),
            roles=frozenset({"org_admin"}),
            memberships=(Membership("BIZ-009", "org_admin"),),
            request_id="req-pilot-risk-runs",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        payload = service.governance.list_risk_runs("BIZ-009", "2026-09", context=context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        run = payload["risk_runs"][0]
        self.assertEqual(payload["organization_id"], "BIZ-009")
        self.assertEqual(payload["period_key"], "2026-09")
        self.assertEqual(run["period_key"], "2026-09")
        self.assertEqual(run["feature_snapshot_id"], "1a77f087-29d8-4a45-afd1-fcb8af827001")
        self.assertEqual(run["model_version"], "rules-v1")
        self.assertEqual(run["ruleset_version"], "risk-rules-v1")
        self.assertEqual(run["review_status"], "pending_review")
        self.assertEqual(run["feature_payload"]["period_key"], "2026-09")
        self.assertTrue(payload["policy_decision_id"])
        self.assertTrue(payload["audit_event_id"])
        self.assertIn("RISK_RUNS_VIEWED", sql_text)
        self.assertIn("LEFT JOIN feature_snapshots", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("WHERE %s IS NULL OR rp.period_key = %s", sql_text)
        self.assertEqual(connector.connection.commits, 1)

        empty_connector = _FakePostgresConnector([{"analytics_no_period": True}])
        empty_service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=empty_connector)
        empty_payload = empty_service.governance.list_risk_runs("BIZ-009", "2026-02", context=context)
        self.assertEqual(empty_payload["period_key"], "2026-02")
        self.assertEqual(empty_payload["risk_runs"], [])

    def test_postgres_pilot_match_runs_read_candidates_with_policy_audit_and_review_status(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="analyst-oidc-1",
            actor_role="network_analyst",
            purpose="supplier_shortlist_review",
            scopes=frozenset({"matching:read"}),
            roles=frozenset({"network_analyst"}),
            memberships=(Membership("BIZ-009", "network_analyst"),),
            request_id="req-pilot-match-runs",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        payload = service.governance.list_match_runs("BIZ-009", "2026-09", context=context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        run = payload["match_runs"][0]
        candidate = run["candidates"][0]
        self.assertEqual(payload["organization_id"], "BIZ-009")
        self.assertEqual(payload["period_key"], "2026-09")
        self.assertEqual(run["period_key"], "2026-09")
        self.assertEqual(run["buyer_organization_id"], "BIZ-009")
        self.assertEqual(run["review_status"], "pending_review")
        self.assertEqual(candidate["supplier_organization_id"], "BIZ-018")
        self.assertEqual(candidate["consent_status"], "not_requested")
        self.assertEqual(candidate["explanation"]["capacity_fit"], "strong")
        self.assertTrue(payload["policy_decision_id"])
        self.assertTrue(payload["audit_event_id"])
        self.assertIn("MATCH_RUNS_VIEWED", sql_text)
        self.assertIn("FROM match_candidates candidate", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("Analytics outputs are versioned decision-support artifacts", payload["advisory_notice"])
        self.assertEqual(connector.connection.commits, 1)

    def test_postgres_pilot_scenario_runs_read_period_provenance_and_guardrail(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="analyst-oidc-1",
            actor_role="network_analyst",
            purpose="scenario_review",
            scopes=frozenset({"scenario:read"}),
            roles=frozenset({"network_analyst"}),
            memberships=(Membership("BIZ-009", "network_analyst"),),
            request_id="req-pilot-scenario-runs",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        payload = service.governance.list_scenario_runs("BIZ-009", "2026-09", context=context)

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        run = payload["scenario_runs"][0]
        self.assertEqual(payload["organization_id"], "BIZ-009")
        self.assertEqual(payload["period_key"], "2026-09")
        self.assertEqual(run["period_key"], "2026-09")
        self.assertEqual(run["input_snapshot_id"], "1a77f087-29d8-4a45-afd1-fcb8af827001")
        self.assertEqual(run["ruleset_version"], "scenario-rules-v0.1")
        self.assertEqual(run["model_version"], "deterministic-postgres-v0.1")
        self.assertEqual(run["review_status"], "pending_human_review")
        self.assertIn("human review", run["payload"]["guardrail"])
        self.assertTrue(payload["policy_decision_id"])
        self.assertTrue(payload["audit_event_id"])
        self.assertIn("SCENARIO_RUNS_VIEWED", sql_text)
        self.assertIn("LEFT JOIN scenario_runs", sql_text)
        self.assertIn("INSERT INTO policy_decisions", sql_text)
        self.assertIn("INSERT INTO audit_logs", sql_text)
        self.assertIn("Analytics outputs are versioned decision-support artifacts", payload["advisory_notice"])
        self.assertEqual(connector.connection.commits, 1)

        empty_connector = _FakePostgresConnector([{"analytics_no_period": True}])
        empty_service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=empty_connector)
        empty_payload = empty_service.governance.list_scenario_runs("BIZ-009", "2026-02", context=context)
        self.assertEqual(empty_payload["period_key"], "2026-02")
        self.assertEqual(empty_payload["scenario_runs"], [])

    def test_postgres_pilot_admin_ops_reads_registry_and_recompute_jobs_with_audit(self) -> None:
        connector = _FakePostgresConnector([])
        service = PostgresPilotService("postgresql://user:pass@localhost/db", "pilot", connector=connector)
        context = RequestContext(
            tenant_id="tenant-demo",
            organization_id="BIZ-009",
            actor_id="admin-oidc-1",
            actor_role="system_admin",
            purpose="ops_governance_review",
            scopes=frozenset({"ops:read"}),
            roles=frozenset({"system_admin"}),
            memberships=(Membership("BIZ-009", "system_admin"),),
            request_id="req-pilot-admin-ops",
            auth_assurance="oidc-jwks",
            app_mode="pilot",
        )

        models = service.governance.list_model_registry("risk", context=context)
        rulesets = service.governance.list_ruleset_registry("risk", context=context)
        jobs = service.governance.list_recompute_jobs(
            organization_id="BIZ-009",
            status="queued",
            limit=20,
            context=context,
        )

        sql_text = "\n".join(statement for statement, _ in connector.connection.calls)
        params_text = "\n".join(str(params) for _, params in connector.connection.calls)
        self.assertEqual(models["models"][0]["model_version"], "deterministic-postgres-v0.1")
        self.assertEqual(rulesets["rulesets"][0]["ruleset_version"], "intake-risk-rules-v0.1")
        self.assertEqual(jobs["jobs"][0]["status"], "queued")
        self.assertEqual(jobs["jobs"][0]["payload"]["reason"], "approved_intake_materialized")
        self.assertTrue(models["policy_decision_id"])
        self.assertTrue(rulesets["audit_event_id"])
        self.assertTrue(jobs["audit_event_id"])
        self.assertIn("FROM model_registry item", sql_text)
        self.assertIn("FROM ruleset_registry item", sql_text)
        self.assertIn("FROM analytics_recompute_jobs job", sql_text)
        self.assertIn("RECOMPUTE_JOBS_VIEWED", sql_text)
        self.assertIn("MODEL_REGISTRY_VIEWED", params_text)
        self.assertIn("RULESET_REGISTRY_VIEWED", params_text)
        self.assertGreaterEqual(connector.connection.commits, 3)


if __name__ == "__main__":
    unittest.main()
