from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.postgres_migrations import PostgresMigrationRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply VietSupply Radar PostgreSQL trust migrations.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL DATABASE_URL.")
    parser.add_argument("--revision", action="append", help="Specific revision to apply; defaults to all pending migrations.")
    parser.add_argument("--plan-only", action="store_true", help="Print the migration plan without connecting to the database.")
    args = parser.parse_args()

    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    runner = PostgresMigrationRunner(args.database_url)
    plan = runner.plan()
    if args.plan_only:
        for migration in plan:
            print(f"{migration.revision}\t{migration.path.name}")
        return 0

    applied = runner.apply(target_revisions=args.revision)
    if applied:
        print(f"Applied PostgreSQL migrations: {', '.join(applied)}")
    else:
        print("No pending PostgreSQL migrations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
