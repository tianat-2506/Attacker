from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.database import DEFAULT_DB_PATH, ensure_database


def main() -> None:
    database = ensure_database(reset=True)
    print(f"Seeded SQLite database: {DEFAULT_DB_PATH}")


if __name__ == "__main__":
    main()
