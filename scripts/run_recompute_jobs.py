from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.database import DEFAULT_DB_PATH, Database
from backend.app.services.recompute_workers import RecomputeJobWorkerService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local analytics recompute job worker skeleton.")
    parser.add_argument("--sqlite-path", default=str(DEFAULT_DB_PATH), help="SQLite DB path for demo/local worker runs.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--execute", action="store_true", help="Execute queued jobs. Default is dry-run.")
    parser.add_argument(
        "--unsafe-mark-succeeded",
        action="store_true",
        help="Demo/testing only: mark queued jobs succeeded without real recompute.",
    )
    args = parser.parse_args()

    database = Database(Path(args.sqlite_path))
    database.initialize()
    worker = RecomputeJobWorkerService(database)
    handler = (lambda job: ("succeeded", "unsafe_demo_mark_succeeded")) if args.unsafe_mark_succeeded else None
    result = worker.process_queued(limit=args.limit, dry_run=not args.execute, handler=handler)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
