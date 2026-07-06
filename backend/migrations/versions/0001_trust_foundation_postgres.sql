-- VietSupply Radar trust foundation migration for PostgreSQL/PostGIS.
-- Alembic revision: 0001_trust_foundation_postgres
-- This migration is intentionally SQL-first so DB-level RLS can be reviewed.

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE period_type AS ENUM ('month');
CREATE TYPE submission_status AS ENUM ('draft', 'ready', 'in_review', 'changes_requested', 'approved', 'rejected', 'superseded');
CREATE TYPE consent_status AS ENUM ('granted', 'pending', 'revoked', 'expired');
CREATE TYPE policy_effect AS ENUM ('allow', 'deny');
CREATE TYPE invoice_claim_status AS ENUM ('registered', 'verified', 'pledged', 'financed', 'released', 'disputed');

CREATE TABLE tenants (
  tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_key text UNIQUE NOT NULL,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE organizations (
  organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  external_business_id text UNIQUE,
  name text NOT NULL,
  organization_type text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_accounts (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  external_subject text UNIQUE NOT NULL,
  email citext,
  display_name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE roles (
  role_id text PRIMARY KEY,
  description text NOT NULL
);

CREATE TABLE memberships (
  membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  user_id uuid NOT NULL REFERENCES user_accounts(user_id),
  role_id text NOT NULL REFERENCES roles(role_id),
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, user_id, role_id)
);

CREATE TABLE organization_relationships (
  relationship_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  source_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  target_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  relationship_type text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE business_profiles (
  profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  legal_name text NOT NULL,
  trade_name text NOT NULL,
  business_type text NOT NULL,
  industry text NOT NULL,
  product_category text NOT NULL,
  tax_registration_status text NOT NULL,
  scale text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id)
);

CREATE TABLE facilities (
  facility_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  facility_type text NOT NULL,
  province text NOT NULL,
  address text NOT NULL,
  location geography(Point, 4326) NOT NULL,
  status text NOT NULL DEFAULT 'active'
);

CREATE TABLE reporting_periods (
  reporting_period_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  period_type period_type NOT NULL DEFAULT 'month',
  period_key text NOT NULL CHECK (period_key ~ '^[0-9]{4}-[0-9]{2}$'),
  period_start date NOT NULL,
  period_end date NOT NULL,
  status text NOT NULL DEFAULT 'open',
  lock_version integer NOT NULL DEFAULT 1,
  UNIQUE (tenant_id, organization_id, period_type, period_key)
);

CREATE TABLE data_submissions (
  submission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid NOT NULL REFERENCES reporting_periods(reporting_period_id),
  source_type text NOT NULL CHECK (source_type IN ('manual', 'csv', 'seed')),
  status submission_status NOT NULL DEFAULT 'draft',
  version integer NOT NULL,
  submitted_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz,
  validated_at timestamptz,
  canonicalized_at timestamptz,
  locked_at timestamptz
);

CREATE TABLE submission_sections (
  section_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id uuid NOT NULL REFERENCES data_submissions(submission_id),
  section_name text NOT NULL,
  status text NOT NULL,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (submission_id, section_name)
);

CREATE TABLE validation_issues (
  issue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id uuid NOT NULL REFERENCES data_submissions(submission_id),
  section_name text NOT NULL,
  path text NOT NULL,
  row_number integer,
  column_name text,
  code text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
  message text NOT NULL,
  suggestion text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE review_tasks (
  review_task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id uuid NOT NULL REFERENCES data_submissions(submission_id),
  status text NOT NULL CHECK (status IN ('open', 'closed')) DEFAULT 'open',
  assigned_role text NOT NULL DEFAULT 'reviewer',
  assigned_to uuid REFERENCES user_accounts(user_id),
  assignment_reason text,
  assigned_at timestamptz,
  decided_by uuid REFERENCES user_accounts(user_id),
  decision text CHECK (decision IN ('approve', 'reject', 'request_changes')),
  decision_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

CREATE TABLE ingestion_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id uuid NOT NULL REFERENCES data_submissions(submission_id),
  dataset text NOT NULL CHECK (dataset IN ('financials', 'products', 'evidence')),
  source_type text NOT NULL CHECK (source_type IN ('csv')) DEFAULT 'csv',
  status text NOT NULL CHECK (status IN ('parsed', 'validated', 'quarantined')) DEFAULT 'parsed',
  checksum text NOT NULL,
  row_count integer NOT NULL CHECK (row_count >= 0),
  created_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ingestion_batch_replay_idx
  ON ingestion_batches (submission_id, dataset, checksum);

CREATE TABLE raw_file_objects (
  raw_file_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES ingestion_batches(batch_id),
  submission_id uuid NOT NULL REFERENCES data_submissions(submission_id),
  file_name text NOT NULL,
  object_key text NOT NULL,
  checksum text NOT NULL,
  content_type text NOT NULL DEFAULT 'text/csv',
  byte_size bigint NOT NULL CHECK (byte_size > 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw_records (
  raw_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES ingestion_batches(batch_id),
  raw_file_id uuid NOT NULL REFERENCES raw_file_objects(raw_file_id),
  row_number integer NOT NULL CHECK (row_number > 0),
  payload jsonb NOT NULL,
  normalized_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, row_number)
);

CREATE TABLE raw_record_errors (
  error_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_record_id uuid NOT NULL REFERENCES raw_records(raw_record_id),
  code text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
  message text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE financial_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid NOT NULL REFERENCES reporting_periods(reporting_period_id),
  statement_type text NOT NULL DEFAULT 'management',
  version integer NOT NULL,
  metrics jsonb NOT NULL,
  source_submission_id uuid NOT NULL REFERENCES data_submissions(submission_id),
  source_record_id text NOT NULL,
  valid_from date NOT NULL,
  valid_to date,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, reporting_period_id, statement_type, version)
);

CREATE TABLE product_capabilities (
  capability_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid NOT NULL REFERENCES reporting_periods(reporting_period_id),
  sku text NOT NULL,
  product_name text NOT NULL,
  category text NOT NULL,
  specification text,
  available_capacity numeric(18,2) NOT NULL DEFAULT 0,
  min_order_value numeric(18,2) NOT NULL DEFAULT 0,
  price_range text,
  certifications text,
  shelf_life_days integer,
  temperature_band text,
  packaging_type text,
  case_pack text,
  substitution_group text,
  version integer NOT NULL,
  source_submission_id uuid NOT NULL REFERENCES data_submissions(submission_id),
  source_record_id text NOT NULL,
  valid_from date NOT NULL,
  valid_to date,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, reporting_period_id, sku, version)
);

CREATE TABLE evidence_documents (
  evidence_document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid REFERENCES reporting_periods(reporting_period_id),
  document_type text NOT NULL,
  title text NOT NULL,
  classification text NOT NULL CHECK (classification IN ('public', 'partner_visible', 'confidential', 'restricted_financial')),
  retention_status text NOT NULL DEFAULT 'active',
  legal_hold boolean NOT NULL DEFAULT false,
  source_submission_id uuid REFERENCES data_submissions(submission_id),
  source_record_id text,
  valid_from date,
  valid_to date,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_versions (
  evidence_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_document_id uuid NOT NULL REFERENCES evidence_documents(evidence_document_id),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  object_key text NOT NULL,
  object_version text NOT NULL,
  document_hash text NOT NULL,
  content_type text NOT NULL,
  byte_size bigint NOT NULL CHECK (byte_size > 0),
  malware_scan_status text NOT NULL CHECK (malware_scan_status IN ('pending_scan', 'clean', 'infected', 'failed')),
  uploader_id uuid NOT NULL REFERENCES user_accounts(user_id),
  supersedes_version_id uuid REFERENCES evidence_versions(evidence_version_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_access_grants (
  grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  evidence_document_id uuid NOT NULL REFERENCES evidence_documents(evidence_document_id),
  subject_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  grantee_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  scope text NOT NULL,
  purpose text NOT NULL,
  status text NOT NULL CHECK (status IN ('active', 'revoked', 'expired')),
  expires_at timestamptz,
  revoked_at timestamptz,
  granted_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_object_access_logs (
  access_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  evidence_document_id uuid REFERENCES evidence_documents(evidence_document_id),
  evidence_version_id uuid REFERENCES evidence_versions(evidence_version_id),
  organization_id uuid REFERENCES organizations(organization_id),
  actor_id uuid NOT NULL REFERENCES user_accounts(user_id),
  access_type text NOT NULL CHECK (access_type IN ('metadata_read', 'download_ticket', 'download_denied', 'scan_worker', 'lifecycle_worker')),
  access_status text NOT NULL CHECK (access_status IN ('allowed', 'denied', 'executed', 'skipped')),
  purpose text NOT NULL,
  request_id text NOT NULL,
  policy_decision_id uuid REFERENCES policy_decisions(decision_id),
  object_storage_status text,
  object_key_hash text,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE consent_records (
  consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  actor_id uuid NOT NULL REFERENCES user_accounts(user_id),
  subject_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  recipient_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  scope text NOT NULL,
  purpose text NOT NULL,
  legal_basis text NOT NULL,
  status consent_status NOT NULL DEFAULT 'granted',
  expires_at timestamptz,
  revoked_at timestamptz,
  evidence_reference uuid REFERENCES evidence_documents(evidence_document_id),
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE policy_decisions (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  actor_id uuid NOT NULL REFERENCES user_accounts(user_id),
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text,
  data_classification text,
  effect policy_effect NOT NULL,
  reason text NOT NULL,
  purpose text NOT NULL,
  request_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  event_type text NOT NULL,
  actor_id uuid NOT NULL REFERENCES user_accounts(user_id),
  actor_role text NOT NULL,
  subject_id text NOT NULL,
  purpose text NOT NULL,
  request_id text NOT NULL,
  policy_decision_id uuid REFERENCES policy_decisions(decision_id),
  previous_hash text,
  event_hash text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  app_mode text NOT NULL,
  auth_assurance text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invoice_claims (
  claim_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  seller_id uuid NOT NULL REFERENCES organizations(organization_id),
  buyer_id uuid NOT NULL REFERENCES organizations(organization_id),
  financier_id uuid NOT NULL REFERENCES organizations(organization_id),
  invoice_id text,
  invoice_hash text NOT NULL,
  invoice_identity_hash text NOT NULL,
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  currency char(3) NOT NULL DEFAULT 'VND',
  issue_date date,
  due_date date NOT NULL,
  status invoice_claim_status NOT NULL DEFAULT 'registered',
  idempotency_key text,
  review_status text NOT NULL DEFAULT 'pending_review',
  reviewer_id uuid REFERENCES user_accounts(user_id),
  source_evidence_id uuid REFERENCES evidence_documents(evidence_document_id),
  created_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  released_at timestamptz,
  dispute_reason text
);

CREATE UNIQUE INDEX invoice_claim_idempotency_idx
  ON invoice_claims (tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX invoice_claim_active_financing_idx
  ON invoice_claims (tenant_id, invoice_identity_hash)
  WHERE status IN ('pledged', 'financed');

CREATE TABLE feature_snapshots (
  feature_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid NOT NULL REFERENCES reporting_periods(reporting_period_id),
  source_snapshot_id text,
  feature_set_version text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_runs (
  risk_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid NOT NULL REFERENCES reporting_periods(reporting_period_id),
  feature_snapshot_id uuid REFERENCES feature_snapshots(feature_snapshot_id),
  model_version text NOT NULL,
  ruleset_version text NOT NULL,
  score integer NOT NULL CHECK (score BETWEEN 0 AND 100),
  level text NOT NULL,
  explanation text NOT NULL,
  review_status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE match_runs (
  match_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  buyer_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid NOT NULL REFERENCES reporting_periods(reporting_period_id),
  disrupted_supplier_id uuid REFERENCES organizations(organization_id),
  product_category text NOT NULL,
  ruleset_version text NOT NULL,
  review_status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE match_candidates (
  candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_run_id uuid NOT NULL REFERENCES match_runs(match_run_id),
  supplier_organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  rank integer NOT NULL,
  score integer NOT NULL CHECK (score BETWEEN 0 AND 100),
  explanation jsonb NOT NULL,
  consent_status text NOT NULL DEFAULT 'not_requested'
);

CREATE TABLE model_registry (
  model_registry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  artifact_type text NOT NULL CHECK (artifact_type IN ('risk', 'matching', 'scenario', 'feature')),
  model_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
  approval_status text NOT NULL CHECK (approval_status IN ('pending_review', 'approved', 'rejected')),
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  checksum text NOT NULL,
  created_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, artifact_type, model_version)
);

CREATE TABLE ruleset_registry (
  ruleset_registry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  artifact_type text NOT NULL CHECK (artifact_type IN ('risk', 'matching', 'scenario', 'feature')),
  ruleset_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
  approval_status text NOT NULL CHECK (approval_status IN ('pending_review', 'approved', 'rejected')),
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  checksum text NOT NULL,
  created_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, artifact_type, ruleset_version)
);

CREATE TABLE scenario_runs (
  scenario_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid REFERENCES reporting_periods(reporting_period_id),
  input_snapshot_id uuid REFERENCES feature_snapshots(feature_snapshot_id),
  shock_organization_id uuid REFERENCES organizations(organization_id),
  product_category text,
  ruleset_version text NOT NULL,
  model_version text NOT NULL,
  payload jsonb NOT NULL,
  review_status text NOT NULL,
  created_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analytics_recompute_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id uuid REFERENCES reporting_periods(reporting_period_id),
  source_submission_id uuid REFERENCES data_submissions(submission_id),
  job_type text NOT NULL CHECK (job_type IN ('analytics_recompute')),
  status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter', 'skipped')),
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 3,
  last_error text,
  created_by uuid NOT NULL REFERENCES user_accounts(user_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  available_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE OR REPLACE FUNCTION app_try_uuid(raw_value text) RETURNS uuid
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF raw_value IS NULL OR raw_value = '' THEN
    RETURN NULL;
  END IF;
  RETURN raw_value::uuid;
EXCEPTION WHEN invalid_text_representation THEN
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION app_tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  WITH session_value AS (
    SELECT NULLIF(current_setting('app.tenant_id', true), '') AS raw_value
  )
  SELECT COALESCE(
    app_try_uuid((SELECT raw_value FROM session_value)),
    (
      SELECT tenants.tenant_id
      FROM tenants
      WHERE tenants.external_key = (SELECT raw_value FROM session_value)
      LIMIT 1
    )
  )
$$;

CREATE OR REPLACE FUNCTION app_actor_org_ids() RETURNS uuid[]
LANGUAGE sql STABLE AS $$
  WITH raw_values AS (
    SELECT trim(value) AS raw_value
    FROM regexp_split_to_table(COALESCE(NULLIF(current_setting('app.organization_ids', true), ''), ''), ',') AS value
    WHERE trim(value) <> ''
  )
  SELECT COALESCE(array_agg(DISTINCT organizations.organization_id), ARRAY[]::uuid[])
  FROM raw_values
  JOIN organizations
    ON organizations.tenant_id = app_tenant_id()
   AND (
     organizations.organization_id = app_try_uuid(raw_values.raw_value)
     OR organizations.external_business_id = raw_values.raw_value
   )
$$;

CREATE OR REPLACE FUNCTION app_is_member(org_id uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT org_id = ANY(app_actor_org_ids())
$$;

CREATE OR REPLACE FUNCTION app_has_active_consent(subject_org uuid, requested_scope text, requested_purpose text) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1
    FROM consent_records cr
    WHERE cr.tenant_id = app_tenant_id()
      AND cr.subject_organization_id = subject_org
      AND cr.recipient_organization_id = ANY(app_actor_org_ids())
      AND cr.scope = requested_scope
      AND cr.purpose = requested_purpose
      AND cr.status = 'granted'
      AND cr.revoked_at IS NULL
      AND (cr.expires_at IS NULL OR cr.expires_at > now())
  )
$$;

CREATE OR REPLACE FUNCTION app_has_active_evidence_grant(document_id uuid, requested_scope text, requested_purpose text) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1
    FROM evidence_access_grants grant_row
    WHERE grant_row.tenant_id = app_tenant_id()
      AND grant_row.evidence_document_id = document_id
      AND grant_row.grantee_organization_id = ANY(app_actor_org_ids())
      AND grant_row.scope = requested_scope
      AND grant_row.purpose = requested_purpose
      AND grant_row.status = 'active'
      AND grant_row.revoked_at IS NULL
      AND (grant_row.expires_at IS NULL OR grant_row.expires_at > now())
  )
$$;

CREATE OR REPLACE FUNCTION app_has_relationship(subject_org uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1
    FROM organization_relationships rel
    WHERE rel.tenant_id = app_tenant_id()
      AND rel.status = 'active'
      AND (
        rel.source_organization_id = subject_org AND rel.target_organization_id = ANY(app_actor_org_ids())
        OR rel.target_organization_id = subject_org AND rel.source_organization_id = ANY(app_actor_org_ids())
      )
  )
$$;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE facilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE reporting_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE submission_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_issues ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_file_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_record_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_access_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_object_access_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE ruleset_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE scenario_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_recompute_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_same_tenant ON tenants
  USING (tenant_id = app_tenant_id());

CREATE POLICY organizations_member_or_relationship ON organizations
  USING (tenant_id = app_tenant_id() AND (app_is_member(organization_id) OR app_has_relationship(organization_id)));

CREATE POLICY own_memberships ON memberships
  USING (tenant_id = app_tenant_id() AND app_is_member(organization_id));

CREATE POLICY profiles_member_or_relationship ON business_profiles
  USING (tenant_id = app_tenant_id() AND (app_is_member(organization_id) OR app_has_relationship(organization_id)));

CREATE POLICY periods_own_org ON reporting_periods
  USING (tenant_id = app_tenant_id() AND app_is_member(organization_id));

CREATE POLICY submissions_own_org ON data_submissions
  USING (tenant_id = app_tenant_id() AND app_is_member(organization_id))
  WITH CHECK (tenant_id = app_tenant_id() AND app_is_member(organization_id));

CREATE POLICY sections_via_submission ON submission_sections
  USING (EXISTS (
    SELECT 1 FROM data_submissions ds
    WHERE ds.submission_id = submission_sections.submission_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ));

CREATE POLICY validation_via_submission ON validation_issues
  USING (EXISTS (
    SELECT 1 FROM data_submissions ds
    WHERE ds.submission_id = validation_issues.submission_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ));

CREATE POLICY review_tasks_via_submission ON review_tasks
  USING (EXISTS (
    SELECT 1 FROM data_submissions ds
    WHERE ds.submission_id = review_tasks.submission_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM data_submissions ds
    WHERE ds.submission_id = review_tasks.submission_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ));

CREATE POLICY ingestion_batches_via_submission ON ingestion_batches
  USING (EXISTS (
    SELECT 1 FROM data_submissions ds
    WHERE ds.submission_id = ingestion_batches.submission_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ));

CREATE POLICY raw_files_via_submission ON raw_file_objects
  USING (EXISTS (
    SELECT 1 FROM data_submissions ds
    WHERE ds.submission_id = raw_file_objects.submission_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ));

CREATE POLICY raw_records_via_batch ON raw_records
  USING (EXISTS (
    SELECT 1
    FROM ingestion_batches batch
    JOIN data_submissions ds ON ds.submission_id = batch.submission_id
    WHERE batch.batch_id = raw_records.batch_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ));

CREATE POLICY raw_errors_via_record ON raw_record_errors
  USING (EXISTS (
    SELECT 1
    FROM raw_records record
    JOIN ingestion_batches batch ON batch.batch_id = record.batch_id
    JOIN data_submissions ds ON ds.submission_id = batch.submission_id
    WHERE record.raw_record_id = raw_record_errors.raw_record_id
      AND ds.tenant_id = app_tenant_id()
      AND app_is_member(ds.organization_id)
  ));

CREATE POLICY financials_consent_or_owner ON financial_snapshots
  USING (tenant_id = app_tenant_id() AND (app_is_member(organization_id) OR app_has_active_consent(organization_id, 'financial_summary', NULLIF(current_setting('app.purpose', true), ''))));

CREATE POLICY products_consent_or_owner ON product_capabilities
  USING (tenant_id = app_tenant_id() AND (app_is_member(organization_id) OR app_has_active_consent(organization_id, 'product_capability', NULLIF(current_setting('app.purpose', true), ''))));

CREATE POLICY evidence_consent_or_owner ON evidence_documents
  USING (
    tenant_id = app_tenant_id()
    AND (
      app_is_member(organization_id)
      OR app_has_active_consent(organization_id, 'evidence_review', NULLIF(current_setting('app.purpose', true), ''))
      OR app_has_active_evidence_grant(evidence_document_id, 'evidence_review', NULLIF(current_setting('app.purpose', true), ''))
    )
  );

CREATE POLICY evidence_versions_via_document ON evidence_versions
  USING (
    tenant_id = app_tenant_id()
    AND (
      app_is_member(organization_id)
      OR app_has_active_consent(organization_id, 'evidence_review', NULLIF(current_setting('app.purpose', true), ''))
      OR app_has_active_evidence_grant(evidence_document_id, 'evidence_review', NULLIF(current_setting('app.purpose', true), ''))
    )
  );

CREATE POLICY evidence_access_grants_subject_or_grantee ON evidence_access_grants
  USING (
    tenant_id = app_tenant_id()
    AND (
      app_is_member(subject_organization_id)
      OR app_is_member(grantee_organization_id)
    )
  )
  WITH CHECK (
    tenant_id = app_tenant_id()
    AND app_is_member(subject_organization_id)
  );

CREATE POLICY evidence_object_access_logs_tenant ON evidence_object_access_logs
  USING (tenant_id = app_tenant_id())
  WITH CHECK (tenant_id = app_tenant_id());

CREATE POLICY consent_subject_or_recipient ON consent_records
  USING (tenant_id = app_tenant_id() AND (app_is_member(subject_organization_id) OR app_is_member(recipient_organization_id)));

CREATE POLICY policy_decisions_actor_tenant ON policy_decisions
  USING (tenant_id = app_tenant_id());

CREATE POLICY audit_actor_tenant ON audit_logs
  USING (tenant_id = app_tenant_id());

CREATE POLICY invoice_claims_party_or_consent ON invoice_claims
  USING (
    tenant_id = app_tenant_id()
    AND (
      app_is_member(seller_id)
      OR app_is_member(buyer_id)
      OR app_is_member(financier_id)
      OR app_has_active_consent(seller_id, 'invoice_claim', NULLIF(current_setting('app.purpose', true), ''))
    )
  )
  WITH CHECK (
    tenant_id = app_tenant_id()
    AND (app_is_member(seller_id) OR app_has_active_consent(seller_id, 'invoice_claim', NULLIF(current_setting('app.purpose', true), '')))
  );

CREATE POLICY risk_runs_consent_or_owner ON risk_runs
  USING (tenant_id = app_tenant_id() AND (app_is_member(organization_id) OR app_has_active_consent(organization_id, 'financial_summary', NULLIF(current_setting('app.purpose', true), ''))));

CREATE POLICY feature_snapshots_consent_or_owner ON feature_snapshots
  USING (tenant_id = app_tenant_id() AND (app_is_member(organization_id) OR app_has_active_consent(organization_id, 'financial_summary', NULLIF(current_setting('app.purpose', true), ''))));

CREATE POLICY match_runs_owner ON match_runs
  USING (tenant_id = app_tenant_id() AND app_is_member(buyer_organization_id));

CREATE POLICY match_candidates_via_run ON match_candidates
  USING (EXISTS (
    SELECT 1 FROM match_runs mr
    WHERE mr.match_run_id = match_candidates.match_run_id
      AND mr.tenant_id = app_tenant_id()
      AND app_is_member(mr.buyer_organization_id)
  ));

CREATE POLICY model_registry_tenant ON model_registry
  USING (tenant_id = app_tenant_id())
  WITH CHECK (tenant_id = app_tenant_id());

CREATE POLICY ruleset_registry_tenant ON ruleset_registry
  USING (tenant_id = app_tenant_id())
  WITH CHECK (tenant_id = app_tenant_id());

CREATE POLICY scenario_runs_consent_or_owner ON scenario_runs
  USING (tenant_id = app_tenant_id() AND (app_is_member(organization_id) OR app_has_active_consent(organization_id, 'scenario_review', NULLIF(current_setting('app.purpose', true), ''))));

CREATE POLICY analytics_recompute_jobs_owner ON analytics_recompute_jobs
  USING (tenant_id = app_tenant_id() AND app_is_member(organization_id))
  WITH CHECK (tenant_id = app_tenant_id() AND app_is_member(organization_id));

CREATE OR REPLACE FUNCTION audit_logs_no_update_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_logs are append-only through the application role';
END;
$$;

CREATE TRIGGER audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION audit_logs_no_update_delete();

COMMIT;
