from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.database import DEFAULT_DB_PATH, Database
from backend.app.services.evidence_workers import EvidenceWorkerService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local evidence worker skeletons.")
    parser.add_argument("--sqlite-path", default=str(DEFAULT_DB_PATH), help="SQLite DB path for demo/local worker runs.")
    parser.add_argument("--mode", choices=["scan", "lifecycle"], required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--execute", action="store_true", help="Execute changes. Default is dry-run.")
    parser.add_argument(
        "--unsafe-mark-clean",
        action="store_true",
        help="Demo/testing only: mark pending scan rows clean without a real scanner.",
    )
    parser.add_argument(
        "--local-demo-scanner",
        action="store_true",
        help="Demo only: scan local evidence_objects bytes with hash/size checks and demo threat markers.",
    )
    parser.add_argument("--clamav-host", help="ClamAV daemon host for INSTREAM scanning.")
    parser.add_argument("--clamav-port", type=int, default=3310, help="ClamAV daemon TCP port.")
    parser.add_argument("--clamav-timeout", type=float, default=10.0, help="ClamAV connection timeout in seconds.")
    args = parser.parse_args()
    scanner_flags = sum(bool(item) for item in (args.unsafe_mark_clean, args.local_demo_scanner, args.clamav_host))
    if args.mode == "scan" and scanner_flags > 1:
        parser.error("Choose only one scanner option: --unsafe-mark-clean, --local-demo-scanner, or --clamav-host.")

    database = Database(Path(args.sqlite_path))
    database.initialize()
    worker = EvidenceWorkerService(database)
    dry_run = not args.execute

    if args.mode == "scan":
        scanner = None
        if args.unsafe_mark_clean:
            scanner = lambda row: ("clean", "unsafe_demo_mark_clean")
        elif args.local_demo_scanner:
            scanner = worker.local_demo_scanner
        elif args.clamav_host:
            scanner = lambda row: worker.clamav_scanner(
                row,
                host=args.clamav_host,
                port=args.clamav_port,
                timeout=args.clamav_timeout,
            )
        result = worker.scan_pending_versions(limit=args.limit, dry_run=dry_run, scanner=scanner)
    else:
        result = worker.apply_retention_lifecycle(limit=args.limit, dry_run=dry_run)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
