from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.app.services.access_control import RequestContext


ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = ROOT / "backend" / "migrations" / "versions"


class PostgresMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationFile:
    revision: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def migration_revision(path: Path) -> str:
    name = path.name
    if "_" not in name or not name.endswith(".sql"):
        raise PostgresMigrationError(f"Migration filename must look like '<revision>_name.sql': {path.name}")
    return name.split("_", maxsplit=1)[0]


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[MigrationFile]:
    if not directory.exists():
        raise PostgresMigrationError(f"Migration directory does not exist: {directory}")
    files = [MigrationFile(migration_revision(path), path) for path in sorted(directory.glob("*.sql"))]
    revisions = [item.revision for item in files]
    if len(revisions) != len(set(revisions)):
        raise PostgresMigrationError(f"Duplicate migration revisions found: {revisions}")
    return files


def normalize_postgres_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    if database_url.startswith("postgresql://"):
        return database_url
    raise PostgresMigrationError("DATABASE_URL must start with postgresql:// or postgresql+psycopg://")


def executable_migration_sql(sql: str) -> str:
    lines = [
        line
        for line in sql.splitlines()
        if line.strip().upper() not in {"BEGIN;", "COMMIT;"}
    ]
    return "\n".join(lines).strip() + "\n"


def rls_session_settings(context: RequestContext) -> dict[str, str]:
    return {
        "app.tenant_id": context.tenant_id,
        "app.actor_id": context.actor_id,
        "app.organization_ids": ",".join(sorted(context.organization_ids)),
        "app.purpose": context.purpose,
        "app.scopes": " ".join(sorted(context.scopes)),
    }


def set_rls_session(connection: Any, context: RequestContext) -> None:
    for key, value in rls_session_settings(context).items():
        connection.execute("SELECT set_config(%s, %s, true)", (key, value))


class PostgresMigrationRunner:
    def __init__(self, database_url: str, migrations_dir: Path = MIGRATIONS_DIR) -> None:
        self.database_url = normalize_postgres_url(database_url)
        self.migrations_dir = migrations_dir

    def plan(self) -> list[MigrationFile]:
        return migration_files(self.migrations_dir)

    def apply(self, target_revisions: Iterable[str] | None = None) -> list[str]:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ImportError as exc:
            raise PostgresMigrationError("Install backend requirements with psycopg before applying PostgreSQL migrations.") from exc

        selected = self._selected_migrations(target_revisions)
        applied: list[str] = []
        with psycopg.connect(self.database_url, autocommit=False) as connection:
            self._ensure_schema_migrations(connection)
            existing = self._applied_revisions(connection)
            for migration in selected:
                if migration.revision in existing:
                    continue
                with connection.transaction():
                    connection.execute(executable_migration_sql(migration.sql))
                    connection.execute(
                        """
                        INSERT INTO schema_migrations (revision, file_name)
                        VALUES (%s, %s)
                        """,
                        (migration.revision, migration.path.name),
                    )
                applied.append(migration.revision)
        return applied

    def _selected_migrations(self, target_revisions: Iterable[str] | None) -> list[MigrationFile]:
        files = self.plan()
        if target_revisions is None:
            return files
        wanted = set(target_revisions)
        selected = [item for item in files if item.revision in wanted]
        missing = wanted.difference(item.revision for item in selected)
        if missing:
            raise PostgresMigrationError(f"Unknown migration revisions: {sorted(missing)}")
        return selected

    def _ensure_schema_migrations(self, connection: Any) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              revision text PRIMARY KEY,
              file_name text NOT NULL,
              applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

    def _applied_revisions(self, connection: Any) -> set[str]:
        rows = connection.execute("SELECT revision FROM schema_migrations").fetchall()
        return {str(row[0]) for row in rows}
