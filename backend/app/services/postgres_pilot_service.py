from __future__ import annotations

import calendar
import csv
import hashlib
import hmac
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote, urlsplit
from uuid import uuid4

from backend.app.services.access_control import AccessDeniedError, PolicyService, RequestContext
from backend.app.services.governance_service import (
    INVOICE_STATES,
    INVOICE_TRANSITIONS,
    RESTRICTED_FINANCIAL_EVIDENCE_TYPES,
    invoice_identity_hash,
    require_evidence_upload_classification,
)
from backend.app.services.intake_service import EVIDENCE_REQUIREMENTS, IntakeNotFoundError
from backend.app.services.postgres_migrations import PostgresMigrationRunner, normalize_postgres_url, set_rls_session


TRUST_NOTICE = (
    "Operational decision-support only. This platform does not approve financing, assign a credit score, "
    "confirm fraud, or make legal breach findings without independent review."
)
P0_SECTIONS = ("profile", "financials", "products", "evidence")


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


@dataclass(frozen=True)
class ObjectStorageSettings:
    endpoint_url: str | None = None
    bucket: str = "vietsupply-evidence"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    region: str = "us-east-1"
    upload_ttl_seconds: int = 900
    download_ttl_seconds: int = 300

    @classmethod
    def from_env(cls) -> "ObjectStorageSettings":
        ttl_raw = os.getenv("EVIDENCE_UPLOAD_URL_TTL_SECONDS", "900")
        try:
            ttl = int(ttl_raw)
        except ValueError:
            ttl = 900
        download_ttl_raw = os.getenv("EVIDENCE_DOWNLOAD_URL_TTL_SECONDS", "300")
        try:
            download_ttl = int(download_ttl_raw)
        except ValueError:
            download_ttl = 300
        return cls(
            endpoint_url=os.getenv("EVIDENCE_OBJECT_STORE_ENDPOINT") or None,
            bucket=os.getenv("EVIDENCE_OBJECT_STORE_BUCKET", "vietsupply-evidence"),
            access_key_id=os.getenv("EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID") or None,
            secret_access_key=os.getenv("EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY") or None,
            region=os.getenv("EVIDENCE_OBJECT_STORE_REGION", "us-east-1"),
            upload_ttl_seconds=max(60, min(ttl, 3600)),
            download_ttl_seconds=max(60, min(download_ttl, 900)),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint_url and self.bucket and self.access_key_id and self.secret_access_key)

    def presign_put_url(self, object_key: str, request_time: datetime | None = None) -> str:
        return self._presign_url("PUT", object_key, self.upload_ttl_seconds, request_time=request_time)

    def presign_get_url(self, object_key: str, request_time: datetime | None = None) -> str:
        return self._presign_url("GET", object_key, self.download_ttl_seconds, request_time=request_time)

    def presign_delete_url(self, object_key: str, request_time: datetime | None = None) -> str:
        return self._presign_url("DELETE", object_key, self.download_ttl_seconds, request_time=request_time)

    def _presign_url(
        self,
        method: str,
        object_key: str,
        expires_in_seconds: int,
        *,
        request_time: datetime | None = None,
    ) -> str:
        if not self.is_configured:
            raise PilotFeatureUnavailableError("object_storage.presign.unconfigured")
        bucket, key = self._bucket_and_key(object_key)
        endpoint = urlsplit(str(self.endpoint_url).rstrip("/"))
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
            raise PilotFeatureUnavailableError("object_storage.presign.invalid_endpoint")
        now = request_time or datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        canonical_uri = self._canonical_uri(endpoint.path, bucket, key)
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        signed_headers = "host"
        query_params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key_id}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_in_seconds),
            "X-Amz-SignedHeaders": signed_headers,
        }
        canonical_query = self._canonical_query(query_params)
        canonical_headers = f"host:{endpoint.netloc}\n"
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                "UNSIGNED-PAYLOAD",
            ]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            self._signing_key(date_stamp),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{endpoint.scheme}://{endpoint.netloc}{canonical_uri}?{canonical_query}&X-Amz-Signature={signature}"

    def _bucket_and_key(self, object_key: str) -> tuple[str, str]:
        if object_key.startswith("s3://"):
            path = object_key.removeprefix("s3://")
            bucket, _, key = path.partition("/")
            return bucket or self.bucket, key
        return self.bucket, object_key.lstrip("/")

    def _canonical_uri(self, endpoint_path: str, bucket: str, key: str) -> str:
        base_path = endpoint_path.rstrip("/")
        raw_path = f"{base_path}/{bucket}/{key}" if base_path else f"/{bucket}/{key}"
        return quote(raw_path, safe="/~")

    def _canonical_query(self, params: dict[str, str]) -> str:
        encoded = [
            (quote(str(key), safe="-_.~"), quote(str(value), safe="-_.~"))
            for key, value in params.items()
        ]
        return "&".join(f"{key}={value}" for key, value in sorted(encoded))

    def _signing_key(self, date_stamp: str) -> bytes:
        assert self.secret_access_key is not None
        key_date = hmac.new(f"AWS4{self.secret_access_key}".encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
        key_region = hmac.new(key_date, self.region.encode("utf-8"), hashlib.sha256).digest()
        key_service = hmac.new(key_region, b"s3", hashlib.sha256).digest()
        return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()


class PilotFeatureUnavailableError(RuntimeError):
    status_code = 503
    code = "POSTGRES_ADAPTER_INCOMPLETE"

    def __init__(self, feature: str) -> None:
        self.feature = feature
        super().__init__(
            f"{feature} is not available in the PostgreSQL pilot adapter yet. "
            "Port this workflow to PostgreSQL repositories and DB-level RLS before exposing pilot data."
        )


@dataclass(frozen=True)
class PostgresPilotRuntime:
    database_url: str
    app_mode: str

    @property
    def migration_revisions(self) -> list[str]:
        return [migration.revision for migration in PostgresMigrationRunner(self.database_url).plan()]

    def status_payload(self) -> dict[str, Any]:
        return {
            "database": "postgresql",
            "app_mode": self.app_mode,
            "adapter_status": "pilot_boot_boundary",
            "migration_revisions": self.migration_revisions,
            "advisory_notice": (
                "PostgreSQL runtime is configured, but only trust bootstrap endpoints are available until "
                "repositories are ported and DB-level RLS smoke tests pass."
            ),
        }


class PostgresConnectionFactory:
    def __init__(self, database_url: str) -> None:
        self.database_url = normalize_postgres_url(database_url)

    def connect(self) -> Any:
        try:
            import psycopg  # type: ignore[import-not-found]
            from psycopg.rows import dict_row  # type: ignore[import-not-found]
        except ImportError as exc:
            raise PilotFeatureUnavailableError("postgres.connection") from exc
        return psycopg.connect(self.database_url, autocommit=False, row_factory=dict_row)


class _UnsupportedPilotComponent:
    def __init__(self, component_name: str) -> None:
        self.component_name = component_name

    def _raise(self, method_name: str) -> None:
        raise PilotFeatureUnavailableError(f"{self.component_name}.{method_name}")

    def __getattr__(self, method_name: str) -> Callable[..., Any]:
        def unavailable(*args: Any, **kwargs: Any) -> Any:
            self._raise(method_name)

        return unavailable


class PostgresPilotIntakeService(_UnsupportedPilotComponent):
    def __init__(self, runtime: PostgresPilotRuntime, connector: PostgresConnectionFactory | Any) -> None:
        super().__init__("intake")
        self.runtime = runtime
        self.connector = connector

    def _can_view_all_review_tasks(self, context: RequestContext) -> bool:
        return context.is_demo_actor() or context.has_role("demo_admin", "system_admin") or "policy:override" in context.scopes

    def list_periods(self, organization_id: str, context: RequestContext | None = None) -> list[dict[str, Any]]:
        if context is None:
            raise PilotFeatureUnavailableError("intake.list_periods.anonymous_context")
        PolicyService.require(
            "read_financials",
            context,
            resource_type="reporting_period",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            rows = connection.execute(
                """
                SELECT
                  rp.reporting_period_id::text AS id,
                  tenant.external_key AS tenant_id,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id,
                  rp.period_type::text AS period_type,
                  rp.period_key,
                  rp.period_start::text AS period_start,
                  rp.period_end::text AS period_end,
                  CASE
                    WHEN EXISTS (
                      SELECT 1
                      FROM data_submissions approved
                      WHERE approved.reporting_period_id = rp.reporting_period_id
                        AND approved.status = 'approved'
                    )
                    THEN 'approved'
                    ELSE rp.status
                  END AS status,
                  rp.lock_version,
                  latest.status::text AS latest_submission_status
                FROM reporting_periods rp
                JOIN organizations org ON org.organization_id = rp.organization_id
                JOIN tenants tenant ON tenant.tenant_id = rp.tenant_id
                LEFT JOIN LATERAL (
                  SELECT ds.status
                  FROM data_submissions ds
                  WHERE ds.reporting_period_id = rp.reporting_period_id
                  ORDER BY ds.updated_at DESC
                  LIMIT 1
                ) latest ON true
                WHERE org.tenant_id = app_tenant_id()
                  AND (
                    org.organization_id = app_try_uuid(%s)
                    OR org.external_business_id = %s
                  )
                ORDER BY rp.period_start DESC
                """,
                (organization_id, organization_id),
            ).fetchall()
        return [self._period_payload(row) for row in rows]

    def create_submission(
        self,
        *,
        organization_id: str,
        period_key: str,
        source_type: str,
        sections: dict[str, Any] | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        if source_type not in {"manual", "csv"}:
            raise ValueError("source_type must be manual or csv")
        decision = PolicyService.require(
            "create_submission",
            context,
            resource_type="data_submission",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        period_start, period_end = _period_dates(period_key)
        section_payloads = [
            {"section_name": section_name, "payload": payload if payload is not None else {}}
            for section_name, payload in (sections or {name: {} for name in P0_SECTIONS}).items()
        ]
        sections_json = json.dumps(section_payloads, ensure_ascii=False, sort_keys=True)
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id, ua.external_subject
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                org_row AS (
                  SELECT
                    org.organization_id,
                    org.tenant_id,
                    COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                period_row AS (
                  INSERT INTO reporting_periods (
                    tenant_id, organization_id, period_type, period_key,
                    period_start, period_end, status, lock_version
                  )
                  SELECT
                    org.tenant_id, org.organization_id, 'month', %s,
                    %s::date, %s::date, 'open', 1
                  FROM org_row org
                  ON CONFLICT (tenant_id, organization_id, period_type, period_key)
                  DO UPDATE SET period_key = EXCLUDED.period_key
                  RETURNING *
                ),
                next_version AS (
                  SELECT COALESCE(MAX(ds.version), 0) + 1 AS version
                  FROM data_submissions ds
                  JOIN period_row period ON period.reporting_period_id = ds.reporting_period_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    org.tenant_id, actor.user_id, %s, 'data_submission', org.external_id, %s,
                    'allow', %s, %s, %s
                  FROM org_row org, actor_row actor
                  RETURNING decision_id
                ),
                submission_row AS (
                  INSERT INTO data_submissions (
                    tenant_id, organization_id, reporting_period_id, source_type,
                    status, version, submitted_by
                  )
                  SELECT
                    period.tenant_id, period.organization_id, period.reporting_period_id, %s,
                    'draft', next_version.version, actor.user_id
                  FROM period_row period, next_version, actor_row actor
                  RETURNING *
                ),
                sections_input AS (
                  SELECT section_name, payload
                  FROM jsonb_to_recordset(%s::jsonb) AS section_payload(section_name text, payload jsonb)
                ),
                sections_insert AS (
                  INSERT INTO submission_sections (
                    submission_id, section_name, status, payload
                  )
                  SELECT
                    submission.submission_id, sections_input.section_name, 'draft', sections_input.payload
                  FROM submission_row submission, sections_input
                  RETURNING section_id, section_name, status, payload, updated_at
                ),
                sections_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'section_id', section_id::text,
                        'section_name', section_name,
                        'status', status,
                        'payload', payload,
                        'updated_at', updated_at::text
                      )
                      ORDER BY section_name
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM sections_insert
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    submission.tenant_id, 'DATA_SUBMISSION_DRAFT_CREATED', actor.user_id, %s, submission.submission_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || submission.submission_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', org.external_id,
                      'period_key', period.period_key,
                      'source_type', submission.source_type,
                      'version', submission.version
                    ),
                    %s, %s
                  FROM submission_row submission, actor_row actor, org_row org, period_row period, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  submission.submission_id::text AS submission_id,
                  tenant.external_key AS tenant_id,
                  org.external_id AS organization_id,
                  period.reporting_period_id::text AS id,
                  period.period_type::text AS period_type,
                  period.period_key,
                  period.period_start::text AS period_start,
                  period.period_end::text AS period_end,
                  period.status,
                  period.lock_version,
                  submission.source_type,
                  submission.status::text AS submission_status,
                  submission.version,
                  COALESCE(actor.external_subject, submission.submitted_by::text) AS submitted_by,
                  submission.created_at::text AS created_at,
                  submission.updated_at::text AS updated_at,
                  submission.submitted_at::text AS submitted_at,
                  submission.validated_at::text AS validated_at,
                  submission.canonicalized_at::text AS canonicalized_at,
                  sections_json.data AS sections,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM submission_row submission
                JOIN period_row period ON period.reporting_period_id = submission.reporting_period_id
                JOIN org_row org ON org.organization_id = submission.organization_id
                JOIN tenants tenant ON tenant.tenant_id = submission.tenant_id
                JOIN actor_row actor ON actor.user_id = submission.submitted_by
                JOIN sections_json ON true
                JOIN policy ON true
                JOIN audit ON true
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    period_key,
                    period_start,
                    period_end,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    source_type,
                    sections_json,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.create_submission.unprovisioned_identity")
        return self._submission_payload(row)

    def get_submission(self, submission_id: str, context: RequestContext | None = None) -> dict[str, Any]:
        if context is None:
            raise PilotFeatureUnavailableError("intake.get_submission.anonymous_context")
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  ds.submission_id::text AS submission_id,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id
                FROM data_submissions ds
                JOIN organizations org ON org.organization_id = ds.organization_id
                WHERE ds.tenant_id = app_tenant_id()
                  AND ds.submission_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (submission_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(submission_id)
            decision = PolicyService.require(
                "read_financials",
                context,
                resource_type="data_submission",
                resource_id=submission_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="restricted_financial",
            )
            row = connection.execute(
                self._submission_read_sql("DATA_SUBMISSION_READ"),
                (
                    context.actor_id,
                    context.actor_id,
                    submission_id,
                    decision.action,
                    submission_id,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise IntakeNotFoundError(submission_id)
        return self._submission_payload(row)

    def update_submission(self, submission_id: str, sections: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        section_payloads = [
            {"section_name": section_name, "payload": payload if payload is not None else {}}
            for section_name, payload in sections.items()
        ]
        sections_json = json.dumps(section_payloads, ensure_ascii=False, sort_keys=True)
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  ds.submission_id::text AS submission_id,
                  ds.status::text AS status,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id
                FROM data_submissions ds
                JOIN organizations org ON org.organization_id = ds.organization_id
                WHERE ds.tenant_id = app_tenant_id()
                  AND ds.submission_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (submission_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(submission_id)
            if str(existing["status"]) in {"approved", "rejected", "superseded"}:
                raise ValueError("Locked submission cannot be edited.")
            decision = PolicyService.require(
                "update_submission",
                context,
                resource_type="data_submission",
                resource_id=submission_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="restricted_financial",
            )
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id, ua.external_subject
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                existing_submission AS (
                  SELECT ds.*
                  FROM data_submissions ds
                  WHERE ds.tenant_id = app_tenant_id()
                    AND ds.submission_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    existing.tenant_id, actor.user_id, %s, 'data_submission', existing.submission_id::text, %s,
                    'allow', %s, %s, %s
                  FROM existing_submission existing, actor_row actor
                  RETURNING decision_id
                ),
                updated_submission AS (
                  UPDATE data_submissions
                  SET status = 'draft', validated_at = NULL, updated_at = now()
                  WHERE submission_id = (SELECT submission_id FROM existing_submission)
                  RETURNING *
                ),
                sections_input AS (
                  SELECT section_name, payload
                  FROM jsonb_to_recordset(%s::jsonb) AS section_payload(section_name text, payload jsonb)
                ),
                upsert_sections AS (
                  INSERT INTO submission_sections (submission_id, section_name, status, payload)
                  SELECT updated.submission_id, sections_input.section_name, 'draft', sections_input.payload
                  FROM updated_submission updated, sections_input
                  ON CONFLICT (submission_id, section_name)
                  DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload, updated_at = now()
                  RETURNING section_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'DATA_SUBMISSION_DRAFT_UPDATED', actor.user_id, %s, updated.submission_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated.submission_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('updated_sections', (SELECT COUNT(*) FROM sections_input)),
                    %s, %s
                  FROM updated_submission updated, actor_row actor, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN updated_submission updated ON updated.reporting_period_id = rp.reporting_period_id
                ),
                org_row AS (
                  SELECT COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated_submission updated ON updated.organization_id = org.organization_id
                ),
                sections_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'section_id', section.section_id::text,
                        'section_name', section.section_name,
                        'status', section.status,
                        'payload', section.payload,
                        'updated_at', section.updated_at::text
                      )
                      ORDER BY section.section_name
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM submission_sections section
                  JOIN updated_submission updated ON updated.submission_id = section.submission_id
                ),
                issues_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'issue_id', issue.issue_id::text,
                        'section_name', issue.section_name,
                        'path', issue.path,
                        'row_number', issue.row_number,
                        'column_name', issue.column_name,
                        'code', issue.code,
                        'severity', issue.severity,
                        'message', issue.message,
                        'suggestion', issue.suggestion
                      )
                      ORDER BY issue.severity, issue.section_name, issue.row_number
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM validation_issues issue
                  JOIN updated_submission updated ON updated.submission_id = issue.submission_id
                )
                SELECT
                  updated.submission_id::text AS submission_id,
                  tenant.external_key AS tenant_id,
                  org.external_id AS organization_id,
                  period.reporting_period_id::text AS id,
                  period.period_type::text AS period_type,
                  period.period_key,
                  period.period_start::text AS period_start,
                  period.period_end::text AS period_end,
                  period.status,
                  period.lock_version,
                  updated.source_type,
                  updated.status::text AS submission_status,
                  updated.version,
                  COALESCE(submitter.external_subject, updated.submitted_by::text) AS submitted_by,
                  updated.created_at::text AS created_at,
                  updated.updated_at::text AS updated_at,
                  updated.submitted_at::text AS submitted_at,
                  updated.validated_at::text AS validated_at,
                  updated.canonicalized_at::text AS canonicalized_at,
                  sections_json.data AS sections,
                  issues_json.data AS issues,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated_submission updated
                JOIN period_row period ON period.reporting_period_id = updated.reporting_period_id
                JOIN org_row org ON true
                JOIN tenants tenant ON tenant.tenant_id = updated.tenant_id
                JOIN user_accounts submitter ON submitter.user_id = updated.submitted_by
                JOIN sections_json ON true
                JOIN issues_json ON true
                JOIN policy ON true
                JOIN audit ON true
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    submission_id,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    sections_json,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.update_submission.unprovisioned_identity")
        return self._submission_payload(row)

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
        if dataset not in {"financials", "products", "evidence"}:
            raise ValueError("dataset must be financials, products, or evidence")
        decision = PolicyService.require(
            "create_import_batch",
            context,
            resource_type="ingestion_batch",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        rows = list(csv.DictReader(io.StringIO(csv_text.strip()))) if csv_text.strip() else []
        checksum = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        if submission_id is None:
            submission = self.create_submission(
                organization_id=organization_id,
                period_key=period_key,
                source_type="csv",
                sections={dataset: [] if dataset in {"products", "evidence"} else {}},
                context=context,
            )
            submission_id = submission["id"]
        raw_rows = [
            {
                "row_number": index,
                "payload": dict(row),
                "normalized_key": self._normalized_key(dataset, row, index),
            }
            for index, row in enumerate(rows, start=1)
        ]
        parsed_payload = self._csv_payload(dataset, rows)
        raw_rows_json = json.dumps(raw_rows, ensure_ascii=False, sort_keys=True)
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  batch.batch_id::text AS batch_id,
                  batch.submission_id::text AS submission_id,
                  batch.dataset,
                  file.file_name,
                  batch.row_count,
                  batch.status,
                  batch.checksum,
                  COALESCE(
                    jsonb_agg(record.payload ORDER BY record.row_number)
                      FILTER (WHERE record.raw_record_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS preview_rows
                FROM ingestion_batches batch
                LEFT JOIN raw_file_objects file ON file.batch_id = batch.batch_id
                LEFT JOIN raw_records record ON record.batch_id = batch.batch_id AND record.row_number <= 20
                WHERE batch.submission_id = app_try_uuid(%s)
                  AND batch.dataset = %s
                  AND batch.checksum = %s
                GROUP BY batch.batch_id, file.file_name
                LIMIT 1
                """,
                (submission_id, dataset, checksum),
            ).fetchone()
            if existing is not None:
                return self._import_batch_payload(existing, idempotent_replay=True)
            existing_submission = connection.execute(
                """
                SELECT
                  ds.submission_id::text AS submission_id,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id
                FROM data_submissions ds
                JOIN organizations org ON org.organization_id = ds.organization_id
                WHERE ds.tenant_id = app_tenant_id()
                  AND ds.submission_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (submission_id,),
            ).fetchone()
            if existing_submission is None:
                raise IntakeNotFoundError(submission_id)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                submission_row AS (
                  SELECT ds.*
                  FROM data_submissions ds
                  WHERE ds.tenant_id = app_tenant_id()
                    AND ds.submission_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    submission.tenant_id, actor.user_id, %s, 'ingestion_batch', submission.submission_id::text, %s,
                    'allow', %s, %s, %s
                  FROM submission_row submission, actor_row actor
                  RETURNING decision_id
                ),
                batch AS (
                  INSERT INTO ingestion_batches (
                    submission_id, dataset, source_type, status, checksum, row_count, created_by
                  )
                  SELECT submission.submission_id, %s, 'csv', 'parsed', %s, %s, actor.user_id
                  FROM submission_row submission, actor_row actor
                  RETURNING *
                ),
                raw_file AS (
                  INSERT INTO raw_file_objects (
                    batch_id, submission_id, file_name, object_key, checksum, content_type, byte_size
                  )
                  SELECT
                    batch.batch_id,
                    batch.submission_id,
                    %s,
                    'raw/' || batch.submission_id::text || '/' || %s,
                    %s,
                    'text/csv',
                    %s
                  FROM batch
                  RETURNING *
                ),
                raw_input AS (
                  SELECT *
                  FROM jsonb_to_recordset(%s::jsonb) AS raw_payload(
                    row_number integer,
                    payload jsonb,
                    normalized_key text
                  )
                ),
                raw_insert AS (
                  INSERT INTO raw_records (
                    batch_id, raw_file_id, row_number, payload, normalized_key
                  )
                  SELECT
                    batch.batch_id,
                    raw_file.raw_file_id,
                    raw_input.row_number,
                    raw_input.payload,
                    raw_input.normalized_key
                  FROM batch, raw_file, raw_input
                  RETURNING raw_record_id, payload, row_number
                ),
                section_upsert AS (
                  INSERT INTO submission_sections (submission_id, section_name, status, payload)
                  SELECT submission.submission_id, %s, 'draft', %s::jsonb
                  FROM submission_row submission
                  ON CONFLICT (submission_id, section_name)
                  DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload, updated_at = now()
                  RETURNING section_id
                ),
                submission_update AS (
                  UPDATE data_submissions
                  SET status = 'draft', validated_at = NULL, updated_at = now()
                  WHERE submission_id = (SELECT submission_id FROM submission_row)
                  RETURNING submission_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    submission.tenant_id, 'CSV_IMPORT_BATCH_PARSED', actor.user_id, %s, batch.batch_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || batch.batch_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('dataset', batch.dataset, 'row_count', batch.row_count, 'checksum', batch.checksum),
                    %s, %s
                  FROM submission_row submission, actor_row actor, batch, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  batch.batch_id::text AS batch_id,
                  batch.submission_id::text AS submission_id,
                  batch.dataset,
                  raw_file.file_name,
                  batch.row_count,
                  batch.status,
                  batch.checksum,
                  COALESCE(
                    jsonb_agg(raw_insert.payload ORDER BY raw_insert.row_number)
                      FILTER (WHERE raw_insert.raw_record_id IS NOT NULL AND raw_insert.row_number <= 20),
                    '[]'::jsonb
                  ) AS preview_rows,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM batch
                JOIN raw_file ON raw_file.batch_id = batch.batch_id
                LEFT JOIN raw_insert ON true
                JOIN policy ON true
                JOIN audit ON true
                GROUP BY batch.batch_id, raw_file.file_name, policy.decision_id, audit.event_id
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    submission_id,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    dataset,
                    checksum,
                    len(rows),
                    file_name,
                    file_name,
                    checksum,
                    len(csv_text.encode("utf-8")),
                    raw_rows_json,
                    dataset,
                    json.dumps(parsed_payload, ensure_ascii=False, sort_keys=True),
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.create_import_batch.unprovisioned_identity")
        return self._import_batch_payload(row, idempotent_replay=False)

    def validate_submission(self, submission_id: str, context: RequestContext) -> dict[str, Any]:
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  ds.submission_id::text AS submission_id,
                  ds.status::text AS status,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id,
                  COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'section_name', section.section_name,
                        'payload', section.payload
                      )
                      ORDER BY section.section_name
                    ) FILTER (WHERE section.section_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS sections
                FROM data_submissions ds
                JOIN organizations org ON org.organization_id = ds.organization_id
                LEFT JOIN submission_sections section ON section.submission_id = ds.submission_id
                WHERE ds.tenant_id = app_tenant_id()
                  AND ds.submission_id = app_try_uuid(%s)
                GROUP BY ds.submission_id, ds.status, org.external_business_id, org.organization_id
                LIMIT 1
                """,
                (submission_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(submission_id)
            decision = PolicyService.require(
                "validate_submission",
                context,
                resource_type="data_submission",
                resource_id=submission_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="restricted_financial",
            )
            issues = self._validate_sections(self._json_list(existing.get("sections")))
            error_count = len([issue for issue in issues if issue["severity"] == "error"])
            status = "ready" if error_count == 0 else "draft"
            section_status = "ready" if error_count == 0 else "has_errors"
            batch_status = "quarantined" if error_count else "validated"
            issues_json = json.dumps(issues, ensure_ascii=False, sort_keys=True)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                submission_row AS (
                  SELECT ds.*
                  FROM data_submissions ds
                  WHERE ds.tenant_id = app_tenant_id()
                    AND ds.submission_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    submission.tenant_id, actor.user_id, %s, 'data_submission', submission.submission_id::text, %s,
                    'allow', %s, %s, %s
                  FROM submission_row submission, actor_row actor
                  RETURNING decision_id
                ),
                deleted_issues AS (
                  DELETE FROM validation_issues
                  WHERE submission_id = (SELECT submission_id FROM submission_row)
                ),
                issue_input AS (
                  SELECT *
                  FROM jsonb_to_recordset(%s::jsonb) AS issue_payload(
                    section text,
                    path text,
                    code text,
                    severity text,
                    message text,
                    suggestion text,
                    row_number integer,
                    column_name text
                  )
                ),
                inserted_issues AS (
                  INSERT INTO validation_issues (
                    submission_id, section_name, path, row_number, column_name,
                    code, severity, message, suggestion
                  )
                  SELECT
                    submission.submission_id,
                    issue.section,
                    issue.path,
                    issue.row_number,
                    issue.column_name,
                    issue.code,
                    issue.severity,
                    issue.message,
                    issue.suggestion
                  FROM submission_row submission, issue_input issue
                  RETURNING issue_id
                ),
                deleted_raw_errors AS (
                  DELETE FROM raw_record_errors
                  WHERE raw_record_id IN (
                    SELECT record.raw_record_id
                    FROM raw_records record
                    JOIN ingestion_batches batch ON batch.batch_id = record.batch_id
                    JOIN submission_row submission ON submission.submission_id = batch.submission_id
                  )
                ),
                inserted_raw_errors AS (
                  INSERT INTO raw_record_errors (
                    raw_record_id, code, severity, message
                  )
                  SELECT
                    record.raw_record_id,
                    issue.code,
                    issue.severity,
                    issue.message
                  FROM issue_input issue
                  JOIN ingestion_batches batch
                    ON batch.submission_id = (SELECT submission_id FROM submission_row)
                   AND batch.dataset = issue.section
                  JOIN raw_records record
                    ON record.batch_id = batch.batch_id
                   AND record.row_number = issue.row_number
                  WHERE issue.row_number IS NOT NULL
                  RETURNING error_id
                ),
                updated_sections AS (
                  UPDATE submission_sections
                  SET status = %s, updated_at = now()
                  WHERE submission_id = (SELECT submission_id FROM submission_row)
                  RETURNING section_id
                ),
                updated_batches AS (
                  UPDATE ingestion_batches
                  SET status = %s
                  WHERE submission_id = (SELECT submission_id FROM submission_row)
                  RETURNING batch_id
                ),
                updated_submission AS (
                  UPDATE data_submissions
                  SET status = %s, validated_at = now(), updated_at = now()
                  WHERE submission_id = (SELECT submission_id FROM submission_row)
                  RETURNING *
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'DATA_SUBMISSION_VALIDATED', actor.user_id, %s, updated.submission_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated.submission_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'status', updated.status,
                      'error_count', %s,
                      'issue_count', (SELECT COUNT(*) FROM inserted_issues),
                      'raw_error_count', (SELECT COUNT(*) FROM inserted_raw_errors),
                      'updated_batch_count', (SELECT COUNT(*) FROM updated_batches)
                    ),
                    %s, %s
                  FROM updated_submission updated, actor_row actor, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN updated_submission updated ON updated.reporting_period_id = rp.reporting_period_id
                ),
                org_row AS (
                  SELECT COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated_submission updated ON updated.organization_id = org.organization_id
                ),
                sections_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'section_id', section.section_id::text,
                        'section_name', section.section_name,
                        'status', section.status,
                        'payload', section.payload,
                        'updated_at', section.updated_at::text
                      )
                      ORDER BY section.section_name
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM submission_sections section
                  JOIN updated_submission updated ON updated.submission_id = section.submission_id
                ),
                issues_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'issue_id', issue.issue_id::text,
                        'section_name', issue.section_name,
                        'path', issue.path,
                        'row_number', issue.row_number,
                        'column_name', issue.column_name,
                        'code', issue.code,
                        'severity', issue.severity,
                        'message', issue.message,
                        'suggestion', issue.suggestion
                      )
                      ORDER BY issue.severity, issue.section_name, issue.row_number
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM validation_issues issue
                  JOIN updated_submission updated ON updated.submission_id = issue.submission_id
                )
                SELECT
                  updated.submission_id::text AS submission_id,
                  tenant.external_key AS tenant_id,
                  org.external_id AS organization_id,
                  period.reporting_period_id::text AS id,
                  period.period_type::text AS period_type,
                  period.period_key,
                  period.period_start::text AS period_start,
                  period.period_end::text AS period_end,
                  period.status,
                  period.lock_version,
                  updated.source_type,
                  updated.status::text AS submission_status,
                  updated.version,
                  COALESCE(submitter.external_subject, updated.submitted_by::text) AS submitted_by,
                  updated.created_at::text AS created_at,
                  updated.updated_at::text AS updated_at,
                  updated.submitted_at::text AS submitted_at,
                  updated.validated_at::text AS validated_at,
                  updated.canonicalized_at::text AS canonicalized_at,
                  sections_json.data AS sections,
                  issues_json.data AS issues,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated_submission updated
                JOIN period_row period ON period.reporting_period_id = updated.reporting_period_id
                JOIN org_row org ON true
                JOIN tenants tenant ON tenant.tenant_id = updated.tenant_id
                JOIN user_accounts submitter ON submitter.user_id = updated.submitted_by
                JOIN sections_json ON true
                JOIN issues_json ON true
                JOIN policy ON true
                JOIN audit ON true
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    submission_id,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    issues_json,
                    section_status,
                    batch_status,
                    status,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    error_count,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.validate_submission.unprovisioned_identity")
        return self._submission_payload(row)

    def error_report(self, submission_id: str, context: RequestContext, report_format: str = "json") -> dict[str, Any]:
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  ds.submission_id::text AS submission_id,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id
                FROM data_submissions ds
                JOIN organizations org ON org.organization_id = ds.organization_id
                WHERE ds.tenant_id = app_tenant_id()
                  AND ds.submission_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (submission_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(submission_id)
            decision = PolicyService.require(
                "read_financials",
                context,
                resource_type="data_submission_error_report",
                resource_id=submission_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="restricted_financial",
            )
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                submission_row AS (
                  SELECT ds.*
                  FROM data_submissions ds
                  WHERE ds.tenant_id = app_tenant_id()
                    AND ds.submission_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    submission.tenant_id, actor.user_id, %s, 'data_submission_error_report', submission.submission_id::text, %s,
                    'allow', %s, %s, %s
                  FROM submission_row submission, actor_row actor
                  RETURNING decision_id
                ),
                issue_rows AS (
                  SELECT jsonb_build_object(
                    'source', 'validation_issue',
                    'batch_id', batch.batch_id::text,
                    'dataset', COALESCE(batch.dataset, issue.section_name),
                    'file_name', raw_file.file_name,
                    'raw_record_id', record.raw_record_id::text,
                    'row', issue.row_number,
                    'column', issue.column_name,
                    'path', issue.path,
                    'code', issue.code,
                    'severity', issue.severity,
                    'message', issue.message,
                    'suggestion', issue.suggestion,
                    'payload', COALESCE(record.payload, '{}'::jsonb)
                  ) AS row_payload
                  FROM validation_issues issue
                  JOIN submission_row submission ON submission.submission_id = issue.submission_id
                  LEFT JOIN ingestion_batches batch
                    ON batch.submission_id = issue.submission_id
                   AND batch.dataset = issue.section_name
                  LEFT JOIN raw_records record
                    ON record.batch_id = batch.batch_id
                   AND record.row_number = issue.row_number
                  LEFT JOIN raw_file_objects raw_file ON raw_file.raw_file_id = record.raw_file_id
                ),
                raw_error_rows AS (
                  SELECT jsonb_build_object(
                    'source', 'raw_record_error',
                    'batch_id', batch.batch_id::text,
                    'dataset', batch.dataset,
                    'file_name', raw_file.file_name,
                    'raw_record_id', record.raw_record_id::text,
                    'row', record.row_number,
                    'column', NULL,
                    'path', NULL,
                    'code', raw_error.code,
                    'severity', raw_error.severity,
                    'message', raw_error.message,
                    'suggestion', NULL,
                    'payload', record.payload
                  ) AS row_payload
                  FROM raw_record_errors raw_error
                  JOIN raw_records record ON record.raw_record_id = raw_error.raw_record_id
                  JOIN ingestion_batches batch ON batch.batch_id = record.batch_id
                  JOIN raw_file_objects raw_file ON raw_file.raw_file_id = record.raw_file_id
                  JOIN submission_row submission ON submission.submission_id = batch.submission_id
                ),
                report_rows AS (
                  SELECT row_payload FROM issue_rows
                  UNION ALL
                  SELECT row_payload FROM raw_error_rows
                ),
                report_json AS (
                  SELECT COALESCE(jsonb_agg(row_payload), '[]'::jsonb) AS rows
                  FROM report_rows
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    submission.tenant_id, 'DATA_SUBMISSION_ERROR_REPORT_VIEWED', actor.user_id, %s, submission.submission_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || submission.submission_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('format', %s, 'row_count', jsonb_array_length(report_json.rows)),
                    %s, %s
                  FROM submission_row submission, actor_row actor, policy, report_json
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  report_json.rows,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM report_json, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    submission_id,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    report_format,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.error_report.unprovisioned_identity")
        rows = [item for item in self._json_list(row.get("rows")) if isinstance(item, dict)]
        summary = {
            "errors": len([item for item in rows if item.get("severity") == "error"]),
            "warnings": len([item for item in rows if item.get("severity") == "warning"]),
            "infos": len([item for item in rows if item.get("severity") == "info"]),
            "rows": len(rows),
        }
        return {
            "submission_id": submission_id,
            "format": report_format,
            "summary": summary,
            "rows": rows,
            "csv": self._error_report_csv(rows) if report_format == "csv" else None,
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
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
        can_view_all = self._can_view_all_review_tasks(context)
        scoped_organization_ids = sorted(context.organization_ids)
        organization_clause = ""
        assignment_clause = ""
        status_clause = "" if status == "all" else "AND review.status = %s"
        params: list[Any] = [context.actor_id, context.actor_id]
        if not can_view_all:
            if scoped_organization_ids:
                placeholders = ", ".join("%s" for _ in scoped_organization_ids)
                organization_clause = f"AND COALESCE(org.external_business_id, org.organization_id::text) IN ({placeholders})"
                params.extend(scoped_organization_ids)
                assignment_clause = "AND review.assigned_to = (SELECT user_id FROM actor_row)"
            else:
                organization_clause = "AND false"
        if status != "all":
            params.append(status)
        params.extend(
            [
                bounded_limit,
                decision.action,
                status,
                decision.data_classification,
                decision.reason,
                context.purpose,
                context.request_id,
                context.actor_role,
                context.purpose,
                context.request_id,
                status,
                bounded_limit,
                "all" if can_view_all else "membership",
                status,
                context.app_mode,
                context.auth_assurance,
            ]
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                f"""
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                queue_source AS (
                  SELECT
                    review.review_task_id::text AS review_task_id,
                    ds.submission_id::text AS submission_id,
                    COALESCE(org.external_business_id, org.organization_id::text) AS organization_id,
                    COALESCE(profile.trade_name, org.name, org.organization_id::text) AS organization_name,
                    rp.period_key,
                    rp.period_start::text AS period_start,
                    rp.period_end::text AS period_end,
                    review.status::text AS review_status,
                    review.assigned_role,
                    COALESCE(assigned_user.external_subject, review.assigned_to::text) AS assigned_to,
                    review.assignment_reason,
                    review.assigned_at::text AS assigned_at,
                    ds.status::text AS submission_status,
                    ds.source_type AS source,
                    ds.version,
                    COALESCE(submitter.external_subject, ds.submitted_by::text) AS submitted_by,
                    ds.submitted_at::text AS submitted_at,
                    ds.updated_at::text AS updated_at,
                    (
                      SELECT COUNT(*)::int
                      FROM validation_issues issue
                      WHERE issue.submission_id = ds.submission_id AND issue.severity = 'error'
                    ) AS error_count,
                    (
                      SELECT COUNT(*)::int
                      FROM validation_issues issue
                      WHERE issue.submission_id = ds.submission_id AND issue.severity = 'warning'
                    ) AS warning_count,
                    (
                      SELECT COUNT(*)::int
                      FROM validation_issues issue
                      WHERE issue.submission_id = ds.submission_id AND issue.severity = 'info'
                    ) AS info_count,
                    jsonb_build_object(
                      'total', COALESCE(evidence_counts.total, 0),
                      'clean', COALESCE(evidence_counts.clean, 0),
                      'pending', COALESCE(evidence_counts.pending, 0),
                      'rejected', COALESCE(evidence_counts.rejected, 0),
                      'required', COALESCE(evidence_counts.total, 0) > 0,
                      'approval_blocked', COALESCE(evidence_counts.total, 0) > 0
                        AND (COALESCE(evidence_counts.pending, 0) > 0 OR COALESCE(evidence_counts.rejected, 0) > 0),
                      'advisory',
                        CASE
                          WHEN COALESCE(evidence_counts.total, 0) > 0
                            AND (COALESCE(evidence_counts.pending, 0) > 0 OR COALESCE(evidence_counts.rejected, 0) > 0)
                          THEN 'Approval blocked until submitted/uploaded evidence has clean malware scan status.'
                          ELSE 'Evidence gate passed or no evidence was submitted for this period.'
                        END
                    ) AS evidence_summary,
                    (
                      SELECT COALESCE(
                        jsonb_agg(
                          jsonb_build_object('section', section.section_name, 'status', section.status)
                          ORDER BY section.section_name
                        ),
                        '[]'::jsonb
                      )
                      FROM submission_sections section
                      WHERE section.submission_id = ds.submission_id
                    ) AS sections
                  FROM review_tasks review
                  JOIN data_submissions ds ON ds.submission_id = review.submission_id
                  JOIN reporting_periods rp ON rp.reporting_period_id = ds.reporting_period_id
                  JOIN organizations org ON org.organization_id = ds.organization_id
                  LEFT JOIN business_profiles profile ON profile.organization_id = ds.organization_id
                  JOIN user_accounts submitter ON submitter.user_id = ds.submitted_by
                  LEFT JOIN user_accounts assigned_user ON assigned_user.user_id = review.assigned_to
                  LEFT JOIN LATERAL (
                    SELECT
                      COUNT(*)::int AS total,
                      COUNT(*) FILTER (WHERE status_row.scan_status = 'clean')::int AS clean,
                      COUNT(*) FILTER (WHERE status_row.scan_status IN ('infected', 'failed'))::int AS rejected,
                      COUNT(*) FILTER (WHERE status_row.scan_status NOT IN ('clean', 'infected', 'failed'))::int AS pending
                    FROM (
                      SELECT COALESCE(item.value->>'malware_scan_status', 'pending_scan') AS scan_status
                      FROM submission_sections section
                      CROSS JOIN LATERAL jsonb_array_elements(
                        CASE
                          WHEN jsonb_typeof(section.payload) = 'array' THEN section.payload
                          WHEN section.payload = '{{}}'::jsonb THEN '[]'::jsonb
                          ELSE jsonb_build_array(section.payload)
                        END
                      ) item(value)
                      WHERE section.submission_id = ds.submission_id
                        AND section.section_name = 'evidence'
                      UNION ALL
                      SELECT COALESCE(document.malware_scan_status, 'pending_scan') AS scan_status
                      FROM evidence_documents document
                      WHERE document.tenant_id = ds.tenant_id
                        AND document.organization_id = ds.organization_id
                        AND document.reporting_period_id = ds.reporting_period_id
                      UNION ALL
                      SELECT COALESCE(version.malware_scan_status, 'pending_scan') AS scan_status
                      FROM evidence_versions version
                      WHERE version.tenant_id = ds.tenant_id
                        AND version.organization_id = ds.organization_id
                        AND version.period_key = rp.period_key
                        AND version.evidence_document_id IS NULL
                    ) status_row
                  ) evidence_counts ON true
                  WHERE ds.tenant_id = app_tenant_id()
                    {organization_clause}
                    {assignment_clause}
                    {status_clause}
                  ORDER BY
                    CASE review.status WHEN 'open' THEN 0 ELSE 1 END,
                    ds.submitted_at DESC NULLS LAST,
                    review.created_at DESC
                  LIMIT %s
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    app_tenant_id(), actor.user_id, %s, 'review_queue', %s, %s,
                    'allow', %s, %s, %s
                  FROM actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    app_tenant_id(), 'DATA_SUBMISSION_REVIEW_QUEUE_VIEWED', actor.user_id, %s, %s, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || %s || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'status', %s,
                      'limit', %s,
                      'scope', %s,
                      'count', (SELECT COUNT(*) FROM queue_source)
                    ),
                    %s, %s
                  FROM actor_row actor, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  COALESCE((SELECT jsonb_agg(to_jsonb(queue_source)) FROM queue_source), '[]'::jsonb) AS review_tasks,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM policy, audit
                """,
                tuple(params),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.review_tasks.unprovisioned_identity")
        return {
            "review_tasks": [self._review_queue_payload(item) for item in self._json_list(row.get("review_tasks")) if isinstance(item, dict)],
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": "Review queue supports human approval only; it is not an automated financing or legal decision.",
        }

    def submit_submission(self, submission_id: str, context: RequestContext) -> dict[str, Any]:
        validated = self.validate_submission(submission_id, context)
        if validated["validation_summary"]["errors"]:
            return validated
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  ds.submission_id::text AS submission_id,
                  ds.status::text AS status,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id
                FROM data_submissions ds
                JOIN organizations org ON org.organization_id = ds.organization_id
                WHERE ds.tenant_id = app_tenant_id()
                  AND ds.submission_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (submission_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(submission_id)
            decision = PolicyService.require(
                "submit_submission",
                context,
                resource_type="data_submission",
                resource_id=submission_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="restricted_financial",
            )
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                existing_submission AS (
                  SELECT ds.*
                  FROM data_submissions ds
                  WHERE ds.tenant_id = app_tenant_id()
                    AND ds.submission_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    existing.tenant_id, actor.user_id, %s, 'data_submission', existing.submission_id::text, %s,
                    'allow', %s, %s, %s
                  FROM existing_submission existing, actor_row actor
                  RETURNING decision_id
                ),
                updated_submission AS (
                  UPDATE data_submissions
                  SET status = 'in_review', submitted_at = now(), locked_at = now(), updated_at = now()
                  WHERE submission_id = (SELECT submission_id FROM existing_submission)
                  RETURNING *
                ),
                reviewer_assignment AS (
                  SELECT ua.user_id
                  FROM memberships membership
                  JOIN updated_submission updated ON updated.organization_id = membership.organization_id
                  JOIN user_accounts ua ON ua.user_id = membership.user_id
                  WHERE membership.tenant_id = app_tenant_id()
                    AND membership.status = 'active'
                    AND membership.role_id = 'reviewer'
                    AND ua.status = 'active'
                  ORDER BY ua.created_at, ua.user_id
                  LIMIT 1
                ),
                review AS (
                  INSERT INTO review_tasks (
                    submission_id, status, assigned_role, assigned_to, assignment_reason, assigned_at
                  )
                  SELECT
                    updated.submission_id,
                    'open',
                    'reviewer',
                    reviewer.user_id,
                    CASE WHEN reviewer.user_id IS NULL THEN 'unassigned_no_active_org_reviewer' ELSE 'auto_assigned_primary_org_reviewer' END,
                    now()
                  FROM updated_submission updated
                  LEFT JOIN reviewer_assignment reviewer ON true
                  RETURNING *
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'DATA_SUBMISSION_SUBMITTED', actor.user_id, %s, updated.submission_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated.submission_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('review_task_id', review.review_task_id::text, 'status', updated.status),
                    %s, %s
                  FROM updated_submission updated, actor_row actor, policy, review
                  LEFT JOIN previous ON true
                  RETURNING event_id
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN updated_submission updated ON updated.reporting_period_id = rp.reporting_period_id
                ),
                org_row AS (
                  SELECT COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated_submission updated ON updated.organization_id = org.organization_id
                ),
                sections_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'section_id', section.section_id::text,
                        'section_name', section.section_name,
                        'status', section.status,
                        'payload', section.payload,
                        'updated_at', section.updated_at::text
                      )
                      ORDER BY section.section_name
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM submission_sections section
                  JOIN updated_submission updated ON updated.submission_id = section.submission_id
                ),
                issues_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'issue_id', issue.issue_id::text,
                        'section_name', issue.section_name,
                        'path', issue.path,
                        'row_number', issue.row_number,
                        'column_name', issue.column_name,
                        'code', issue.code,
                        'severity', issue.severity,
                        'message', issue.message,
                        'suggestion', issue.suggestion
                      )
                      ORDER BY issue.severity, issue.section_name, issue.row_number
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM validation_issues issue
                  JOIN updated_submission updated ON updated.submission_id = issue.submission_id
                )
                SELECT
                  updated.submission_id::text AS submission_id,
                  tenant.external_key AS tenant_id,
                  org.external_id AS organization_id,
                  period.reporting_period_id::text AS id,
                  period.period_type::text AS period_type,
                  period.period_key,
                  period.period_start::text AS period_start,
                  period.period_end::text AS period_end,
                  period.status,
                  period.lock_version,
                  updated.source_type,
                  updated.status::text AS submission_status,
                  updated.version,
                  COALESCE(submitter.external_subject, updated.submitted_by::text) AS submitted_by,
                  updated.created_at::text AS created_at,
                  updated.updated_at::text AS updated_at,
                  updated.submitted_at::text AS submitted_at,
                  updated.validated_at::text AS validated_at,
                  updated.canonicalized_at::text AS canonicalized_at,
                  sections_json.data AS sections,
                  issues_json.data AS issues,
                  jsonb_build_object(
                    'review_task_id', review.review_task_id::text,
                    'status', review.status,
                    'assigned_role', review.assigned_role,
                    'assigned_to', COALESCE(assigned_user.external_subject, review.assigned_to::text),
                    'assignment_reason', review.assignment_reason,
                    'assigned_at', review.assigned_at::text,
                    'decided_by', review.decided_by::text,
                    'decision', review.decision,
                    'decision_note', review.decision_note,
                    'created_at', review.created_at::text,
                    'decided_at', review.decided_at::text
                  ) AS review_task,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated_submission updated
                JOIN period_row period ON period.reporting_period_id = updated.reporting_period_id
                JOIN org_row org ON true
                JOIN tenants tenant ON tenant.tenant_id = updated.tenant_id
                JOIN user_accounts submitter ON submitter.user_id = updated.submitted_by
                JOIN review ON review.submission_id = updated.submission_id
                LEFT JOIN user_accounts assigned_user ON assigned_user.user_id = review.assigned_to
                JOIN sections_json ON true
                JOIN issues_json ON true
                JOIN policy ON true
                JOIN audit ON true
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    submission_id,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.submit_submission.unprovisioned_identity")
        return self._submission_payload(row)

    def review_decision(self, review_task_id: str, decision: str, note: str | None, context: RequestContext) -> dict[str, Any]:
        if decision not in {"approve", "reject", "request_changes"}:
            raise ValueError("Unsupported review decision.")
        submission_status = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested"}[decision]
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  review.review_task_id::text AS review_task_id,
                  review.submission_id::text AS submission_id,
                  COALESCE(assigned_user.external_subject, review.assigned_to::text) AS assigned_to,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id
                FROM review_tasks review
                JOIN data_submissions ds ON ds.submission_id = review.submission_id
                JOIN organizations org ON org.organization_id = ds.organization_id
                LEFT JOIN user_accounts assigned_user ON assigned_user.user_id = review.assigned_to
                WHERE ds.tenant_id = app_tenant_id()
                  AND review.review_task_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (review_task_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(review_task_id)
            policy_decision = PolicyService.require(
                "review_submission",
                context,
                resource_type="review_task",
                resource_id=review_task_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="restricted_financial",
            )
            if not self._can_view_all_review_tasks(context) and existing.get("assigned_to") != context.actor_id:
                raise AccessDeniedError("POLICY_DENIED", "Review task is assigned to a different reviewer.", status_code=403)
            evidence_review = self._submission_evidence_review_summary(connection, str(existing["submission_id"]))
            if decision == "approve" and evidence_review["approval_blocked"]:
                raise ValueError("Approval blocked until submitted or uploaded evidence for this period has clean malware scan status.")
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                review_row AS (
                  SELECT review.*
                  FROM review_tasks review
                  JOIN data_submissions ds ON ds.submission_id = review.submission_id
                  WHERE ds.tenant_id = app_tenant_id()
                    AND review.review_task_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                submission_before AS (
                  SELECT ds.*
                  FROM data_submissions ds
                  JOIN review_row review ON review.submission_id = ds.submission_id
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN submission_before submission ON submission.reporting_period_id = rp.reporting_period_id
                ),
                org_row AS (
                  SELECT COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN submission_before submission ON submission.organization_id = org.organization_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    submission.tenant_id, actor.user_id, %s, 'review_task', review.review_task_id::text, %s,
                    'allow', %s, %s, %s
                  FROM submission_before submission, review_row review, actor_row actor
                  RETURNING decision_id
                ),
                sections AS (
                  SELECT section.section_name, section.payload
                  FROM submission_sections section
                  JOIN submission_before submission ON submission.submission_id = section.submission_id
                ),
                financial_section AS (
                  SELECT payload
                  FROM sections
                  WHERE section_name = 'financials'
                  LIMIT 1
                ),
                product_items AS (
                  SELECT item.value AS payload, item.ordinality AS row_number
                  FROM sections section
                  CROSS JOIN LATERAL jsonb_array_elements(
                    CASE
                      WHEN jsonb_typeof(section.payload) = 'array' THEN section.payload
                      WHEN jsonb_typeof(section.payload) = 'object' AND section.payload <> '{}'::jsonb THEN jsonb_build_array(section.payload)
                      ELSE '[]'::jsonb
                    END
                  ) WITH ORDINALITY AS item(value, ordinality)
                  WHERE section.section_name = 'products'
                ),
                evidence_items AS (
                  SELECT item.value AS payload, item.ordinality AS row_number
                  FROM sections section
                  CROSS JOIN LATERAL jsonb_array_elements(
                    CASE
                      WHEN jsonb_typeof(section.payload) = 'array' THEN section.payload
                      WHEN jsonb_typeof(section.payload) = 'object' AND section.payload <> '{}'::jsonb THEN jsonb_build_array(section.payload)
                      ELSE '[]'::jsonb
                    END
                  ) WITH ORDINALITY AS item(value, ordinality)
                  WHERE section.section_name = 'evidence'
                ),
                financial_insert AS (
                  INSERT INTO financial_snapshots (
                    tenant_id, organization_id, reporting_period_id, statement_type,
                    version, metrics, source_submission_id, source_record_id, valid_from, valid_to
                  )
                  SELECT
                    submission.tenant_id, submission.organization_id, submission.reporting_period_id, 'management',
                    submission.version, financial.payload, submission.submission_id,
                    'SECTION-' || submission.submission_id::text || '-FINANCIALS',
                    period.period_start, NULL
                  FROM submission_before submission, period_row period, financial_section financial
                  WHERE %s = 'approve'
                    AND financial.payload IS NOT NULL
                    AND financial.payload <> '{}'::jsonb
                  ON CONFLICT (organization_id, reporting_period_id, statement_type, version) DO NOTHING
                  RETURNING snapshot_id
                ),
                product_insert AS (
                  INSERT INTO product_capabilities (
                    tenant_id, organization_id, reporting_period_id, sku, product_name,
                    category, specification, available_capacity, min_order_value, price_range,
                    certifications, shelf_life_days, temperature_band, packaging_type,
                    case_pack, substitution_group, version, source_submission_id,
                    source_record_id, valid_from, valid_to
                  )
                  SELECT
                    submission.tenant_id,
                    submission.organization_id,
                    submission.reporting_period_id,
                    COALESCE(NULLIF(product.payload->>'sku', ''), 'SKU-' || lpad(product.row_number::text, 3, '0')),
                    COALESCE(NULLIF(product.payload->>'product_name', ''), NULLIF(product.payload->>'name', ''), 'Submitted product'),
                    COALESCE(NULLIF(product.payload->>'category', ''), 'uncategorized'),
                    product.payload->>'specification',
                    COALESCE(NULLIF(product.payload->>'available_capacity', '')::numeric, 0),
                    COALESCE(NULLIF(product.payload->>'min_order_value', '')::numeric, 0),
                    product.payload->>'price_range',
                    product.payload->>'certifications',
                    COALESCE(NULLIF(product.payload->>'shelf_life_days', '')::integer, 180),
                    COALESCE(NULLIF(product.payload->>'temperature_band', ''), 'ambient'),
                    COALESCE(NULLIF(product.payload->>'packaging_type', ''), 'case'),
                    COALESCE(NULLIF(product.payload->>'case_pack', ''), 'standard'),
                    COALESCE(NULLIF(product.payload->>'substitution_group', ''), NULLIF(product.payload->>'category', ''), 'general'),
                    submission.version,
                    submission.submission_id,
                    'SECTION-' || submission.submission_id::text || '-PRODUCT-' || product.row_number::text,
                    period.period_start,
                    NULL
                  FROM submission_before submission, period_row period, product_items product
                  WHERE %s = 'approve'
                  ON CONFLICT (organization_id, reporting_period_id, sku, version) DO NOTHING
                  RETURNING capability_id
                ),
                evidence_input AS (
                  SELECT
                    evidence.payload,
                    evidence.row_number,
                    'SECTION-' || submission.submission_id::text || '-EVIDENCE-' || evidence.row_number::text AS source_record_id
                  FROM evidence_items evidence, submission_before submission
                  WHERE %s = 'approve'
                    AND evidence.payload->>'malware_scan_status' = 'clean'
                    AND COALESCE(NULLIF(evidence.payload->>'document_hash', ''), '') <> ''
                ),
                evidence_document_insert AS (
                  INSERT INTO evidence_documents (
                    tenant_id, organization_id, reporting_period_id, document_type,
                    title, classification, retention_status, legal_hold,
                    source_submission_id, source_record_id, valid_from, valid_to
                  )
                  SELECT
                    submission.tenant_id,
                    submission.organization_id,
                    submission.reporting_period_id,
                    COALESCE(NULLIF(evidence.payload->>'document_type', ''), NULLIF(evidence.payload->>'type', ''), 'SUPPORTING_DOCUMENT'),
                    COALESCE(NULLIF(evidence.payload->>'title', ''), NULLIF(evidence.payload->>'file_name', ''), 'Evidence ' || evidence.row_number::text),
                    COALESCE(NULLIF(evidence.payload->>'classification', ''), 'confidential'),
                    'active',
                    false,
                    submission.submission_id,
                    evidence.source_record_id,
                    period.period_start,
                    NULL
                  FROM submission_before submission, period_row period, evidence_input evidence
                  RETURNING evidence_document_id, source_record_id
                ),
                evidence_version_insert AS (
                  INSERT INTO evidence_versions (
                    evidence_document_id, tenant_id, organization_id, object_key, object_version,
                    document_hash, content_type, byte_size, malware_scan_status,
                    uploader_id, supersedes_version_id
                  )
                  SELECT
                    document.evidence_document_id,
                    submission.tenant_id,
                    submission.organization_id,
                    COALESCE(NULLIF(evidence.payload->>'object_key', ''), 'submitted/' || submission.submission_id::text || '/' || document.evidence_document_id::text),
                    COALESCE(NULLIF(evidence.payload->>'object_version', ''), evidence.payload->>'document_hash'),
                    evidence.payload->>'document_hash',
                    COALESCE(NULLIF(evidence.payload->>'content_type', ''), 'application/octet-stream'),
                    GREATEST(COALESCE(NULLIF(evidence.payload->>'byte_size', '')::bigint, 1), 1),
                    'clean',
                    submission.submitted_by,
                    NULL
                  FROM evidence_document_insert document
                  JOIN evidence_input evidence ON evidence.source_record_id = document.source_record_id
                  CROSS JOIN submission_before submission
                  RETURNING evidence_version_id
                ),
                analytics_feature AS (
                  SELECT
                    submission.tenant_id,
                    submission.organization_id,
                    submission.reporting_period_id,
                    submission.submission_id,
                    period.period_key,
                    COALESCE(NULLIF(financial.payload->>'revenue', '')::numeric, 1) AS revenue,
                    COALESCE(NULLIF(financial.payload->>'cash_in', '')::numeric, 0)
                      - COALESCE(NULLIF(financial.payload->>'cash_out', '')::numeric, 0) AS net_cashflow,
                    COALESCE(NULLIF(financial.payload->>'debt', '')::numeric, 0)
                      / GREATEST(COALESCE(NULLIF(financial.payload->>'revenue', '')::numeric, 1), 1) AS debt_ratio,
                    CASE
                      WHEN COALESCE(NULLIF(financial.payload->>'late_payment_rate', '')::numeric, 0) > 1
                      THEN COALESCE(NULLIF(financial.payload->>'late_payment_rate', '')::numeric, 0) / 100
                      ELSE COALESCE(NULLIF(financial.payload->>'late_payment_rate', '')::numeric, 0)
                    END AS late_rate,
                    CASE
                      WHEN COALESCE(NULLIF(financial.payload->>'delivery_delay_rate', '')::numeric, 0) > 1
                      THEN COALESCE(NULLIF(financial.payload->>'delivery_delay_rate', '')::numeric, 0) / 100
                      ELSE COALESCE(NULLIF(financial.payload->>'delivery_delay_rate', '')::numeric, 0)
                    END AS delay_rate,
                    (SELECT COUNT(*) FROM product_items) AS product_count,
                    COALESCE(
                      NULLIF((SELECT payload->>'category' FROM product_items ORDER BY row_number LIMIT 1), ''),
                      'general'
                    ) AS product_category,
                    'PS-' || submission.organization_id::text || '-' || period.period_key AS source_snapshot_id
                  FROM submission_before submission, period_row period
                  LEFT JOIN financial_section financial ON true
                  WHERE %s = 'approve'
                ),
                feature_insert AS (
                  INSERT INTO feature_snapshots (
                    tenant_id, organization_id, reporting_period_id, source_snapshot_id,
                    feature_set_version, payload
                  )
                  SELECT
                    feature.tenant_id,
                    feature.organization_id,
                    feature.reporting_period_id,
                    feature.source_snapshot_id,
                    'intake-feature-set-v0.1-postgres',
                    jsonb_build_object(
                      'source_submission_id', feature.submission_id::text,
                      'period_key', feature.period_key,
                      'net_cashflow', feature.net_cashflow,
                      'debt_to_monthly_revenue', round(feature.debt_ratio, 4),
                      'late_payment_rate', feature.late_rate,
                      'delivery_delay_rate', feature.delay_rate,
                      'product_count', feature.product_count,
                      'notice', 'Feature snapshot is for management review; not a credit score input without lender approval.'
                    )
                  FROM analytics_feature feature
                  WHERE NOT EXISTS (
                    SELECT 1
                    FROM feature_snapshots existing
                    WHERE existing.tenant_id = feature.tenant_id
                      AND existing.source_snapshot_id = feature.source_snapshot_id
                  )
                  RETURNING *
                ),
                risk_insert AS (
                  INSERT INTO risk_runs (
                    tenant_id, organization_id, reporting_period_id, feature_snapshot_id,
                    model_version, ruleset_version, score, level, explanation, review_status
                  )
                  SELECT
                    inserted.tenant_id,
                    inserted.organization_id,
                    inserted.reporting_period_id,
                    inserted.feature_snapshot_id,
                    'deterministic-postgres-v0.1',
                    'intake-risk-rules-v0.1',
                    score.score,
                    CASE WHEN score.score >= 70 THEN 'high' WHEN score.score >= 50 THEN 'watch' ELSE 'stable' END,
                    'Advisory operational signal from approved period intake; not a credit score or default probability.',
                    'pending_human_review'
                  FROM feature_insert inserted
                  JOIN analytics_feature feature ON feature.source_snapshot_id = inserted.source_snapshot_id
                  CROSS JOIN LATERAL (
                    SELECT LEAST(
                      100,
                      GREATEST(
                        0,
                        round(
                          35
                          + CASE WHEN feature.net_cashflow < 0 THEN 15 ELSE -8 END
                          + LEAST(25, feature.debt_ratio * 25)
                          + feature.late_rate * 30
                          + feature.delay_rate * 30
                        )
                      )
                    )::integer AS score
                  ) score
                  RETURNING risk_run_id
                ),
                match_run_insert AS (
                  INSERT INTO match_runs (
                    tenant_id, buyer_organization_id, reporting_period_id,
                    disrupted_supplier_id, product_category, ruleset_version, review_status
                  )
                  SELECT
                    feature.tenant_id,
                    feature.organization_id,
                    feature.reporting_period_id,
                    NULL,
                    feature.product_category,
                    'supplier-shortlist-rules-v0.1',
                    'pending_human_review'
                  FROM analytics_feature feature
                  JOIN feature_insert inserted ON inserted.source_snapshot_id = feature.source_snapshot_id
                  WHERE feature.product_count > 0
                  RETURNING match_run_id, tenant_id, buyer_organization_id, product_category
                ),
                match_candidate_source AS (
                  SELECT
                    match_run.match_run_id,
                    candidate.organization_id AS supplier_organization_id,
                    row_number() OVER (PARTITION BY match_run.match_run_id ORDER BY candidate.organization_id) AS rank
                  FROM match_run_insert match_run
                  JOIN business_profiles candidate
                    ON candidate.tenant_id = match_run.tenant_id
                   AND candidate.product_category = match_run.product_category
                   AND candidate.organization_id <> match_run.buyer_organization_id
                   AND candidate.status = 'active'
                ),
                match_candidate_insert AS (
                  INSERT INTO match_candidates (
                    match_run_id, supplier_organization_id, rank, score, explanation, consent_status
                  )
                  SELECT
                    source.match_run_id,
                    source.supplier_organization_id,
                    source.rank,
                    GREATEST(50, 82 - source.rank * 7),
                    jsonb_build_object(
                      'reason', 'Same product category from approved profile.',
                      'guardrail', 'Contact reveal requires consent and human approval.'
                    ),
                    'not_requested'
                  FROM match_candidate_source source
                  WHERE source.rank <= 3
                  RETURNING candidate_id
                ),
                scenario_insert AS (
                  INSERT INTO scenario_runs (
                    tenant_id, organization_id, reporting_period_id, input_snapshot_id,
                    shock_organization_id, product_category, ruleset_version, model_version,
                    payload, review_status, created_by
                  )
                  SELECT
                    feature.tenant_id,
                    feature.organization_id,
                    feature.reporting_period_id,
                    inserted.feature_snapshot_id,
                    NULL,
                    feature.product_category,
                    'scenario-rules-v0.1',
                    'deterministic-postgres-v0.1',
                    jsonb_build_object(
                      'source_submission_id', feature.submission_id::text,
                      'period_key', feature.period_key,
                      'input_snapshot_id', inserted.feature_snapshot_id::text,
                      'shock_organization_id', NULL,
                      'product_category', feature.product_category,
                      'impact_model', 'deterministic adjacency placeholder',
                      'guardrail', 'Scenario output is decision-support only and requires human review before operational action.'
                    ),
                    'pending_human_review',
                    (SELECT submitted_by FROM submission_before)
                  FROM analytics_feature feature
                  JOIN feature_insert inserted ON inserted.source_snapshot_id = feature.source_snapshot_id
                  RETURNING scenario_run_id
                ),
                model_seed AS (
                  SELECT *
                  FROM (
                    VALUES
                      ('risk', 'deterministic-postgres-v0.1', jsonb_build_object('purpose', 'risk decision-support')),
                      ('scenario', 'deterministic-postgres-v0.1', jsonb_build_object('purpose', 'scenario decision-support'))
                  ) AS seed(artifact_type, model_version, config)
                ),
                model_registry_insert AS (
                  INSERT INTO model_registry (
                    tenant_id, artifact_type, model_version, status, approval_status,
                    config, checksum, created_by
                  )
                  SELECT
                    feature.tenant_id,
                    seed.artifact_type,
                    seed.model_version,
                    'active',
                    'approved',
                    seed.config,
                    encode(digest(seed.artifact_type || ':' || seed.model_version || ':' || seed.config::text, 'sha256'), 'hex'),
                    (SELECT submitted_by FROM submission_before)
                  FROM analytics_feature feature
                  CROSS JOIN model_seed seed
                  ON CONFLICT (tenant_id, artifact_type, model_version) DO NOTHING
                  RETURNING model_registry_id
                ),
                ruleset_seed AS (
                  SELECT *
                  FROM (
                    VALUES
                      ('feature', 'intake-feature-set-v0.1-postgres', jsonb_build_object('sections', jsonb_build_array('profile', 'financials', 'products', 'evidence'))),
                      ('risk', 'intake-risk-rules-v0.1', jsonb_build_object('inputs', jsonb_build_array('cashflow', 'debt', 'late_payment', 'delivery_delay'))),
                      ('matching', 'supplier-shortlist-rules-v0.1', jsonb_build_object('guardrail', 'consent_required')),
                      ('scenario', 'scenario-rules-v0.1', jsonb_build_object('guardrail', 'human_review_required'))
                  ) AS seed(artifact_type, ruleset_version, config)
                ),
                ruleset_registry_insert AS (
                  INSERT INTO ruleset_registry (
                    tenant_id, artifact_type, ruleset_version, status, approval_status,
                    config, checksum, created_by
                  )
                  SELECT
                    feature.tenant_id,
                    seed.artifact_type,
                    seed.ruleset_version,
                    'active',
                    'approved',
                    seed.config,
                    encode(digest(seed.artifact_type || ':' || seed.ruleset_version || ':' || seed.config::text, 'sha256'), 'hex'),
                    (SELECT submitted_by FROM submission_before)
                  FROM analytics_feature feature
                  CROSS JOIN ruleset_seed seed
                  ON CONFLICT (tenant_id, artifact_type, ruleset_version) DO NOTHING
                  RETURNING ruleset_registry_id
                ),
                recompute_job_insert AS (
                  INSERT INTO analytics_recompute_jobs (
                    tenant_id, organization_id, reporting_period_id, source_submission_id,
                    job_type, status, idempotency_key, payload, attempts, max_attempts,
                    created_by, created_at, updated_at, available_at
                  )
                  SELECT
                    feature.tenant_id,
                    feature.organization_id,
                    feature.reporting_period_id,
                    feature.submission_id,
                    'analytics_recompute',
                    'queued',
                    'analytics:' || feature.submission_id::text,
                    jsonb_build_object(
                      'source_submission_id', feature.submission_id::text,
                      'period_key', feature.period_key,
                      'input_snapshot_id', inserted.feature_snapshot_id::text,
                      'expected_artifacts', jsonb_build_array('feature_snapshot', 'risk_run', 'match_run', 'scenario_run'),
                      'reason', 'approved_intake_materialized',
                      'guardrail', 'Worker must be idempotent and must not overwrite historical approved artifacts.'
                    ),
                    0,
                    3,
                    (SELECT submitted_by FROM submission_before),
                    now(),
                    now(),
                    now()
                  FROM analytics_feature feature
                  JOIN feature_insert inserted ON inserted.source_snapshot_id = feature.source_snapshot_id
                  ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                  RETURNING job_id
                ),
                closed_review AS (
                  UPDATE review_tasks
                  SET status = 'closed',
                      decided_by = (SELECT user_id FROM actor_row),
                      decision = %s,
                      decision_note = %s,
                      decided_at = now()
                  WHERE review_task_id = (SELECT review_task_id FROM review_row)
                  RETURNING *
                ),
                updated_submission AS (
                  UPDATE data_submissions
                  SET status = %s,
                      canonicalized_at = CASE WHEN %s = 'approve' THEN now() ELSE canonicalized_at END,
                      locked_at = CASE WHEN %s = 'request_changes' THEN NULL ELSE locked_at END,
                      updated_at = now()
                  WHERE submission_id = (SELECT submission_id FROM submission_before)
                  RETURNING *
                ),
                period_update AS (
                  UPDATE reporting_periods
                  SET status = 'approved', lock_version = lock_version + 1
                  WHERE reporting_period_id = (SELECT reporting_period_id FROM submission_before)
                    AND %s = 'approve'
                  RETURNING reporting_period_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'DATA_SUBMISSION_REVIEW_DECIDED', actor.user_id, %s, review.review_task_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || review.review_task_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'decision', review.decision,
                      'submission_status', updated.status,
                      'financial_snapshots', (SELECT COUNT(*) FROM financial_insert),
                      'product_capabilities', (SELECT COUNT(*) FROM product_insert),
                      'evidence_documents', (SELECT COUNT(*) FROM evidence_document_insert),
                      'feature_snapshots', (SELECT COUNT(*) FROM feature_insert),
                      'risk_runs', (SELECT COUNT(*) FROM risk_insert),
                      'match_runs', (SELECT COUNT(*) FROM match_run_insert),
                      'match_candidates', (SELECT COUNT(*) FROM match_candidate_insert),
                      'scenario_runs', (SELECT COUNT(*) FROM scenario_insert),
                      'model_registry', (SELECT COUNT(*) FROM model_registry_insert),
                      'ruleset_registry', (SELECT COUNT(*) FROM ruleset_registry_insert),
                      'recompute_jobs', (SELECT COUNT(*) FROM recompute_job_insert)
                    ),
                    %s, %s
                  FROM updated_submission updated, actor_row actor, closed_review review, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                ),
                sections_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'section_id', section.section_id::text,
                        'section_name', section.section_name,
                        'status', section.status,
                        'payload', section.payload,
                        'updated_at', section.updated_at::text
                      )
                      ORDER BY section.section_name
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM submission_sections section
                  JOIN updated_submission updated ON updated.submission_id = section.submission_id
                ),
                issues_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'issue_id', issue.issue_id::text,
                        'section_name', issue.section_name,
                        'path', issue.path,
                        'row_number', issue.row_number,
                        'column_name', issue.column_name,
                        'code', issue.code,
                        'severity', issue.severity,
                        'message', issue.message,
                        'suggestion', issue.suggestion
                      )
                      ORDER BY issue.severity, issue.section_name, issue.row_number
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM validation_issues issue
                  JOIN updated_submission updated ON updated.submission_id = issue.submission_id
                )
                SELECT
                  updated.submission_id::text AS submission_id,
                  tenant.external_key AS tenant_id,
                  org.external_id AS organization_id,
                  period.reporting_period_id::text AS id,
                  period.period_type::text AS period_type,
                  period.period_key,
                  period.period_start::text AS period_start,
                  period.period_end::text AS period_end,
                  CASE WHEN %s = 'approve' THEN 'approved' ELSE period.status END AS status,
                  CASE WHEN %s = 'approve' THEN period.lock_version + 1 ELSE period.lock_version END AS lock_version,
                  updated.source_type,
                  updated.status::text AS submission_status,
                  updated.version,
                  COALESCE(submitter.external_subject, updated.submitted_by::text) AS submitted_by,
                  updated.created_at::text AS created_at,
                  updated.updated_at::text AS updated_at,
                  updated.submitted_at::text AS submitted_at,
                  updated.validated_at::text AS validated_at,
                  updated.canonicalized_at::text AS canonicalized_at,
                  sections_json.data AS sections,
                  issues_json.data AS issues,
                  jsonb_build_object(
                    'review_task_id', review.review_task_id::text,
                    'status', review.status,
                    'assigned_role', review.assigned_role,
                    'assigned_to', COALESCE(assigned_user.external_subject, review.assigned_to::text),
                    'assignment_reason', review.assignment_reason,
                    'assigned_at', review.assigned_at::text,
                    'decided_by', review.decided_by::text,
                    'decision', review.decision,
                    'decision_note', review.decision_note,
                    'created_at', review.created_at::text,
                    'decided_at', review.decided_at::text
                  ) AS review_task,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated_submission updated
                JOIN period_row period ON period.reporting_period_id = updated.reporting_period_id
                JOIN org_row org ON true
                JOIN tenants tenant ON tenant.tenant_id = updated.tenant_id
                JOIN user_accounts submitter ON submitter.user_id = updated.submitted_by
                JOIN closed_review review ON review.submission_id = updated.submission_id
                LEFT JOIN user_accounts assigned_user ON assigned_user.user_id = review.assigned_to
                JOIN sections_json ON true
                JOIN issues_json ON true
                JOIN policy ON true
                JOIN audit ON true
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    review_task_id,
                    policy_decision.action,
                    policy_decision.data_classification,
                    policy_decision.reason,
                    context.purpose,
                    context.request_id,
                    decision,
                    decision,
                    decision,
                    decision,
                    decision,
                    note,
                    submission_status,
                    decision,
                    decision,
                    decision,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                    decision,
                    decision,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("intake.review_decision.unprovisioned_identity")
        return self._submission_payload(row)

    def _period_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "organization_id": str(row["organization_id"]),
            "period_type": str(row["period_type"]),
            "period_key": str(row["period_key"]),
            "period_start": str(row["period_start"]),
            "period_end": str(row["period_end"]),
            "status": str(row["status"]),
            "lock_version": int(row["lock_version"]),
            "latest_submission_status": row.get("latest_submission_status"),
        }

    def period_snapshot(self, organization_id: str, period_key: str, context: RequestContext | None = None) -> dict[str, Any]:
        if context is None:
            raise PilotFeatureUnavailableError("intake.period_snapshot.anonymous_context")
        decision = PolicyService.require(
            "read_financials",
            context,
            resource_type="period_snapshot",
            resource_id=f"{organization_id}:{period_key}",
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                org_row AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                period_row AS (
                  SELECT
                    rp.*,
                    tenant.external_key AS tenant_external_key,
                    org.external_id AS organization_external_id
                  FROM reporting_periods rp
                  JOIN tenants tenant ON tenant.tenant_id = rp.tenant_id
                  JOIN org_row org ON org.organization_id = rp.organization_id
                  WHERE rp.tenant_id = app_tenant_id()
                    AND rp.period_type = 'month'
                    AND rp.period_key = %s
                  LIMIT 1
                ),
                latest_submission AS (
                  SELECT ds.submission_id, ds.status, ds.version, ds.updated_at, ds.canonicalized_at
                  FROM data_submissions ds
                  JOIN period_row period ON period.reporting_period_id = ds.reporting_period_id
                  ORDER BY ds.updated_at DESC, ds.submission_id DESC
                  LIMIT 1
                ),
                approved_submission AS (
                  SELECT ds.submission_id, ds.status, ds.version, ds.updated_at, ds.canonicalized_at
                  FROM data_submissions ds
                  JOIN period_row period ON period.reporting_period_id = ds.reporting_period_id
                  WHERE ds.status = 'approved'
                  ORDER BY ds.version DESC, ds.updated_at DESC
                  LIMIT 1
                ),
                review_decision AS (
                  SELECT (
                    SELECT jsonb_strip_nulls(
                      jsonb_build_object(
                        'review_task_id', review.review_task_id::text,
                        'assigned_to', review.assigned_to::text,
                        'assignment_reason', review.assignment_reason,
                        'decided_by', review.decided_by::text,
                        'decision', review.decision,
                        'decision_note', review.decision_note,
                        'decided_at', review.decided_at::text
                      )
                    )
                    FROM review_tasks review
                    JOIN approved_submission approved ON approved.submission_id = review.submission_id
                    WHERE review.status = 'closed'
                    ORDER BY review.decided_at DESC NULLS LAST, review.created_at DESC, review.review_task_id DESC
                    LIMIT 1
                  ) AS data
                ),
                review_history AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_strip_nulls(
                        jsonb_build_object(
                          'review_task_id', review.review_task_id::text,
                          'submission_id', submission.submission_id::text,
                          'review_status', review.status,
                          'assigned_to', review.assigned_to::text,
                          'assignment_reason', review.assignment_reason,
                          'assigned_at', review.assigned_at::text,
                          'decided_by', review.decided_by::text,
                          'decision', review.decision,
                          'decision_note', review.decision_note,
                          'decided_at', review.decided_at::text,
                          'created_at', review.created_at::text,
                          'submission_status', submission.status,
                          'source', submission.source_type,
                          'version', submission.version,
                          'submitted_at', submission.submitted_at::text
                        )
                      )
                      ORDER BY COALESCE(review.decided_at, review.created_at) DESC, review.review_task_id DESC
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM review_tasks review
                  JOIN data_submissions submission ON submission.submission_id = review.submission_id
                  JOIN period_row period ON period.reporting_period_id = submission.reporting_period_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    period.tenant_id, actor.user_id, %s, 'period_snapshot', %s, %s,
                    'allow', %s, %s, %s
                  FROM period_row period, actor_row actor
                  RETURNING decision_id
                ),
                financials AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_strip_nulls(
                        jsonb_build_object(
                          'snapshot_id', fs.snapshot_id::text,
                          'statement_type', fs.statement_type,
                          'version', fs.version,
                          'source_submission_id', fs.source_submission_id::text,
                          'source_record_id', fs.source_record_id,
                          'valid_from', fs.valid_from::text,
                          'valid_to', fs.valid_to::text,
                          'created_at', fs.created_at::text
                        ) || fs.metrics
                      )
                      ORDER BY fs.version DESC, fs.created_at DESC
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM financial_snapshots fs
                  JOIN period_row period ON period.reporting_period_id = fs.reporting_period_id
                  WHERE EXISTS (SELECT 1 FROM approved_submission)
                ),
                products AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_strip_nulls(
                        jsonb_build_object(
                          'capability_id', product.capability_id::text,
                          'sku', product.sku,
                          'product_name', product.product_name,
                          'category', product.category,
                          'specification', product.specification,
                          'available_capacity', product.available_capacity,
                          'min_order_value', product.min_order_value,
                          'price_range', product.price_range,
                          'certifications', product.certifications,
                          'shelf_life_days', product.shelf_life_days,
                          'temperature_band', product.temperature_band,
                          'packaging_type', product.packaging_type,
                          'case_pack', product.case_pack,
                          'substitution_group', product.substitution_group,
                          'version', product.version,
                          'source_submission_id', product.source_submission_id::text,
                          'source_record_id', product.source_record_id,
                          'valid_from', product.valid_from::text,
                          'valid_to', product.valid_to::text,
                          'created_at', product.created_at::text
                        )
                      )
                      ORDER BY product.sku, product.version DESC
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM product_capabilities product
                  JOIN period_row period ON period.reporting_period_id = product.reporting_period_id
                  WHERE EXISTS (SELECT 1 FROM approved_submission)
                ),
                evidence AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_strip_nulls(
                        jsonb_build_object(
                          'evidence_document_id', document.evidence_document_id::text,
                          'id', document.evidence_document_id::text,
                          'document_type', document.document_type,
                          'title', document.title,
                          'classification', document.classification,
                          'retention_status', document.retention_status,
                          'legal_hold', document.legal_hold,
                          'source_submission_id', document.source_submission_id::text,
                          'source_record_id', document.source_record_id,
                          'valid_from', document.valid_from::text,
                          'valid_to', document.valid_to::text,
                          'created_at', document.created_at::text,
                          'evidence_version_id', version.evidence_version_id::text,
                          'object_version', version.object_version,
                          'document_hash', version.document_hash,
                          'content_type', version.content_type,
                          'byte_size', version.byte_size,
                          'malware_scan_status', version.malware_scan_status
                        )
                      )
                      ORDER BY document.created_at DESC
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM evidence_documents document
                  JOIN period_row period ON period.reporting_period_id = document.reporting_period_id
                  LEFT JOIN LATERAL (
                    SELECT ev.*
                    FROM evidence_versions ev
                    WHERE ev.evidence_document_id = document.evidence_document_id
                    ORDER BY ev.created_at DESC, ev.evidence_version_id DESC
                    LIMIT 1
                  ) version ON true
                  WHERE EXISTS (SELECT 1 FROM approved_submission)
                    AND version.malware_scan_status = 'clean'
                ),
                source_ids AS (
                  SELECT COALESCE(jsonb_agg(DISTINCT source_id), '[]'::jsonb) AS data
                  FROM (
                    SELECT fs.source_submission_id::text AS source_id
                    FROM financial_snapshots fs
                    JOIN period_row period ON period.reporting_period_id = fs.reporting_period_id
                    WHERE EXISTS (SELECT 1 FROM approved_submission)
                    UNION
                    SELECT product.source_submission_id::text AS source_id
                    FROM product_capabilities product
                    JOIN period_row period ON period.reporting_period_id = product.reporting_period_id
                    WHERE EXISTS (SELECT 1 FROM approved_submission)
                    UNION
                    SELECT document.source_submission_id::text AS source_id
                    FROM evidence_documents document
                    JOIN period_row period ON period.reporting_period_id = document.reporting_period_id
                    WHERE EXISTS (SELECT 1 FROM approved_submission)
                      AND document.source_submission_id IS NOT NULL
                    UNION
                    SELECT approved.submission_id::text AS source_id
                    FROM approved_submission approved
                  ) ids
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    period.tenant_id, 'PERIOD_SNAPSHOT_READ', actor.user_id, %s, period.reporting_period_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || period.reporting_period_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', period.organization_external_id,
                      'period_key', period.period_key,
                      'latest_submission_status', latest.status,
                      'approved_version', approved.version
                    ),
                    %s, %s
                  FROM period_row period, actor_row actor, policy
                  LEFT JOIN latest_submission latest ON true
                  LEFT JOIN approved_submission approved ON true
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  period.reporting_period_id::text AS id,
                  period.tenant_external_key AS tenant_id,
                  period.organization_external_id AS organization_id,
                  period.period_type::text AS period_type,
                  period.period_key,
                  period.period_start::text AS period_start,
                  period.period_end::text AS period_end,
                  CASE WHEN approved.submission_id IS NULL THEN period.status ELSE 'approved' END AS status,
                  period.lock_version,
                  latest.status::text AS latest_submission_status,
                  approved.version AS approved_version,
                  COALESCE(approved.canonicalized_at, approved.updated_at)::text AS approved_at,
                  financials.data AS financials,
                  products.data AS products,
                  evidence.data AS evidence,
                  source_ids.data AS source_submission_ids,
                  review_decision.data AS review_decision,
                  review_history.data AS review_history,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM period_row period
                JOIN policy ON true
                JOIN audit ON true
                LEFT JOIN latest_submission latest ON true
                LEFT JOIN approved_submission approved ON true
                CROSS JOIN financials
                CROSS JOIN products
                CROSS JOIN evidence
                CROSS JOIN source_ids
                CROSS JOIN review_decision
                CROSS JOIN review_history
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    period_key,
                    decision.action,
                    f"{organization_id}:{period_key}",
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            return self._empty_snapshot(organization_id, period_key, None)
        return self._snapshot_payload(row, organization_id, period_key)

    def _snapshot_payload(self, row: dict[str, Any], organization_id: str, period_key: str) -> dict[str, Any]:
        if row.get("approved_version") is None:
            empty = self._empty_snapshot(
                str(row.get("organization_id") or organization_id),
                period_key,
                {"status": row.get("latest_submission_status")} if row.get("latest_submission_status") else None,
            )
            empty["period"] = self._period_payload(row)
            empty["policy_decision_id"] = str(row["policy_decision_id"])
            empty["audit_event_id"] = str(row["audit_event_id"])
            return empty
        return {
            "business_id": str(row["organization_id"]),
            "organization_id": str(row["organization_id"]),
            "period": self._period_payload(row),
            "approved_version": int(row["approved_version"]),
            "approved_at": row.get("approved_at"),
            "review_decision": self._json_object(row.get("review_decision")),
            "review_history": self._json_list(row.get("review_history")),
            "latest_submission_status": row.get("latest_submission_status"),
            "sections": {},
            "financials": self._json_list(row.get("financials")),
            "products": self._json_list(row.get("products")),
            "evidence": self._json_list(row.get("evidence")),
            "source_submission_ids": self._json_list(row.get("source_submission_ids")),
            "advisory_notice": TRUST_NOTICE,
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
        }

    def _submission_evidence_review_summary(self, connection: Any, submission_id: str) -> dict[str, Any]:
        row = connection.execute(
            """
            WITH submission_row AS (
              SELECT ds.*, rp.period_key
              FROM data_submissions ds
              JOIN reporting_periods rp ON rp.reporting_period_id = ds.reporting_period_id
              WHERE ds.tenant_id = app_tenant_id()
                AND ds.submission_id = app_try_uuid(%s)
              LIMIT 1
            ),
            status_rows AS (
              SELECT COALESCE(item.value->>'malware_scan_status', 'pending_scan') AS scan_status
              FROM submission_sections section
              JOIN submission_row submission ON submission.submission_id = section.submission_id
              CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                  WHEN jsonb_typeof(section.payload) = 'array' THEN section.payload
                  WHEN section.payload = '{}'::jsonb THEN '[]'::jsonb
                  ELSE jsonb_build_array(section.payload)
                END
              ) item(value)
              WHERE section.section_name = 'evidence'
              UNION ALL
              SELECT COALESCE(document.malware_scan_status, 'pending_scan') AS scan_status
              FROM evidence_documents document
              JOIN submission_row submission
                ON submission.tenant_id = document.tenant_id
               AND submission.organization_id = document.organization_id
               AND submission.reporting_period_id = document.reporting_period_id
              UNION ALL
              SELECT COALESCE(version.malware_scan_status, 'pending_scan') AS scan_status
              FROM evidence_versions version
              JOIN submission_row submission
                ON submission.tenant_id = version.tenant_id
               AND submission.organization_id = version.organization_id
               AND submission.period_key = version.period_key
              WHERE version.evidence_document_id IS NULL
            )
            SELECT
              COUNT(*)::int AS total,
              COUNT(*) FILTER (WHERE scan_status = 'clean')::int AS clean,
              COUNT(*) FILTER (WHERE scan_status IN ('infected', 'failed'))::int AS rejected,
              COUNT(*) FILTER (WHERE scan_status NOT IN ('clean', 'infected', 'failed'))::int AS pending
            FROM status_rows
            """,
            (submission_id,),
        ).fetchone()
        if row is None:
            return self._evidence_review_payload(None)
        total = int(row.get("total") or 0)
        pending = int(row.get("pending") or 0)
        rejected = int(row.get("rejected") or 0)
        return self._evidence_review_payload(
            {
                "total": total,
                "clean": int(row.get("clean") or 0),
                "pending": pending,
                "rejected": rejected,
                "required": total > 0,
                "approval_blocked": total > 0 and (pending > 0 or rejected > 0),
            }
        )

    def _empty_snapshot(
        self, organization_id: str, period_key: str, latest_submission: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "business_id": organization_id,
            "organization_id": organization_id,
            "period": {"period_key": period_key, "status": "not_created"},
            "approved_version": None,
            "approved_at": None,
            "review_decision": None,
            "review_history": [],
            "latest_submission_status": latest_submission["status"] if latest_submission else None,
            "sections": {},
            "financials": [],
            "products": [],
            "evidence": [],
            "source_submission_ids": [],
            "advisory_notice": TRUST_NOTICE,
        }

    def _json_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            loaded = json.loads(value)
            return loaded if isinstance(loaded, list) else []
        return []

    def _json_object(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else None
        return None

    def _list_payload(self, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload] if payload else []
        return []

    def _csv_payload(self, dataset: str, rows: list[dict[str, Any]]) -> Any:
        normalized_rows = [{self._normalize_column(key): value for key, value in row.items()} for row in rows]
        if dataset == "financials":
            return normalized_rows[0] if normalized_rows else {}
        if dataset in {"products", "evidence"}:
            return normalized_rows
        return normalized_rows

    def _normalized_key(self, dataset: str, row: dict[str, Any], index: int) -> str:
        for key in ["sku", "invoice_id", "document_hash", "title", "file_name"]:
            if row.get(key):
                return f"{dataset}:{row[key]}"
        return f"{dataset}:row:{index}"

    def _normalize_column(self, column: str) -> str:
        return column.strip().lower().replace(" ", "_").replace("-", "_")

    def _import_batch_payload(self, row: dict[str, Any], *, idempotent_replay: bool) -> dict[str, Any]:
        payload = {
            "id": str(row["batch_id"]),
            "submission_id": str(row["submission_id"]),
            "dataset": str(row["dataset"]),
            "file_name": str(row["file_name"]),
            "row_count": int(row["row_count"]),
            "status": str(row["status"]),
            "checksum": str(row["checksum"]),
            "preview_rows": self._json_list(row.get("preview_rows")),
            "idempotent_replay": idempotent_replay,
        }
        if row.get("policy_decision_id"):
            payload["policy_decision_id"] = str(row["policy_decision_id"])
        if row.get("audit_event_id"):
            payload["audit_event_id"] = str(row["audit_event_id"])
        return payload

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

    def _validate_sections(self, sections: list[Any]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if not sections:
            issues.append(self._issue("submission", "$", "NO_SECTIONS", "error", "At least one intake section is required."))
            return issues
        for row in sections:
            if not isinstance(row, dict):
                continue
            section = str(row.get("section_name") or "")
            payload = row.get("payload") or {}
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

    def _issue(
        self,
        section: str,
        path: str,
        code: str,
        severity: str,
        message: str,
        row: int | None = None,
        column: str | None = None,
        suggestion: str | None = None,
    ) -> dict[str, Any]:
        return {
            "section": section,
            "path": path,
            "code": code,
            "severity": severity,
            "message": message,
            "row_number": row,
            "column_name": column,
            "suggestion": suggestion,
        }

    def _submission_read_sql(self, event_type: str) -> str:
        return f"""
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                submission_row AS (
                  SELECT ds.*
                  FROM data_submissions ds
                  WHERE ds.tenant_id = app_tenant_id()
                    AND ds.submission_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN submission_row submission ON submission.reporting_period_id = rp.reporting_period_id
                ),
                org_row AS (
                  SELECT COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN submission_row submission ON submission.organization_id = org.organization_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    submission.tenant_id, actor.user_id, %s, 'data_submission', %s, %s,
                    'allow', %s, %s, %s
                  FROM submission_row submission, actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    submission.tenant_id, '{event_type}', actor.user_id, %s, submission.submission_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || submission.submission_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('organization_id', org.external_id, 'period_key', period.period_key, 'status', submission.status),
                    %s, %s
                  FROM submission_row submission, actor_row actor, org_row org, period_row period, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                ),
                sections_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'section_id', section.section_id::text,
                        'section_name', section.section_name,
                        'status', section.status,
                        'payload', section.payload,
                        'updated_at', section.updated_at::text
                      )
                      ORDER BY section.section_name
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM submission_sections section
                  JOIN submission_row submission ON submission.submission_id = section.submission_id
                ),
                issues_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'issue_id', issue.issue_id::text,
                        'section_name', issue.section_name,
                        'path', issue.path,
                        'row_number', issue.row_number,
                        'column_name', issue.column_name,
                        'code', issue.code,
                        'severity', issue.severity,
                        'message', issue.message,
                        'suggestion', issue.suggestion
                      )
                      ORDER BY issue.severity, issue.section_name, issue.row_number
                    ),
                    '[]'::jsonb
                  ) AS data
                  FROM validation_issues issue
                  JOIN submission_row submission ON submission.submission_id = issue.submission_id
                ),
                review_json AS (
                  SELECT jsonb_build_object(
                    'review_task_id', review.review_task_id::text,
                    'status', review.status,
                    'assigned_role', review.assigned_role,
                    'assigned_to', COALESCE(assigned_user.external_subject, review.assigned_to::text),
                    'assignment_reason', review.assignment_reason,
                    'assigned_at', review.assigned_at::text,
                    'decided_by', review.decided_by::text,
                    'decision', review.decision,
                    'decision_note', review.decision_note,
                    'created_at', review.created_at::text,
                    'decided_at', review.decided_at::text
                  ) AS data
                  FROM review_tasks review
                  JOIN submission_row submission ON submission.submission_id = review.submission_id
                  LEFT JOIN user_accounts assigned_user ON assigned_user.user_id = review.assigned_to
                  ORDER BY review.created_at DESC, review.review_task_id DESC
                  LIMIT 1
                )
                SELECT
                  submission.submission_id::text AS submission_id,
                  tenant.external_key AS tenant_id,
                  org.external_id AS organization_id,
                  period.reporting_period_id::text AS id,
                  period.period_type::text AS period_type,
                  period.period_key,
                  period.period_start::text AS period_start,
                  period.period_end::text AS period_end,
                  period.status,
                  period.lock_version,
                  submission.source_type,
                  submission.status::text AS submission_status,
                  submission.version,
                  COALESCE(submitter.external_subject, submission.submitted_by::text) AS submitted_by,
                  submission.created_at::text AS created_at,
                  submission.updated_at::text AS updated_at,
                  submission.submitted_at::text AS submitted_at,
                  submission.validated_at::text AS validated_at,
                  submission.canonicalized_at::text AS canonicalized_at,
                  sections_json.data AS sections,
                  issues_json.data AS issues,
                  review_json.data AS review_task,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM submission_row submission
                JOIN period_row period ON period.reporting_period_id = submission.reporting_period_id
                JOIN org_row org ON true
                JOIN tenants tenant ON tenant.tenant_id = submission.tenant_id
                JOIN user_accounts submitter ON submitter.user_id = submission.submitted_by
                JOIN sections_json ON true
                JOIN issues_json ON true
                LEFT JOIN review_json ON true
                JOIN policy ON true
                JOIN audit ON true
                """

    def _submission_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        sections: dict[str, dict[str, Any]] = {}
        for section in self._json_list(row.get("sections")):
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("section_name") or "")
            if not section_name:
                continue
            payload = section.get("payload")
            if isinstance(payload, str):
                payload = json.loads(payload)
            sections[section_name] = {
                "status": str(section.get("status") or "draft"),
                "payload": payload if payload is not None else {},
                "updated_at": section.get("updated_at"),
            }
        issues = [self._issue_payload(issue) for issue in self._json_list(row.get("issues")) if isinstance(issue, dict)]
        return {
            "id": str(row["submission_id"]),
            "submission_id": str(row["submission_id"]),
            "tenant_id": str(row["tenant_id"]),
            "business_id": str(row["organization_id"]),
            "organization_id": str(row["organization_id"]),
            "period": self._period_payload(row),
            "source": str(row["source_type"]),
            "status": str(row["submission_status"]),
            "version": int(row["version"]),
            "submitted_by": str(row["submitted_by"]),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "submitted_at": row.get("submitted_at"),
            "validated_at": row.get("validated_at"),
            "canonicalized_at": row.get("canonicalized_at"),
            "sections": sections,
            "issues": issues,
            "validation_summary": {
                "errors": len([issue for issue in issues if issue["severity"] == "error"]),
                "warnings": len([issue for issue in issues if issue["severity"] == "warning"]),
                "infos": len([issue for issue in issues if issue["severity"] == "info"]),
            },
            "review_task": self._review_payload(row.get("review_task")) if row.get("review_task") else None,
            "advisory_notice": TRUST_NOTICE,
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
        }

    def _review_queue_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "review_task_id": str(row["review_task_id"]),
            "submission_id": str(row["submission_id"]),
            "organization_id": str(row["organization_id"]),
            "organization_name": str(row["organization_name"]),
            "period_key": str(row["period_key"]),
            "period_start": str(row["period_start"]),
            "period_end": str(row["period_end"]),
            "review_status": str(row["review_status"]),
            "assigned_role": str(row["assigned_role"]),
            "assigned_to": row.get("assigned_to"),
            "assignment_reason": row.get("assignment_reason"),
            "assigned_at": row.get("assigned_at"),
            "submission_status": str(row["submission_status"]),
            "source": str(row["source"]),
            "version": int(row["version"]),
            "submitted_by": str(row["submitted_by"]),
            "submitted_at": row.get("submitted_at"),
            "updated_at": row.get("updated_at"),
            "validation_summary": {
                "errors": int(row.get("error_count") or 0),
                "warnings": int(row.get("warning_count") or 0),
                "infos": int(row.get("info_count") or 0),
            },
            "sections": self._json_list(row.get("sections")),
            "evidence_review": self._evidence_review_payload(row.get("evidence_summary")),
        }

    def _evidence_review_payload(self, value: Any) -> dict[str, Any]:
        row = json.loads(value) if isinstance(value, str) else value
        if not isinstance(row, dict):
            row = {}
        total = int(row.get("total") or 0)
        clean = int(row.get("clean") or 0)
        pending = int(row.get("pending") or 0)
        rejected = int(row.get("rejected") or 0)
        approval_blocked = bool(row.get("approval_blocked") or (total > 0 and (pending > 0 or rejected > 0)))
        requirements = row.get("requirements")
        if not isinstance(requirements, list):
            requirements = [
                {
                    "document_type": document_type,
                    "title": title,
                    "section": section,
                    "total": 0,
                    "clean": 0,
                    "pending": 0,
                    "rejected": 0,
                    "status": "missing",
                    "satisfied": False,
                }
                for document_type, title, section in EVIDENCE_REQUIREMENTS
            ]
        return {
            "total": total,
            "clean": clean,
            "pending": pending,
            "rejected": rejected,
            "required": bool(row.get("required") or total > 0),
            "approval_blocked": approval_blocked,
            "advisory": str(
                row.get("advisory")
                or (
                    "Approval blocked until submitted/uploaded evidence has clean malware scan status."
                    if approval_blocked
                    else "Evidence gate passed or no evidence was submitted for this period."
                )
            ),
            "requirements": requirements,
        }

    def _review_payload(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        row = json.loads(value) if isinstance(value, str) else value
        if not isinstance(row, dict):
            return None
        return {
            "id": str(row["review_task_id"]),
            "status": str(row["status"]),
            "assigned_role": str(row["assigned_role"]),
            "assigned_to": row.get("assigned_to"),
            "assignment_reason": row.get("assignment_reason"),
            "assigned_at": row.get("assigned_at"),
            "decided_by": row.get("decided_by"),
            "decision": row.get("decision"),
            "decision_note": row.get("decision_note"),
            "created_at": row.get("created_at"),
            "decided_at": row.get("decided_at"),
        }

    def _issue_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["issue_id"]),
            "section": str(row["section_name"]),
            "path": str(row["path"]),
            "row": row.get("row_number"),
            "column": row.get("column_name"),
            "code": str(row["code"]),
            "severity": str(row["severity"]),
            "message": str(row["message"]),
            "suggestion": row.get("suggestion"),
        }


class PostgresPilotGovernanceService(_UnsupportedPilotComponent):
    def __init__(
        self,
        runtime: PostgresPilotRuntime,
        connector: PostgresConnectionFactory | Any,
        object_storage: ObjectStorageSettings | None = None,
    ) -> None:
        super().__init__("governance")
        self.runtime = runtime
        self.connector = connector
        self.object_storage = object_storage or ObjectStorageSettings.from_env()

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
            "adapter_status": self.runtime.status_payload()["adapter_status"],
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
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH tenant_row AS (
                  SELECT tenant_id, external_key
                  FROM tenants
                  WHERE tenant_id = app_try_uuid(%s) OR external_key = %s
                  LIMIT 1
                ),
                actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  JOIN tenant_row tr ON tr.tenant_id = ua.tenant_id
                  WHERE ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s
                  LIMIT 1
                ),
                subject_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN tenant_row tr ON tr.tenant_id = org.tenant_id
                  WHERE org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s
                  LIMIT 1
                ),
                recipient_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN tenant_row tr ON tr.tenant_id = org.tenant_id
                  WHERE org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    tr.tenant_id, ar.user_id, %s, 'consent', %s, %s,
                    'allow', %s, %s, %s
                  FROM tenant_row tr, actor_row ar
                  RETURNING decision_id
                ),
                consent AS (
                  INSERT INTO consent_records (
                    tenant_id, actor_id, subject_organization_id, recipient_organization_id,
                    scope, purpose, legal_basis, status, expires_at, revoked_at,
                    evidence_reference, version
                  )
                  SELECT
                    tr.tenant_id, ar.user_id, so.organization_id, ro.organization_id,
                    %s, %s, %s, 'granted', %s::timestamptz, NULL,
                    app_try_uuid(%s), 1
                  FROM tenant_row tr, actor_row ar, subject_org so, recipient_org ro
                  RETURNING *
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  JOIN tenant_row tr ON tr.tenant_id = al.tenant_id
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    tr.tenant_id, 'CONSENT_GRANTED', ar.user_id, %s, consent.consent_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || consent.consent_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('subject_id', so.external_id, 'recipient_id', ro.external_id, 'scope', consent.scope, 'purpose', consent.purpose),
                    %s, %s
                  FROM tenant_row tr, actor_row ar, subject_org so, recipient_org ro, policy, consent
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  consent.consent_id::text,
                  so.external_id AS subject_id,
                  ro.external_id AS recipient_id,
                  consent.scope,
                  consent.purpose,
                  consent.legal_basis,
                  consent.status::text,
                  consent.expires_at::text,
                  consent.revoked_at::text,
                  consent.version,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM consent, subject_org so, recipient_org ro, policy, audit
                """,
                (
                    context.tenant_id,
                    context.tenant_id,
                    context.actor_id,
                    context.actor_id,
                    subject_id,
                    subject_id,
                    recipient_id,
                    recipient_id,
                    decision.action,
                    subject_id,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    scope,
                    purpose,
                    legal_basis,
                    expires_at,
                    evidence_reference,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.create_consent.unprovisioned_identity")
        return self._consent_payload(row)

    def revoke_consent(self, consent_id: str, context: RequestContext) -> dict[str, Any]:
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  consent.consent_id::text,
                  COALESCE(subject.external_business_id, subject.organization_id::text) AS subject_id
                FROM consent_records consent
                JOIN organizations subject ON subject.organization_id = consent.subject_organization_id
                WHERE consent.consent_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (consent_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(consent_id)
            decision = PolicyService.require(
                "revoke_consent",
                context,
                resource_type="consent",
                resource_id=consent_id,
                resource_organization_id=str(existing["subject_id"]),
                data_classification="confidential",
            )
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                updated AS (
                  UPDATE consent_records
                  SET status = 'revoked', revoked_at = now(), version = version + 1, updated_at = now()
                  WHERE consent_id = app_try_uuid(%s)
                  RETURNING *
                ),
                subject_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated ON updated.subject_organization_id = org.organization_id
                ),
                recipient_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated ON updated.recipient_organization_id = org.organization_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    updated.tenant_id, actor_row.user_id, %s, 'consent', %s, %s,
                    'allow', %s, %s, %s
                  FROM updated, actor_row
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'CONSENT_REVOKED', actor_row.user_id, %s, updated.consent_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated.consent_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('subject_id', subject_org.external_id, 'recipient_id', recipient_org.external_id, 'scope', updated.scope, 'purpose', updated.purpose),
                    %s, %s
                  FROM updated, actor_row, subject_org, recipient_org, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  updated.consent_id::text,
                  subject_org.external_id AS subject_id,
                  recipient_org.external_id AS recipient_id,
                  updated.scope,
                  updated.purpose,
                  updated.legal_basis,
                  updated.status::text,
                  updated.expires_at::text,
                  updated.revoked_at::text,
                  updated.version,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated, subject_org, recipient_org, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    consent_id,
                    decision.action,
                    consent_id,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.revoke_consent.unprovisioned_identity")
        return self._consent_payload(row)

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
        object_key = f"s3://{self.object_storage.bucket}/{context.tenant_id}/{organization_id}/{uuid4().hex}-{file_name}"
        period_start, period_end = _period_dates(period_key) if period_key else (None, None)
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH tenant_row AS (
                  SELECT tenant_id, external_key
                  FROM tenants
                  WHERE tenant_id = app_try_uuid(%s) OR external_key = %s
                  LIMIT 1
                ),
                actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  JOIN tenant_row tr ON tr.tenant_id = ua.tenant_id
                  WHERE ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s
                  LIMIT 1
                ),
                org_row AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN tenant_row tr ON tr.tenant_id = org.tenant_id
                  WHERE org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s
                  LIMIT 1
                ),
                period_input AS (
                  SELECT NULLIF(%s, '') AS period_key
                ),
                period_row AS (
                  INSERT INTO reporting_periods (
                    tenant_id, organization_id, period_type, period_key,
                    period_start, period_end, status, lock_version
                  )
                  SELECT
                    tr.tenant_id, org.organization_id, 'month', period_input.period_key,
                    %s::date, %s::date, 'open', 1
                  FROM tenant_row tr, org_row org, period_input
                  WHERE period_input.period_key IS NOT NULL
                  ON CONFLICT (tenant_id, organization_id, period_type, period_key)
                  DO UPDATE SET period_key = EXCLUDED.period_key
                  RETURNING reporting_period_id, period_key
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    tr.tenant_id, ar.user_id, %s, 'evidence', %s, %s,
                    'allow', %s, %s, %s
                  FROM tenant_row tr, actor_row ar
                  RETURNING decision_id
                ),
                document AS (
                  INSERT INTO evidence_documents (
                    tenant_id, organization_id, reporting_period_id, document_type,
                    title, classification, retention_status, legal_hold
                  )
                  SELECT
                    tr.tenant_id, org.organization_id, period_row.reporting_period_id, %s,
                    %s, %s, 'active', false
                  FROM tenant_row tr
                  JOIN org_row org ON true
                  LEFT JOIN period_row ON true
                  RETURNING *
                ),
                version AS (
                  INSERT INTO evidence_versions (
                    evidence_document_id, tenant_id, organization_id, object_key, object_version,
                    document_hash, content_type, byte_size, malware_scan_status,
                    uploader_id, supersedes_version_id
                  )
                  SELECT
                    document.evidence_document_id, tr.tenant_id, org.organization_id, %s, 'pending-upload',
                    'pending-upload', %s, %s, 'pending_scan',
                    ar.user_id, NULL
                  FROM tenant_row tr, actor_row ar, org_row org, document
                  RETURNING *
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  JOIN tenant_row tr ON tr.tenant_id = al.tenant_id
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    tr.tenant_id, 'EVIDENCE_UPLOAD_URL_CREATED', ar.user_id, %s, version.evidence_version_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || version.evidence_version_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', org.external_id,
                      'period_key', period_row.period_key,
                      'evidence_document_id', document.evidence_document_id::text,
                      'object_key_hash', encode(digest(version.object_key, 'sha256'), 'hex'),
                      'document_type', document.document_type,
                      'classification', document.classification,
                      'malware_scan_status', version.malware_scan_status
                    ),
                    %s, %s
                  FROM tenant_row tr, actor_row ar, org_row org, document, version, policy
                  LEFT JOIN period_row ON true
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  version.evidence_version_id::text,
                  document.evidence_document_id::text,
                  org.external_id AS organization_id,
                  period_row.period_key,
                  document.document_type,
                  document.title AS file_name,
                  document.classification,
                  version.object_key,
                  version.content_type,
                  version.byte_size,
                  version.object_version,
                  version.document_hash,
                  version.malware_scan_status,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM document, version, org_row org, policy, audit
                LEFT JOIN period_row ON true
                """,
                (
                    context.tenant_id,
                    context.tenant_id,
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    period_key,
                    period_start,
                    period_end,
                    decision.action,
                    organization_id,
                    decision.data_classification,
                    decision.reason,
                    purpose,
                    context.request_id,
                    document_type,
                    file_name,
                    classification,
                    object_key,
                    content_type,
                    byte_size,
                    context.actor_role,
                    purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.create_evidence_upload.unprovisioned_identity")
        return self._evidence_upload_payload(row)

    def list_evidence_upload_tickets(
        self,
        *,
        organization_id: str,
        period_key: str | None,
        context: RequestContext,
    ) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_evidence",
            context,
            resource_type="evidence_upload_ticket",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH tenant_row AS (
                  SELECT tenant_id
                  FROM tenants
                  WHERE tenant_id = app_try_uuid(%s) OR external_key = %s
                  LIMIT 1
                ),
                actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  JOIN tenant_row tr ON tr.tenant_id = ua.tenant_id
                  WHERE ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s
                  LIMIT 1
                ),
                org_row AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN tenant_row tr ON tr.tenant_id = org.tenant_id
                  WHERE org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s
                  LIMIT 1
                ),
                tickets AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'id', version.evidence_version_id::text,
                        'evidence_version_id', version.evidence_version_id::text,
                        'organization_id', org.external_id,
                        'business_id', org.external_id,
                        'period_key', period.period_key,
                        'document_type', document.document_type,
                        'file_name', document.title,
                        'content_type', version.content_type,
                        'byte_size', version.byte_size,
                        'classification', document.classification,
                        'status', version.malware_scan_status,
                        'malware_scan_status', version.malware_scan_status,
                        'uploaded_at', version.created_at::text,
                        'policy_decision_id', NULL,
                        'advisory_notice', 'Pending upload ticket only; file is not verified evidence until checksum and malware scan pass.'
                      )
                      ORDER BY version.created_at DESC, version.evidence_version_id DESC
                    ) FILTER (WHERE version.evidence_version_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM org_row org
                  LEFT JOIN evidence_versions version
                    ON version.organization_id = org.organization_id
                   AND version.tenant_id = app_tenant_id()
                   AND version.object_version = 'pending-upload'
                   AND version.malware_scan_status IN ('pending_scan', 'failed')
                  LEFT JOIN evidence_documents document
                    ON document.evidence_document_id = version.evidence_document_id
                  LEFT JOIN reporting_periods period
                    ON period.reporting_period_id = document.reporting_period_id
                  WHERE %s IS NULL OR period.period_key = %s
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    tr.tenant_id, ar.user_id, %s, 'evidence_upload_ticket', %s, %s,
                    'allow', %s, %s, %s
                  FROM tenant_row tr, actor_row ar
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    tr.tenant_id, 'EVIDENCE_UPLOAD_TICKETS_VIEWED', ar.user_id, %s, org.external_id, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || org.external_id || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('organization_id', org.external_id, 'period_key', %s, 'count', jsonb_array_length(tickets.data)),
                    %s, %s
                  FROM tenant_row tr, actor_row ar, org_row org, tickets, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  org.external_id AS organization_id,
                  %s::text AS period_key,
                  tickets.data AS tickets,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM org_row org, tickets, policy, audit
                """,
                (
                    context.tenant_id,
                    context.tenant_id,
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    period_key,
                    period_key,
                    decision.action,
                    organization_id,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    period_key,
                    context.app_mode,
                    context.auth_assurance,
                    period_key,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.list_evidence_upload_tickets.unprovisioned_identity")
        tickets = self._json_list(row.get("tickets"))
        return {
            "organization_id": str(row["organization_id"]),
            "period_key": row.get("period_key"),
            "tickets": [
                {**ticket, "policy_decision_id": str(row["policy_decision_id"]), "audit_event_id": str(row["audit_event_id"])}
                for ticket in tickets
            ],
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Pending upload tickets are not verified evidence and cannot support approved snapshots until scan/checksum gates pass."
            ),
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
        if content_base64:
            raise PilotFeatureUnavailableError("governance.complete_evidence_upload_ticket.base64_not_supported_for_pilot")
        decision = PolicyService.require(
            "create_evidence_version",
            context,
            resource_type="evidence_upload_ticket",
            resource_id=evidence_version_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        normalized_hash = document_hash.strip().lower()
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH tenant_row AS (
                  SELECT tenant_id
                  FROM tenants
                  WHERE tenant_id = app_try_uuid(%s) OR external_key = %s
                  LIMIT 1
                ),
                actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  JOIN tenant_row tr ON tr.tenant_id = ua.tenant_id
                  WHERE ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s
                  LIMIT 1
                ),
                org_row AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN tenant_row tr ON tr.tenant_id = org.tenant_id
                  WHERE org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s
                  LIMIT 1
                ),
                ticket AS (
                  SELECT
                    version.evidence_version_id,
                    version.tenant_id,
                    version.organization_id,
                    version.evidence_document_id,
                    version.object_key,
                    version.content_type,
                    version.byte_size,
                    document.document_type,
                    document.title,
                    document.classification,
                    period.period_key,
                    period.period_start,
                    org.external_id
                  FROM evidence_versions version
                  JOIN evidence_documents document ON document.evidence_document_id = version.evidence_document_id
                  JOIN org_row org ON org.organization_id = version.organization_id
                  LEFT JOIN reporting_periods period ON period.reporting_period_id = document.reporting_period_id
                  WHERE version.tenant_id = app_tenant_id()
                    AND version.evidence_version_id = app_try_uuid(%s)
                    AND version.object_version = 'pending-upload'
                  LIMIT 1
                ),
                updated_document AS (
                  UPDATE evidence_documents document
                  SET title = COALESCE(NULLIF(%s, ''), document.title),
                      valid_from = COALESCE(document.valid_from, ticket.period_start, CURRENT_DATE)
                  FROM ticket
                  WHERE document.evidence_document_id = ticket.evidence_document_id
                  RETURNING document.*
                ),
                updated_version AS (
                  UPDATE evidence_versions version
                  SET object_version = version.evidence_version_id::text,
                      document_hash = %s,
                      malware_scan_status = 'pending_scan'
                  FROM ticket
                  WHERE version.evidence_version_id = ticket.evidence_version_id
                  RETURNING version.*
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    ticket.tenant_id, ar.user_id, %s, 'evidence_upload_ticket', ticket.evidence_version_id::text, ticket.classification,
                    'allow', %s, %s, %s
                  FROM ticket, actor_row ar
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    ticket.tenant_id, 'EVIDENCE_UPLOAD_COMPLETED', ar.user_id, %s, ticket.evidence_version_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || ticket.evidence_version_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', ticket.external_id,
                      'evidence_document_id', ticket.evidence_document_id::text,
                      'period_key', ticket.period_key,
                      'malware_scan_status', 'pending_scan',
                      'client_requested_scan_status', %s,
                      'object_key_hash', encode(digest(ticket.object_key, 'sha256'), 'hex')
                    ),
                    %s, %s
                  FROM ticket, actor_row ar, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  updated_version.evidence_version_id::text,
                  updated_document.evidence_document_id::text,
                  ticket.external_id AS organization_id,
                  ticket.period_key,
                  updated_document.document_type,
                  updated_document.title,
                  updated_version.object_key,
                  updated_version.object_version,
                  updated_version.document_hash,
                  updated_version.malware_scan_status,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM ticket, updated_document, updated_version, policy, audit
                """,
                (
                    context.tenant_id,
                    context.tenant_id,
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    evidence_version_id,
                    title,
                    normalized_hash,
                    decision.action,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    malware_scan_status,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise IntakeNotFoundError(evidence_version_id)
        payload = self._evidence_version_payload(row)
        payload.pop("object_key", None)
        payload.update(
            {
                "period_key": row.get("period_key"),
                "document_type": row.get("document_type"),
                "title": row.get("title"),
                "object_storage_status": "metadata_recorded",
                "usable": False,
                "advisory_notice": (
                    f"{TRUST_NOTICE} Evidence object metadata is recorded after S3/MinIO upload; scanner clean status is required before use."
                ),
            }
        )
        return payload

    def get_evidence_document(self, evidence_document_id: str, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_evidence",
            context,
            resource_type="evidence",
            resource_id=evidence_document_id,
            data_classification="confidential",
            external_access_allowed=True,
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                document_row AS (
                  SELECT
                    document.evidence_document_id,
                    document.tenant_id,
                    document.organization_id,
                    COALESCE(org.external_business_id, org.organization_id::text) AS organization_external_id,
                    document.reporting_period_id::text AS reporting_period_id,
                    period.period_key,
                    document.document_type,
                    document.title,
                    document.classification,
                    document.retention_status,
                    document.legal_hold,
                    document.source_submission_id::text AS source_submission_id,
                    document.source_record_id,
                    document.valid_from::text AS valid_from,
                    document.valid_to::text AS valid_to,
                    document.created_at::text AS created_at
                  FROM evidence_documents document
                  JOIN organizations org ON org.organization_id = document.organization_id
                  LEFT JOIN reporting_periods period ON period.reporting_period_id = document.reporting_period_id
                  WHERE document.tenant_id = app_tenant_id()
                    AND document.evidence_document_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                versions AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'evidence_version_id', version.evidence_version_id::text,
                        'object_version', version.object_version,
                        'document_hash', version.document_hash,
                        'content_type', version.content_type,
                        'byte_size', version.byte_size,
                        'malware_scan_status', version.malware_scan_status,
                        'uploader_id', version.uploader_id::text,
                        'supersedes_version_id', version.supersedes_version_id::text,
                        'created_at', version.created_at::text,
                        'usable', version.malware_scan_status = 'clean'
                      )
                      ORDER BY version.created_at DESC, version.evidence_version_id DESC
                    ) FILTER (WHERE version.evidence_version_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM evidence_versions version
                  JOIN document_row document ON document.evidence_document_id = version.evidence_document_id
                ),
                active_grants AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'grant_id', grant_row.grant_id::text,
                        'grantee_organization_id', COALESCE(grantee.external_business_id, grantee.organization_id::text),
                        'scope', grant_row.scope,
                        'purpose', grant_row.purpose,
                        'status', grant_row.status,
                        'expires_at', grant_row.expires_at::text,
                        'created_at', grant_row.created_at::text
                      )
                      ORDER BY grant_row.created_at DESC
                    ) FILTER (WHERE grant_row.grant_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM evidence_access_grants grant_row
                  JOIN document_row document ON document.evidence_document_id = grant_row.evidence_document_id
                  JOIN organizations grantee ON grantee.organization_id = grant_row.grantee_organization_id
                  WHERE grant_row.status = 'active'
                    AND grant_row.revoked_at IS NULL
                    AND grant_row.purpose = %s
                    AND (grant_row.expires_at IS NULL OR grant_row.expires_at > now())
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    document.tenant_id, actor.user_id, %s, 'evidence', document.evidence_document_id::text, document.classification,
                    'allow', %s, %s, %s
                  FROM document_row document, actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    document.tenant_id, 'EVIDENCE_DOCUMENT_READ', actor.user_id, %s, document.evidence_document_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || document.evidence_document_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', document.organization_external_id,
                      'classification', document.classification,
                      'version_count', jsonb_array_length(versions.data),
                      'active_grant_count', jsonb_array_length(active_grants.data)
                    ),
                    %s, %s
                  FROM document_row document, actor_row actor, versions, active_grants, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  document.evidence_document_id::text,
                  document.organization_external_id AS organization_id,
                  document.reporting_period_id,
                  document.period_key,
                  document.document_type,
                  document.title,
                  document.classification,
                  document.retention_status,
                  document.legal_hold,
                  document.source_submission_id,
                  document.source_record_id,
                  document.valid_from,
                  document.valid_to,
                  document.created_at,
                  versions.data AS versions,
                  active_grants.data AS active_grants,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM document_row document, versions, active_grants, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    evidence_document_id,
                    context.purpose,
                    decision.action,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            if row is None:
                self._audit_denied_evidence_access(
                    connection,
                    resource_id=evidence_document_id,
                    resource_type="evidence",
                    event_type="EVIDENCE_DOCUMENT_READ_DENIED",
                    action=decision.action,
                    context=context,
                    reason="not_found_or_not_authorized",
                )
                connection.commit()
                raise IntakeNotFoundError(evidence_document_id)
            connection.commit()
        return self._evidence_document_payload(row)

    def create_evidence_download_url(self, evidence_version_id: str, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_evidence",
            context,
            resource_type="evidence_version",
            resource_id=evidence_version_id,
            data_classification="confidential",
            external_access_allowed=True,
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                SELECT
                  version.evidence_version_id::text,
                  version.evidence_document_id::text,
                  version.tenant_id::text,
                  version.organization_id::text AS organization_uuid,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id,
                  version.object_key,
                  version.object_version,
                  version.document_hash,
                  version.content_type,
                  version.byte_size,
                  version.malware_scan_status,
                  COALESCE(document.retention_status, version.retention_status, 'active') AS retention_status,
                  document.classification
                FROM evidence_versions version
                JOIN evidence_documents document ON document.evidence_document_id = version.evidence_document_id
                JOIN organizations org ON org.organization_id = version.organization_id
                WHERE version.tenant_id = app_tenant_id()
                  AND version.evidence_version_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (evidence_version_id,),
            ).fetchone()
            if row is None:
                self._audit_denied_evidence_access(
                    connection,
                    resource_id=evidence_version_id,
                    resource_type="evidence_version",
                    event_type="EVIDENCE_DOWNLOAD_URL_DENIED",
                    action=decision.action,
                    context=context,
                    reason="not_found_or_not_authorized",
                )
                connection.commit()
                raise IntakeNotFoundError(evidence_version_id)
            if str(row["malware_scan_status"]) != "clean":
                self._audit_denied_evidence_access(
                    connection,
                    resource_id=evidence_version_id,
                    resource_type="evidence_version",
                    event_type="EVIDENCE_DOWNLOAD_URL_DENIED",
                    action=decision.action,
                    context=context,
                    reason=f"malware_scan_status_{row['malware_scan_status']}_not_downloadable",
                    evidence_document_id=str(row["evidence_document_id"]),
                    evidence_version_id=evidence_version_id,
                    organization_id=str(row["organization_uuid"]),
                    object_key=str(row["object_key"]),
                    object_storage_status="not_issued",
                )
                connection.commit()
                raise AccessDeniedError(
                    "EVIDENCE_VERSION_NOT_CLEAN",
                    "Evidence version is not downloadable until malware scan status is clean.",
                    status_code=409,
                )
            retention_status = str(row["retention_status"])
            if retention_status in {"scheduled_delete", "deleted"}:
                self._audit_denied_evidence_access(
                    connection,
                    resource_id=evidence_version_id,
                    resource_type="evidence_version",
                    event_type="EVIDENCE_DOWNLOAD_URL_DENIED",
                    action=decision.action,
                    context=context,
                    reason=f"retention_status_{retention_status}_not_downloadable",
                    evidence_document_id=str(row["evidence_document_id"]),
                    evidence_version_id=evidence_version_id,
                    organization_id=str(row["organization_uuid"]),
                    object_key=str(row["object_key"]),
                    object_storage_status="not_issued",
                )
                connection.commit()
                raise AccessDeniedError(
                    "EVIDENCE_VERSION_RETIRED",
                    "Evidence version is not downloadable while retention status is scheduled_delete or deleted.",
                    status_code=409,
                )

            object_storage_status = "configured" if self.object_storage.is_configured else "not_configured"
            if self.object_storage.is_configured:
                download_url = self.object_storage.presign_get_url(str(row["object_key"]))
            else:
                download_url = f"object-storage-not-configured://download-ticket/{evidence_version_id}"
            audit_row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT %s, actor.user_id, %s, 'evidence_version', %s, %s, 'allow', %s, %s, %s
                  FROM actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                object_access AS (
                  INSERT INTO evidence_object_access_logs (
                    tenant_id, evidence_document_id, evidence_version_id, organization_id, actor_id,
                    access_type, access_status, purpose, request_id, policy_decision_id,
                    object_storage_status, object_key_hash, reason
                  )
                  SELECT
                    %s, app_try_uuid(%s), app_try_uuid(%s), app_try_uuid(%s), actor.user_id,
                    'download_ticket', 'allowed', %s, %s, policy.decision_id,
                    %s, encode(digest(%s, 'sha256'), 'hex'), NULL
                  FROM actor_row actor, policy
                  RETURNING access_id
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    %s, 'EVIDENCE_DOWNLOAD_URL_CREATED', actor.user_id, %s, %s, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || %s || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', %s,
                      'evidence_document_id', %s,
                      'evidence_version_id', %s,
                      'object_storage_status', %s,
                      'expires_in_seconds', %s
                    ),
                    %s, %s
                  FROM actor_row actor, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id,
                  object_access.access_id::text AS object_access_id
                FROM policy, audit, object_access
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    row["tenant_id"],
                    decision.action,
                    evidence_version_id,
                    row["classification"],
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    row["tenant_id"],
                    row["evidence_document_id"],
                    evidence_version_id,
                    row["organization_uuid"],
                    context.purpose,
                    context.request_id,
                    object_storage_status,
                    row["object_key"],
                    row["tenant_id"],
                    context.actor_role,
                    evidence_version_id,
                    context.purpose,
                    context.request_id,
                    evidence_version_id,
                    row["organization_id"],
                    row["evidence_document_id"],
                    evidence_version_id,
                    object_storage_status,
                    self.object_storage.download_ttl_seconds,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if audit_row is None:
            raise PilotFeatureUnavailableError("governance.create_evidence_download_url.unprovisioned_identity")
        return {
            "evidence_version_id": evidence_version_id,
            "evidence_document_id": str(row["evidence_document_id"]),
            "organization_id": str(row["organization_id"]),
            "download_url": download_url,
            "download_method": "GET",
            "expires_in_seconds": self.object_storage.download_ttl_seconds,
            "object_storage_status": object_storage_status,
            "object_version": str(row["object_version"]),
            "document_hash": str(row["document_hash"]),
            "content_type": str(row["content_type"]),
            "byte_size": int(row["byte_size"]),
            "malware_scan_status": str(row["malware_scan_status"]),
            "policy_decision_id": str(audit_row["policy_decision_id"]),
            "audit_event_id": str(audit_row["audit_event_id"]),
            "object_access_id": str(audit_row["object_access_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Download tickets are short-lived, audited, and only issued for clean evidence versions."
            ),
        }

    def _audit_denied_evidence_access(
        self,
        connection: Any,
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
    ) -> None:
        access_type = "metadata_read" if event_type == "EVIDENCE_DOCUMENT_READ_DENIED" else "download_denied"
        object_key_hash = hashlib.sha256(object_key.encode("utf-8")).hexdigest() if object_key else None
        connection.execute(
            """
            WITH tenant_row AS (
              SELECT app_tenant_id() AS tenant_id
              WHERE app_tenant_id() IS NOT NULL
            ),
            actor_row AS (
              SELECT ua.user_id
              FROM tenant_row tenant
              JOIN user_accounts ua ON ua.tenant_id = tenant.tenant_id
              WHERE ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s
              LIMIT 1
            ),
            policy AS (
              INSERT INTO policy_decisions (
                tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                effect, reason, purpose, request_id
              )
              SELECT tenant.tenant_id, actor.user_id, %s, %s, %s, 'confidential', 'deny', %s, %s, %s
              FROM tenant_row tenant, actor_row actor
              RETURNING decision_id
            ),
            object_access AS (
              INSERT INTO evidence_object_access_logs (
                tenant_id, evidence_document_id, evidence_version_id, organization_id, actor_id,
                access_type, access_status, purpose, request_id, policy_decision_id,
                object_storage_status, object_key_hash, reason
              )
              SELECT
                tenant.tenant_id, app_try_uuid(%s), app_try_uuid(%s), app_try_uuid(%s), actor.user_id,
                %s, 'denied', %s, %s, policy.decision_id,
                %s, %s, %s
              FROM tenant_row tenant, actor_row actor, policy
              RETURNING access_id
            ),
            previous AS (
              SELECT event_hash
              FROM audit_logs
              WHERE tenant_id = app_tenant_id()
              ORDER BY created_at DESC, event_id DESC
              LIMIT 1
            )
            INSERT INTO audit_logs (
              tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
              request_id, policy_decision_id, previous_hash, event_hash, payload,
              app_mode, auth_assurance
            )
            SELECT
              tenant.tenant_id, %s, actor.user_id, %s, %s, %s,
              %s, policy.decision_id, previous.event_hash,
              encode(digest(policy.decision_id::text || %s || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
              jsonb_build_object('resource_type', %s, 'reason', %s),
              %s, %s
            FROM tenant_row tenant, actor_row actor, policy, object_access
            LEFT JOIN previous ON true
            """,
            (
                context.actor_id,
                context.actor_id,
                action,
                resource_type,
                resource_id,
                reason,
                context.purpose,
                context.request_id,
                evidence_document_id,
                evidence_version_id,
                organization_id,
                access_type,
                context.purpose,
                context.request_id,
                object_storage_status,
                object_key_hash,
                reason,
                event_type,
                context.actor_role,
                resource_id,
                context.purpose,
                context.request_id,
                resource_id,
                resource_type,
                reason,
                context.app_mode,
                context.auth_assurance,
            ),
        )

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
        decision = PolicyService.require(
            "create_evidence_version",
            context,
            resource_type="evidence",
            resource_id=evidence_document_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                document_row AS (
                  SELECT
                    document.evidence_document_id,
                    document.tenant_id,
                    document.organization_id,
                    document.classification,
                    COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM evidence_documents document
                  JOIN organizations org ON org.organization_id = document.organization_id
                  WHERE document.tenant_id = app_tenant_id()
                    AND document.evidence_document_id = app_try_uuid(%s)
                    AND (
                      document.organization_id = app_try_uuid(%s)
                      OR org.external_business_id = %s
                    )
                  LIMIT 1
                ),
                superseded AS (
                  SELECT ev.evidence_version_id
                  FROM evidence_versions ev
                  JOIN document_row document ON document.evidence_document_id = ev.evidence_document_id
                  WHERE ev.evidence_version_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    document.tenant_id, actor.user_id, %s, 'evidence', document.evidence_document_id::text, document.classification,
                    'allow', %s, %s, %s
                  FROM document_row document, actor_row actor
                  RETURNING decision_id
                ),
                version AS (
                  INSERT INTO evidence_versions (
                    evidence_document_id, tenant_id, organization_id, object_key, object_version,
                    document_hash, content_type, byte_size, malware_scan_status,
                    uploader_id, supersedes_version_id
                  )
                  SELECT
                    document.evidence_document_id, document.tenant_id, document.organization_id, %s, gen_random_uuid()::text,
                    %s, %s, %s, %s,
                    actor.user_id,
                    CASE WHEN %s IS NULL THEN NULL ELSE superseded.evidence_version_id END
                  FROM document_row document, actor_row actor
                  LEFT JOIN superseded ON true
                  WHERE %s IS NULL OR superseded.evidence_version_id IS NOT NULL
                  RETURNING *
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs al
                  WHERE al.tenant_id = app_tenant_id()
                  ORDER BY al.created_at DESC, al.event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    version.tenant_id, 'EVIDENCE_VERSION_RECORDED', actor.user_id, %s, document.evidence_document_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || version.evidence_version_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', document.external_id,
                      'evidence_version_id', version.evidence_version_id::text,
                      'object_key', version.object_key,
                      'document_hash', version.document_hash,
                      'malware_scan_status', version.malware_scan_status,
                      'usable', version.malware_scan_status = 'clean'
                    ),
                    %s, %s
                  FROM document_row document, actor_row actor, version, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  version.evidence_version_id::text,
                  document.evidence_document_id::text,
                  document.external_id AS organization_id,
                  version.object_key,
                  version.object_version,
                  version.document_hash,
                  version.malware_scan_status,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM document_row document, version, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    evidence_document_id,
                    organization_id,
                    organization_id,
                    supersedes_version_id,
                    decision.action,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    object_key,
                    document_hash,
                    content_type,
                    byte_size,
                    "pending_scan",
                    supersedes_version_id,
                    supersedes_version_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.add_evidence_version.unprovisioned_document_or_superseded_version")
        return self._evidence_version_payload(row)

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
        decision = PolicyService.require(
            "record_malware_scan_result",
            context,
            resource_type="evidence_version",
            resource_id=evidence_version_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                version_row AS (
                  SELECT
                    version.evidence_version_id,
                    version.evidence_document_id,
                    version.tenant_id,
                    version.organization_id,
                    version.object_key,
                    version.object_version,
                    version.document_hash,
                    version.content_type,
                    version.byte_size,
                    version.malware_scan_status AS previous_scan_status,
                    document.classification,
                    document.retention_status AS previous_retention_status,
                    COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM evidence_versions version
                  JOIN evidence_documents document ON document.evidence_document_id = version.evidence_document_id
                  JOIN organizations org ON org.organization_id = version.organization_id
                  WHERE version.tenant_id = app_tenant_id()
                    AND version.evidence_version_id = app_try_uuid(%s)
                    AND (
                      version.organization_id = app_try_uuid(%s)
                      OR org.external_business_id = %s
                    )
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    version.tenant_id, actor.user_id, %s, 'evidence_version', version.evidence_version_id::text, version.classification,
                    'allow', %s, %s, %s
                  FROM version_row version, actor_row actor
                  RETURNING decision_id
                ),
                updated_version AS (
                  UPDATE evidence_versions
                  SET malware_scan_status = %s
                  WHERE evidence_version_id = (SELECT evidence_version_id FROM version_row)
                  RETURNING *
                ),
                updated_document AS (
                  UPDATE evidence_documents
                  SET retention_status = CASE
                        WHEN %s IN ('infected', 'failed') THEN 'retention_locked'
                        ELSE retention_status
                      END
                  WHERE evidence_document_id = (SELECT evidence_document_id FROM version_row)
                  RETURNING retention_status
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated_version.tenant_id, 'EVIDENCE_SCAN_RESULT_RECORDED', actor.user_id, %s, updated_version.evidence_version_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated_version.evidence_version_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', version.external_id,
                      'evidence_document_id', updated_version.evidence_document_id::text,
                      'previous_scan_status', version.previous_scan_status,
                      'malware_scan_status', updated_version.malware_scan_status,
                      'scanner_name', %s,
                      'scanner_version', %s,
                      'scanned_at', %s,
                      'details', %s,
                      'retention_status', updated_document.retention_status
                    ),
                    %s, %s
                  FROM updated_version, updated_document, version_row version, actor_row actor, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  updated_version.evidence_version_id::text,
                  updated_version.evidence_document_id::text,
                  version.external_id AS organization_id,
                  updated_version.object_key,
                  updated_version.object_version,
                  updated_version.document_hash,
                  updated_version.malware_scan_status,
                  updated_document.retention_status,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated_version, updated_document, version_row version, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    evidence_version_id,
                    organization_id,
                    organization_id,
                    decision.action,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    malware_scan_status,
                    malware_scan_status,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    scanner_name,
                    scanner_version,
                    scanned_at,
                    details,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.record_evidence_scan_result.unprovisioned_version")
        return self._evidence_scan_result_payload(row)

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
        decision = PolicyService.require(
            "grant_evidence_access",
            context,
            resource_type="evidence_access_grant",
            resource_id=evidence_document_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                document_row AS (
                  SELECT
                    document.evidence_document_id,
                    document.tenant_id,
                    document.organization_id,
                    document.classification,
                    COALESCE(subject.external_business_id, subject.organization_id::text) AS subject_external_id
                  FROM evidence_documents document
                  JOIN organizations subject ON subject.organization_id = document.organization_id
                  WHERE document.tenant_id = app_tenant_id()
                    AND document.evidence_document_id = app_try_uuid(%s)
                    AND (
                      document.organization_id = app_try_uuid(%s)
                      OR subject.external_business_id = %s
                    )
                  LIMIT 1
                ),
                grantee_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    document.tenant_id, actor.user_id, %s, 'evidence_access_grant', document.evidence_document_id::text, document.classification,
                    'allow', %s, %s, %s
                  FROM document_row document, actor_row actor, grantee_org
                  RETURNING decision_id
                ),
                grant_row AS (
                  INSERT INTO evidence_access_grants (
                    tenant_id, evidence_document_id, subject_organization_id, grantee_organization_id,
                    scope, purpose, status, expires_at, revoked_at, granted_by
                  )
                  SELECT
                    document.tenant_id, document.evidence_document_id, document.organization_id, grantee.organization_id,
                    %s, %s, 'active', %s::timestamptz, NULL, actor.user_id
                  FROM document_row document, actor_row actor, grantee_org grantee, policy
                  RETURNING *
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    grant_row.tenant_id, 'EVIDENCE_ACCESS_GRANTED', actor.user_id, %s, grant_row.grant_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || grant_row.grant_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'evidence_document_id', document.evidence_document_id::text,
                      'organization_id', document.subject_external_id,
                      'grantee_organization_id', grantee.external_id,
                      'scope', grant_row.scope,
                      'purpose', grant_row.purpose,
                      'expires_at', grant_row.expires_at
                    ),
                    %s, %s
                  FROM grant_row, document_row document, grantee_org grantee, actor_row actor, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  grant_row.grant_id::text,
                  grant_row.evidence_document_id::text,
                  document.subject_external_id AS organization_id,
                  grantee.external_id AS grantee_organization_id,
                  grant_row.scope,
                  grant_row.purpose,
                  grant_row.status,
                  grant_row.expires_at::text,
                  grant_row.revoked_at::text,
                  grant_row.created_at::text,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM grant_row, document_row document, grantee_org grantee, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    evidence_document_id,
                    organization_id,
                    organization_id,
                    grantee_organization_id,
                    grantee_organization_id,
                    decision.action,
                    decision.reason,
                    purpose,
                    context.request_id,
                    scope,
                    purpose,
                    expires_at,
                    context.actor_role,
                    purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.create_evidence_access_grant.unprovisioned_document_or_grantee")
        return self._evidence_access_grant_payload(row)

    def revoke_evidence_access_grant(self, grant_id: str, context: RequestContext) -> dict[str, Any]:
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  grant.grant_id::text,
                  grant.evidence_document_id::text,
                  COALESCE(subject.external_business_id, subject.organization_id::text) AS organization_id
                FROM evidence_access_grants grant
                JOIN organizations subject ON subject.organization_id = grant.subject_organization_id
                WHERE grant.tenant_id = app_tenant_id()
                  AND grant.grant_id = app_try_uuid(%s)
                LIMIT 1
                """,
                (grant_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(grant_id)
            decision = PolicyService.require(
                "revoke_evidence_access",
                context,
                resource_type="evidence_access_grant",
                resource_id=grant_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="confidential",
            )
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                updated AS (
                  UPDATE evidence_access_grants
                  SET status = 'revoked', revoked_at = now(), updated_at = now()
                  WHERE grant_id = app_try_uuid(%s)
                  RETURNING *
                ),
                subject_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated ON updated.subject_organization_id = org.organization_id
                ),
                grantee_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated ON updated.grantee_organization_id = org.organization_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    updated.tenant_id, actor.user_id, %s, 'evidence_access_grant', updated.grant_id::text, %s,
                    'allow', %s, %s, %s
                  FROM updated, actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'EVIDENCE_ACCESS_REVOKED', actor.user_id, %s, updated.grant_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated.grant_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'evidence_document_id', updated.evidence_document_id::text,
                      'organization_id', subject_org.external_id,
                      'grantee_organization_id', grantee_org.external_id,
                      'scope', updated.scope
                    ),
                    %s, %s
                  FROM updated, actor_row actor, subject_org, grantee_org, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  updated.grant_id::text,
                  updated.evidence_document_id::text,
                  subject_org.external_id AS organization_id,
                  grantee_org.external_id AS grantee_organization_id,
                  updated.scope,
                  updated.purpose,
                  updated.status,
                  updated.expires_at::text,
                  updated.revoked_at::text,
                  updated.created_at::text,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated, subject_org, grantee_org, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    grant_id,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.revoke_evidence_access_grant.unprovisioned_identity")
        return self._evidence_access_grant_payload(row)

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
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                """
                SELECT
                  document.evidence_document_id::text,
                  document.legal_hold,
                  COALESCE(org.external_business_id, org.organization_id::text) AS organization_id
                FROM evidence_documents document
                JOIN organizations org ON org.organization_id = document.organization_id
                WHERE document.tenant_id = app_tenant_id()
                  AND document.evidence_document_id = app_try_uuid(%s)
                  AND (
                    document.organization_id = app_try_uuid(%s)
                    OR org.external_business_id = %s
                  )
                LIMIT 1
                """,
                (evidence_document_id, organization_id, organization_id),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(evidence_document_id)
            if bool(existing["legal_hold"]) and retention_status == "deleted":
                raise ValueError("Evidence on legal hold cannot be marked deleted.")
            decision = PolicyService.require(
                "update_evidence_retention",
                context,
                resource_type="evidence",
                resource_id=evidence_document_id,
                resource_organization_id=str(existing["organization_id"]),
                data_classification="confidential",
            )
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                updated AS (
                  UPDATE evidence_documents
                  SET retention_status = %s,
                      legal_hold = %s,
                      valid_to = CASE WHEN %s = 'deleted' THEN CURRENT_DATE ELSE valid_to END
                  WHERE tenant_id = app_tenant_id()
                    AND evidence_document_id = app_try_uuid(%s)
                  RETURNING *
                ),
                org_row AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN updated ON updated.organization_id = org.organization_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    updated.tenant_id, actor.user_id, %s, 'evidence', updated.evidence_document_id::text, updated.classification,
                    'allow', %s, %s, %s
                  FROM updated, actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'EVIDENCE_RETENTION_UPDATED', actor.user_id, %s, updated.evidence_document_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated.evidence_document_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', org.external_id,
                      'retention_status', updated.retention_status,
                      'legal_hold', updated.legal_hold,
                      'reason', %s
                    ),
                    %s, %s
                  FROM updated, actor_row actor, org_row org, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  updated.evidence_document_id::text,
                  org.external_id AS organization_id,
                  updated.retention_status,
                  updated.legal_hold,
                  updated.valid_to::text AS valid_to,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated, org_row org, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    retention_status,
                    legal_hold,
                    retention_status,
                    evidence_document_id,
                    decision.action,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    reason,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.update_evidence_retention.unprovisioned_identity")
        return self._evidence_retention_payload(row)

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
            raise AccessDeniedError(
                "POLICY_DENIED",
                "Invoice claim financier must match the actor organization or platform operations.",
                status_code=403,
            )
        decision = PolicyService.require(
            "register_invoice_claim",
            context,
            resource_type="invoice_claim",
            resource_id=invoice_id,
            resource_organization_id=seller_id,
            data_classification="restricted_financial",
            external_access_allowed=True,
        )
        identity = invoice_identity_hash(seller_id, buyer_id, invoice_hash_value, amount, due_date)
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            if idempotency_key:
                existing = connection.execute(
                    self._invoice_claim_select_sql("claim.idempotency_key = %s"),
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    return self._invoice_claim_payload(existing, decision.decision_id, None)
            active = connection.execute(
                """
                SELECT claim_id::text
                FROM invoice_claims
                WHERE tenant_id = app_tenant_id()
                  AND invoice_identity_hash = %s
                  AND status IN ('pledged', 'financed')
                LIMIT 1
                """,
                (identity,),
            ).fetchone()
            if active is not None:
                raise ValueError("Invoice already has an active pledged/financed claim.")
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                seller_org AS (
                  SELECT org.organization_id, org.tenant_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                buyer_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                financier_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                source_evidence AS (
                  SELECT document.evidence_document_id
                  FROM evidence_documents document
                  JOIN seller_org seller ON seller.organization_id = document.organization_id
                  WHERE document.evidence_document_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                claim_inputs AS (
                  SELECT
                    seller.tenant_id,
                    actor.user_id AS actor_id,
                    seller.organization_id AS seller_uuid,
                    buyer.organization_id AS buyer_uuid,
                    financier.organization_id AS financier_uuid,
                    seller.external_id AS seller_external_id,
                    buyer.external_id AS buyer_external_id,
                    financier.external_id AS financier_external_id,
                    CASE WHEN %s IS NULL THEN NULL ELSE source_evidence.evidence_document_id END AS source_evidence_uuid
                  FROM actor_row actor, seller_org seller, buyer_org buyer, financier_org financier
                  LEFT JOIN source_evidence ON true
                  WHERE %s IS NULL OR source_evidence.evidence_document_id IS NOT NULL
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    claim_inputs.tenant_id, claim_inputs.actor_id, %s, 'invoice_claim', %s, %s,
                    'allow', %s, %s, %s
                  FROM claim_inputs
                  RETURNING decision_id
                ),
                claim AS (
                  INSERT INTO invoice_claims (
                    tenant_id, seller_id, buyer_id, financier_id, invoice_id, invoice_hash,
                    invoice_identity_hash, amount, currency, issue_date, due_date, status,
                    idempotency_key, review_status, reviewer_id, source_evidence_id, created_by
                  )
                  SELECT
                    claim_inputs.tenant_id, claim_inputs.seller_uuid, claim_inputs.buyer_uuid, claim_inputs.financier_uuid,
                    %s, %s, %s, %s, %s, %s::date, %s::date, 'registered',
                    %s, 'pending_review', NULL, claim_inputs.source_evidence_uuid, claim_inputs.actor_id
                  FROM claim_inputs, policy
                  RETURNING *
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    claim.tenant_id, 'INVOICE_CLAIM_REGISTERED', claim.created_by, %s, claim.claim_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || claim.claim_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'seller_id', claim_inputs.seller_external_id,
                      'buyer_id', claim_inputs.buyer_external_id,
                      'financier_id', claim_inputs.financier_external_id,
                      'invoice_identity_hash', claim.invoice_identity_hash,
                      'status', claim.status,
                      'review_status', claim.review_status
                    ),
                    %s, %s
                  FROM claim, claim_inputs, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  claim.claim_id::text,
                  claim_inputs.seller_external_id AS seller_id,
                  claim_inputs.buyer_external_id AS buyer_id,
                  claim_inputs.financier_external_id AS financier_id,
                  claim.invoice_id,
                  claim.invoice_hash,
                  claim.invoice_identity_hash,
                  claim.amount::text AS amount,
                  claim.currency,
                  claim.issue_date::text AS issue_date,
                  claim.due_date::text AS due_date,
                  claim.status::text,
                  claim.idempotency_key,
                  claim.review_status,
                  claim.reviewer_id::text AS reviewer_id,
                  claim.source_evidence_id::text AS source_evidence_id,
                  claim.created_by::text AS created_by,
                  claim.created_at::text AS created_at,
                  claim.updated_at::text AS updated_at,
                  claim.released_at::text AS released_at,
                  claim.dispute_reason,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM claim, claim_inputs, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    seller_id,
                    seller_id,
                    buyer_id,
                    buyer_id,
                    financier_id,
                    financier_id,
                    source_evidence_id,
                    source_evidence_id,
                    source_evidence_id,
                    decision.action,
                    invoice_id or identity,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    invoice_id,
                    invoice_hash_value,
                    identity,
                    amount,
                    currency,
                    issue_date,
                    due_date,
                    idempotency_key,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.create_invoice_claim.unprovisioned_identity_or_evidence")
        return self._invoice_claim_payload(row, decision.decision_id, row.get("audit_event_id"))

    def transition_invoice_claim(self, claim_id: str, to_status: str, note: str | None, context: RequestContext) -> dict[str, Any]:
        if to_status not in INVOICE_STATES:
            raise ValueError("Unsupported invoice claim status.")
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            existing = connection.execute(
                self._invoice_claim_select_sql("claim.claim_id = app_try_uuid(%s)"),
                (claim_id,),
            ).fetchone()
            if existing is None:
                raise IntakeNotFoundError(claim_id)
            current_status = str(existing["status"])
            allowed = INVOICE_TRANSITIONS.get(current_status, set())
            if to_status not in allowed:
                raise ValueError(f"Cannot transition invoice claim from {current_status} to {to_status}.")
            if to_status in {"financed", "released"} and not context.has_role("lender", "reviewer", "demo_operator", "demo_admin", "system_admin"):
                raise ValueError("Financing lifecycle transitions require lender/reviewer approval.")
            decision = PolicyService.require(
                "transition_invoice_claim",
                context,
                resource_type="invoice_claim",
                resource_id=claim_id,
                resource_organization_id=str(existing["seller_id"]),
                data_classification="restricted_financial",
                external_access_allowed=True,
            )
            if to_status in {"pledged", "financed"}:
                active = connection.execute(
                    """
                    SELECT claim_id::text
                    FROM invoice_claims
                    WHERE tenant_id = app_tenant_id()
                      AND invoice_identity_hash = %s
                      AND status IN ('pledged', 'financed')
                      AND claim_id <> app_try_uuid(%s)
                    LIMIT 1
                    """,
                    (existing["invoice_identity_hash"], claim_id),
                ).fetchone()
                if active is not None:
                    raise ValueError("Invoice already has another active pledged/financed claim.")
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                existing_claim AS (
                  SELECT claim.*
                  FROM invoice_claims claim
                  WHERE claim.tenant_id = app_tenant_id()
                    AND claim.claim_id = app_try_uuid(%s)
                  LIMIT 1
                ),
                seller_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN existing_claim claim ON claim.seller_id = org.organization_id
                ),
                buyer_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN existing_claim claim ON claim.buyer_id = org.organization_id
                ),
                financier_org AS (
                  SELECT org.organization_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  JOIN existing_claim claim ON claim.financier_id = org.organization_id
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    existing_claim.tenant_id, actor.user_id, %s, 'invoice_claim', existing_claim.claim_id::text, %s,
                    'allow', %s, %s, %s
                  FROM existing_claim, actor_row actor
                  RETURNING decision_id
                ),
                updated AS (
                  UPDATE invoice_claims
                  SET status = %s,
                      review_status = CASE WHEN %s IN ('verified', 'pledged', 'financed', 'released') THEN 'reviewed' ELSE 'disputed' END,
                      reviewer_id = actor.user_id,
                      updated_at = now(),
                      released_at = CASE WHEN %s = 'released' THEN now() ELSE released_at END,
                      dispute_reason = CASE WHEN %s = 'disputed' THEN %s ELSE dispute_reason END
                  FROM actor_row actor
                  WHERE invoice_claims.claim_id = (SELECT claim_id FROM existing_claim)
                  RETURNING invoice_claims.*
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    updated.tenant_id, 'INVOICE_CLAIM_TRANSITIONED', actor.user_id, %s, updated.claim_id::text, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || updated.claim_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'from_status', existing_claim.status,
                      'to_status', updated.status,
                      'review_status', updated.review_status,
                      'note', %s
                    ),
                    %s, %s
                  FROM updated, existing_claim, actor_row actor, policy
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  updated.claim_id::text,
                  seller_org.external_id AS seller_id,
                  buyer_org.external_id AS buyer_id,
                  financier_org.external_id AS financier_id,
                  updated.invoice_id,
                  updated.invoice_hash,
                  updated.invoice_identity_hash,
                  updated.amount::text AS amount,
                  updated.currency,
                  updated.issue_date::text AS issue_date,
                  updated.due_date::text AS due_date,
                  updated.status::text,
                  updated.idempotency_key,
                  updated.review_status,
                  updated.reviewer_id::text AS reviewer_id,
                  updated.source_evidence_id::text AS source_evidence_id,
                  updated.created_by::text AS created_by,
                  updated.created_at::text AS created_at,
                  updated.updated_at::text AS updated_at,
                  updated.released_at::text AS released_at,
                  updated.dispute_reason,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM updated, seller_org, buyer_org, financier_org, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    claim_id,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    to_status,
                    to_status,
                    to_status,
                    to_status,
                    note,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    note,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.transition_invoice_claim.unprovisioned_identity")
        return self._invoice_claim_payload(row, decision.decision_id, row.get("audit_event_id"))

    def list_risk_runs(self, organization_id: str, period_key: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_risk_run",
            context,
            resource_type="risk_run",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="restricted_financial",
            external_access_allowed=True,
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                org_row AS (
                  SELECT org.organization_id, org.tenant_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN org_row org ON org.organization_id = rp.organization_id
                  WHERE %s IS NULL OR rp.period_key = %s
                  ORDER BY rp.period_start DESC
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    org.tenant_id, actor.user_id, %s, 'risk_run', org.external_id, %s,
                    'allow', %s, %s, %s
                  FROM org_row org, actor_row actor
                  RETURNING decision_id
                ),
                runs AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'risk_run_id', rr.risk_run_id::text,
                        'organization_id', org.external_id,
                        'reporting_period_id', rr.reporting_period_id::text,
                        'period_key', period.period_key,
                        'feature_snapshot_id', rr.feature_snapshot_id::text,
                        'model_version', rr.model_version,
                        'ruleset_version', rr.ruleset_version,
                        'score', rr.score,
                        'level', rr.level,
                        'explanation', rr.explanation,
                        'review_status', rr.review_status,
                        'created_at', rr.created_at::text,
                        'feature_payload', feature.payload
                      )
                      ORDER BY rr.created_at DESC
                    ) FILTER (WHERE rr.risk_run_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM org_row org
                  LEFT JOIN period_row period ON true
                  LEFT JOIN risk_runs rr
                    ON rr.organization_id = org.organization_id
                   AND rr.reporting_period_id = period.reporting_period_id
                  LEFT JOIN feature_snapshots feature
                    ON feature.feature_snapshot_id = rr.feature_snapshot_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    org.tenant_id, 'RISK_RUNS_VIEWED', actor.user_id, %s, org.external_id, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || org.organization_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', org.external_id,
                      'period_key', COALESCE((SELECT period_key FROM period_row), %s),
                      'run_count', jsonb_array_length(runs.data)
                    ),
                    %s, %s
                  FROM org_row org, actor_row actor, policy, runs
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  org.external_id AS organization_id,
                  COALESCE((SELECT period_key FROM period_row), %s) AS period_key,
                  runs.data AS risk_runs,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM org_row org, runs, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    period_key,
                    period_key,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    period_key,
                    context.app_mode,
                    context.auth_assurance,
                    period_key,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.list_risk_runs.unprovisioned_identity_or_organization")
        return self._runs_payload("risk_runs", row)

    def list_match_runs(self, organization_id: str, period_key: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_match_run",
            context,
            resource_type="match_run",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                org_row AS (
                  SELECT org.organization_id, org.tenant_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN org_row org ON org.organization_id = rp.organization_id
                  WHERE %s IS NULL OR rp.period_key = %s
                  ORDER BY rp.period_start DESC
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    org.tenant_id, actor.user_id, %s, 'match_run', org.external_id, %s,
                    'allow', %s, %s, %s
                  FROM org_row org, actor_row actor
                  RETURNING decision_id
                ),
                runs AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'match_run_id', mr.match_run_id::text,
                        'buyer_organization_id', org.external_id,
                        'reporting_period_id', mr.reporting_period_id::text,
                        'period_key', period.period_key,
                        'disrupted_supplier_id', COALESCE(disrupted.external_business_id, disrupted.organization_id::text),
                        'product_category', mr.product_category,
                        'ruleset_version', mr.ruleset_version,
                        'review_status', mr.review_status,
                        'created_at', mr.created_at::text,
                        'candidates', (
                          SELECT COALESCE(
                            jsonb_agg(
                              jsonb_build_object(
                                'candidate_id', candidate.candidate_id::text,
                                'supplier_organization_id', COALESCE(supplier.external_business_id, supplier.organization_id::text),
                                'rank', candidate.rank,
                                'score', candidate.score,
                                'explanation', candidate.explanation,
                                'consent_status', candidate.consent_status
                              )
                              ORDER BY candidate.rank
                            ),
                            '[]'::jsonb
                          )
                          FROM match_candidates candidate
                          JOIN organizations supplier ON supplier.organization_id = candidate.supplier_organization_id
                          WHERE candidate.match_run_id = mr.match_run_id
                        )
                      )
                      ORDER BY mr.created_at DESC
                    ) FILTER (WHERE mr.match_run_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM org_row org
                  LEFT JOIN period_row period ON true
                  LEFT JOIN match_runs mr
                    ON mr.buyer_organization_id = org.organization_id
                   AND mr.reporting_period_id = period.reporting_period_id
                  LEFT JOIN organizations disrupted ON disrupted.organization_id = mr.disrupted_supplier_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    org.tenant_id, 'MATCH_RUNS_VIEWED', actor.user_id, %s, org.external_id, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || org.organization_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', org.external_id,
                      'period_key', COALESCE((SELECT period_key FROM period_row), %s),
                      'run_count', jsonb_array_length(runs.data)
                    ),
                    %s, %s
                  FROM org_row org, actor_row actor, policy, runs
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  org.external_id AS organization_id,
                  COALESCE((SELECT period_key FROM period_row), %s) AS period_key,
                  runs.data AS match_runs,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM org_row org, runs, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    period_key,
                    period_key,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    period_key,
                    context.app_mode,
                    context.auth_assurance,
                    period_key,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.list_match_runs.unprovisioned_identity_or_organization")
        return self._runs_payload("match_runs", row)

    def list_scenario_runs(self, organization_id: str, period_key: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_scenario_run",
            context,
            resource_type="scenario_run",
            resource_id=organization_id,
            resource_organization_id=organization_id,
            data_classification="confidential",
        )
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                org_row AS (
                  SELECT org.organization_id, org.tenant_id, COALESCE(org.external_business_id, org.organization_id::text) AS external_id
                  FROM organizations org
                  WHERE org.tenant_id = app_tenant_id()
                    AND (org.organization_id = app_try_uuid(%s) OR org.external_business_id = %s)
                  LIMIT 1
                ),
                period_row AS (
                  SELECT rp.*
                  FROM reporting_periods rp
                  JOIN org_row org ON org.organization_id = rp.organization_id
                  WHERE %s IS NULL OR rp.period_key = %s
                  ORDER BY rp.period_start DESC
                  LIMIT 1
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT
                    org.tenant_id, actor.user_id, %s, 'scenario_run', org.external_id, %s,
                    'allow', %s, %s, %s
                  FROM org_row org, actor_row actor
                  RETURNING decision_id
                ),
                runs AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'scenario_run_id', sr.scenario_run_id::text,
                        'organization_id', org.external_id,
                        'reporting_period_id', sr.reporting_period_id::text,
                        'period_key', period.period_key,
                        'input_snapshot_id', sr.input_snapshot_id::text,
                        'shock_organization_id', COALESCE(shock.external_business_id, shock.organization_id::text),
                        'product_category', sr.product_category,
                        'ruleset_version', sr.ruleset_version,
                        'model_version', sr.model_version,
                        'payload', sr.payload,
                        'review_status', sr.review_status,
                        'created_at', sr.created_at::text
                      )
                      ORDER BY sr.created_at DESC
                    ) FILTER (WHERE sr.scenario_run_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM org_row org
                  LEFT JOIN period_row period ON true
                  LEFT JOIN scenario_runs sr
                    ON sr.organization_id = org.organization_id
                   AND sr.reporting_period_id = period.reporting_period_id
                  LEFT JOIN organizations shock ON shock.organization_id = sr.shock_organization_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    org.tenant_id, 'SCENARIO_RUNS_VIEWED', actor.user_id, %s, org.external_id, %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || org.organization_id::text || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object(
                      'organization_id', org.external_id,
                      'period_key', COALESCE((SELECT period_key FROM period_row), %s),
                      'run_count', jsonb_array_length(runs.data)
                    ),
                    %s, %s
                  FROM org_row org, actor_row actor, policy, runs
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  org.external_id AS organization_id,
                  COALESCE((SELECT period_key FROM period_row), %s) AS period_key,
                  runs.data AS scenario_runs,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM org_row org, runs, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    period_key,
                    period_key,
                    decision.action,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    context.purpose,
                    context.request_id,
                    period_key,
                    context.app_mode,
                    context.auth_assurance,
                    period_key,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.list_scenario_runs.unprovisioned_identity_or_organization")
        return self._runs_payload("scenario_runs", row)

    def list_model_registry(self, artifact_type: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_ops",
            context,
            resource_type="model_registry",
            resource_id=artifact_type or "all",
            data_classification="confidential",
        )
        row = self._list_registry_rows(
            table_name="model_registry",
            event_type="MODEL_REGISTRY_VIEWED",
            output_key="models",
            version_column="model_version",
            artifact_type=artifact_type,
            decision=decision,
            context=context,
        )
        return {
            "artifact_type": artifact_type,
            "models": self._json_list(row.get("models")),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": TRUST_NOTICE,
        }

    def list_ruleset_registry(self, artifact_type: str | None, context: RequestContext) -> dict[str, Any]:
        decision = PolicyService.require(
            "read_ops",
            context,
            resource_type="ruleset_registry",
            resource_id=artifact_type or "all",
            data_classification="confidential",
        )
        row = self._list_registry_rows(
            table_name="ruleset_registry",
            event_type="RULESET_REGISTRY_VIEWED",
            output_key="rulesets",
            version_column="ruleset_version",
            artifact_type=artifact_type,
            decision=decision,
            context=context,
        )
        return {
            "artifact_type": artifact_type,
            "rulesets": self._json_list(row.get("rulesets")),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
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
        safe_limit = max(1, min(limit, 100))
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                """
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                jobs AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'job_id', job.job_id::text,
                        'organization_id', COALESCE(org.external_business_id, org.organization_id::text),
                        'reporting_period_id', job.reporting_period_id::text,
                        'source_submission_id', job.source_submission_id::text,
                        'job_type', job.job_type,
                        'status', job.status,
                        'idempotency_key', job.idempotency_key,
                        'payload', job.payload,
                        'attempts', job.attempts,
                        'max_attempts', job.max_attempts,
                        'last_error', job.last_error,
                        'created_at', job.created_at::text,
                        'updated_at', job.updated_at::text,
                        'available_at', job.available_at::text,
                        'started_at', job.started_at::text,
                        'completed_at', job.completed_at::text
                      )
                      ORDER BY job.created_at DESC
                    ) FILTER (WHERE job.job_id IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM analytics_recompute_jobs job
                  JOIN organizations org ON org.organization_id = job.organization_id
                  WHERE job.tenant_id = app_tenant_id()
                    AND (%s IS NULL OR org.external_business_id = %s OR org.organization_id = app_try_uuid(%s))
                    AND (%s IS NULL OR job.status = %s)
                  LIMIT %s
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT app_tenant_id(), actor.user_id, %s, 'analytics_recompute_jobs', COALESCE(%s, %s, 'all'), %s,
                    'allow', %s, %s, %s
                  FROM actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    app_tenant_id(), 'RECOMPUTE_JOBS_VIEWED', actor.user_id, %s, COALESCE(%s, 'all'), %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || COALESCE(%s, 'all') || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('organization_id', %s, 'status', %s, 'count', jsonb_array_length(jobs.data)),
                    %s, %s
                  FROM actor_row actor, policy, jobs
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  jobs.data AS jobs,
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM jobs, policy, audit
                """,
                (
                    context.actor_id,
                    context.actor_id,
                    organization_id,
                    organization_id,
                    organization_id,
                    status,
                    status,
                    safe_limit,
                    decision.action,
                    organization_id,
                    status,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    context.actor_role,
                    organization_id,
                    context.purpose,
                    context.request_id,
                    organization_id,
                    organization_id,
                    status,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError("governance.list_recompute_jobs.unprovisioned_identity")
        return {
            "organization_id": organization_id,
            "status": status,
            "limit": safe_limit,
            "jobs": self._json_list(row.get("jobs")),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": TRUST_NOTICE,
        }

    def _list_registry_rows(
        self,
        *,
        table_name: str,
        event_type: str,
        output_key: str,
        version_column: str,
        artifact_type: str | None,
        decision: Any,
        context: RequestContext,
    ) -> dict[str, Any]:
        if table_name not in {"model_registry", "ruleset_registry"}:
            raise PilotFeatureUnavailableError("governance.registry.invalid_table")
        statement = f"""
                WITH actor_row AS (
                  SELECT ua.user_id
                  FROM user_accounts ua
                  WHERE ua.tenant_id = app_tenant_id()
                    AND (ua.user_id = app_try_uuid(%s) OR ua.external_subject = %s)
                  LIMIT 1
                ),
                rows_json AS (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'artifact_type', item.artifact_type,
                        '{version_column}', item.{version_column},
                        'status', item.status,
                        'approval_status', item.approval_status,
                        'config', item.config,
                        'checksum', item.checksum,
                        'created_by', item.created_by::text,
                        'created_at', item.created_at::text
                      )
                      ORDER BY item.artifact_type, item.{version_column}
                    ) FILTER (WHERE item.{version_column} IS NOT NULL),
                    '[]'::jsonb
                  ) AS data
                  FROM {table_name} item
                  WHERE item.tenant_id = app_tenant_id()
                    AND (%s IS NULL OR item.artifact_type = %s)
                ),
                policy AS (
                  INSERT INTO policy_decisions (
                    tenant_id, actor_id, action, resource_type, resource_id, data_classification,
                    effect, reason, purpose, request_id
                  )
                  SELECT app_tenant_id(), actor.user_id, %s, %s, COALESCE(%s, 'all'), %s,
                    'allow', %s, %s, %s
                  FROM actor_row actor
                  RETURNING decision_id
                ),
                previous AS (
                  SELECT event_hash
                  FROM audit_logs
                  WHERE tenant_id = app_tenant_id()
                  ORDER BY created_at DESC, event_id DESC
                  LIMIT 1
                ),
                audit AS (
                  INSERT INTO audit_logs (
                    tenant_id, event_type, actor_id, actor_role, subject_id, purpose,
                    request_id, policy_decision_id, previous_hash, event_hash, payload,
                    app_mode, auth_assurance
                  )
                  SELECT
                    app_tenant_id(), %s, actor.user_id, %s, COALESCE(%s, 'all'), %s,
                    %s, policy.decision_id, previous.event_hash,
                    encode(digest(policy.decision_id::text || COALESCE(%s, 'all') || COALESCE(previous.event_hash, ''), 'sha256'), 'hex'),
                    jsonb_build_object('artifact_type', %s, 'count', jsonb_array_length(rows_json.data)),
                    %s, %s
                  FROM actor_row actor, policy, rows_json
                  LEFT JOIN previous ON true
                  RETURNING event_id
                )
                SELECT
                  rows_json.data AS {output_key},
                  policy.decision_id::text AS policy_decision_id,
                  audit.event_id::text AS audit_event_id
                FROM rows_json, policy, audit
                """
        with self.connector.connect() as connection:
            set_rls_session(connection, context)
            row = connection.execute(
                statement,
                (
                    context.actor_id,
                    context.actor_id,
                    artifact_type,
                    artifact_type,
                    decision.action,
                    table_name,
                    artifact_type,
                    decision.data_classification,
                    decision.reason,
                    context.purpose,
                    context.request_id,
                    event_type,
                    context.actor_role,
                    artifact_type,
                    context.purpose,
                    context.request_id,
                    artifact_type,
                    artifact_type,
                    context.app_mode,
                    context.auth_assurance,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise PilotFeatureUnavailableError(f"governance.{table_name}.unprovisioned_identity")
        return row

    def _invoice_claim_select_sql(self, where_clause: str) -> str:
        return f"""
            SELECT
              claim.claim_id::text,
              COALESCE(seller.external_business_id, seller.organization_id::text) AS seller_id,
              COALESCE(buyer.external_business_id, buyer.organization_id::text) AS buyer_id,
              COALESCE(financier.external_business_id, financier.organization_id::text) AS financier_id,
              claim.invoice_id,
              claim.invoice_hash,
              claim.invoice_identity_hash,
              claim.amount::text AS amount,
              claim.currency,
              claim.issue_date::text AS issue_date,
              claim.due_date::text AS due_date,
              claim.status::text,
              claim.idempotency_key,
              claim.review_status,
              claim.reviewer_id::text AS reviewer_id,
              claim.source_evidence_id::text AS source_evidence_id,
              claim.created_by::text AS created_by,
              claim.created_at::text AS created_at,
              claim.updated_at::text AS updated_at,
              claim.released_at::text AS released_at,
              claim.dispute_reason
            FROM invoice_claims claim
            JOIN organizations seller ON seller.organization_id = claim.seller_id
            JOIN organizations buyer ON buyer.organization_id = claim.buyer_id
            JOIN organizations financier ON financier.organization_id = claim.financier_id
            WHERE claim.tenant_id = app_tenant_id()
              AND {where_clause}
            LIMIT 1
            """

    def _invoice_claim_payload(
        self,
        row: dict[str, Any],
        policy_decision_id: str,
        audit_event_id: str | None,
    ) -> dict[str, Any]:
        amount = float(str(row["amount"]))
        amount_payload: int | float = int(amount) if amount.is_integer() else amount
        return {
            "claim_id": str(row["claim_id"]),
            "seller_id": str(row["seller_id"]),
            "buyer_id": str(row["buyer_id"]),
            "financier_id": str(row["financier_id"]),
            "invoice_id": row.get("invoice_id"),
            "invoice_hash": str(row["invoice_hash"]),
            "invoice_identity_hash": str(row["invoice_identity_hash"]),
            "amount": amount_payload,
            "currency": str(row["currency"]),
            "issue_date": row.get("issue_date"),
            "due_date": str(row["due_date"]),
            "status": str(row["status"]),
            "idempotency_key": row.get("idempotency_key"),
            "review_status": str(row["review_status"]),
            "reviewer_id": row.get("reviewer_id"),
            "source_evidence_id": row.get("source_evidence_id"),
            "created_by": str(row["created_by"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "released_at": row.get("released_at"),
            "dispute_reason": row.get("dispute_reason"),
            "policy_decision_id": policy_decision_id,
            "audit_event_id": audit_event_id,
            "advisory_notice": (
                f"{TRUST_NOTICE} Invoice claim registry is a control workflow; it does not confirm invoice authenticity, "
                "fraud, double financing, or financing approval; lender/human decision remains required."
            ),
        }

    def _runs_payload(self, kind: str, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "organization_id": str(row["organization_id"]),
            "period_key": row.get("period_key"),
            kind: self._json_list(row.get(kind)),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Analytics outputs are versioned decision-support artifacts tied to source periods and review status."
            ),
        }

    def _json_list(self, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, str):
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        if isinstance(value, list):
            return [dict(item) if isinstance(item, dict) else {"value": item} for item in value]
        return []

    def _consent_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "consent_id": str(row["consent_id"]),
            "subject_id": str(row["subject_id"]),
            "recipient_id": str(row["recipient_id"]),
            "scope": str(row["scope"]),
            "purpose": str(row["purpose"]),
            "legal_basis": str(row["legal_basis"]),
            "status": str(row["status"]),
            "expires_at": row.get("expires_at"),
            "revoked_at": row.get("revoked_at"),
            "version": int(row["version"]),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": TRUST_NOTICE,
        }

    def _evidence_upload_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        object_key = str(row["object_key"])
        if self.object_storage.is_configured:
            upload_url = self.object_storage.presign_put_url(object_key)
            object_storage_status = "configured"
            advisory_notice = (
                f"{TRUST_NOTICE} Upload URL is signed for configured S3/MinIO storage; malware scan must still complete before use."
            )
        else:
            upload_url = f"object-storage-not-configured://{object_key}"
            object_storage_status = "not_configured"
            advisory_notice = (
                f"{TRUST_NOTICE} Upload metadata is reserved in PostgreSQL; configure S3/MinIO before accepting real files."
            )
        return {
            "evidence_version_id": str(row["evidence_version_id"]),
            "evidence_document_id": str(row["evidence_document_id"]),
            "organization_id": str(row["organization_id"]),
            "period_key": row.get("period_key"),
            "document_type": row.get("document_type"),
            "file_name": row.get("file_name"),
            "content_type": row.get("content_type"),
            "byte_size": int(row["byte_size"]) if row.get("byte_size") is not None else None,
            "classification": row.get("classification"),
            "object_key": object_key,
            "upload_url": upload_url,
            "upload_method": "PUT",
            "expires_in_seconds": self.object_storage.upload_ttl_seconds,
            "object_storage_status": object_storage_status,
            "malware_scan_status": str(row["malware_scan_status"]),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": advisory_notice,
        }

    def _evidence_document_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "evidence_document_id": str(row["evidence_document_id"]),
            "organization_id": str(row["organization_id"]),
            "reporting_period_id": row.get("reporting_period_id"),
            "period_key": row.get("period_key"),
            "document_type": str(row["document_type"]),
            "title": str(row["title"]),
            "classification": str(row["classification"]),
            "retention_status": str(row["retention_status"]),
            "legal_hold": bool(row["legal_hold"]),
            "source_submission_id": row.get("source_submission_id"),
            "source_record_id": row.get("source_record_id"),
            "valid_from": row.get("valid_from"),
            "valid_to": row.get("valid_to"),
            "created_at": row.get("created_at"),
            "versions": self._public_evidence_versions(row.get("versions")),
            "active_grants": self._json_list(row.get("active_grants")),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Evidence reads are metadata-only and require owner, active consent, or active evidence grant policy."
            ),
        }

    def _public_evidence_versions(self, value: Any) -> list[dict[str, Any]]:
        versions = self._json_list(value)
        for version in versions:
            version.pop("object_key", None)
        return versions

    def _evidence_version_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        malware_scan_status = str(row["malware_scan_status"])
        return {
            "evidence_version_id": str(row["evidence_version_id"]),
            "evidence_document_id": str(row["evidence_document_id"]),
            "organization_id": str(row["organization_id"]),
            "object_key": str(row["object_key"]),
            "object_version": str(row["object_version"]),
            "document_hash": str(row["document_hash"]),
            "malware_scan_status": malware_scan_status,
            "usable": malware_scan_status == "clean",
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Evidence versions are append-only; clean malware scan is required before approval workflows can rely on this file."
            ),
        }

    def _evidence_scan_result_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        malware_scan_status = str(row["malware_scan_status"])
        return {
            "evidence_version_id": str(row["evidence_version_id"]),
            "evidence_document_id": str(row["evidence_document_id"]),
            "organization_id": str(row["organization_id"]),
            "object_key": str(row["object_key"]),
            "object_version": str(row["object_version"]),
            "document_hash": str(row["document_hash"]),
            "malware_scan_status": malware_scan_status,
            "retention_status": str(row["retention_status"]),
            "usable": malware_scan_status == "clean",
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Malware scan results control evidence usability; infected or failed scans stay out of approval workflows."
            ),
        }

    def _evidence_access_grant_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "grant_id": str(row["grant_id"]),
            "evidence_document_id": str(row["evidence_document_id"]),
            "organization_id": str(row["organization_id"]),
            "grantee_organization_id": str(row["grantee_organization_id"]),
            "scope": str(row["scope"]),
            "purpose": str(row["purpose"]),
            "status": str(row["status"]),
            "expires_at": row.get("expires_at"),
            "revoked_at": row.get("revoked_at"),
            "created_at": row.get("created_at"),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Evidence access is limited to the granted scope, purpose, expiry, and active policy checks."
            ),
        }

    def _evidence_retention_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "evidence_document_id": str(row["evidence_document_id"]),
            "organization_id": str(row["organization_id"]),
            "retention_status": str(row["retention_status"]),
            "legal_hold": bool(row["legal_hold"]),
            "valid_to": row.get("valid_to"),
            "policy_decision_id": str(row["policy_decision_id"]),
            "audit_event_id": str(row["audit_event_id"]),
            "advisory_notice": (
                f"{TRUST_NOTICE} Retention metadata does not delete object storage by itself; storage lifecycle enforcement must run separately."
            ),
        }


class PostgresPilotService:
    adapter_status = "pilot_boot_boundary"

    def __init__(
        self,
        database_url: str,
        app_mode: str,
        connector: PostgresConnectionFactory | Any | None = None,
        object_storage: ObjectStorageSettings | None = None,
    ) -> None:
        self.runtime = PostgresPilotRuntime(database_url=database_url, app_mode=app_mode)
        self.connector = connector or PostgresConnectionFactory(database_url)
        self.governance = PostgresPilotGovernanceService(self.runtime, self.connector, object_storage=object_storage)
        self.intake = PostgresPilotIntakeService(self.runtime, self.connector)
        self.audit = _UnsupportedPilotComponent("audit")

    def health_payload(self) -> dict[str, Any]:
        return self.runtime.status_payload()

    def __getattr__(self, method_name: str) -> Callable[..., Any]:
        def unavailable(*args: Any, **kwargs: Any) -> Any:
            raise PilotFeatureUnavailableError(f"service.{method_name}")

        return unavailable
