from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_trust_readiness_gate as gate


ROOT = Path(__file__).resolve().parents[2]


class TrustReadinessGateTests(unittest.TestCase):
    def test_missing_live_proof_fails_strict_gate(self) -> None:
        report = gate.run_gate(require_live=True, database_url=None, env={})
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["overall_status"], "fail")
        self.assertFalse(report["pilot_ready"])
        self.assertEqual(checks["postgres_migration_static"]["status"], "pass")
        self.assertEqual(checks["runtime_guardrails"]["status"], "pass")
        self.assertEqual(checks["postgres_rls_live"]["status"], "fail")
        self.assertEqual(checks["oidc_runtime_config"]["status"], "fail")
        self.assertEqual(checks["oidc_signed_token_live"]["status"], "fail")
        self.assertEqual(checks["evidence_object_storage_config"]["status"], "fail")
        self.assertEqual(checks["evidence_object_storage_live"]["status"], "fail")
        self.assertEqual(checks["evidence_malware_scanner_config"]["status"], "fail")
        self.assertEqual(checks["evidence_malware_scanner_live"]["status"], "fail")

    def test_allow_missing_live_keeps_local_gate_green_but_not_pilot_ready(self) -> None:
        report = gate.run_gate(require_live=False, database_url=None, env={})
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["overall_status"], "pass")
        self.assertFalse(report["pilot_ready"])
        self.assertEqual(checks["postgres_rls_live"]["status"], "skip")
        self.assertEqual(checks["oidc_runtime_config"]["status"], "skip")
        self.assertEqual(checks["oidc_signed_token_live"]["status"], "skip")
        self.assertEqual(checks["evidence_object_storage_config"]["status"], "skip")
        self.assertEqual(checks["evidence_object_storage_live"]["status"], "skip")
        self.assertEqual(checks["evidence_malware_scanner_config"]["status"], "skip")
        self.assertEqual(checks["evidence_malware_scanner_live"]["status"], "skip")
        self.assertIn("postgres_rls_live", report["missing_required_live_checks"])

    def test_configured_oidc_object_storage_and_scanner_still_need_live_smokes_and_rls(self) -> None:
        env = {
            "AUTH_PROVIDER": "oidc",
            "AUTH_JWKS_URL": "https://issuer.example/.well-known/jwks.json",
            "AUTH_JWT_ISSUER": "https://issuer.example/",
            "AUTH_JWT_AUDIENCE": "vietsupply-api",
            "EVIDENCE_OBJECT_STORE_ENDPOINT": "https://minio.example",
            "EVIDENCE_OBJECT_STORE_BUCKET": "vietsupply-evidence",
            "EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID": "access-key",
            "EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY": "secret-key",
            "EVIDENCE_MALWARE_SCANNER": "clamav",
            "CLAMAV_HOST": "clamav.local",
            "CLAMAV_PORT": "3310",
        }

        report = gate.run_gate(require_live=False, database_url=None, env=env)
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(checks["oidc_runtime_config"]["status"], "pass")
        self.assertEqual(checks["oidc_signed_token_live"]["status"], "skip")
        self.assertEqual(checks["evidence_object_storage_config"]["status"], "pass")
        self.assertEqual(checks["evidence_object_storage_live"]["status"], "skip")
        self.assertEqual(checks["evidence_malware_scanner_config"]["status"], "pass")
        self.assertEqual(checks["evidence_malware_scanner_live"]["status"], "skip")
        self.assertEqual(checks["postgres_rls_live"]["status"], "skip")
        self.assertFalse(report["pilot_ready"])

    def test_oidc_signed_token_live_flag_runs_smoke_script(self) -> None:
        env = {
            "AUTH_PROVIDER": "oidc",
            "AUTH_JWKS_URL": "https://issuer.example/.well-known/jwks.json",
            "AUTH_JWT_ISSUER": "https://issuer.example/",
            "AUTH_JWT_AUDIENCE": "vietsupply-api",
            "OIDC_SMOKE_TOKEN": "test-token",
            "OIDC_SIGNED_TOKEN_LIVE_SMOKE": "1",
        }

        with patch.object(
            gate.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout='{"overall_status":"pass"}', stderr=""),
        ) as run:
            report = gate.run_gate(require_live=False, database_url=None, env=env)

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(checks["oidc_runtime_config"]["status"], "pass")
        self.assertEqual(checks["oidc_signed_token_live"]["status"], "pass")
        self.assertIn("run_oidc_jwks_smoke.py", checks["oidc_signed_token_live"]["command"])
        run.assert_called_once()

    def test_live_smoke_output_redacts_env_secrets(self) -> None:
        env = {
            "AUTH_PROVIDER": "oidc",
            "AUTH_JWKS_URL": "https://issuer.example/.well-known/jwks.json",
            "AUTH_JWT_ISSUER": "https://issuer.example/",
            "AUTH_JWT_AUDIENCE": "vietsupply-api",
            "OIDC_SMOKE_TOKEN": "secret-smoke-token",
            "OIDC_SIGNED_TOKEN_LIVE_SMOKE": "1",
        }

        with patch.object(
            gate.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout="verified secret-smoke-token", stderr=""),
        ):
            report = gate.run_gate(require_live=False, database_url=None, env=env)

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(checks["oidc_signed_token_live"]["status"], "pass")
        self.assertIn("***", checks["oidc_signed_token_live"]["message"])
        self.assertNotIn("secret-smoke-token", checks["oidc_signed_token_live"]["message"])

    def test_all_required_live_proofs_can_mark_gate_pilot_ready(self) -> None:
        env = {
            "AUTH_PROVIDER": "oidc",
            "AUTH_JWKS_URL": "https://issuer.example/.well-known/jwks.json",
            "AUTH_JWT_ISSUER": "https://issuer.example/",
            "AUTH_JWT_AUDIENCE": "vietsupply-api",
            "OIDC_SMOKE_TOKEN": "secret-smoke-token",
            "OIDC_SIGNED_TOKEN_LIVE_SMOKE": "1",
            "EVIDENCE_OBJECT_STORE_ENDPOINT": "https://minio.example",
            "EVIDENCE_OBJECT_STORE_BUCKET": "vietsupply-evidence",
            "EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID": "access-key",
            "EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY": "secret-key",
            "EVIDENCE_OBJECT_STORAGE_LIVE_SMOKE": "1",
            "EVIDENCE_MALWARE_SCANNER": "clamav",
            "EVIDENCE_MALWARE_SCANNER_LIVE_SMOKE": "1",
            "CLAMAV_HOST": "clamav.local",
            "CLAMAV_PORT": "3310",
        }

        with patch.object(
            gate.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout='{"overall_status":"pass"}', stderr=""),
        ) as run:
            report = gate.run_gate(require_live=True, database_url="postgresql://user:password@localhost:5432/smoke", env=env)

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["overall_status"], "pass")
        self.assertTrue(report["pilot_ready"])
        self.assertEqual(report["missing_required_live_checks"], [])
        self.assertTrue(all(item["status"] == "pass" for item in checks.values()))
        self.assertEqual(run.call_count, 4)

    def test_cli_json_allows_missing_live_without_claiming_pilot_ready(self) -> None:
        env = os.environ.copy()
        for key in (
            "POSTGRES_TEST_DATABASE_URL",
            "AUTH_PROVIDER",
            "AUTH_JWKS_URL",
            "AUTH_JWT_ISSUER",
            "AUTH_JWT_AUDIENCE",
            "OIDC_SMOKE_TOKEN",
            "OIDC_SIGNED_TOKEN_LIVE_SMOKE",
            "OIDC_SMOKE_EXPECTED_SUBJECT",
            "OIDC_SMOKE_EXPECTED_ORGANIZATION_ID",
            "OIDC_SMOKE_EXPECTED_ROLE",
            "EVIDENCE_OBJECT_STORE_ENDPOINT",
            "EVIDENCE_OBJECT_STORE_BUCKET",
            "EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID",
            "EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY",
            "EVIDENCE_OBJECT_STORAGE_LIVE_SMOKE",
            "EVIDENCE_MALWARE_SCANNER",
            "EVIDENCE_MALWARE_SCANNER_LIVE_SMOKE",
            "CLAMAV_HOST",
            "CLAMAV_PORT",
        ):
            env.pop(key, None)

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "run_trust_readiness_gate.py"),
                "--allow-missing-live",
                "--json",
            ],
            cwd=ROOT,
            env=env,
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        report = json.loads(completed.stdout)
        self.assertEqual(report["overall_status"], "pass")
        self.assertFalse(report["pilot_ready"])


if __name__ == "__main__":
    unittest.main()
