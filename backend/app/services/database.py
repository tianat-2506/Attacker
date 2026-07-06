from __future__ import annotations

import calendar
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.app.domain.invoice_verification import invoice_hash
from backend.app.services.data_loader import DATA_DIR, load_data


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = ROOT / "backend" / "app" / "data" / "vietsupply.db"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS businesses (
  business_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  industry TEXT NOT NULL,
  product_category TEXT NOT NULL,
  province TEXT NOT NULL,
  lat REAL NOT NULL,
  lng REAL NOT NULL,
  scale TEXT NOT NULL,
  monthly_revenue INTEGER NOT NULL,
  capacity INTEGER NOT NULL,
  financial_health_score INTEGER NOT NULL,
  supply_risk_score INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS supply_edges (
  edge_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES businesses(business_id),
  target_id TEXT NOT NULL REFERENCES businesses(business_id),
  product TEXT NOT NULL,
  product_category TEXT NOT NULL,
  monthly_volume INTEGER NOT NULL,
  lead_time_days INTEGER NOT NULL,
  transport_cost INTEGER NOT NULL,
  reliability REAL NOT NULL,
  payment_term_days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS financial_snapshots (
  business_id TEXT NOT NULL REFERENCES businesses(business_id),
  month TEXT NOT NULL,
  cash_in INTEGER NOT NULL,
  cash_out INTEGER NOT NULL,
  revenue INTEGER NOT NULL,
  debt INTEGER NOT NULL,
  accounts_receivable INTEGER NOT NULL,
  accounts_payable INTEGER NOT NULL,
  inventory_value INTEGER NOT NULL,
  late_payment_rate REAL NOT NULL,
  delivery_delay_rate REAL NOT NULL,
  PRIMARY KEY (business_id, month)
);

CREATE TABLE IF NOT EXISTS products (
  sku TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(business_id),
  product_name TEXT NOT NULL,
  category TEXT NOT NULL,
  specification TEXT NOT NULL,
  available_capacity INTEGER NOT NULL,
  min_order_value INTEGER NOT NULL,
  price_range TEXT NOT NULL,
  certifications TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_verifications (
  invoice_id TEXT PRIMARY KEY,
  seller_id TEXT NOT NULL REFERENCES businesses(business_id),
  buyer_id TEXT NOT NULL REFERENCES businesses(business_id),
  amount INTEGER NOT NULL,
  issue_date TEXT NOT NULL,
  due_date TEXT NOT NULL,
  invoice_hash TEXT NOT NULL,
  funding_status TEXT NOT NULL,
  confirmed_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
  contract_id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES businesses(business_id),
  buyer_id TEXT NOT NULL REFERENCES businesses(business_id),
  product_category TEXT NOT NULL,
  status TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  expiry_date TEXT NOT NULL,
  payment_term_days INTEGER NOT NULL,
  sla_lead_time_days INTEGER NOT NULL,
  has_exclusivity INTEGER NOT NULL,
  has_backup_supplier_clause INTEGER NOT NULL,
  verification_status TEXT NOT NULL,
  source_label TEXT NOT NULL,
  document_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL REFERENCES contracts(contract_id),
  supplier_id TEXT NOT NULL REFERENCES businesses(business_id),
  buyer_id TEXT NOT NULL REFERENCES businesses(business_id),
  sku TEXT NOT NULL,
  order_date TEXT NOT NULL,
  expected_delivery_date TEXT NOT NULL,
  actual_delivery_date TEXT,
  quantity INTEGER NOT NULL,
  value INTEGER NOT NULL,
  status TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  document_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_notes (
  delivery_note_id TEXT PRIMARY KEY,
  po_id TEXT NOT NULL REFERENCES purchase_orders(po_id),
  supplier_id TEXT NOT NULL REFERENCES businesses(business_id),
  buyer_id TEXT NOT NULL REFERENCES businesses(business_id),
  logistics_partner_id TEXT REFERENCES businesses(business_id),
  delivery_date TEXT NOT NULL,
  delivered_quantity INTEGER NOT NULL,
  delay_days INTEGER NOT NULL,
  verified_by_buyer INTEGER NOT NULL,
  logistics_confirmed INTEGER NOT NULL,
  status TEXT NOT NULL,
  document_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS certifications (
  certification_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL REFERENCES businesses(business_id),
  certification_type TEXT NOT NULL,
  issuer TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  expiry_date TEXT NOT NULL,
  status TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  document_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guarantees (
  guarantee_id TEXT PRIMARY KEY,
  applicant_id TEXT NOT NULL REFERENCES businesses(business_id),
  beneficiary_id TEXT NOT NULL REFERENCES businesses(business_id),
  issuer_id TEXT NOT NULL REFERENCES businesses(business_id),
  guarantee_type TEXT NOT NULL,
  amount INTEGER NOT NULL,
  effective_date TEXT NOT NULL,
  expiry_date TEXT NOT NULL,
  status TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  document_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connection_requests (
  request_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'tenant-demo',
  requester_id TEXT NOT NULL,
  buyer_id TEXT NOT NULL REFERENCES businesses(business_id),
  target_supplier_id TEXT NOT NULL REFERENCES businesses(business_id),
  disrupted_supplier_id TEXT REFERENCES businesses(business_id),
  purpose TEXT NOT NULL,
  status TEXT NOT NULL,
  consent_status TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by TEXT,
  decision_note TEXT,
  contract_evidence_id TEXT,
  relationship_id TEXT,
  relationship_edge_id TEXT,
  policy_decision_id TEXT,
  audit_event_id TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS supply_map_registrations (
  registration_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'tenant-demo',
  organization_id TEXT NOT NULL,
  organization_name TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  stakeholder_role TEXT NOT NULL,
  province TEXT NOT NULL,
  category TEXT NOT NULL,
  scale TEXT NOT NULL,
  contact_email TEXT NOT NULL,
  intended_relationships_json TEXT NOT NULL,
  data_boundary TEXT NOT NULL,
  status TEXT NOT NULL,
  review_status TEXT NOT NULL,
  map_visibility TEXT NOT NULL,
  linked_business_id TEXT,
  submitted_at TEXT NOT NULL,
  reviewed_at TEXT,
  reviewer_note TEXT,
  policy_decision_id TEXT,
  audit_event_id TEXT,
  advisory_notice TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consent_records (
  consent_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'tenant-demo',
  actor_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  recipient_id TEXT,
  scope TEXT NOT NULL,
  purpose TEXT NOT NULL,
  legal_basis TEXT,
  status TEXT NOT NULL,
  expires_at TEXT,
  revoked_at TEXT,
  evidence_reference TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
  event_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'tenant-demo',
  event_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  actor_role TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  purpose TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  request_id TEXT NOT NULL,
  policy_decision_id TEXT,
  previous_hash TEXT,
  event_hash TEXT,
  payload_json TEXT,
  app_mode TEXT NOT NULL DEFAULT 'demo',
  auth_assurance TEXT NOT NULL DEFAULT 'demo-header'
);

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
  organization_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  external_business_id TEXT UNIQUE REFERENCES businesses(business_id),
  name TEXT NOT NULL,
  organization_type TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
  role_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_accounts (
  user_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  email TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
  membership_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  user_id TEXT NOT NULL REFERENCES user_accounts(user_id),
  role_id TEXT NOT NULL REFERENCES roles(role_id),
  status TEXT NOT NULL,
  UNIQUE (organization_id, user_id, role_id)
);

CREATE TABLE IF NOT EXISTS organization_relationships (
  relationship_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  source_organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  target_organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  relationship_type TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visibility_policies (
  policy_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  role_id TEXT NOT NULL REFERENCES roles(role_id),
  data_classification TEXT NOT NULL,
  scope TEXT NOT NULL,
  effect TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS business_profiles (
  profile_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  legal_name TEXT NOT NULL,
  trade_name TEXT NOT NULL,
  business_type TEXT NOT NULL,
  industry TEXT NOT NULL,
  product_category TEXT NOT NULL,
  tax_registration_status TEXT NOT NULL,
  scale TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (organization_id)
);

CREATE TABLE IF NOT EXISTS facilities (
  facility_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  facility_type TEXT NOT NULL,
  province TEXT NOT NULL,
  address TEXT NOT NULL,
  lat REAL NOT NULL,
  lng REAL NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reporting_periods (
  reporting_period_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  period_type TEXT NOT NULL,
  period_key TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  status TEXT NOT NULL,
  lock_version INTEGER NOT NULL,
  UNIQUE (tenant_id, organization_id, period_type, period_key)
);

CREATE TABLE IF NOT EXISTS data_submissions (
  submission_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id TEXT NOT NULL REFERENCES reporting_periods(reporting_period_id),
  source_type TEXT NOT NULL,
  status TEXT NOT NULL,
  version INTEGER NOT NULL,
  submitted_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  submitted_at TEXT,
  validated_at TEXT,
  canonicalized_at TEXT,
  locked_at TEXT
);

CREATE TABLE IF NOT EXISTS submission_sections (
  section_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES data_submissions(submission_id),
  section_name TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (submission_id, section_name)
);

CREATE TABLE IF NOT EXISTS validation_issues (
  issue_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES data_submissions(submission_id),
  section_name TEXT NOT NULL,
  path TEXT NOT NULL,
  row_number INTEGER,
  column_name TEXT,
  code TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  suggestion TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_tasks (
  review_task_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES data_submissions(submission_id),
  status TEXT NOT NULL,
  assigned_role TEXT NOT NULL,
  assigned_to TEXT,
  assignment_reason TEXT,
  assigned_at TEXT,
  decided_by TEXT,
  decision TEXT,
  decision_note TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_batches (
  batch_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES data_submissions(submission_id),
  dataset TEXT NOT NULL,
  source_type TEXT NOT NULL,
  status TEXT NOT NULL,
  checksum TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (submission_id, dataset, checksum)
);

CREATE TABLE IF NOT EXISTS raw_file_objects (
  raw_file_id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES ingestion_batches(batch_id),
  submission_id TEXT NOT NULL REFERENCES data_submissions(submission_id),
  file_name TEXT NOT NULL,
  object_key TEXT NOT NULL,
  checksum TEXT NOT NULL,
  content_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (submission_id, checksum)
);

CREATE TABLE IF NOT EXISTS raw_records (
  raw_record_id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES ingestion_batches(batch_id),
  raw_file_id TEXT NOT NULL REFERENCES raw_file_objects(raw_file_id),
  row_number INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  normalized_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS raw_record_errors (
  error_id TEXT PRIMARY KEY,
  raw_record_id TEXT NOT NULL REFERENCES raw_records(raw_record_id),
  code TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS period_financial_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id TEXT NOT NULL REFERENCES reporting_periods(reporting_period_id),
  statement_type TEXT NOT NULL,
  version INTEGER NOT NULL,
  revenue INTEGER NOT NULL,
  cash_in INTEGER NOT NULL,
  cash_out INTEGER NOT NULL,
  debt INTEGER NOT NULL,
  accounts_receivable INTEGER NOT NULL,
  accounts_payable INTEGER NOT NULL,
  inventory_value INTEGER NOT NULL,
  late_payment_rate REAL NOT NULL,
  delivery_delay_rate REAL NOT NULL,
  source_submission_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (organization_id, reporting_period_id, statement_type, version)
);

CREATE TABLE IF NOT EXISTS product_capabilities (
  capability_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id TEXT NOT NULL REFERENCES reporting_periods(reporting_period_id),
  sku TEXT NOT NULL,
  product_name TEXT NOT NULL,
  category TEXT NOT NULL,
  specification TEXT NOT NULL,
  available_capacity INTEGER NOT NULL,
  min_order_value INTEGER NOT NULL,
  price_range TEXT NOT NULL,
  certifications TEXT NOT NULL,
  shelf_life_days INTEGER NOT NULL,
  temperature_band TEXT NOT NULL,
  packaging_type TEXT NOT NULL,
  case_pack TEXT NOT NULL,
  substitution_group TEXT NOT NULL,
  source_submission_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (organization_id, reporting_period_id, sku, source_submission_id)
);

CREATE TABLE IF NOT EXISTS evidence_documents (
  evidence_document_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id TEXT NOT NULL REFERENCES reporting_periods(reporting_period_id),
  document_type TEXT NOT NULL,
  title TEXT NOT NULL,
  object_key TEXT NOT NULL,
  object_version TEXT,
  document_hash TEXT NOT NULL,
  classification TEXT NOT NULL,
  content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  byte_size INTEGER NOT NULL DEFAULT 0,
  uploader_id TEXT,
  malware_scan_status TEXT NOT NULL,
  retention_status TEXT NOT NULL,
  legal_hold INTEGER NOT NULL DEFAULT 0,
  supersedes_document_id TEXT,
  source_submission_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS period_snapshots (
  period_snapshot_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  reporting_period_id TEXT NOT NULL REFERENCES reporting_periods(reporting_period_id),
  approved_submission_id TEXT NOT NULL REFERENCES data_submissions(submission_id),
  approved_version INTEGER NOT NULL,
  approved_at TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  source_submission_ids_json TEXT NOT NULL,
  UNIQUE (organization_id, reporting_period_id)
);

CREATE TABLE IF NOT EXISTS policy_decisions (
  decision_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  data_classification TEXT,
  effect TEXT NOT NULL,
  reason TEXT NOT NULL,
  purpose TEXT NOT NULL,
  request_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_versions (
  evidence_version_id TEXT PRIMARY KEY,
  evidence_document_id TEXT,
  tenant_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  period_key TEXT,
  document_type TEXT,
  file_name TEXT,
  classification TEXT,
  object_key TEXT NOT NULL,
  object_version TEXT NOT NULL,
  document_hash TEXT NOT NULL,
  content_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  malware_scan_status TEXT NOT NULL,
  retention_status TEXT NOT NULL,
  legal_hold INTEGER NOT NULL,
  uploader_id TEXT NOT NULL,
  supersedes_version_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_access_grants (
  grant_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  evidence_document_id TEXT NOT NULL,
  grantee_organization_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  purpose TEXT NOT NULL,
  status TEXT NOT NULL,
  expires_at TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS evidence_object_access_logs (
  access_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  evidence_document_id TEXT,
  evidence_version_id TEXT,
  organization_id TEXT,
  actor_id TEXT NOT NULL,
  access_type TEXT NOT NULL,
  access_status TEXT NOT NULL,
  purpose TEXT NOT NULL,
  request_id TEXT NOT NULL,
  policy_decision_id TEXT,
  object_storage_status TEXT,
  object_key_hash TEXT,
  reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_claims (
  claim_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  seller_id TEXT NOT NULL,
  buyer_id TEXT NOT NULL,
  financier_id TEXT NOT NULL,
  invoice_id TEXT,
  invoice_hash TEXT NOT NULL,
  invoice_identity_hash TEXT NOT NULL,
  amount INTEGER NOT NULL,
  currency TEXT NOT NULL,
  issue_date TEXT,
  due_date TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT,
  review_status TEXT NOT NULL,
  reviewer_id TEXT,
  source_evidence_id TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  released_at TEXT,
  dispute_reason TEXT
);

CREATE TABLE IF NOT EXISTS invoice_claim_events (
  event_id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES invoice_claims(claim_id),
  tenant_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_snapshots (
  feature_snapshot_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  reporting_period_id TEXT NOT NULL,
  source_snapshot_id TEXT,
  feature_set_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_runs (
  risk_run_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  reporting_period_id TEXT NOT NULL,
  feature_snapshot_id TEXT,
  model_version TEXT NOT NULL,
  ruleset_version TEXT NOT NULL,
  score INTEGER NOT NULL,
  level TEXT NOT NULL,
  explanation TEXT NOT NULL,
  review_status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_runs (
  match_run_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  buyer_organization_id TEXT NOT NULL,
  reporting_period_id TEXT NOT NULL,
  disrupted_supplier_id TEXT,
  product_category TEXT NOT NULL,
  ruleset_version TEXT NOT NULL,
  review_status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_candidates (
  candidate_id TEXT PRIMARY KEY,
  match_run_id TEXT NOT NULL REFERENCES match_runs(match_run_id),
  supplier_organization_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  score INTEGER NOT NULL,
  explanation_json TEXT NOT NULL,
  consent_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry (
  model_registry_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  model_version TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_status TEXT NOT NULL,
  config_json TEXT NOT NULL,
  checksum TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (tenant_id, artifact_type, model_version)
);

CREATE TABLE IF NOT EXISTS ruleset_registry (
  ruleset_registry_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  ruleset_version TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_status TEXT NOT NULL,
  config_json TEXT NOT NULL,
  checksum TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (tenant_id, artifact_type, ruleset_version)
);

CREATE TABLE IF NOT EXISTS scenario_runs (
  scenario_run_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  reporting_period_id TEXT,
  input_snapshot_id TEXT,
  shock_organization_id TEXT,
  product_category TEXT,
  ruleset_version TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT 'deterministic-demo-v0.1',
  payload_json TEXT NOT NULL,
  review_status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_recompute_jobs (
  job_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  reporting_period_id TEXT,
  source_submission_id TEXT,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  last_error TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  available_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON supply_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON supply_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_financial_business ON financial_snapshots(business_id, month);
CREATE INDEX IF NOT EXISTS idx_products_business ON products(business_id);
CREATE INDEX IF NOT EXISTS idx_invoices_parties ON invoice_verifications(seller_id, buyer_id);
CREATE INDEX IF NOT EXISTS idx_contracts_parties ON contracts(supplier_id, buyer_id);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_parties ON purchase_orders(supplier_id, buyer_id);
CREATE INDEX IF NOT EXISTS idx_delivery_notes_po ON delivery_notes(po_id);
CREATE INDEX IF NOT EXISTS idx_certifications_business ON certifications(business_id);
CREATE INDEX IF NOT EXISTS idx_guarantees_parties ON guarantees(applicant_id, beneficiary_id);
CREATE INDEX IF NOT EXISTS idx_connection_requests_buyer ON connection_requests(buyer_id, requested_at);
CREATE INDEX IF NOT EXISTS idx_reporting_period_lookup ON reporting_periods(tenant_id, organization_id, period_key);
CREATE INDEX IF NOT EXISTS idx_data_submissions_period ON data_submissions(organization_id, reporting_period_id, status);
CREATE INDEX IF NOT EXISTS idx_validation_submission ON validation_issues(submission_id, severity);
CREATE INDEX IF NOT EXISTS idx_period_financial_period ON period_financial_snapshots(organization_id, reporting_period_id);
CREATE INDEX IF NOT EXISTS idx_product_capability_period ON product_capabilities(organization_id, reporting_period_id);
CREATE INDEX IF NOT EXISTS idx_evidence_period ON evidence_documents(organization_id, reporting_period_id);
CREATE INDEX IF NOT EXISTS idx_policy_decisions_request ON policy_decisions(request_id, actor_id);
CREATE INDEX IF NOT EXISTS idx_supply_map_registrations_tenant_status ON supply_map_registrations(tenant_id, status, submitted_at);
CREATE INDEX IF NOT EXISTS idx_supply_map_registrations_org ON supply_map_registrations(tenant_id, organization_id, submitted_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_claim_idempotency ON invoice_claims(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_claim_active_financing ON invoice_claims(tenant_id, invoice_identity_hash) WHERE status IN ('pledged', 'financed');
CREATE INDEX IF NOT EXISTS idx_risk_runs_period ON risk_runs(organization_id, reporting_period_id, created_at);
CREATE INDEX IF NOT EXISTS idx_match_runs_period ON match_runs(buyer_organization_id, reporting_period_id, created_at);
CREATE INDEX IF NOT EXISTS idx_recompute_jobs_status ON analytics_recompute_jobs(status, available_at, created_at);
"""


class Database:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(SCHEMA_SQL)
            self._apply_sqlite_migrations(connection)
            connection.commit()

    def has_seed_data(self) -> bool:
        self.initialize()
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM businesses").fetchone()
            return bool(row and row["count"])

    def seed_from_csv(self, data_dir: Path = DATA_DIR, reset: bool = False) -> None:
        self.initialize()
        data = load_data(data_dir)
        with closing(self.connect()) as connection:
            if reset:
                self._delete_seed_data(connection)
            elif connection.execute("SELECT COUNT(*) AS count FROM businesses").fetchone()["count"]:
                self._seed_supply_map_registration_records(connection)
                self._seed_intake_records(connection)
                connection.commit()
                return

            connection.executemany(
                """
                INSERT INTO businesses (
                  business_id, name, type, industry, product_category, province, lat, lng, scale,
                  monthly_revenue, capacity, financial_health_score, supply_risk_score
                )
                VALUES (
                  :business_id, :name, :type, :industry, :product_category, :province, :lat, :lng, :scale,
                  :monthly_revenue, :capacity, :financial_health_score, :supply_risk_score
                )
                """,
                data["business_list"],
            )
            connection.executemany(
                """
                INSERT INTO supply_edges (
                  edge_id, source_id, target_id, product, product_category, monthly_volume,
                  lead_time_days, transport_cost, reliability, payment_term_days
                )
                VALUES (
                  :edge_id, :source_id, :target_id, :product, :product_category, :monthly_volume,
                  :lead_time_days, :transport_cost, :reliability, :payment_term_days
                )
                """,
                data["edges"],
            )
            connection.executemany(
                """
                INSERT INTO financial_snapshots (
                  business_id, month, cash_in, cash_out, revenue, debt, accounts_receivable,
                  accounts_payable, inventory_value, late_payment_rate, delivery_delay_rate
                )
                VALUES (
                  :business_id, :month, :cash_in, :cash_out, :revenue, :debt, :accounts_receivable,
                  :accounts_payable, :inventory_value, :late_payment_rate, :delivery_delay_rate
                )
                """,
                data["financials"],
            )
            connection.executemany(
                """
                INSERT INTO products (
                  sku, business_id, product_name, category, specification, available_capacity,
                  min_order_value, price_range, certifications
                )
                VALUES (
                  :sku, :business_id, :product_name, :category, :specification, :available_capacity,
                  :min_order_value, :price_range, :certifications
                )
                """,
                data["products"],
            )
            invoices = [self._normalized_invoice(row) for row in data["invoices"]]
            connection.executemany(
                """
                INSERT INTO invoice_verifications (
                  invoice_id, seller_id, buyer_id, amount, issue_date, due_date,
                  invoice_hash, funding_status, confirmed_by
                )
                VALUES (
                  :invoice_id, :seller_id, :buyer_id, :amount, :issue_date, :due_date,
                  :invoice_hash, :funding_status, :confirmed_by
                )
                """,
                invoices,
            )
            connection.executemany(
                """
                INSERT INTO contracts (
                  contract_id, supplier_id, buyer_id, product_category, status, effective_date,
                  expiry_date, payment_term_days, sla_lead_time_days, has_exclusivity,
                  has_backup_supplier_clause, verification_status, source_label, document_hash
                )
                VALUES (
                  :contract_id, :supplier_id, :buyer_id, :product_category, :status, :effective_date,
                  :expiry_date, :payment_term_days, :sla_lead_time_days, :has_exclusivity,
                  :has_backup_supplier_clause, :verification_status, :source_label, :document_hash
                )
                """,
                data["contracts"],
            )
            connection.executemany(
                """
                INSERT INTO purchase_orders (
                  po_id, contract_id, supplier_id, buyer_id, sku, order_date,
                  expected_delivery_date, actual_delivery_date, quantity, value,
                  status, verification_status, document_hash
                )
                VALUES (
                  :po_id, :contract_id, :supplier_id, :buyer_id, :sku, :order_date,
                  :expected_delivery_date, :actual_delivery_date, :quantity, :value,
                  :status, :verification_status, :document_hash
                )
                """,
                data["purchase_orders"],
            )
            connection.executemany(
                """
                INSERT INTO delivery_notes (
                  delivery_note_id, po_id, supplier_id, buyer_id, logistics_partner_id,
                  delivery_date, delivered_quantity, delay_days, verified_by_buyer,
                  logistics_confirmed, status, document_hash
                )
                VALUES (
                  :delivery_note_id, :po_id, :supplier_id, :buyer_id, :logistics_partner_id,
                  :delivery_date, :delivered_quantity, :delay_days, :verified_by_buyer,
                  :logistics_confirmed, :status, :document_hash
                )
                """,
                data["delivery_notes"],
            )
            connection.executemany(
                """
                INSERT INTO certifications (
                  certification_id, business_id, certification_type, issuer, effective_date,
                  expiry_date, status, verification_status, document_hash
                )
                VALUES (
                  :certification_id, :business_id, :certification_type, :issuer, :effective_date,
                  :expiry_date, :status, :verification_status, :document_hash
                )
                """,
                data["certifications"],
            )
            connection.executemany(
                """
                INSERT INTO guarantees (
                  guarantee_id, applicant_id, beneficiary_id, issuer_id, guarantee_type,
                  amount, effective_date, expiry_date, status, verification_status, document_hash
                )
                VALUES (
                  :guarantee_id, :applicant_id, :beneficiary_id, :issuer_id, :guarantee_type,
                  :amount, :effective_date, :expiry_date, :status, :verification_status, :document_hash
                )
                """,
                data["guarantees"],
            )
            self._seed_governance_records(connection)
            self._seed_supply_map_registration_records(connection)
            self._seed_intake_records(connection)
            connection.commit()

    def _delete_seed_data(self, connection: sqlite3.Connection) -> None:
        for table in [
            "scenario_runs",
            "analytics_recompute_jobs",
            "ruleset_registry",
            "model_registry",
            "match_candidates",
            "match_runs",
            "risk_runs",
            "feature_snapshots",
            "invoice_claim_events",
            "invoice_claims",
            "evidence_object_access_logs",
            "evidence_access_grants",
            "evidence_versions",
            "policy_decisions",
            "period_snapshots",
            "evidence_documents",
            "product_capabilities",
            "period_financial_snapshots",
            "raw_record_errors",
            "raw_records",
            "raw_file_objects",
            "ingestion_batches",
            "review_tasks",
            "validation_issues",
            "submission_sections",
            "data_submissions",
            "reporting_periods",
            "facilities",
            "business_profiles",
            "visibility_policies",
            "organization_relationships",
            "memberships",
            "user_accounts",
            "roles",
            "organizations",
            "tenants",
            "audit_logs",
            "consent_records",
            "supply_map_registrations",
            "connection_requests",
            "guarantees",
            "certifications",
            "delivery_notes",
            "purchase_orders",
            "contracts",
            "invoice_verifications",
            "products",
            "financial_snapshots",
            "supply_edges",
            "businesses",
        ]:
            connection.execute(f"DELETE FROM {table}")

    def _apply_sqlite_migrations(self, connection: sqlite3.Connection) -> None:
        def columns(table: str) -> set[str]:
            return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}

        def add_column(table: str, name: str, definition: str) -> None:
            if name not in columns(table):
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

        for name, definition in [
            ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant-demo'"),
            ("recipient_id", "TEXT"),
            ("legal_basis", "TEXT"),
            ("evidence_reference", "TEXT"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("created_at", "TEXT NOT NULL DEFAULT ''"),
            ("updated_at", "TEXT NOT NULL DEFAULT ''"),
        ]:
            add_column("consent_records", name, definition)

        for name, definition in [
            ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant-demo'"),
            ("policy_decision_id", "TEXT"),
            ("previous_hash", "TEXT"),
            ("event_hash", "TEXT"),
            ("payload_json", "TEXT"),
            ("app_mode", "TEXT NOT NULL DEFAULT 'demo'"),
            ("auth_assurance", "TEXT NOT NULL DEFAULT 'demo-header'"),
        ]:
            add_column("audit_logs", name, definition)

        for name, definition in [
            ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant-demo'"),
            ("decided_by", "TEXT"),
            ("decision_note", "TEXT"),
            ("contract_evidence_id", "TEXT"),
            ("relationship_id", "TEXT"),
            ("relationship_edge_id", "TEXT"),
            ("policy_decision_id", "TEXT"),
            ("audit_event_id", "TEXT"),
            ("updated_at", "TEXT"),
        ]:
            add_column("connection_requests", name, definition)

        for name, definition in [
            ("object_version", "TEXT"),
            ("content_type", "TEXT NOT NULL DEFAULT 'application/octet-stream'"),
            ("byte_size", "INTEGER NOT NULL DEFAULT 0"),
            ("uploader_id", "TEXT"),
            ("legal_hold", "INTEGER NOT NULL DEFAULT 0"),
            ("supersedes_document_id", "TEXT"),
        ]:
            add_column("evidence_documents", name, definition)

        for name, definition in [
            ("assigned_to", "TEXT"),
            ("assignment_reason", "TEXT"),
            ("assigned_at", "TEXT"),
        ]:
            add_column("review_tasks", name, definition)

        for name, definition in [
            ("period_key", "TEXT"),
            ("document_type", "TEXT"),
            ("file_name", "TEXT"),
            ("classification", "TEXT"),
        ]:
            add_column("evidence_versions", name, definition)

        for name, definition in [
            ("shock_organization_id", "TEXT"),
            ("product_category", "TEXT"),
            ("model_version", "TEXT NOT NULL DEFAULT 'deterministic-demo-v0.1'"),
        ]:
            add_column("scenario_runs", name, definition)

    def _normalized_invoice(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        if normalized.get("invoice_hash") == "generated-by-domain-module":
            normalized["invoice_hash"] = invoice_hash(normalized)
        return normalized

    def _seed_supply_map_registration_records(self, connection: sqlite3.Connection) -> None:
        rows: Iterable[dict[str, Any]] = [
            {
                "registration_id": "REG-BIZ-009",
                "tenant_id": "tenant-demo",
                "organization_id": "BIZ-009",
                "organization_name": "Thu Duc Retail Mart",
                "requested_by": "sme-biz-009",
                "stakeholder_role": "retailer",
                "province": "TP.HCM",
                "category": "beverage",
                "scale": "SME",
                "contact_email": "sme-biz-009@demo.vietsupply.local",
                "intended_relationships_json": json.dumps(["buyer_profile", "supplier_shortlist"]),
                "data_boundary": "masked profile, product demand, evidence metadata",
                "status": "approved",
                "review_status": "approved",
                "map_visibility": "visible_demo_node",
                "linked_business_id": "BIZ-009",
                "submitted_at": "2026-06-01T09:00:00.000Z",
                "reviewed_at": "2026-06-01T11:00:00.000Z",
                "reviewer_note": "Approved demo membership; commercial graph access remains consent-gated.",
                "advisory_notice": "Demo onboarding record; not KYB or legal verification.",
            },
            {
                "registration_id": "REG-BIZ-005",
                "tenant_id": "tenant-demo",
                "organization_id": "BIZ-005",
                "organization_name": "Dai Tin Distribution",
                "requested_by": "supplier-admin-005",
                "stakeholder_role": "distributor",
                "province": "Binh Duong",
                "category": "beverage",
                "scale": "Distributor",
                "contact_email": "supplier-admin-005@demo.vietsupply.local",
                "intended_relationships_json": json.dumps(["supply_relationship", "evidence_sharing"]),
                "data_boundary": "masked profile, product capability, certifications",
                "status": "submitted",
                "review_status": "in_review",
                "map_visibility": "masked_pending_consent",
                "linked_business_id": "BIZ-005",
                "submitted_at": "2026-06-18T08:30:00.000Z",
                "reviewed_at": None,
                "reviewer_note": None,
                "advisory_notice": "Pending review; no unmasked relationship data is opened.",
            },
            {
                "registration_id": "REG-BIZ-062",
                "tenant_id": "tenant-demo",
                "organization_id": "BIZ-062",
                "organization_name": "Saigon Invoice Finance",
                "requested_by": "lender-062",
                "stakeholder_role": "financial_partner",
                "province": "TP.HCM",
                "category": "finance",
                "scale": "Finance partner",
                "contact_email": "lender-062@demo.vietsupply.local",
                "intended_relationships_json": json.dumps(["invoice_review", "consented_finance_signals"]),
                "data_boundary": "invoice registry signals, no automatic lending decision",
                "status": "changes_requested",
                "review_status": "changes_requested",
                "map_visibility": "masked_pending_consent",
                "linked_business_id": "BIZ-062",
                "submitted_at": "2026-06-20T13:15:00.000Z",
                "reviewed_at": "2026-06-21T10:20:00.000Z",
                "reviewer_note": "Add consent scope and lender human-approval terms before enabling graph access.",
                "advisory_notice": "Finance partner onboarding remains review-gated.",
            },
        ]
        connection.executemany(
            """
            INSERT OR IGNORE INTO supply_map_registrations (
              registration_id, tenant_id, organization_id, organization_name, requested_by,
              stakeholder_role, province, category, scale, contact_email, intended_relationships_json,
              data_boundary, status, review_status, map_visibility, linked_business_id,
              submitted_at, reviewed_at, reviewer_note, advisory_notice
            )
            VALUES (
              :registration_id, :tenant_id, :organization_id, :organization_name, :requested_by,
              :stakeholder_role, :province, :category, :scale, :contact_email,
              :intended_relationships_json, :data_boundary, :status, :review_status,
              :map_visibility, :linked_business_id, :submitted_at, :reviewed_at,
              :reviewer_note, :advisory_notice
            )
            """,
            rows,
        )

    def _seed_governance_records(self, connection: sqlite3.Connection) -> None:
        consent_rows: Iterable[tuple[str, str, str, str, str, str, str | None, str | None]] = [
            (
                "CONS-001",
                "BIZ-009",
                "BIZ-009",
                "financial_summary",
                "working_capital_review",
                "granted",
                "2026-12-31T23:59:59Z",
                None,
            ),
            (
                "CONS-002",
                "BIZ-007",
                "BIZ-009",
                "supplier_intro",
                "alternative_supplier_review",
                "pending",
                "2026-12-31T23:59:59Z",
                None,
            ),
        ]
        connection.executemany(
            """
            INSERT INTO consent_records (
              consent_id, actor_id, subject_id, scope, purpose, status, expires_at, revoked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            consent_rows,
        )
        connection.execute(
            """
            INSERT INTO connection_requests (
              request_id, requester_id, buyer_id, target_supplier_id, disrupted_supplier_id,
              purpose, status, consent_status, requested_at, decided_at
            )
            VALUES (
              'REQ-DEMO-001', 'demo-user', 'BIZ-009', 'BIZ-007', 'BIZ-005',
              'alternative_supplier_review', 'pending', 'awaiting_supplier_consent',
              datetime('now', '-1 day'), NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO audit_logs (
              event_id, event_type, actor_id, actor_role, subject_id, purpose, timestamp, request_id
            )
            VALUES (
              'AUD-001', 'DATABASE_SEEDED', 'system', 'system', 'demo',
              'demo_bootstrap', datetime('now'), 'seed'
            )
            """
        )

    def _seed_intake_records(self, connection: sqlite3.Connection) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        connection.execute(
            "INSERT OR IGNORE INTO tenants (tenant_id, name, status) VALUES (?, ?, ?)",
            ("tenant-demo", "VietSupply Demo Tenant", "active"),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO roles (role_id, name, description) VALUES (?, ?, ?)",
            [
                ("demo_operator", "Demo Operator", "Can run synthetic intake and review flows."),
                ("sme_user", "SME User", "Can draft and submit own organization data."),
                ("sme_submitter", "SME Submitter", "Can draft and submit own organization period data."),
                ("org_admin", "Organization Admin", "Can manage own organization data and consent."),
                ("buyer_admin", "Buyer Admin", "Can review masked supplier options and request introductions for the buyer organization."),
                ("supplier_admin", "Supplier Admin", "Can manage supplier profile, product capability, intake and evidence."),
                ("reviewer", "Reviewer", "Can approve period submissions in the demo."),
                ("network_analyst", "Network Analyst", "Can inspect masked commercial graph signals."),
                ("lender", "Lender", "Can review finance artifacts and invoice claims with consent."),
                ("system_admin", "System Admin", "Can administer platform trust controls."),
            ],
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO user_accounts (user_id, tenant_id, email, display_name, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("demo-user", "tenant-demo", "demo@vietsupply.local", "Nguyen Minh", "active"),
        )
        businesses = connection.execute("SELECT * FROM businesses ORDER BY business_id").fetchall()
        for business in businesses:
            business_id = business["business_id"]
            existing_organization = connection.execute(
                "SELECT organization_id FROM organizations WHERE external_business_id = ?",
                (business_id,),
            ).fetchone()
            organization_id = existing_organization["organization_id"] if existing_organization else business_id
            connection.execute(
                """
                INSERT OR IGNORE INTO organizations (
                  organization_id, tenant_id, external_business_id, name, organization_type, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (organization_id, "tenant-demo", business_id, business["name"], business["type"], "active"),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO business_profiles (
                  profile_id, tenant_id, organization_id, legal_name, trade_name, business_type,
                  industry, product_category, tax_registration_status, scale, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"PROF-{organization_id}",
                    "tenant-demo",
                    organization_id,
                    business["name"],
                    business["name"],
                    business["type"],
                    business["industry"],
                    business["product_category"],
                    "synthetic_verified",
                    business["scale"],
                    "active",
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO facilities (
                  facility_id, tenant_id, organization_id, facility_type, province, address, lat, lng, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"FAC-{organization_id}",
                    "tenant-demo",
                    organization_id,
                    business["type"],
                    business["province"],
                    f"Synthetic {business['province']} operating site",
                    business["lat"],
                    business["lng"],
                    "active",
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO memberships (
                  membership_id, tenant_id, organization_id, user_id, role_id, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"MEM-{organization_id}-DEMO", "tenant-demo", organization_id, "demo-user", "demo_operator", "active"),
            )

        edge_rows = connection.execute("SELECT * FROM supply_edges ORDER BY edge_id").fetchall()
        for edge in edge_rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO organization_relationships (
                  relationship_id, tenant_id, source_organization_id, target_organization_id,
                  relationship_type, status
                )
                VALUES (?, 'tenant-demo', ?, ?, 'supply', 'active')
                """,
                (f"REL-{edge['edge_id']}", edge["source_id"], edge["target_id"]),
            )

        financial_rows = connection.execute("SELECT * FROM financial_snapshots ORDER BY business_id, month").fetchall()
        for row in financial_rows:
            period_id, start, end = self._period_identity(row["business_id"], row["month"])
            connection.execute(
                """
                INSERT OR IGNORE INTO reporting_periods (
                  reporting_period_id, tenant_id, organization_id, period_type, period_key,
                  period_start, period_end, status, lock_version
                )
                VALUES (?, ?, ?, 'month', ?, ?, ?, 'approved', 1)
                """,
                (period_id, "tenant-demo", row["business_id"], row["month"], start, end),
            )
            submission_id = f"SUB-SEED-{row['business_id']}-{row['month']}"
            connection.execute(
                """
                INSERT OR IGNORE INTO data_submissions (
                  submission_id, tenant_id, organization_id, reporting_period_id, source_type, status,
                  version, submitted_by, created_at, updated_at, submitted_at, validated_at,
                  canonicalized_at, locked_at
                )
                VALUES (?, ?, ?, ?, 'seed', 'approved', 1, 'system', ?, ?, ?, ?, ?, ?)
                """,
                (submission_id, "tenant-demo", row["business_id"], period_id, now, now, now, now, now, now),
            )
            financial_payload = json.dumps(
                {
                    "revenue": row["revenue"],
                    "cash_in": row["cash_in"],
                    "cash_out": row["cash_out"],
                    "debt": row["debt"],
                    "accounts_receivable": row["accounts_receivable"],
                    "accounts_payable": row["accounts_payable"],
                    "inventory_value": row["inventory_value"],
                    "late_payment_rate": row["late_payment_rate"],
                    "delivery_delay_rate": row["delivery_delay_rate"],
                },
                sort_keys=True,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO submission_sections (
                  section_id, submission_id, section_name, status, payload_json, updated_at
                )
                VALUES (?, ?, 'financials', 'approved', ?, ?)
                """,
                (f"SEC-{submission_id}-FIN", submission_id, financial_payload, now),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO period_financial_snapshots (
                  snapshot_id, tenant_id, organization_id, reporting_period_id, statement_type,
                  version, revenue, cash_in, cash_out, debt, accounts_receivable, accounts_payable,
                  inventory_value, late_payment_rate, delivery_delay_rate, source_submission_id,
                  source_record_id, valid_from, valid_to, created_at
                )
                VALUES (?, ?, ?, ?, 'management', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    f"PFS-{row['business_id']}-{row['month']}",
                    "tenant-demo",
                    row["business_id"],
                    period_id,
                    row["revenue"],
                    row["cash_in"],
                    row["cash_out"],
                    row["debt"],
                    row["accounts_receivable"],
                    row["accounts_payable"],
                    row["inventory_value"],
                    row["late_payment_rate"],
                    row["delivery_delay_rate"],
                    submission_id,
                    f"SEED-FIN-{row['business_id']}-{row['month']}",
                    start,
                    now,
                ),
            )
            summary = {
                "financials": {
                    "status": "approved",
                    "revenue": row["revenue"],
                    "cash_in": row["cash_in"],
                    "cash_out": row["cash_out"],
                },
                "products": {"status": "seed_reference"},
                "evidence": {"status": "seed_reference"},
            }
            connection.execute(
                """
                INSERT OR IGNORE INTO period_snapshots (
                  period_snapshot_id, tenant_id, organization_id, reporting_period_id,
                  approved_submission_id, approved_version, approved_at, summary_json, source_submission_ids_json
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    f"PS-{row['business_id']}-{row['month']}",
                    "tenant-demo",
                    row["business_id"],
                    period_id,
                    submission_id,
                    now,
                    json.dumps(summary, sort_keys=True),
                    json.dumps([submission_id]),
                ),
            )

        latest_period_by_business = {
            item["business_id"]: item["month"]
            for item in connection.execute(
                """
                SELECT business_id, MAX(month) AS month
                FROM financial_snapshots
                GROUP BY business_id
                """
            ).fetchall()
        }
        product_rows = connection.execute("SELECT * FROM products ORDER BY business_id, sku").fetchall()
        for row in product_rows:
            period_key = latest_period_by_business.get(row["business_id"])
            if not period_key:
                continue
            period_id, start, _ = self._period_identity(row["business_id"], period_key)
            submission_id = f"SUB-SEED-{row['business_id']}-{period_key}"
            connection.execute(
                """
                INSERT OR IGNORE INTO product_capabilities (
                  capability_id, tenant_id, organization_id, reporting_period_id, sku, product_name,
                  category, specification, available_capacity, min_order_value, price_range,
                  certifications, shelf_life_days, temperature_band, packaging_type, case_pack,
                  substitution_group, source_submission_id, source_record_id, valid_from, valid_to, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 180, 'ambient', 'case', 'standard',
                  ?, ?, ?, ?, NULL, ?)
                """,
                (
                    f"PC-{row['business_id']}-{row['sku']}-{period_key}",
                    "tenant-demo",
                    row["business_id"],
                    period_id,
                    row["sku"],
                    row["product_name"],
                    row["category"],
                    row["specification"],
                    row["available_capacity"],
                    row["min_order_value"],
                    row["price_range"],
                    row["certifications"],
                    row["category"],
                    submission_id,
                    f"SEED-PROD-{row['sku']}",
                    start,
                    now,
                ),
            )

    def _period_identity(self, organization_id: str, period_key: str) -> tuple[str, str, str]:
        year_text, month_text = period_key.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
        last_day = calendar.monthrange(year, month)[1]
        return (
            f"PER-{organization_id}-{period_key}",
            f"{period_key}-01",
            f"{period_key}-{last_day:02d}",
        )


def ensure_database(path: Path | str = DEFAULT_DB_PATH, reset: bool = False) -> Database:
    database = Database(path)
    database.seed_from_csv(reset=reset)
    return database
