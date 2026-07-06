from __future__ import annotations

import unittest

from scripts import run_oidc_jwks_smoke as smoke


class OidcJwksSmokeTests(unittest.TestCase):
    def test_synthetic_smoke_passes_without_claiming_pilot_ready(self) -> None:
        report = smoke.run_smoke(synthetic=True)
        if "oidc_synthetic_dependencies" in report["failed_checks"]:
            self.skipTest("OIDC synthetic smoke dependencies are not installed.")

        self.assertEqual(report["overall_status"], "pass")
        self.assertFalse(report["pilot_ready"])
        self.assertEqual(report["claim_level"], "synthetic-local-jwks")
        self.assertEqual(report["subject"], "synthetic-oidc-user")
        self.assertNotIn("oidc_rejects_dev_jwt", report["failed_checks"])

    def test_live_smoke_requires_signed_token_from_configured_issuer(self) -> None:
        report = smoke.run_smoke(
            env={
                "AUTH_PROVIDER": "oidc",
                "AUTH_JWKS_URL": "https://issuer.example/.well-known/jwks.json",
                "AUTH_JWT_ISSUER": "https://issuer.example/",
                "AUTH_JWT_AUDIENCE": "vietsupply-api",
            }
        )

        self.assertEqual(report["overall_status"], "fail")
        self.assertFalse(report["pilot_ready"])
        self.assertIn("oidc_smoke_token", report["failed_checks"])


if __name__ == "__main__":
    unittest.main()
