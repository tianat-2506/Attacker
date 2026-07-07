from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.services.access_control import AccessDeniedError, PolicyService, RequestContext
from backend.app.services.database import Database
from backend.app.services.repositories import AuditRepository


P0_SECTIONS = ("profile", "financials", "products", "evidence")
INTAKE_NOTICE = (
    "Periodic intake supports management review only. Submitted data does not create a "
    "credit decision, legal breach finding or automatic supplier replacement."
)
DEFAULT_REVIEWER_ID = "reviewer-001"
EVIDENCE_REQUIREMENTS = (
    ("CERTIFICATION", "Operating certification", "Profile"),
    ("GUARANTEE", "Guarantee document", "Finance"),
    ("INVOICE", "Invoice evidence", "Invoice"),
    ("CONTRACT", "Commercial contract", "Relationship"),
)
RESTRICTED_FINANCIAL_EVIDENCE_TYPES = {"GUARANTEE", "INVOICE"}


class IntakeNotFoundError(KeyError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _load_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    return json.loads(raw)


def _period_dates(period_key: str) -> tuple[str, str]:
    year_text, month_text = period_key.split("-", maxsplit=1)
    year = int(year_text)
    month = int(month_text)
    last_day = calendar.monthrange(year, month)[1]
    return f"{period_key}-01", f"{period_key}-{last_day:02d}"


def _number(value: Any, default: float = 0) -> float:
    if value in (None, ""):
        return default
    return float(str(value).replace(",", "").strip())


def _int(value: Any, default: int = 0) -> int:
    return int(round(_number(value, default)))


def _rate(value: Any, default: float = 0) -> float:
    number = _number(value, default)
    return number / 100 if number > 1 else number


class PeriodicIntakeService:
    def __init__(self, database: Database, audit: AuditRepository) -> None:
        self.database = database
        self.audit = audit

    def _can_view_all_review_tasks(self, context: RequestContext) -> bool:
        return context.is_demo_actor() or context.has_role("demo_admin", "system_admin") or "policy:override" in context.scopes

    def _assigned_reviewer_for(self, organization_id: str) -> str:
        return DEFAULT_REVIEWER_ID

    def list_periods(self, organization_id: str, context: RequestContext | None = None) -> list[dict[str, Any]]:
        active_context = context or RequestContext.demo()
        decision = PolicyService.require(
            "read_financials",
            active_context,
            resource_type="reporting_period",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        self.audit.record_policy_decision(active_context, decision)
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                """
                SELECT rp.*, ps.approved_submission_id, ds.status AS latest_submission_status
                FROM reporting_periods rp
                LEFT JOIN period_snapshots ps ON ps.reporting_period_id = rp.reporting_period_id
                LEFT JOIN data_submissions ds ON ds.submission_id = (
                  SELECT submission_id
                  FROM data_submissions
                  WHERE reporting_period_id = rp.reporting_period_id
                  ORDER BY updated_at DESC
                  LIMIT 1
                )
                WHERE rp.organization_id = ?
                  AND rp.tenant_id = ?
                ORDER BY rp.period_start DESC
                """,
                (organization_id, active_context.tenant_id),
            ).fetchall()
        return [self._period_payload(dict(row)) for row in rows]

    def create_submission(
        self,
        *,
        organization_id: str,
        period_key: str,
        source_type: str,
        sections: dict[str, Any] | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        decision = PolicyService.require(
            "create_submission",
            context,
            resource_type="data_submission",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        self.audit.record_policy_decision(context, decision)
        now = _now()
        with closing(self.database.connect()) as connection:
            self._require_organization(connection, organization_id)
            period = self._ensure_period(connection, organization_id, period_key, context.tenant_id)
            row = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                FROM data_submissions
                WHERE organization_id = ? AND reporting_period_id = ?
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchone()
            version = int(row["next_version"] if row else 1)
            submission_id = _id("SUB")
            connection.execute(
                """
                INSERT INTO data_submissions (
                  submission_id, tenant_id, organization_id, reporting_period_id, source_type,
                  status, version, submitted_by, created_at, updated_at, submitted_at,
                  validated_at, canonicalized_at, locked_at
                )
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, NULL, NULL, NULL, NULL)
                """,
                (
                    submission_id,
                    period["tenant_id"],
                    organization_id,
                    period["reporting_period_id"],
                    source_type,
                    version,
                    context.actor_id,
                    now,
                    now,
                ),
            )
            for section_name, payload in (sections or {name: {} for name in P0_SECTIONS}).items():
                self._upsert_section(connection, submission_id, section_name, payload, "draft", now)
            connection.commit()
        self.audit.record_context("DATA_SUBMISSION_DRAFT_CREATED", context, submission_id, policy_decision=decision)
        return self.get_submission(submission_id)

    def get_submission(self, submission_id: str, context: RequestContext | None = None) -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            submission = self._submission_row(connection, submission_id)
            if context is not None:
                decision = PolicyService.require(
                    "read_financials",
                    context,
                    resource_type="data_submission",
                    resource_id=submission_id,
                    resource_organization_id=submission["organization_id"],
                    data_classification="restricted_financial",
                )
                self.audit.record_policy_decision(context, decision)
            sections = connection.execute(
                "SELECT * FROM submission_sections WHERE submission_id = ? ORDER BY section_name",
                (submission_id,),
            ).fetchall()
            issues = connection.execute(
                "SELECT * FROM validation_issues WHERE submission_id = ? ORDER BY severity, section_name, row_number",
                (submission_id,),
            ).fetchall()
            review = connection.execute(
                "SELECT * FROM review_tasks WHERE submission_id = ? ORDER BY created_at DESC LIMIT 1",
                (submission_id,),
            ).fetchone()
            period = connection.execute(
                "SELECT * FROM reporting_periods WHERE reporting_period_id = ?",
                (submission["reporting_period_id"],),
            ).fetchone()
        return self._submission_payload(dict(submission), [dict(row) for row in sections], [dict(row) for row in issues], dict(review) if review else None, dict(period))

    def update_submission(self, submission_id: str, sections: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        decision = None
        now = _now()
        with closing(self.database.connect()) as connection:
            submission = self._submission_row(connection, submission_id)
            decision = PolicyService.require(
                "update_submission",
                context,
                resource_type="data_submission",
                resource_id=submission_id,
                resource_organization_id=submission["organization_id"],
                data_classification="restricted_financial",
            )
            self.audit.record_policy_decision(context, decision)
            if submission["status"] in {"approved", "rejected", "superseded"}:
                raise ValueError("Locked submission cannot be edited.")
            for section_name, payload in sections.items():
                self._upsert_section(connection, submission_id, section_name, payload, "draft", now)
            connection.execute(
                "UPDATE data_submissions SET status = 'draft', updated_at = ?, validated_at = NULL WHERE submission_id = ?",
                (now, submission_id),
            )
            connection.commit()
        self.audit.record_context("DATA_SUBMISSION_DRAFT_UPDATED", context, submission_id, policy_decision=decision)
        return self.get_submission(submission_id)

    def create_import_batch(
        self,
        *,
        organization_id: str,
        period_key: str,
        dataset: str,
        file_name: str,
        csv_text: str,
        context: RequestContext,
        submission_id: str | None = None,
    ) -> dict[str, Any]:
        decision = PolicyService.require(
            "create_import_batch",
            context,
            resource_type="ingestion_batch",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        self.audit.record_policy_decision(context, decision)
        checksum = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        rows = list(csv.DictReader(io.StringIO(csv_text.strip()))) if csv_text.strip() else []
        if submission_id is None:
            submission = self.create_submission(
                organization_id=organization_id,
                period_key=period_key,
                source_type="csv",
                sections={dataset: [] if dataset in {"products", "evidence"} else {}},
                context=context,
            )
            submission_id = submission["id"]

        now = _now()
        with closing(self.database.connect()) as connection:
            submission = self._submission_row(connection, submission_id)
            existing = connection.execute(
                """
                SELECT * FROM ingestion_batches
                WHERE submission_id = ? AND dataset = ? AND checksum = ?
                """,
                (submission_id, dataset, checksum),
            ).fetchone()
            if existing:
                batch = dict(existing)
                raw_rows = connection.execute(
                    "SELECT payload_json FROM raw_records WHERE batch_id = ? ORDER BY row_number LIMIT 20",
                    (batch["batch_id"],),
                ).fetchall()
                return {
                    "id": batch["batch_id"],
                    "submission_id": submission_id,
                    "dataset": dataset,
                    "file_name": file_name,
                    "row_count": batch["row_count"],
                    "status": batch["status"],
                    "checksum": checksum,
                    "preview_rows": [_load_json(row["payload_json"], {}) for row in raw_rows],
                    "idempotent_replay": True,
                }

            batch_id = _id("BATCH")
            raw_file_id = _id("RAWFILE")
            connection.execute(
                """
                INSERT INTO ingestion_batches (
                  batch_id, submission_id, dataset, source_type, status, checksum, row_count, created_by, created_at
                )
                VALUES (?, ?, ?, 'csv', 'parsed', ?, ?, ?, ?)
                """,
                (batch_id, submission_id, dataset, checksum, len(rows), context.actor_id, now),
            )
            connection.execute(
                """
                INSERT INTO raw_file_objects (
                  raw_file_id, batch_id, submission_id, file_name, object_key, checksum,
                  content_type, byte_size, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'text/csv', ?, ?)
                """,
                (raw_file_id, batch_id, submission_id, file_name, f"raw/{submission_id}/{file_name}", checksum, len(csv_text.encode("utf-8")), now),
            )
            for index, row in enumerate(rows, start=1):
                connection.execute(
                    """
                    INSERT INTO raw_records (
                      raw_record_id, batch_id, raw_file_id, row_number, payload_json, normalized_key, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_id("RAW"), batch_id, raw_file_id, index, _json(dict(row)), self._normalized_key(dataset, row, index), now),
                )
            parsed_payload = self._csv_payload(dataset, rows)
            self._upsert_section(connection, submission_id, dataset, parsed_payload, "draft", now)
            connection.execute("UPDATE data_submissions SET updated_at = ?, status = 'draft' WHERE submission_id = ?", (now, submission_id))
            connection.commit()
        self.audit.record_context("CSV_IMPORT_BATCH_PARSED", context, submission_id, policy_decision=decision)
        return {
            "id": batch_id,
            "submission_id": submission_id,
            "dataset": dataset,
            "file_name": file_name,
            "row_count": len(rows),
            "status": "parsed",
            "checksum": checksum,
            "preview_rows": rows[:20],
            "idempotent_replay": False,
        }

    def validate_submission(self, submission_id: str, context: RequestContext) -> dict[str, Any]:
        decision = None
        now = _now()
        with closing(self.database.connect()) as connection:
            submission = self._submission_row(connection, submission_id)
            decision = PolicyService.require(
                "validate_submission",
                context,
                resource_type="data_submission",
                resource_id=submission_id,
                resource_organization_id=submission["organization_id"],
                data_classification="restricted_financial",
            )
            self.audit.record_policy_decision(context, decision)
            sections = connection.execute(
                "SELECT * FROM submission_sections WHERE submission_id = ? ORDER BY section_name",
                (submission_id,),
            ).fetchall()
            connection.execute("DELETE FROM validation_issues WHERE submission_id = ?", (submission_id,))
            self._clear_raw_record_errors(connection, submission_id)
            issues = self._validate_sections([dict(row) for row in sections])
            for issue in issues:
                connection.execute(
                    """
                    INSERT INTO validation_issues (
                      issue_id, submission_id, section_name, path, row_number, column_name,
                      code, severity, message, suggestion, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _id("ISSUE"),
                        submission_id,
                        issue["section"],
                        issue["path"],
                        issue.get("row"),
                        issue.get("column"),
                        issue["code"],
                        issue["severity"],
                        issue["message"],
                        issue.get("suggestion"),
                        now,
                    ),
                )
            self._record_raw_record_errors(connection, submission_id, issues, now)
            error_count = len([issue for issue in issues if issue["severity"] == "error"])
            status = "ready" if error_count == 0 else "draft"
            section_status = "ready" if error_count == 0 else "has_errors"
            batch_status = "quarantined" if error_count else "validated"
            for row in sections:
                connection.execute(
                    "UPDATE submission_sections SET status = ?, updated_at = ? WHERE section_id = ?",
                    (section_status, now, row["section_id"]),
                )
            connection.execute(
                "UPDATE ingestion_batches SET status = ? WHERE submission_id = ?",
                (batch_status, submission_id),
            )
            connection.execute(
                "UPDATE data_submissions SET status = ?, validated_at = ?, updated_at = ? WHERE submission_id = ?",
                (status, now, now, submission["submission_id"]),
            )
            connection.commit()
        self.audit.record_context("DATA_SUBMISSION_VALIDATED", context, submission_id, policy_decision=decision)
        return self.get_submission(submission_id)

    def error_report(self, submission_id: str, context: RequestContext, report_format: str = "json") -> dict[str, Any]:
        with closing(self.database.connect()) as connection:
            submission = self._submission_row(connection, submission_id)
            decision = PolicyService.require(
                "read_financials",
                context,
                resource_type="data_submission_error_report",
                resource_id=submission_id,
                resource_organization_id=submission["organization_id"],
                data_classification="restricted_financial",
            )
            self.audit.record_policy_decision(context, decision)
            issues = connection.execute(
                """
                SELECT vi.*, ib.batch_id, ib.dataset, rf.file_name, rr.raw_record_id, rr.payload_json
                FROM validation_issues vi
                LEFT JOIN ingestion_batches ib ON ib.submission_id = vi.submission_id AND ib.dataset = vi.section_name
                LEFT JOIN raw_records rr ON rr.batch_id = ib.batch_id AND rr.row_number = vi.row_number
                LEFT JOIN raw_file_objects rf ON rf.raw_file_id = rr.raw_file_id
                WHERE vi.submission_id = ?
                ORDER BY vi.severity, vi.section_name, vi.row_number, vi.path
                """,
                (submission_id,),
            ).fetchall()
            raw_errors = connection.execute(
                """
                SELECT rre.*, rr.row_number, rr.payload_json, ib.batch_id, ib.dataset, rf.file_name
                FROM raw_record_errors rre
                JOIN raw_records rr ON rr.raw_record_id = rre.raw_record_id
                JOIN ingestion_batches ib ON ib.batch_id = rr.batch_id
                LEFT JOIN raw_file_objects rf ON rf.raw_file_id = rr.raw_file_id
                WHERE ib.submission_id = ?
                ORDER BY ib.dataset, rr.row_number, rre.severity, rre.code
                """,
                (submission_id,),
            ).fetchall()
        issue_rows = [self._error_report_row(dict(row), "validation_issue") for row in issues]
        raw_rows = [self._raw_error_report_row(dict(row)) for row in raw_errors]
        rows = issue_rows + raw_rows
        summary = {
            "errors": len([row for row in rows if row["severity"] == "error"]),
            "warnings": len([row for row in rows if row["severity"] == "warning"]),
            "infos": len([row for row in rows if row["severity"] == "info"]),
            "rows": len(rows),
        }
        event_id = self.audit.record_context(
            "DATA_SUBMISSION_ERROR_REPORT_VIEWED",
            context,
            submission_id,
            policy_decision=decision,
            payload={"format": report_format, "row_count": len(rows)},
        )
        csv_text = self._error_report_csv(rows) if report_format == "csv" else None
        return {
            "submission_id": submission_id,
            "format": report_format,
            "summary": summary,
            "rows": rows,
            "csv": csv_text,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Fix validation errors before submission can proceed to review.",
        }

    def list_review_tasks(self, context: RequestContext, status: str = "open", limit: int = 25) -> dict[str, Any]:
        if status not in {"open", "closed", "all"}:
            raise ValueError("status must be open, closed or all.")
        bounded_limit = max(1, min(limit, 100))
        decision = PolicyService.require(
            "review_submission",
            context,
            resource_type="review_queue",
            resource_id=status,
            data_classification="restricted_financial",
        )
        self.audit.record_policy_decision(context, decision)
        status_clause = "" if status == "all" else "AND review.status = ?"
        can_view_all = self._can_view_all_review_tasks(context)
        scoped_organization_ids = sorted(context.organization_ids)
        organization_clause = ""
        assignment_clause = ""
        params: list[Any] = [context.tenant_id]
        if not can_view_all:
            if not scoped_organization_ids:
                event_id = self.audit.record_context(
                    "DATA_SUBMISSION_REVIEW_QUEUE_VIEWED",
                    context,
                    status,
                    policy_decision=decision,
                    payload={"status": status, "limit": bounded_limit, "count": 0, "scope": "no_active_membership"},
                )
                return {
                    "review_tasks": [],
                    "policy_decision_id": decision.decision_id,
                    "audit_event_id": event_id,
                    "advisory_notice": "Review queue supports human approval only; it is not an automated financing or legal decision.",
                }
            placeholders = ", ".join("?" for _ in scoped_organization_ids)
            organization_clause = f"AND submission.organization_id IN ({placeholders})"
            params.extend(scoped_organization_ids)
            assignment_clause = "AND review.assigned_to = ?"
            params.append(context.actor_id)
        if status != "all":
            params.append(status)
        params.append(bounded_limit)
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                  review.*,
                  submission.tenant_id,
                  submission.organization_id,
                  submission.reporting_period_id,
                  submission.status AS submission_status,
                  submission.source_type,
                  submission.version,
                  submission.submitted_by,
                  review.assigned_to,
                  review.assignment_reason,
                  review.assigned_at,
                  submission.submitted_at,
                  submission.updated_at,
                  period.period_key,
                  period.period_start,
                  period.period_end,
                  COALESCE(profile.trade_name, submission.organization_id) AS organization_name,
                  (
                    SELECT COUNT(*)
                    FROM validation_issues issue
                    WHERE issue.submission_id = submission.submission_id AND issue.severity = 'error'
                  ) AS error_count,
                  (
                    SELECT COUNT(*)
                    FROM validation_issues issue
                    WHERE issue.submission_id = submission.submission_id AND issue.severity = 'warning'
                  ) AS warning_count,
                  (
                    SELECT COUNT(*)
                    FROM validation_issues issue
                    WHERE issue.submission_id = submission.submission_id AND issue.severity = 'info'
                  ) AS info_count,
                  (
                    SELECT GROUP_CONCAT(section.section_name || ':' || section.status, ',')
                    FROM submission_sections section
                    WHERE section.submission_id = submission.submission_id
                  ) AS section_statuses
                FROM review_tasks review
                JOIN data_submissions submission ON submission.submission_id = review.submission_id
                JOIN reporting_periods period ON period.reporting_period_id = submission.reporting_period_id
                LEFT JOIN business_profiles profile ON profile.organization_id = submission.organization_id
                WHERE submission.tenant_id = ?
                  {organization_clause}
                  {assignment_clause}
                  {status_clause}
                ORDER BY
                  CASE review.status WHEN 'open' THEN 0 ELSE 1 END,
                  submission.submitted_at DESC,
                  review.created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            review_tasks = [self._review_queue_item(dict(row), connection) for row in rows]
        event_id = self.audit.record_context(
            "DATA_SUBMISSION_REVIEW_QUEUE_VIEWED",
            context,
            status,
            policy_decision=decision,
            payload={"status": status, "limit": bounded_limit, "count": len(review_tasks)},
        )
        return {
            "review_tasks": review_tasks,
            "policy_decision_id": decision.decision_id,
            "audit_event_id": event_id,
            "advisory_notice": "Review queue supports human approval only; it is not an automated financing or legal decision.",
        }

    def submit_submission(self, submission_id: str, context: RequestContext) -> dict[str, Any]:
        submission = self.validate_submission(submission_id, context)
        if submission["validation_summary"]["errors"]:
            return submission
        now = _now()
        with closing(self.database.connect()) as connection:
            row = self._submission_row(connection, submission_id)
            decision = PolicyService.require(
                "submit_submission",
                context,
                resource_type="data_submission",
                resource_id=submission_id,
                resource_organization_id=row["organization_id"],
                data_classification="restricted_financial",
            )
            self.audit.record_policy_decision(context, decision)
            connection.execute(
                """
                UPDATE data_submissions
                SET status = 'in_review', submitted_at = ?, locked_at = ?, updated_at = ?
                WHERE submission_id = ?
                """,
                (now, now, now, submission_id),
            )
            connection.execute(
                """
                INSERT INTO review_tasks (
                  review_task_id, submission_id, status, assigned_role, assigned_to,
                  assignment_reason, assigned_at, decided_by, decision, decision_note,
                  created_at, decided_at
                )
                VALUES (?, ?, 'open', 'reviewer', ?, ?, ?, NULL, NULL, NULL, ?, NULL)
                """,
                (
                    _id("REV"),
                    submission_id,
                    self._assigned_reviewer_for(row["organization_id"]),
                    "auto_assigned_primary_org_reviewer",
                    now,
                    now,
                ),
            )
            connection.commit()
        self.audit.record_context("DATA_SUBMISSION_SUBMITTED", context, submission_id, policy_decision=decision)
        return self.get_submission(submission_id)

    def review_decision(self, review_task_id: str, decision: str, note: str | None, context: RequestContext) -> dict[str, Any]:
        if decision not in {"approve", "reject", "request_changes"}:
            raise ValueError("Unsupported review decision.")
        now = _now()
        with closing(self.database.connect()) as connection:
            review = connection.execute("SELECT * FROM review_tasks WHERE review_task_id = ?", (review_task_id,)).fetchone()
            if review is None:
                raise IntakeNotFoundError(review_task_id)
            submission = self._submission_row(connection, review["submission_id"])
            decision_record = PolicyService.require(
                "review_submission",
                context,
                resource_type="review_task",
                resource_id=review_task_id,
                resource_organization_id=submission["organization_id"],
                data_classification="restricted_financial",
            )
            self.audit.record_policy_decision(context, decision_record)
            if not self._can_view_all_review_tasks(context) and review["assigned_to"] != context.actor_id:
                raise AccessDeniedError(
                    "POLICY_DENIED",
                    "Review task is assigned to a different reviewer.",
                    status_code=403,
                )
            evidence_review = self._evidence_review_summary(connection, dict(submission))
            if decision == "approve" and evidence_review["approval_blocked"]:
                self.audit.record_context(
                    "DATA_SUBMISSION_REVIEW_APPROVAL_BLOCKED",
                    context,
                    review["submission_id"],
                    policy_decision=decision_record,
                    payload={"evidence_review": evidence_review},
                )
                raise ValueError("Approval blocked until submitted or uploaded evidence for this period has clean malware scan status.")
            status = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested"}[decision]
            connection.execute(
                """
                UPDATE review_tasks
                SET status = 'closed', decided_by = ?, decision = ?, decision_note = ?, decided_at = ?
                WHERE review_task_id = ?
                """,
                (context.actor_id, decision, note, now, review_task_id),
            )
            connection.execute(
                "UPDATE data_submissions SET status = ?, updated_at = ? WHERE submission_id = ?",
                (status, now, submission["submission_id"]),
            )
            if decision == "approve":
                self._materialize(connection, dict(submission), now)
                connection.execute(
                    """
                    UPDATE data_submissions
                    SET canonicalized_at = ?, updated_at = ?
                    WHERE submission_id = ?
                    """,
                    (now, now, submission["submission_id"]),
                )
            connection.commit()
        self.audit.record_context("DATA_SUBMISSION_REVIEW_DECIDED", context, review["submission_id"], policy_decision=decision_record)
        return self.get_submission(review["submission_id"])

    def period_snapshot(self, organization_id: str, period_key: str, context: RequestContext | None = None) -> dict[str, Any]:
        active_context = context or RequestContext.demo()
        decision = PolicyService.require(
            "read_financials",
            active_context,
            resource_type="period_snapshot",
            resource_id=f"{organization_id}:{period_key}",
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        self.audit.record_policy_decision(active_context, decision)
        with closing(self.database.connect()) as connection:
            period = connection.execute(
                """
                SELECT * FROM reporting_periods
                WHERE organization_id = ? AND period_key = ? AND tenant_id = ?
                """,
                (organization_id, period_key, active_context.tenant_id),
            ).fetchone()
            if period is None:
                return self._empty_snapshot(organization_id, period_key, None)
            snapshot = connection.execute(
                "SELECT * FROM period_snapshots WHERE organization_id = ? AND reporting_period_id = ?",
                (organization_id, period["reporting_period_id"]),
            ).fetchone()
            latest_submission = connection.execute(
                """
                SELECT * FROM data_submissions
                WHERE organization_id = ? AND reporting_period_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchone()
            if snapshot is None:
                return self._empty_snapshot(organization_id, period_key, dict(latest_submission) if latest_submission else None)
            financials = connection.execute(
                """
                SELECT * FROM period_financial_snapshots
                WHERE organization_id = ? AND reporting_period_id = ?
                ORDER BY version DESC
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchall()
            products = connection.execute(
                """
                SELECT * FROM product_capabilities
                WHERE organization_id = ? AND reporting_period_id = ?
                ORDER BY sku
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchall()
            evidence = connection.execute(
                """
                SELECT * FROM evidence_documents
                WHERE organization_id = ? AND reporting_period_id = ?
                ORDER BY created_at DESC
                """,
                (organization_id, period["reporting_period_id"]),
            ).fetchall()
            review_decision = self._snapshot_review_decision(connection, snapshot["approved_submission_id"])
        return {
            "business_id": organization_id,
            "organization_id": organization_id,
            "period": self._period_payload(dict(period)),
            "approved_version": snapshot["approved_version"],
            "approved_at": snapshot["approved_at"],
            "review_decision": review_decision,
            "latest_submission_status": latest_submission["status"] if latest_submission else None,
            "sections": _load_json(snapshot["summary_json"], {}),
            "financials": [dict(row) for row in financials],
            "products": [dict(row) for row in products],
            "evidence": [self._public_evidence_row(dict(row)) for row in evidence],
            "source_submission_ids": _load_json(snapshot["source_submission_ids_json"], []),
            "advisory_notice": INTAKE_NOTICE,
            "policy_decision_id": decision.decision_id,
        }

    def _public_evidence_row(self, row: dict[str, Any]) -> dict[str, Any]:
        row.pop("object_key", None)
        return row

    def _snapshot_review_decision(self, connection: Any, submission_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT review_task_id, assigned_to, assignment_reason, decided_by, decision, decision_note, decided_at
            FROM review_tasks
            WHERE submission_id = ? AND status = 'closed'
            ORDER BY decided_at DESC, created_at DESC
            LIMIT 1
            """,
            (submission_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "review_task_id": row["review_task_id"],
            "assigned_to": row["assigned_to"],
            "assignment_reason": row["assignment_reason"],
            "decided_by": row["decided_by"],
            "decision": row["decision"],
            "decision_note": row["decision_note"],
            "decided_at": row["decided_at"],
        }

    def _materialize(self, connection: Any, submission: dict[str, Any], now: str) -> None:
        sections = {
            row["section_name"]: _load_json(row["payload_json"], {})
            for row in connection.execute(
                "SELECT * FROM submission_sections WHERE submission_id = ?",
                (submission["submission_id"],),
            ).fetchall()
        }
        period = connection.execute(
            "SELECT * FROM reporting_periods WHERE reporting_period_id = ?",
            (submission["reporting_period_id"],),
        ).fetchone()
        if period is None:
            raise IntakeNotFoundError(submission["reporting_period_id"])
        source_record_id = f"SECTION-{submission['submission_id']}"
        raw_lineage = self._raw_record_lineage(connection, submission["submission_id"])
        financials = sections.get("financials") or {}
        if financials:
            financial_source_record_id = self._source_record_id(raw_lineage, "financials", 1, source_record_id)
            connection.execute(
                """
                INSERT OR REPLACE INTO period_financial_snapshots (
                  snapshot_id, tenant_id, organization_id, reporting_period_id, statement_type,
                  version, revenue, cash_in, cash_out, debt, accounts_receivable, accounts_payable,
                  inventory_value, late_payment_rate, delivery_delay_rate, source_submission_id,
                  source_record_id, valid_from, valid_to, created_at
                )
                VALUES (?, ?, ?, ?, 'management', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    f"PFS-{submission['organization_id']}-{period['period_key']}-V{submission['version']}",
                    submission["tenant_id"],
                    submission["organization_id"],
                    submission["reporting_period_id"],
                    submission["version"],
                    _int(financials.get("revenue")),
                    _int(financials.get("cash_in")),
                    _int(financials.get("cash_out")),
                    _int(financials.get("debt")),
                    _int(financials.get("accounts_receivable")),
                    _int(financials.get("accounts_payable")),
                    _int(financials.get("inventory_value")),
                    _rate(financials.get("late_payment_rate")),
                    _rate(financials.get("delivery_delay_rate")),
                    submission["submission_id"],
                    financial_source_record_id,
                    period["period_start"],
                    now,
                ),
            )

        for index, item in enumerate(self._list_payload(sections.get("products")), start=1):
            sku = str(item.get("sku") or f"SKU-{index:03d}")
            item_source_record_id = self._source_record_id(raw_lineage, "products", index, f"{source_record_id}-PRODUCT-{index}")
            connection.execute(
                """
                INSERT OR REPLACE INTO product_capabilities (
                  capability_id, tenant_id, organization_id, reporting_period_id, sku, product_name,
                  category, specification, available_capacity, min_order_value, price_range,
                  certifications, shelf_life_days, temperature_band, packaging_type, case_pack,
                  substitution_group, source_submission_id, source_record_id, valid_from, valid_to, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    f"PC-{submission['organization_id']}-{period['period_key']}-{sku}-{submission['version']}",
                    submission["tenant_id"],
                    submission["organization_id"],
                    submission["reporting_period_id"],
                    sku,
                    str(item.get("product_name") or item.get("name") or "Submitted product"),
                    str(item.get("category") or "beverage"),
                    str(item.get("specification") or ""),
                    _int(item.get("available_capacity")),
                    _int(item.get("min_order_value")),
                    str(item.get("price_range") or "not_provided"),
                    str(item.get("certifications") or ""),
                    _int(item.get("shelf_life_days"), 180),
                    str(item.get("temperature_band") or "ambient"),
                    str(item.get("packaging_type") or "case"),
                    str(item.get("case_pack") or "standard"),
                    str(item.get("substitution_group") or item.get("category") or "general"),
                    submission["submission_id"],
                    item_source_record_id,
                    period["period_start"],
                    now,
                ),
            )

        for index, item in enumerate(self._list_payload(sections.get("evidence")), start=1):
            malware_scan_status = str(item.get("malware_scan_status") or "pending_scan")
            if malware_scan_status != "clean":
                continue
            item_source_record_id = self._source_record_id(raw_lineage, "evidence", index, f"{source_record_id}-EVIDENCE-{index}")
            title = str(item.get("title") or item.get("file_name") or f"Evidence {index}")
            digest = str(item.get("document_hash") or hashlib.sha256(title.encode("utf-8")).hexdigest())
            connection.execute(
                """
                INSERT OR REPLACE INTO evidence_documents (
                  evidence_document_id, tenant_id, organization_id, reporting_period_id,
                  document_type, title, object_key, document_hash, classification,
                  malware_scan_status, retention_status, source_submission_id, source_record_id,
                  valid_from, valid_to, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL, ?)
                """,
                (
                    f"EVD-{submission['organization_id']}-{period['period_key']}-{index}-{submission['version']}",
                    submission["tenant_id"],
                    submission["organization_id"],
                    submission["reporting_period_id"],
                    str(item.get("document_type") or item.get("type") or "SUPPORTING_DOCUMENT"),
                    title,
                    str(item.get("object_key") or f"demo/{submission['submission_id']}/{title}"),
                    digest,
                    str(item.get("classification") or "confidential"),
                    malware_scan_status,
                    submission["submission_id"],
                    item_source_record_id,
                    period["period_start"],
                    now,
                ),
            )

        approved_evidence_rows = connection.execute(
            """
            SELECT evidence_document_id, source_submission_id
            FROM evidence_documents
            WHERE tenant_id = ?
              AND organization_id = ?
              AND reporting_period_id = ?
              AND LOWER(COALESCE(malware_scan_status, '')) = 'clean'
            ORDER BY created_at, evidence_document_id
            """,
            (submission["tenant_id"], submission["organization_id"], submission["reporting_period_id"]),
        ).fetchall()
        approved_evidence_count = len(approved_evidence_rows)
        source_submission_ids = [submission["submission_id"]]
        for evidence_row in approved_evidence_rows:
            source_submission_id = evidence_row["source_submission_id"]
            if source_submission_id and source_submission_id not in source_submission_ids:
                source_submission_ids.append(source_submission_id)

        summary = {
            "profile": {"status": "approved" if sections.get("profile") else "not_submitted"},
            "financials": {"status": "approved" if financials else "not_submitted", "revenue": _int(financials.get("revenue")) if financials else 0},
            "products": {"status": "approved", "count": len(self._list_payload(sections.get("products")))},
            "evidence": {"status": "approved_clean_only", "count": approved_evidence_count},
        }
        connection.execute(
            """
            INSERT OR REPLACE INTO period_snapshots (
              period_snapshot_id, tenant_id, organization_id, reporting_period_id,
              approved_submission_id, approved_version, approved_at, summary_json, source_submission_ids_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"PS-{submission['organization_id']}-{period['period_key']}",
                submission["tenant_id"],
                submission["organization_id"],
                submission["reporting_period_id"],
                submission["submission_id"],
                submission["version"],
                now,
                _json(summary),
                _json(source_submission_ids),
            ),
        )
        connection.execute(
            "UPDATE reporting_periods SET status = 'approved', lock_version = lock_version + 1 WHERE reporting_period_id = ?",
            (submission["reporting_period_id"],),
        )
        self._record_versioned_artifacts(connection, submission, dict(period), financials, self._list_payload(sections.get("products")), now)

    def _raw_record_lineage(self, connection: Any, submission_id: str) -> dict[str, list[str]]:
        rows = connection.execute(
            """
            SELECT batch.dataset, record.raw_record_id
            FROM raw_records record
            JOIN ingestion_batches batch ON batch.batch_id = record.batch_id
            WHERE batch.submission_id = ?
            ORDER BY batch.dataset, record.row_number
            """,
            (submission_id,),
        ).fetchall()
        lineage: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            lineage[row["dataset"]].append(row["raw_record_id"])
        return lineage

    def _source_record_id(self, raw_lineage: dict[str, list[str]], dataset: str, row_number: int, fallback: str) -> str:
        rows = raw_lineage.get(dataset) or []
        if 0 < row_number <= len(rows):
            return rows[row_number - 1]
        return fallback

    def _record_versioned_artifacts(
        self,
        connection: Any,
        submission: dict[str, Any],
        period: dict[str, Any],
        financials: dict[str, Any],
        products: list[dict[str, Any]],
        now: str,
    ) -> None:
        feature_snapshot_id = f"FS-{submission['submission_id']}"
        revenue = max(1, _int(financials.get("revenue")))
        net_cashflow = _int(financials.get("cash_in")) - _int(financials.get("cash_out"))
        debt_ratio = _int(financials.get("debt")) / revenue
        late_rate = _rate(financials.get("late_payment_rate"))
        delay_rate = _rate(financials.get("delivery_delay_rate"))
        feature_payload = {
            "source_submission_id": submission["submission_id"],
            "period_key": period["period_key"],
            "net_cashflow": net_cashflow,
            "debt_to_monthly_revenue": round(debt_ratio, 4),
            "late_payment_rate": late_rate,
            "delivery_delay_rate": delay_rate,
            "product_count": len(products),
            "notice": "Feature snapshot is for management review; not a credit score input without lender approval.",
        }
        connection.execute(
            """
            INSERT OR REPLACE INTO feature_snapshots (
              feature_snapshot_id, tenant_id, organization_id, reporting_period_id,
              source_snapshot_id, feature_set_version, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'intake-feature-set-v0.1-demo', ?, ?)
            """,
            (
                feature_snapshot_id,
                submission["tenant_id"],
                submission["organization_id"],
                submission["reporting_period_id"],
                f"PS-{submission['organization_id']}-{period['period_key']}",
                _json(feature_payload),
                now,
            ),
        )
        risk_score = round(
            min(
                100,
                max(
                    0,
                    35
                    + (15 if net_cashflow < 0 else -8)
                    + min(25, debt_ratio * 25)
                    + late_rate * 30
                    + delay_rate * 30,
                ),
            )
        )
        risk_level = "high" if risk_score >= 70 else "watch" if risk_score >= 50 else "stable"
        connection.execute(
            """
            INSERT OR REPLACE INTO risk_runs (
              risk_run_id, tenant_id, organization_id, reporting_period_id, feature_snapshot_id,
              model_version, ruleset_version, score, level, explanation, review_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'deterministic-demo-v0.1', 'intake-risk-rules-v0.1',
              ?, ?, ?, 'pending_human_review', ?)
            """,
            (
                f"RR-{submission['submission_id']}",
                submission["tenant_id"],
                submission["organization_id"],
                submission["reporting_period_id"],
                feature_snapshot_id,
                risk_score,
                risk_level,
                "Advisory operational signal from approved period intake; not a credit score or default probability.",
                now,
            ),
        )
        if products:
            category = str(products[0].get("category") or "general")
            match_run_id = f"MR-{submission['submission_id']}"
            connection.execute(
                """
                INSERT OR REPLACE INTO match_runs (
                  match_run_id, tenant_id, buyer_organization_id, reporting_period_id,
                  disrupted_supplier_id, product_category, ruleset_version, review_status, created_at
                )
                VALUES (?, ?, ?, ?, NULL, ?, 'supplier-shortlist-rules-v0.1', 'pending_human_review', ?)
                """,
                (
                    match_run_id,
                    submission["tenant_id"],
                    submission["organization_id"],
                    submission["reporting_period_id"],
                    category,
                    now,
                ),
            )
            candidates = connection.execute(
                """
                SELECT organization_id
                FROM business_profiles
                WHERE tenant_id = ? AND product_category = ? AND organization_id <> ?
                ORDER BY organization_id
                LIMIT 3
                """,
                (submission["tenant_id"], category, submission["organization_id"]),
            ).fetchall()
            for rank, candidate in enumerate(candidates, start=1):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO match_candidates (
                      candidate_id, match_run_id, supplier_organization_id, rank, score,
                      explanation_json, consent_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'not_requested')
                    """,
                    (
                        f"MC-{submission['submission_id']}-{rank}",
                        match_run_id,
                        candidate["organization_id"],
                        rank,
                        max(50, 82 - rank * 7),
                        _json(
                            {
                                "reason": "Same product category from approved demo profile.",
                                "guardrail": "Contact reveal requires consent and human approval.",
                            }
                        ),
                    ),
                )
        scenario_payload = {
            "source_submission_id": submission["submission_id"],
            "period_key": period["period_key"],
            "input_snapshot_id": feature_snapshot_id,
            "shock_organization_id": None,
            "product_category": str(products[0].get("category") or "general") if products else "general",
            "impact_model": "deterministic adjacency placeholder",
            "guardrail": "Scenario output is decision-support only and requires human review before operational action.",
        }
        connection.execute(
            """
            INSERT OR REPLACE INTO scenario_runs (
              scenario_run_id, tenant_id, organization_id, reporting_period_id, input_snapshot_id,
              shock_organization_id, product_category, ruleset_version, model_version, payload_json,
              review_status, created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'scenario-rules-v0.1', 'deterministic-demo-v0.1',
              ?, 'pending_human_review', ?, ?)
            """,
            (
                f"SR-{submission['submission_id']}",
                submission["tenant_id"],
                submission["organization_id"],
                submission["reporting_period_id"],
                feature_snapshot_id,
                None,
                scenario_payload["product_category"],
                _json(scenario_payload),
                submission["submitted_by"],
                now,
            ),
        )
        self._record_registry_and_recompute_job(connection, submission, period, feature_snapshot_id, now)

    def _record_registry_and_recompute_job(
        self,
        connection: Any,
        submission: dict[str, Any],
        period: dict[str, Any],
        feature_snapshot_id: str,
        now: str,
    ) -> None:
        model_rows = [
            ("risk", "deterministic-demo-v0.1", {"purpose": "risk decision-support"}),
            ("scenario", "deterministic-demo-v0.1", {"purpose": "scenario decision-support"}),
        ]
        for artifact_type, model_version, config in model_rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO model_registry (
                  model_registry_id, tenant_id, artifact_type, model_version, status,
                  approval_status, config_json, checksum, created_by, created_at
                )
                VALUES (?, ?, ?, ?, 'active', 'approved', ?, ?, ?, ?)
                """,
                (
                    f"MOD-{artifact_type}-{model_version}",
                    submission["tenant_id"],
                    artifact_type,
                    model_version,
                    _json(config),
                    hashlib.sha256(f"{artifact_type}:{model_version}:{_json(config)}".encode("utf-8")).hexdigest(),
                    submission["submitted_by"],
                    now,
                ),
            )
        ruleset_rows = [
            ("feature", "intake-feature-set-v0.1-demo", {"sections": P0_SECTIONS}),
            ("risk", "intake-risk-rules-v0.1", {"inputs": ["cashflow", "debt", "late_payment", "delivery_delay"]}),
            ("matching", "supplier-shortlist-rules-v0.1", {"guardrail": "consent_required"}),
            ("scenario", "scenario-rules-v0.1", {"guardrail": "human_review_required"}),
        ]
        for artifact_type, ruleset_version, config in ruleset_rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO ruleset_registry (
                  ruleset_registry_id, tenant_id, artifact_type, ruleset_version, status,
                  approval_status, config_json, checksum, created_by, created_at
                )
                VALUES (?, ?, ?, ?, 'active', 'approved', ?, ?, ?, ?)
                """,
                (
                    f"RUL-{artifact_type}-{ruleset_version}",
                    submission["tenant_id"],
                    artifact_type,
                    ruleset_version,
                    _json(config),
                    hashlib.sha256(f"{artifact_type}:{ruleset_version}:{_json(config)}".encode("utf-8")).hexdigest(),
                    submission["submitted_by"],
                    now,
                ),
            )
        job_payload = {
            "source_submission_id": submission["submission_id"],
            "period_key": period["period_key"],
            "input_snapshot_id": feature_snapshot_id,
            "expected_artifacts": ["feature_snapshot", "risk_run", "match_run", "scenario_run"],
            "reason": "approved_intake_materialized",
            "guardrail": "Worker must be idempotent and must not overwrite historical approved artifacts.",
        }
        connection.execute(
            """
            INSERT OR IGNORE INTO analytics_recompute_jobs (
              job_id, tenant_id, organization_id, reporting_period_id, source_submission_id,
              job_type, status, idempotency_key, payload_json, attempts, max_attempts,
              last_error, created_by, created_at, updated_at, available_at, started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, 'analytics_recompute', 'queued', ?, ?, 0, 3,
              NULL, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                f"JOB-{submission['submission_id']}",
                submission["tenant_id"],
                submission["organization_id"],
                submission["reporting_period_id"],
                submission["submission_id"],
                f"analytics:{submission['submission_id']}",
                _json(job_payload),
                submission["submitted_by"],
                now,
                now,
                now,
            ),
        )

    def _validate_sections(self, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if not sections:
            issues.append(self._issue("submission", "$", "NO_SECTIONS", "error", "At least one intake section is required."))
            return issues
        for row in sections:
            section = row["section_name"]
            payload = _load_json(row["payload_json"], {})
            if section == "financials":
                issues.extend(self._validate_financials(payload))
            elif section == "products":
                issues.extend(self._validate_products(payload))
            elif section == "evidence":
                issues.extend(self._validate_evidence(payload))
            elif section == "profile" and not isinstance(payload, dict):
                issues.append(self._issue(section, "$", "INVALID_PROFILE", "error", "Profile payload must be an object."))
        return issues

    def _validate_financials(self, payload: Any) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if not isinstance(payload, dict) or not payload:
            return [self._issue("financials", "$", "FINANCIALS_REQUIRED", "error", "Financials section must contain monthly values.")]
        for key in ["revenue", "cash_in", "cash_out", "debt", "accounts_receivable", "accounts_payable", "inventory_value"]:
            if _number(payload.get(key), 0) < 0:
                issues.append(self._issue("financials", key, "NEGATIVE_VALUE", "error", f"{key} must be greater than or equal to 0."))
        for key in ["late_payment_rate", "delivery_delay_rate"]:
            rate = _rate(payload.get(key), 0)
            if rate < 0 or rate > 1:
                issues.append(self._issue("financials", key, "RATE_OUT_OF_RANGE", "error", f"{key} must be between 0 and 1."))
        if _number(payload.get("revenue"), 0) == 0:
            issues.append(self._issue("financials", "revenue", "ZERO_REVENUE", "warning", "Revenue is zero for this period; reviewer should confirm."))
        return issues

    def _validate_products(self, payload: Any) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        rows = self._list_payload(payload)
        if not rows:
            return [self._issue("products", "$", "PRODUCT_REQUIRED", "warning", "No product capability was submitted.")]
        seen: set[str] = set()
        for index, item in enumerate(rows, start=1):
            sku = str(item.get("sku") or "").strip()
            if not sku:
                issues.append(self._issue("products", "sku", "SKU_REQUIRED", "error", "SKU is required.", row=index))
            elif sku in seen:
                issues.append(self._issue("products", "sku", "DUPLICATE_SKU", "error", f"Duplicate SKU {sku}.", row=index))
            seen.add(sku)
            if _number(item.get("available_capacity"), 0) < 0:
                issues.append(self._issue("products", "available_capacity", "NEGATIVE_CAPACITY", "error", "Available capacity cannot be negative.", row=index))
        return issues

    def _validate_evidence(self, payload: Any) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for index, item in enumerate(self._list_payload(payload), start=1):
            document_type = str(item.get("document_type") or item.get("type") or "").upper()
            classification = str(item.get("classification") or "confidential")
            if not item.get("title") and not item.get("file_name"):
                issues.append(self._issue("evidence", "title", "TITLE_REQUIRED", "error", "Evidence title or file name is required.", row=index))
            if not item.get("document_hash"):
                issues.append(self._issue("evidence", "document_hash", "HASH_RECOMMENDED", "warning", "Document hash is missing; demo will derive one from title.", row=index))
            if document_type in RESTRICTED_FINANCIAL_EVIDENCE_TYPES and classification != "restricted_financial":
                issues.append(
                    self._issue(
                        "evidence",
                        "classification",
                        "RESTRICTED_FINANCIAL_CLASSIFICATION_REQUIRED",
                        "error",
                        "Guarantee and invoice evidence must use restricted_financial classification.",
                        row=index,
                    )
                )
            if item.get("malware_scan_status") != "clean":
                issues.append(
                    self._issue(
                        "evidence",
                        "malware_scan_status",
                        "EVIDENCE_SCAN_PENDING",
                        "warning",
                        "Evidence will not be materialized into approved snapshots until malware_scan_status is clean.",
                        row=index,
                    )
                )
        return issues

    def _issue(self, section: str, path: str, code: str, severity: str, message: str, row: int | None = None) -> dict[str, Any]:
        return {"section": section, "path": path, "code": code, "severity": severity, "message": message, "row": row}

    def _clear_raw_record_errors(self, connection: Any, submission_id: str) -> None:
        connection.execute(
            """
            DELETE FROM raw_record_errors
            WHERE raw_record_id IN (
              SELECT rr.raw_record_id
              FROM raw_records rr
              JOIN ingestion_batches ib ON ib.batch_id = rr.batch_id
              WHERE ib.submission_id = ?
            )
            """,
            (submission_id,),
        )

    def _record_raw_record_errors(self, connection: Any, submission_id: str, issues: list[dict[str, Any]], now: str) -> None:
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for issue in issues:
            row_number = issue.get("row")
            if not isinstance(row_number, int):
                continue
            grouped[(issue["section"], row_number)].append(issue)
        for (dataset, row_number), row_issues in grouped.items():
            raw_record = connection.execute(
                """
                SELECT rr.raw_record_id
                FROM raw_records rr
                JOIN ingestion_batches ib ON ib.batch_id = rr.batch_id
                WHERE ib.submission_id = ? AND ib.dataset = ? AND rr.row_number = ?
                """,
                (submission_id, dataset, row_number),
            ).fetchone()
            if raw_record is None:
                continue
            for issue in row_issues:
                connection.execute(
                    """
                    INSERT INTO raw_record_errors (
                      error_id, raw_record_id, code, severity, message, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _id("RAWERR"),
                        raw_record["raw_record_id"],
                        issue["code"],
                        issue["severity"],
                        issue["message"],
                        now,
                    ),
                )

    def _error_report_row(self, row: dict[str, Any], source: str) -> dict[str, Any]:
        return {
            "source": source,
            "batch_id": row.get("batch_id"),
            "dataset": row.get("dataset") or row.get("section_name"),
            "file_name": row.get("file_name"),
            "raw_record_id": row.get("raw_record_id"),
            "row": row.get("row_number"),
            "column": row.get("column_name"),
            "path": row.get("path"),
            "code": row["code"],
            "severity": row["severity"],
            "message": row["message"],
            "suggestion": row.get("suggestion"),
            "payload": _load_json(row.get("payload_json"), {}),
        }

    def _raw_error_report_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "raw_record_error",
            "batch_id": row.get("batch_id"),
            "dataset": row.get("dataset"),
            "file_name": row.get("file_name"),
            "raw_record_id": row.get("raw_record_id"),
            "row": row.get("row_number"),
            "column": None,
            "path": None,
            "code": row["code"],
            "severity": row["severity"],
            "message": row["message"],
            "suggestion": None,
            "payload": _load_json(row.get("payload_json"), {}),
        }

    def _evidence_review_summary(self, connection: Any, submission: dict[str, Any]) -> dict[str, Any]:
        statuses: list[str] = []
        statuses_by_type: dict[str, list[str]] = defaultdict(list)
        section = connection.execute(
            "SELECT payload_json FROM submission_sections WHERE submission_id = ? AND section_name = 'evidence'",
            (submission["submission_id"],),
        ).fetchone()
        if section is not None:
            payload = _load_json(section["payload_json"], [])
            for item in self._list_payload(payload):
                status = str(item.get("malware_scan_status") or "pending_scan")
                document_type = self._normalize_document_type(item.get("document_type") or item.get("type"))
                statuses.append(status)
                statuses_by_type[document_type].append(status)

        period = connection.execute(
            "SELECT period_key FROM reporting_periods WHERE reporting_period_id = ?",
            (submission["reporting_period_id"],),
        ).fetchone()
        for row in connection.execute(
            """
            SELECT document_type, malware_scan_status
            FROM evidence_documents
            WHERE tenant_id = ?
              AND organization_id = ?
              AND reporting_period_id = ?
            """,
            (submission["tenant_id"], submission["organization_id"], submission["reporting_period_id"]),
        ).fetchall():
            status = str(row["malware_scan_status"] or "pending_scan")
            document_type = self._normalize_document_type(row["document_type"])
            statuses.append(status)
            statuses_by_type[document_type].append(status)
        if period is not None:
            for row in connection.execute(
                """
                SELECT document_type, malware_scan_status
                FROM evidence_versions
                WHERE tenant_id = ?
                  AND organization_id = ?
                  AND period_key = ?
                  AND evidence_document_id IS NULL
                """,
                (submission["tenant_id"], submission["organization_id"], period["period_key"]),
            ).fetchall():
                status = str(row["malware_scan_status"] or "pending_scan")
                document_type = self._normalize_document_type(row["document_type"])
                statuses.append(status)
                statuses_by_type[document_type].append(status)
        return self._evidence_summary_from_statuses(statuses, statuses_by_type)

    def _evidence_summary_from_statuses(
        self,
        statuses: list[str],
        statuses_by_type: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        normalized = [(status or "pending_scan").strip().lower() for status in statuses]
        clean = sum(1 for status in normalized if status == "clean")
        rejected = sum(1 for status in normalized if status in {"infected", "failed"})
        pending = sum(1 for status in normalized if status not in {"clean", "infected", "failed"})
        total = len(normalized)
        approval_blocked = total > 0 and (pending > 0 or rejected > 0)
        return {
            "total": total,
            "clean": clean,
            "pending": pending,
            "rejected": rejected,
            "required": total > 0,
            "approval_blocked": approval_blocked,
            "advisory": (
                "Approval blocked until submitted/uploaded evidence has clean malware scan status."
                if approval_blocked
                else "Evidence gate passed or no evidence was submitted for this period."
            ),
            "requirements": self._evidence_requirement_payload(statuses_by_type or {}),
        }

    def _normalize_document_type(self, value: Any) -> str:
        document_type = str(value or "SUPPORTING_DOCUMENT").strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "CERTIFICATE": "CERTIFICATION",
            "SUPPORTING": "SUPPORTING_DOCUMENT",
            "SUPPORTING_DOC": "SUPPORTING_DOCUMENT",
        }
        return aliases.get(document_type, document_type)

    def _evidence_requirement_payload(self, statuses_by_type: dict[str, list[str]]) -> list[dict[str, Any]]:
        requirements: list[dict[str, Any]] = []
        for document_type, title, section in EVIDENCE_REQUIREMENTS:
            statuses = statuses_by_type.get(document_type, [])
            summary = self._status_counts(statuses)
            requirements.append(
                {
                    "document_type": document_type,
                    "title": title,
                    "section": section,
                    "total": summary["total"],
                    "clean": summary["clean"],
                    "pending": summary["pending"],
                    "rejected": summary["rejected"],
                    "status": summary["status"],
                    "satisfied": summary["clean"] > 0,
                }
            )
        return requirements

    def _status_counts(self, statuses: list[str]) -> dict[str, Any]:
        normalized = [(status or "pending_scan").strip().lower() for status in statuses]
        clean = sum(1 for status in normalized if status == "clean")
        rejected = sum(1 for status in normalized if status in {"infected", "failed"})
        pending = sum(1 for status in normalized if status not in {"clean", "infected", "failed"})
        total = len(normalized)
        if clean > 0:
            status = "verified"
        elif rejected > 0:
            status = "rejected"
        elif pending > 0:
            status = "pending"
        else:
            status = "missing"
        return {"total": total, "clean": clean, "pending": pending, "rejected": rejected, "status": status}

    def _review_queue_item(self, row: dict[str, Any], connection: Any | None = None) -> dict[str, Any]:
        sections: list[dict[str, str]] = []
        for item in str(row.get("section_statuses") or "").split(","):
            if not item:
                continue
            section, _, status = item.partition(":")
            sections.append({"section": section, "status": status or "unknown"})
        evidence_review = self._evidence_review_summary(connection, row) if connection is not None else self._evidence_summary_from_statuses([])
        return {
            "review_task_id": row["review_task_id"],
            "submission_id": row["submission_id"],
            "organization_id": row["organization_id"],
            "organization_name": row["organization_name"],
            "period_key": row["period_key"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "review_status": row["status"],
            "assigned_role": row["assigned_role"],
            "assigned_to": row.get("assigned_to"),
            "assignment_reason": row.get("assignment_reason"),
            "assigned_at": row.get("assigned_at"),
            "submission_status": row["submission_status"],
            "source": row["source_type"],
            "version": int(row["version"]),
            "submitted_by": row["submitted_by"],
            "submitted_at": row["submitted_at"],
            "updated_at": row["updated_at"],
            "validation_summary": {
                "errors": int(row["error_count"] or 0),
                "warnings": int(row["warning_count"] or 0),
                "infos": int(row["info_count"] or 0),
            },
            "sections": sections,
            "evidence_review": evidence_review,
        }

    def _error_report_csv(self, rows: list[dict[str, Any]]) -> str:
        output = io.StringIO()
        fieldnames = [
            "source",
            "batch_id",
            "dataset",
            "file_name",
            "row",
            "column",
            "path",
            "code",
            "severity",
            "message",
            "suggestion",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return output.getvalue()

    def _csv_payload(self, dataset: str, rows: list[dict[str, Any]]) -> Any:
        normalized_rows = [{self._normalize_column(key): value for key, value in row.items()} for row in rows]
        if dataset == "financials":
            return normalized_rows[0] if normalized_rows else {}
        if dataset == "products":
            return normalized_rows
        if dataset == "evidence":
            return normalized_rows
        return normalized_rows

    def _normalized_key(self, dataset: str, row: dict[str, Any], index: int) -> str:
        for key in ["sku", "invoice_id", "document_hash", "title", "file_name"]:
            if row.get(key):
                return f"{dataset}:{row[key]}"
        return f"{dataset}:row:{index}"

    def _normalize_column(self, column: str) -> str:
        return column.strip().lower().replace(" ", "_").replace("-", "_")

    def _list_payload(self, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload] if payload else []
        return []

    def _empty_snapshot(self, organization_id: str, period_key: str, latest_submission: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "business_id": organization_id,
            "organization_id": organization_id,
            "period": {"period_key": period_key, "status": "not_created"},
            "approved_version": None,
            "approved_at": None,
            "review_decision": None,
            "latest_submission_status": latest_submission["status"] if latest_submission else None,
            "sections": {},
            "financials": [],
            "products": [],
            "evidence": [],
            "source_submission_ids": [],
            "advisory_notice": INTAKE_NOTICE,
        }

    def _period_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["reporting_period_id"],
            "tenant_id": row["tenant_id"],
            "organization_id": row["organization_id"],
            "period_type": row["period_type"],
            "period_key": row["period_key"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "status": "approved" if row.get("approved_submission_id") else row["status"],
            "lock_version": row["lock_version"],
            "latest_submission_status": row.get("latest_submission_status"),
        }

    def _submission_payload(
        self,
        submission: dict[str, Any],
        sections: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        review: dict[str, Any] | None,
        period: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": submission["submission_id"],
            "submission_id": submission["submission_id"],
            "tenant_id": submission["tenant_id"],
            "business_id": submission["organization_id"],
            "organization_id": submission["organization_id"],
            "period": self._period_payload(period),
            "source": submission["source_type"],
            "status": submission["status"],
            "version": submission["version"],
            "submitted_by": submission["submitted_by"],
            "created_at": submission["created_at"],
            "updated_at": submission["updated_at"],
            "submitted_at": submission["submitted_at"],
            "validated_at": submission["validated_at"],
            "canonicalized_at": submission["canonicalized_at"],
            "sections": {
                row["section_name"]: {
                    "status": row["status"],
                    "payload": _load_json(row["payload_json"], {}),
                    "updated_at": row["updated_at"],
                }
                for row in sections
            },
            "issues": [self._issue_payload(row) for row in issues],
            "validation_summary": {
                "errors": len([row for row in issues if row["severity"] == "error"]),
                "warnings": len([row for row in issues if row["severity"] == "warning"]),
                "infos": len([row for row in issues if row["severity"] == "info"]),
            },
            "review_task": self._review_payload(review) if review else None,
            "advisory_notice": INTAKE_NOTICE,
        }

    def _issue_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["issue_id"],
            "section": row["section_name"],
            "path": row["path"],
            "row": row["row_number"],
            "column": row["column_name"],
            "code": row["code"],
            "severity": row["severity"],
            "message": row["message"],
            "suggestion": row["suggestion"],
        }

    def _review_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["review_task_id"],
            "status": row["status"],
            "assigned_role": row["assigned_role"],
            "assigned_to": row.get("assigned_to"),
            "assignment_reason": row.get("assignment_reason"),
            "assigned_at": row.get("assigned_at"),
            "decided_by": row["decided_by"],
            "decision": row["decision"],
            "decision_note": row["decision_note"],
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
        }

    def _upsert_section(self, connection: Any, submission_id: str, section_name: str, payload: Any, status: str, now: str) -> None:
        existing = connection.execute(
            "SELECT section_id FROM submission_sections WHERE submission_id = ? AND section_name = ?",
            (submission_id, section_name),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE submission_sections
                SET status = ?, payload_json = ?, updated_at = ?
                WHERE section_id = ?
                """,
                (status, _json(payload), now, existing["section_id"]),
            )
            return
        connection.execute(
            """
            INSERT INTO submission_sections (
              section_id, submission_id, section_name, status, payload_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_id("SEC"), submission_id, section_name, status, _json(payload), now),
        )

    def _ensure_period(self, connection: Any, organization_id: str, period_key: str, tenant_id: str) -> dict[str, Any]:
        existing = connection.execute(
            """
            SELECT * FROM reporting_periods
            WHERE tenant_id = ? AND organization_id = ? AND period_type = 'month' AND period_key = ?
            """,
            (tenant_id, organization_id, period_key),
        ).fetchone()
        if existing:
            return dict(existing)
        start, end = _period_dates(period_key)
        period_id = f"PER-{organization_id}-{period_key}"
        connection.execute(
            """
            INSERT INTO reporting_periods (
              reporting_period_id, tenant_id, organization_id, period_type, period_key,
              period_start, period_end, status, lock_version
            )
            VALUES (?, ?, ?, 'month', ?, ?, ?, 'open', 1)
            """,
            (period_id, tenant_id, organization_id, period_key, start, end),
        )
        return dict(
            connection.execute("SELECT * FROM reporting_periods WHERE reporting_period_id = ?", (period_id,)).fetchone()
        )

    def _submission_row(self, connection: Any, submission_id: str) -> Any:
        row = connection.execute("SELECT * FROM data_submissions WHERE submission_id = ?", (submission_id,)).fetchone()
        if row is None:
            raise IntakeNotFoundError(submission_id)
        return row

    def _require_organization(self, connection: Any, organization_id: str) -> None:
        row = connection.execute("SELECT organization_id FROM organizations WHERE organization_id = ?", (organization_id,)).fetchone()
        if row is None:
            raise IntakeNotFoundError(organization_id)
