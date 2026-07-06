from __future__ import annotations

import argparse
import json
import shutil
import sys
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.access_control import AccessDeniedError, JwtVerificationError, context_from_headers, issue_dev_jwt
from backend.app.services.database import Database
from backend.app.services.radar_service import create_service


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    message: str
    elapsed_ms: float | None = None
    threshold_ms: float | None = None


def run_smoke(*, graph_threshold_ms: float = 1000.0, snapshot_threshold_ms: float = 1000.0) -> dict[str, Any]:
    checks: list[SmokeCheck] = []
    with TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        database = Database(temp / "primary.db")
        database.seed_from_csv(reset=True)
        service = create_service(database)

        checks.append(_counts_check(database))
        checks.append(_backup_restore_check(database, temp))
        checks.extend(_security_checks(service))
        checks.append(
            _performance_check(
                "masked_graph_latency",
                graph_threshold_ms,
                lambda: service.graph_payload(masked=True),
            )
        )
        submitter_context = context_from_headers(
            authorization=f"Bearer {issue_dev_jwt(subject='smoke-sme-009', organization_id='BIZ-009', roles=['sme_submitter'])}",
            app_mode="demo",
            request_id="local-smoke-period-snapshot",
        )
        checks.append(
            _performance_check(
                "period_snapshot_latency",
                snapshot_threshold_ms,
                lambda: service.intake.period_snapshot("BIZ-009", "2026-05", context=submitter_context),
            )
        )
        checks.append(_audit_tamper_check(database, service))

    failed = [check for check in checks if check.status == "fail"]
    return {
        "overall_status": "fail" if failed else "pass",
        "claim_level": "local-sqlite-smoke",
        "pilot_ready": False,
        "notice": (
            "Local operational smoke covers the SQLite demo adapter only. It is not live PostgreSQL/RLS, "
            "real OIDC, object storage, malware scanning, or production recovery proof."
        ),
        "checks": [asdict(check) for check in checks],
        "failed_checks": [check.name for check in failed],
    }


def _counts_check(database: Database) -> SmokeCheck:
    expected = {
        "businesses": 62,
        "supply_edges": 120,
        "reporting_periods": 744,
        "period_snapshots": 744,
    }
    with closing(database.connect()) as connection:
        actual = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in expected
        }
    if actual != expected:
        return SmokeCheck("seed_counts", "fail", f"Expected {expected}, got {actual}.")
    return SmokeCheck("seed_counts", "pass", "Seed counts match deterministic demo baseline.")


def _backup_restore_check(database: Database, temp: Path) -> SmokeCheck:
    backup = temp / "backup.db"
    restored = temp / "restored.db"
    shutil.copy2(database.path, backup)
    shutil.copy2(backup, restored)
    restored_database = Database(restored)
    with closing(database.connect()) as primary, closing(restored_database.connect()) as copy:
        primary_counts = _core_counts(primary)
        restored_counts = _core_counts(copy)
        audit_ok = create_service(restored_database).audit.verify_chain()
    if primary_counts != restored_counts:
        return SmokeCheck("sqlite_backup_restore", "fail", f"Restored counts differ: {primary_counts} != {restored_counts}.")
    if not audit_ok["ok"]:
        return SmokeCheck("sqlite_backup_restore", "fail", f"Restored audit chain failed: {audit_ok}.")
    return SmokeCheck("sqlite_backup_restore", "pass", "SQLite backup copy restores core counts and audit chain.")


def _core_counts(connection: Any) -> dict[str, int]:
    tables = ("businesses", "supply_edges", "financial_snapshots", "audit_logs")
    return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def _security_checks(service: Any) -> list[SmokeCheck]:
    checks = [
        _expect_exception(
            "pilot_demo_headers_denied",
            JwtVerificationError,
            lambda: context_from_headers(actor_id="spoofed", actor_role="system_admin", app_mode="pilot"),
            "Pilot mode rejects self-declared demo headers.",
        ),
        _expect_exception(
            "unmasked_graph_denied",
            AccessDeniedError,
            lambda: service.graph_payload(masked=False),
            "Unmasked commercial graph requires explicit sensitive scope/policy.",
        ),
    ]
    masked_graph = service.graph_payload(masked=True)
    nodes_masked = all(
        node.get("masked") is True
        and node.get("monthly_revenue") == 0
        and node.get("capacity") == 0
        and node.get("financial_health_score") == 0
        for node in masked_graph["nodes"]
    )
    edges_masked = all(
        edge.get("masked") is True
        and edge.get("monthly_volume") == 0
        and edge.get("transport_cost") == 0
        and edge.get("payment_term_days") == 0
        for edge in masked_graph["edges"]
    )
    checks.append(
        SmokeCheck(
            "masked_graph_redaction",
            "pass" if nodes_masked and edges_masked else "fail",
            "Masked graph redacts revenue, capacity, volume, cost and payment terms."
            if nodes_masked and edges_masked
            else "Masked graph leaked at least one sensitive metric.",
        )
    )
    lender_context = context_from_headers(
        authorization=f"Bearer {issue_dev_jwt(subject='smoke-lender-062', organization_id='BIZ-062', roles=['lender'])}",
        app_mode="demo",
        request_id="local-smoke-finance-deny",
    )
    checks.append(
        _expect_exception(
            "external_finance_without_consent_denied",
            AccessDeniedError,
            lambda: service.finance_payload_for_context("BIZ-005", lender_context),
            "External finance read is denied without active consent.",
        )
    )
    return checks


def _expect_exception(
    name: str,
    expected: type[BaseException],
    action: Callable[[], Any],
    success_message: str,
) -> SmokeCheck:
    try:
        action()
    except expected:
        return SmokeCheck(name, "pass", success_message)
    except Exception as exc:
        return SmokeCheck(name, "fail", f"Expected {expected.__name__}, got {type(exc).__name__}: {exc}.")
    return SmokeCheck(name, "fail", f"Expected {expected.__name__}, but action succeeded.")


def _performance_check(name: str, threshold_ms: float, action: Callable[[], Any]) -> SmokeCheck:
    started = perf_counter()
    result = action()
    elapsed_ms = (perf_counter() - started) * 1000
    if not result:
        return SmokeCheck(name, "fail", "Operation returned an empty result.", elapsed_ms, threshold_ms)
    if elapsed_ms > threshold_ms:
        return SmokeCheck(
            name,
            "fail",
            f"Latency {elapsed_ms:.2f}ms exceeded threshold {threshold_ms:.2f}ms.",
            elapsed_ms,
            threshold_ms,
        )
    return SmokeCheck(name, "pass", f"Latency {elapsed_ms:.2f}ms within threshold.", elapsed_ms, threshold_ms)


def _audit_tamper_check(database: Database, service: Any) -> SmokeCheck:
    service.business_detail_payload("BIZ-005")
    before = service.audit.verify_chain()
    if not before["ok"]:
        return SmokeCheck("audit_tamper_detection", "fail", f"Audit chain was not valid before tamper: {before}.")
    with closing(database.connect()) as connection:
        row = connection.execute(
            "SELECT event_id FROM audit_logs WHERE event_hash IS NOT NULL ORDER BY timestamp DESC, event_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return SmokeCheck("audit_tamper_detection", "fail", "No hashed audit event was available to tamper.")
        connection.execute("UPDATE audit_logs SET subject_id = ? WHERE event_id = ?", ("BIZ-TAMPERED", row["event_id"]))
        connection.commit()
    after = service.audit.verify_chain()
    if after["ok"] or after["reason"] != "event_hash_mismatch":
        return SmokeCheck("audit_tamper_detection", "fail", f"Tamper was not detected as expected: {after}.")
    return SmokeCheck("audit_tamper_detection", "pass", "Audit hash chain detects subject tampering.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local SQLite operational smoke gates.")
    parser.add_argument("--graph-threshold-ms", type=float, default=1000.0)
    parser.add_argument("--snapshot-threshold-ms", type=float, default=1000.0)
    parser.add_argument("--json", action="store_true", help="Print only the JSON report.")
    args = parser.parse_args()

    report = run_smoke(
        graph_threshold_ms=args.graph_threshold_ms,
        snapshot_threshold_ms=args.snapshot_threshold_ms,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["overall_status"] == "pass" else 1


def _print_human(report: dict[str, Any]) -> None:
    print(f"Local operational smoke: {report['overall_status']} (pilot_ready={report['pilot_ready']})")
    for check in report["checks"]:
        suffix = ""
        if check.get("elapsed_ms") is not None:
            suffix = f" ({check['elapsed_ms']:.2f}ms / {check['threshold_ms']:.2f}ms)"
        print(f"- {check['status'].upper()} {check['name']}: {check['message']}{suffix}")
    print(report["notice"])


if __name__ == "__main__":
    raise SystemExit(main())
