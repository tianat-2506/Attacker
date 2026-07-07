from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.postgres_pilot_service import ObjectStorageSettings, PilotFeatureUnavailableError


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    message: str


def run_smoke(
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float = 20.0,
    content: bytes | None = None,
) -> dict[str, Any]:
    active_env = env if env is not None else os.environ
    settings = _settings_from_env(active_env)
    checks: list[SmokeCheck] = []
    if not settings.is_configured:
        checks.append(
            SmokeCheck(
                "object_storage_config",
                "fail",
                "Missing S3/MinIO config. Set endpoint, bucket, access key id and secret access key.",
            )
        )
        return _report(checks, settings=settings, object_key=None)

    checks.append(SmokeCheck("object_storage_config", "pass", "S3/MinIO config is present."))
    payload = content or b"vietsupply-object-storage-live-smoke\n"
    object_key = f"s3://{settings.bucket}/vietsupply-smoke/{uuid.uuid4().hex}.txt"

    try:
        put_url = settings.presign_put_url(object_key)
        request = Request(put_url, data=payload, method="PUT")
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 0)
        if status not in {200, 201, 204}:
            checks.append(SmokeCheck("object_storage_put", "fail", f"PUT returned unexpected HTTP {status}."))
            return _report(checks, settings=settings, object_key=object_key)
        checks.append(SmokeCheck("object_storage_put", "pass", "PUT smoke wrote a temporary evidence object."))
    except (HTTPError, URLError, OSError, PilotFeatureUnavailableError) as exc:
        checks.append(SmokeCheck("object_storage_put", "fail", f"PUT smoke failed: {_safe_error(exc)}."))
        return _report(checks, settings=settings, object_key=object_key)

    try:
        get_url = settings.presign_get_url(object_key)
        with urlopen(get_url, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 0)
            downloaded = response.read()
        if status not in {200, 206}:
            checks.append(SmokeCheck("object_storage_get_verify", "fail", f"GET returned unexpected HTTP {status}."))
        elif downloaded != payload:
            checks.append(SmokeCheck("object_storage_get_verify", "fail", "Downloaded bytes did not match uploaded bytes."))
        else:
            checks.append(SmokeCheck("object_storage_get_verify", "pass", "GET smoke verified uploaded bytes."))
    except (HTTPError, URLError, OSError, PilotFeatureUnavailableError) as exc:
        checks.append(SmokeCheck("object_storage_get_verify", "fail", f"GET smoke failed: {_safe_error(exc)}."))

    try:
        delete_url = settings.presign_delete_url(object_key)
        request = Request(delete_url, method="DELETE")
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 0)
        if status not in {200, 202, 204}:
            checks.append(SmokeCheck("object_storage_delete", "fail", f"DELETE returned unexpected HTTP {status}."))
        else:
            checks.append(SmokeCheck("object_storage_delete", "pass", "DELETE smoke removed the temporary evidence object."))
    except (HTTPError, URLError, OSError, PilotFeatureUnavailableError) as exc:
        checks.append(SmokeCheck("object_storage_delete", "fail", f"DELETE smoke failed: {_safe_error(exc)}."))

    return _report(checks, settings=settings, object_key=object_key)


def _settings_from_env(env: dict[str, str]) -> ObjectStorageSettings:
    return ObjectStorageSettings(
        endpoint_url=env.get("EVIDENCE_OBJECT_STORE_ENDPOINT") or None,
        bucket=env.get("EVIDENCE_OBJECT_STORE_BUCKET", "vietsupply-evidence"),
        access_key_id=env.get("EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID") or None,
        secret_access_key=env.get("EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY") or None,
        region=env.get("EVIDENCE_OBJECT_STORE_REGION", "us-east-1"),
    )


def _report(checks: list[SmokeCheck], *, settings: ObjectStorageSettings, object_key: str | None) -> dict[str, Any]:
    failed = [check for check in checks if check.status == "fail"]
    return {
        "overall_status": "fail" if failed else "pass",
        "pilot_ready": not failed,
        "bucket": settings.bucket,
        "object_key": object_key,
        "checks": [asdict(check) for check in checks],
        "failed_checks": [check.name for check in failed],
        "notice": "Live object storage proof performs a real PUT, GET and DELETE cleanup against the configured S3/MinIO bucket.",
    }


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code} {exc.reason}"
    if isinstance(exc, URLError):
        return f"{exc.__class__.__name__}:{exc.reason}"
    return exc.__class__.__name__


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live S3/MinIO PUT/GET/DELETE smoke for evidence object storage.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print only the JSON report.")
    args = parser.parse_args()

    report = run_smoke(timeout_seconds=args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Evidence object storage smoke: {report['overall_status']}")
        for check in report["checks"]:
            print(f"- {check['status'].upper()} {check['name']}: {check['message']}")
        print(report["notice"])
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
