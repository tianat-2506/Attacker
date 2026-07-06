from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.access_control import JwtVerificationError, context_from_headers, issue_dev_jwt


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    message: str


def run_smoke(*, env: dict[str, str] | None = None, synthetic: bool = False) -> dict[str, Any]:
    active_env = env if env is not None else os.environ
    checks: list[SmokeCheck] = []
    if synthetic:
        return _run_synthetic_smoke(checks)

    provider = active_env.get("AUTH_PROVIDER", "").strip().lower()
    jwks_url = active_env.get("AUTH_JWKS_URL", "").strip()
    issuer = active_env.get("AUTH_JWT_ISSUER", "").strip()
    audience = active_env.get("AUTH_JWT_AUDIENCE", "").strip()
    token = active_env.get("OIDC_SMOKE_TOKEN", "").strip()
    if provider != "oidc" or not jwks_url or not issuer or not audience:
        checks.append(
            SmokeCheck(
                "oidc_config",
                "fail",
                "Set AUTH_PROVIDER=oidc, AUTH_JWKS_URL, AUTH_JWT_ISSUER and AUTH_JWT_AUDIENCE.",
            )
        )
        return _report(checks, subject=None, synthetic=synthetic)
    checks.append(SmokeCheck("oidc_config", "pass", "OIDC/JWKS config is present."))
    if not token:
        checks.append(SmokeCheck("oidc_smoke_token", "fail", "Set OIDC_SMOKE_TOKEN to a signed token from the configured issuer."))
        return _report(checks, subject=None, synthetic=synthetic)

    try:
        context = context_from_headers(authorization=f"Bearer {token}", app_mode="pilot", request_id="req-oidc-smoke")
    except JwtVerificationError as exc:
        checks.append(SmokeCheck("oidc_signed_token", "fail", f"Signed token was rejected: {exc.code}."))
        return _report(checks, subject=None, synthetic=synthetic)

    if context.auth_assurance != "oidc-jwks":
        checks.append(SmokeCheck("oidc_auth_assurance", "fail", f"Expected oidc-jwks, got {context.auth_assurance}."))
        return _report(checks, subject=context.actor_id, synthetic=synthetic)
    checks.append(SmokeCheck("oidc_signed_token", "pass", "Signed token was verified through configured JWKS."))
    checks.extend(_optional_claim_checks(active_env, context))
    checks.extend(_dev_jwt_rejection_check())
    return _report(checks, subject=context.actor_id, synthetic=synthetic)


def _optional_claim_checks(env: dict[str, str], context: Any) -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    expected_subject = env.get("OIDC_SMOKE_EXPECTED_SUBJECT", "").strip()
    expected_org = env.get("OIDC_SMOKE_EXPECTED_ORGANIZATION_ID", "").strip()
    expected_role = env.get("OIDC_SMOKE_EXPECTED_ROLE", "").strip()
    if expected_subject:
        status = "pass" if context.actor_id == expected_subject else "fail"
        checks.append(
            SmokeCheck(
                "oidc_expected_subject",
                status,
                f"Expected subject fingerprint {_fingerprint(expected_subject)}, got {_fingerprint(context.actor_id)}.",
            )
        )
    if expected_org:
        status = "pass" if expected_org in context.organization_ids else "fail"
        checks.append(SmokeCheck("oidc_expected_organization", status, f"Expected organization fingerprint {_fingerprint(expected_org)}."))
    if expected_role:
        status = "pass" if expected_role in context.roles else "fail"
        checks.append(SmokeCheck("oidc_expected_role", status, f"Expected role {expected_role}."))
    return checks


def _dev_jwt_rejection_check() -> list[SmokeCheck]:
    token = issue_dev_jwt(subject="dev-token-should-not-pass")
    with patch.dict("os.environ", {"AUTH_PROVIDER": "oidc"}, clear=False):
        try:
            context_from_headers(authorization=f"Bearer {token}", app_mode="pilot")
        except JwtVerificationError:
            return [SmokeCheck("oidc_rejects_dev_jwt", "pass", "OIDC provider did not accept local dev JWT fallback.")]
    return [SmokeCheck("oidc_rejects_dev_jwt", "fail", "OIDC provider accepted a local dev JWT fallback.")]


def _run_synthetic_smoke(checks: list[SmokeCheck]) -> dict[str, Any]:
    try:
        import jwt  # type: ignore[import-not-found]
        from cryptography.hazmat.primitives.asymmetric import rsa  # type: ignore[import-not-found]
    except ImportError as exc:
        checks.append(SmokeCheck("oidc_synthetic_dependencies", "fail", f"Missing PyJWT/cryptography dependency: {exc.__class__.__name__}."))
        return _report(checks, subject=None, synthetic=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    kid = "synthetic-oidc-smoke-key"
    handler = _jwks_handler(
        {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": kid,
                    "alg": "RS256",
                    "n": _base64url_uint(public_numbers.n),
                    "e": _base64url_uint(public_numbers.e),
                }
            ]
        }
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "https://synthetic-issuer.local/",
                "aud": "vietsupply-api",
                "sub": "synthetic-oidc-user",
                "tenant_id": "tenant-demo",
                "organization_id": "BIZ-009",
                "roles": ["org_admin"],
                "scopes": ["finance:read"],
                "iat": now,
                "nbf": now - 5,
                "exp": now + 300,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": kid, "typ": "JWT"},
        )
        with patch.dict(
            "os.environ",
            {
                "AUTH_PROVIDER": "oidc",
                "AUTH_JWKS_URL": f"http://127.0.0.1:{server.server_port}/jwks.json",
                "AUTH_JWT_ISSUER": "https://synthetic-issuer.local/",
                "AUTH_JWT_AUDIENCE": "vietsupply-api",
            },
            clear=False,
        ):
            context = context_from_headers(authorization=f"Bearer {token}", app_mode="pilot", request_id="req-synthetic-oidc-smoke")
    except Exception as exc:
        checks.append(SmokeCheck("oidc_synthetic_signed_token", "fail", f"Synthetic signed token failed: {exc.__class__.__name__}."))
        return _report(checks, subject=None, synthetic=True)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    checks.append(SmokeCheck("oidc_synthetic_signed_token", "pass", "Synthetic RS256 token verified through local JWKS server."))
    checks.extend(_dev_jwt_rejection_check())
    return _report(checks, subject=context.actor_id, synthetic=True)


def _jwks_handler(jwks: dict[str, object]) -> type[BaseHTTPRequestHandler]:
    class JwksHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps(jwks).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return JwksHandler


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _fingerprint(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _report_subject(subject: str | None, *, synthetic: bool) -> str | None:
    if subject is None:
        return None
    return subject if synthetic else f"sha256:{_fingerprint(subject)}"


def _report(checks: list[SmokeCheck], *, subject: str | None, synthetic: bool) -> dict[str, Any]:
    failed = [check for check in checks if check.status == "fail"]
    return {
        "overall_status": "fail" if failed else "pass",
        "pilot_ready": not failed and not synthetic,
        "claim_level": "synthetic-local-jwks" if synthetic else "live-configured-jwks",
        "subject": _report_subject(subject, synthetic=synthetic),
        "subject_fingerprint": _fingerprint(subject),
        "checks": [asdict(check) for check in checks],
        "failed_checks": [check.name for check in failed],
        "notice": (
            "Synthetic mode proves verifier mechanics only; use live mode with OIDC_SMOKE_TOKEN before pilot claims."
            if synthetic
            else "Live OIDC smoke verifies a signed token against configured JWKS and rejects local dev JWT fallback."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OIDC/JWKS signed-token smoke.")
    parser.add_argument("--synthetic", action="store_true", help="Use a local ephemeral JWKS server and synthetic RS256 token.")
    parser.add_argument("--json", action="store_true", help="Print only the JSON report.")
    args = parser.parse_args()

    report = run_smoke(synthetic=args.synthetic)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"OIDC/JWKS smoke: {report['overall_status']}")
        for check in report["checks"]:
            print(f"- {check['status'].upper()} {check['name']}: {check['message']}")
        print(report["notice"])
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
