from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.config import AppSettings
from backend.app.services.postgres_migrations import PostgresMigrationRunner
from backend.app.services.postgres_pilot_service import ObjectStorageSettings
from scripts.validate_postgres_migrations import validate as validate_postgres_migration


PLACEHOLDER_POSTGRES_URL = "postgresql://user:password@localhost:5432/vietsupply"
REDACTED_POSTGRES_URL = "postgresql://user:***@localhost:5432/vietsupply"


@dataclass(frozen=True)
class GateCheck:
    name: str
    status: str
    claim_level: str
    required_for_pilot: bool
    message: str
    command: str | None = None


def run_gate(
    *,
    require_live: bool,
    database_url: str | None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    active_env = env if env is not None else os.environ
    checks = [
        _check_postgres_migration_static(),
        _check_postgres_migration_plan(),
        _check_runtime_guardrails(),
        _check_oidc_config(active_env, require_live=require_live),
        _check_oidc_signed_token_live(active_env, require_live=require_live),
        _check_object_storage_config(active_env, require_live=require_live),
        _check_object_storage_live(active_env, require_live=require_live),
        _check_malware_scanner_config(active_env, require_live=require_live),
        _check_malware_scanner_live(active_env, require_live=require_live),
        _check_postgres_rls_live(database_url, require_live=require_live),
    ]
    failed = [check for check in checks if check.status == "fail"]
    missing_required_live = [
        check
        for check in checks
        if check.required_for_pilot and check.status == "skip" and check.claim_level in {"config", "live"}
    ]
    return {
        "overall_status": "fail" if failed else "pass",
        "pilot_ready": not failed and not missing_required_live,
        "notice": (
            "This gate records proof level. Static/config pass is not live proof; pilot_ready is true only when "
            "required live/config checks are not missing."
        ),
        "checks": [asdict(check) for check in checks],
        "failed_checks": [check.name for check in failed],
        "missing_required_live_checks": [check.name for check in missing_required_live],
    }


def _pass(name: str, claim_level: str, required_for_pilot: bool, message: str, command: str | None = None) -> GateCheck:
    return GateCheck(name, "pass", claim_level, required_for_pilot, message, command)


def _fail(name: str, claim_level: str, required_for_pilot: bool, message: str, command: str | None = None) -> GateCheck:
    return GateCheck(name, "fail", claim_level, required_for_pilot, message, command)


def _skip(name: str, claim_level: str, required_for_pilot: bool, message: str, command: str | None = None) -> GateCheck:
    return GateCheck(name, "skip", claim_level, required_for_pilot, message, command)


def _check_postgres_migration_static() -> GateCheck:
    errors = validate_postgres_migration()
    if errors:
        return _fail(
            "postgres_migration_static",
            "static",
            True,
            "; ".join(errors),
            "python scripts/validate_postgres_migrations.py",
        )
    return _pass(
        "postgres_migration_static",
        "static",
        True,
        "PostgreSQL trust migration contains required RLS, policy, registry and audit snippets.",
        "python scripts/validate_postgres_migrations.py",
    )


def _check_postgres_migration_plan() -> GateCheck:
    try:
        plan = PostgresMigrationRunner(PLACEHOLDER_POSTGRES_URL).plan()
    except Exception as exc:
        return _fail("postgres_migration_plan", "static", True, str(exc))
    revisions = [item.revision for item in plan]
    if "0001" not in revisions:
        return _fail("postgres_migration_plan", "static", True, f"Expected revision 0001, got {revisions}.")
    return _pass(
        "postgres_migration_plan",
        "static",
        True,
        f"Migration plan loads revisions: {', '.join(revisions)}.",
        f"python scripts/apply_postgres_migrations.py --database-url {REDACTED_POSTGRES_URL} --plan-only",
    )


def _check_runtime_guardrails() -> GateCheck:
    valid = AppSettings(
        app_mode="pilot",
        database_url=PLACEHOLDER_POSTGRES_URL,
        allow_demo_headers=False,
        auth_provider="oidc",
        jwks_url="https://issuer.example/.well-known/jwks.json",
    )
    invalid = AppSettings(
        app_mode="pilot",
        database_url="sqlite:///backend/app/data/vietsupply.db",
        allow_demo_headers=True,
        auth_provider="dev_jwt",
        jwks_url=None,
    )
    try:
        valid.validate_runtime()
    except Exception as exc:
        return _fail("runtime_guardrails", "static", True, f"Valid pilot config was rejected: {exc}.")
    try:
        invalid.validate_runtime()
    except RuntimeError:
        return _pass(
            "runtime_guardrails",
            "static",
            True,
            "Pilot config requires PostgreSQL, OIDC/JWKS and disabled demo headers; invalid pilot demo fallback is rejected.",
        )
    return _fail("runtime_guardrails", "static", True, "Invalid pilot demo fallback was accepted.")


def _check_oidc_config(env: dict[str, str], *, require_live: bool) -> GateCheck:
    provider = env.get("AUTH_PROVIDER", "").strip().lower()
    jwks_url = env.get("AUTH_JWKS_URL", "").strip()
    issuer = env.get("AUTH_JWT_ISSUER", "").strip()
    audience = env.get("AUTH_JWT_AUDIENCE", "").strip()
    if provider == "oidc" and jwks_url and issuer and audience:
        return _pass(
            "oidc_runtime_config",
            "config",
            True,
            "OIDC/JWKS runtime variables are present. This is configuration proof, not a real IdP token smoke.",
        )
    message = (
        "Real IdP/OIDC runtime variables are missing. Set AUTH_PROVIDER=oidc, AUTH_JWKS_URL, "
        "AUTH_JWT_ISSUER and AUTH_JWT_AUDIENCE, then run a signed-token smoke."
    )
    return (
        _fail("oidc_runtime_config", "config", True, message)
        if require_live
        else _skip("oidc_runtime_config", "config", True, message)
    )


def _check_oidc_signed_token_live(env: dict[str, str], *, require_live: bool) -> GateCheck:
    command = "python scripts/run_oidc_jwks_smoke.py --json"
    if not _env_enabled(env, "OIDC_SIGNED_TOKEN_LIVE_SMOKE"):
        message = (
            "Live OIDC signed-token smoke was not run. Set OIDC_SIGNED_TOKEN_LIVE_SMOKE=1 "
            "and OIDC_SMOKE_TOKEN to a disposable signed token from the configured issuer."
        )
        return (
            _fail("oidc_signed_token_live", "live", True, message, command)
            if require_live
            else _skip("oidc_signed_token_live", "live", True, message, command)
        )

    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "run_oidc_jwks_smoke.py"), "--json"],
        cwd=ROOT,
        env=_subprocess_env(env),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode == 0:
        return _pass(
            "oidc_signed_token_live",
            "live",
            True,
            _redact_sensitive(_tail(completed.stdout) or "OIDC/JWKS signed-token smoke passed.", env),
            command,
        )
    return _fail(
        "oidc_signed_token_live",
        "live",
        True,
        _redact_sensitive(
            f"OIDC/JWKS signed-token smoke failed with exit {completed.returncode}: "
            f"{_tail(completed.stdout)} {_tail(completed.stderr)}",
            env,
        ).strip(),
        command,
    )


def _check_object_storage_config(env: dict[str, str], *, require_live: bool) -> GateCheck:
    settings = ObjectStorageSettings.from_env()
    # ObjectStorageSettings reads os.environ; use env overlay for tests without mutating process env.
    if env is not os.environ:
        settings = ObjectStorageSettings(
            endpoint_url=env.get("EVIDENCE_OBJECT_STORE_ENDPOINT") or None,
            bucket=env.get("EVIDENCE_OBJECT_STORE_BUCKET", "vietsupply-evidence"),
            access_key_id=env.get("EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID") or None,
            secret_access_key=env.get("EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY") or None,
            region=env.get("EVIDENCE_OBJECT_STORE_REGION", "us-east-1"),
        )
    if settings.is_configured:
        return _pass(
            "evidence_object_storage_config",
            "config",
            True,
            "S3/MinIO-compatible object storage variables are present. Live upload/download must still be proven.",
        )
    message = (
        "Evidence object storage is not configured. Set EVIDENCE_OBJECT_STORE_ENDPOINT, "
        "EVIDENCE_OBJECT_STORE_BUCKET, EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID and "
        "EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY before accepting real files."
    )
    return (
        _fail("evidence_object_storage_config", "config", True, message)
        if require_live
        else _skip("evidence_object_storage_config", "config", True, message)
    )


def _check_malware_scanner_config(env: dict[str, str], *, require_live: bool) -> GateCheck:
    scanner = env.get("EVIDENCE_MALWARE_SCANNER", "").strip().lower()
    host = env.get("CLAMAV_HOST", "").strip()
    port_raw = env.get("CLAMAV_PORT", "").strip() or "3310"
    try:
        port = int(port_raw)
    except ValueError:
        port = 0
    if scanner == "clamav" and host and 1 <= port <= 65535:
        return _pass(
            "evidence_malware_scanner_config",
            "config",
            True,
            "ClamAV malware scanner variables are present. Live clean/infected scan smoke must still be proven.",
        )
    message = (
        "Evidence malware scanner is not configured. Set EVIDENCE_MALWARE_SCANNER=clamav, "
        "CLAMAV_HOST and CLAMAV_PORT before accepting real files."
    )
    return (
        _fail("evidence_malware_scanner_config", "config", True, message)
        if require_live
        else _skip("evidence_malware_scanner_config", "config", True, message)
    )


def _check_object_storage_live(env: dict[str, str], *, require_live: bool) -> GateCheck:
    command = "python scripts/run_evidence_object_storage_smoke.py --json"
    if not _env_enabled(env, "EVIDENCE_OBJECT_STORAGE_LIVE_SMOKE"):
        message = (
            "Live S3/MinIO PUT/GET smoke was not run. Set EVIDENCE_OBJECT_STORAGE_LIVE_SMOKE=1 "
            "after pointing object-storage variables at a disposable pilot bucket."
        )
        return (
            _fail("evidence_object_storage_live", "live", True, message, command)
            if require_live
            else _skip("evidence_object_storage_live", "live", True, message, command)
        )

    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "run_evidence_object_storage_smoke.py"), "--json"],
        cwd=ROOT,
        env=_subprocess_env(env),
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode == 0:
        return _pass(
            "evidence_object_storage_live",
            "live",
            True,
            _redact_sensitive(_tail(completed.stdout) or "S3/MinIO PUT/GET smoke passed.", env),
            command,
        )
    return _fail(
        "evidence_object_storage_live",
        "live",
        True,
        _redact_sensitive(
            f"S3/MinIO PUT/GET smoke failed with exit {completed.returncode}: "
            f"{_tail(completed.stdout)} {_tail(completed.stderr)}",
            env,
        ).strip(),
        command,
    )


def _check_malware_scanner_live(env: dict[str, str], *, require_live: bool) -> GateCheck:
    command = "python scripts/run_clamav_smoke.py --json"
    if not _env_enabled(env, "EVIDENCE_MALWARE_SCANNER_LIVE_SMOKE"):
        message = (
            "Live ClamAV clean/infected smoke was not run. Set EVIDENCE_MALWARE_SCANNER_LIVE_SMOKE=1 "
            "after pointing scanner variables at a disposable ClamAV daemon."
        )
        return (
            _fail("evidence_malware_scanner_live", "live", True, message, command)
            if require_live
            else _skip("evidence_malware_scanner_live", "live", True, message, command)
        )

    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "run_clamav_smoke.py"), "--json"],
        cwd=ROOT,
        env=_subprocess_env(env),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode == 0:
        return _pass(
            "evidence_malware_scanner_live",
            "live",
            True,
            _redact_sensitive(_tail(completed.stdout) or "ClamAV clean/infected smoke passed.", env),
            command,
        )
    return _fail(
        "evidence_malware_scanner_live",
        "live",
        True,
        _redact_sensitive(
            f"ClamAV clean/infected smoke failed with exit {completed.returncode}: "
            f"{_tail(completed.stdout)} {_tail(completed.stderr)}",
            env,
        ).strip(),
        command,
    )


def _check_postgres_rls_live(database_url: str | None, *, require_live: bool) -> GateCheck:
    command = "python scripts/postgres_rls_smoke.py --database-url <POSTGRES_TEST_DATABASE_URL>"
    if not database_url:
        message = (
            "Live PostgreSQL/PostGIS RLS smoke was not run. Set POSTGRES_TEST_DATABASE_URL or pass "
            "--database-url against a disposable test database."
        )
        return (
            _fail("postgres_rls_live", "live", True, message, command)
            if require_live
            else _skip("postgres_rls_live", "live", True, message, command)
        )

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts" / "postgres_rls_smoke.py"),
            "--database-url",
            database_url,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode == 0:
        return _pass(
            "postgres_rls_live",
            "live",
            True,
            _redact(_tail(completed.stdout) or "PostgreSQL RLS smoke passed."),
            command,
        )
    return _fail(
        "postgres_rls_live",
        "live",
        True,
        _redact(f"RLS smoke failed with exit {completed.returncode}: {_tail(completed.stdout)} {_tail(completed.stderr)}").strip(),
        command,
    )


def _tail(value: str, limit: int = 600) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:]


def _redact(value: str) -> str:
    return re.sub(r"(postgresql(?:\+psycopg)?://[^:\s/@]+):([^@\s]+)@", r"\1:***@", value)


def _redact_sensitive(value: str, env: dict[str, str] | None = None) -> str:
    redacted = _redact(value)
    source = env or os.environ
    secret_keys = (
        source.get("EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY"),
        source.get("EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID"),
        source.get("OIDC_SMOKE_TOKEN"),
        source.get("AUTH_JWT_SECRET"),
    )
    for secret in secret_keys:
        if secret:
            redacted = redacted.replace(secret, "***")
    return redacted


def _env_enabled(env: dict[str, str], key: str) -> bool:
    return env.get(key, "").strip().lower() in {"1", "true", "yes", "on"}


def _subprocess_env(env: dict[str, str]) -> dict[str, str]:
    merged = os.environ.copy()
    merged.update(env)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Run trust-first pilot readiness gates.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("POSTGRES_TEST_DATABASE_URL"),
        help="Disposable PostgreSQL/PostGIS test URL for live RLS smoke. Defaults to POSTGRES_TEST_DATABASE_URL.",
    )
    parser.add_argument(
        "--allow-missing-live",
        action="store_true",
        help="Return success for local development even when live/config pilot gates are missing; report skips explicitly.",
    )
    parser.add_argument("--json", action="store_true", help="Print only the JSON report.")
    args = parser.parse_args()

    report = run_gate(require_live=not args.allow_missing_live, database_url=args.database_url)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["overall_status"] == "pass" else 1


def _print_human(report: dict[str, Any]) -> None:
    print(f"Trust readiness gate: {report['overall_status']} (pilot_ready={report['pilot_ready']})")
    for check in report["checks"]:
        print(f"- {check['status'].upper()} [{check['claim_level']}] {check['name']}: {check['message']}")
    if report["missing_required_live_checks"]:
        print("Missing required pilot proof:", ", ".join(report["missing_required_live_checks"]))
    print(report["notice"])


if __name__ == "__main__":
    raise SystemExit(main())
