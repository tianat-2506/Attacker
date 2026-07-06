from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from backend.app.services.database import Database


RecomputeHandler = Callable[[dict[str, Any]], tuple[str, str | None]]


@dataclass(frozen=True)
class RecomputeWorkerSummary:
    dry_run: bool
    candidates: int
    processed: int
    skipped: int
    failed: int
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "candidates": self.candidates,
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors,
        }


class RecomputeJobWorkerService:
    """Durable local outbox worker skeleton for analytics recompute jobs.

    The default handler is intentionally absent. Executing without a handler marks
    jobs as skipped, not succeeded, so operators cannot mistake a queue drain for
    a verified recomputation.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def process_queued(
        self,
        *,
        limit: int = 20,
        dry_run: bool = True,
        handler: RecomputeHandler | None = None,
    ) -> dict[str, Any]:
        rows = self._queued_rows(limit)
        if dry_run:
            return RecomputeWorkerSummary(True, len(rows), 0, len(rows), 0, []).as_dict()

        processed = 0
        skipped = 0
        failed = 0
        errors: list[str] = []
        for row in rows:
            job = dict(row)
            try:
                self._mark_running(job["job_id"], job["attempts"])
                if handler is None:
                    final_status, message = "skipped", "recompute_handler_not_configured"
                else:
                    final_status, message = handler(job)
                if final_status not in {"succeeded", "skipped", "failed"}:
                    raise ValueError(f"unsupported_recompute_status:{final_status}")
                if final_status == "failed" and job["attempts"] + 1 >= job["max_attempts"]:
                    final_status = "dead_letter"
                self._mark_finished(job["job_id"], final_status, message)
                if final_status == "succeeded":
                    processed += 1
                elif final_status == "skipped":
                    skipped += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{job['job_id']}:{exc}")
                self._mark_finished(job["job_id"], "failed", str(exc))
        return RecomputeWorkerSummary(False, len(rows), processed, skipped, failed, errors).as_dict()

    def _queued_rows(self, limit: int) -> list[dict[str, Any]]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM analytics_recompute_jobs
                WHERE status = 'queued'
                  AND available_at <= ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (_now(), max(1, min(limit, 500))),
            ).fetchall()
        return [dict(row) for row in rows]

    def _mark_running(self, job_id: str, attempts: int) -> None:
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                UPDATE analytics_recompute_jobs
                SET status = 'running',
                    attempts = ?,
                    started_at = ?,
                    updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                """,
                (attempts + 1, _now(), _now(), job_id),
            )
            connection.commit()

    def _mark_finished(self, job_id: str, status: str, message: str | None) -> None:
        with closing(self.database.connect()) as connection:
            connection.execute(
                """
                UPDATE analytics_recompute_jobs
                SET status = ?,
                    last_error = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (status, message, _now(), _now(), job_id),
            )
            connection.commit()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
