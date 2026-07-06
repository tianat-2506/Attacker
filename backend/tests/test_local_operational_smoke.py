from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts import run_local_operational_smoke as smoke


ROOT = Path(__file__).resolve().parents[2]


class LocalOperationalSmokeTests(unittest.TestCase):
    def test_local_operational_smoke_passes_core_gates(self) -> None:
        report = smoke.run_smoke(graph_threshold_ms=5000, snapshot_threshold_ms=5000)
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["overall_status"], "pass")
        self.assertFalse(report["pilot_ready"])
        self.assertEqual(checks["seed_counts"]["status"], "pass")
        self.assertEqual(checks["sqlite_backup_restore"]["status"], "pass")
        self.assertEqual(checks["pilot_demo_headers_denied"]["status"], "pass")
        self.assertEqual(checks["unmasked_graph_denied"]["status"], "pass")
        self.assertEqual(checks["masked_graph_redaction"]["status"], "pass")
        self.assertEqual(checks["external_finance_without_consent_denied"]["status"], "pass")
        self.assertEqual(checks["audit_tamper_detection"]["status"], "pass")

    def test_local_operational_smoke_cli_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "run_local_operational_smoke.py"),
                "--json",
                "--graph-threshold-ms",
                "5000",
                "--snapshot-threshold-ms",
                "5000",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            timeout=60,
        )

        self.assertEqual(completed.returncode, 0, msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        report = json.loads(completed.stdout)
        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["claim_level"], "local-sqlite-smoke")

    def test_latency_threshold_failure_marks_gate_failed(self) -> None:
        report = smoke.run_smoke(graph_threshold_ms=0.0, snapshot_threshold_ms=5000)
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(checks["masked_graph_latency"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
