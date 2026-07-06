from __future__ import annotations

import os
import subprocess
import sys
import unittest


class PostgresRlsSmokeTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv("POSTGRES_TEST_DATABASE_URL"), "set POSTGRES_TEST_DATABASE_URL to run DB-level RLS smoke")
    def test_postgres_rls_smoke_script_runs(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "scripts/postgres_rls_smoke.py",
                "--database-url",
                os.environ["POSTGRES_TEST_DATABASE_URL"],
            ],
            check=False,
            cwd=os.getcwd(),
            text=True,
            capture_output=True,
            timeout=100,
        )

        self.assertEqual(result.returncode, 0, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        self.assertIn("PostgreSQL RLS smoke passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
