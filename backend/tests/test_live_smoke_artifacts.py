from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LiveSmokeArtifactTests(unittest.TestCase):
    def test_evidence_live_smoke_docker_script_runs_required_smokes(self) -> None:
        script = (ROOT / "scripts" / "run_evidence_live_smoke_docker.ps1").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("minio/minio:latest", script)
        self.assertIn("clamav/clamav:stable", script)
        self.assertIn("run_evidence_object_storage_smoke.py --json", script)
        self.assertIn("run_clamav_smoke.py --json", script)
        self.assertIn("EVIDENCE_OBJECT_STORAGE_LIVE_SMOKE", script)
        self.assertIn("EVIDENCE_MALWARE_SCANNER_LIVE_SMOKE", script)
        self.assertIn("run_evidence_live_smoke_docker.ps1", readme)

    def test_oidc_signed_token_smoke_is_documented_and_gated(self) -> None:
        script = (ROOT / "scripts" / "run_oidc_jwks_smoke.py").read_text(encoding="utf-8")
        gate = (ROOT / "scripts" / "run_trust_readiness_gate.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("OIDC_SMOKE_TOKEN", script)
        self.assertIn("oidc_rejects_dev_jwt", script)
        self.assertIn("OIDC_SIGNED_TOKEN_LIVE_SMOKE", gate)
        self.assertIn("oidc_signed_token_live", gate)
        self.assertIn("run_oidc_jwks_smoke.py --synthetic --json", readme)
        self.assertIn("OIDC_SIGNED_TOKEN_LIVE_SMOKE", readme)


if __name__ == "__main__":
    unittest.main()
