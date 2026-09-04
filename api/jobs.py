from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AnalysisJob:
    job_id: str
    provider: str
    provider_job_id: str
    status: str
    created_at: float
    updated_at: float
    cost_estimate: dict[str, Any]
    request_summary: dict[str, Any]
    engine_result: dict[str, Any] | None
    provider_error: str | None


class JobStore:
    """Small SQLite registry for analysis submissions.

    This is intentionally provider-agnostic. It lets the API remember that a paid
    submission happened without calling the GPU provider again. SQLite is enough
    for the current single-instance prototype and can later be replaced by
    Postgres without changing the public API shape.
    """

    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("JOB_DB_PATH", "/tmp/football-scout-jobs.sqlite3")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialise()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_job_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    cost_estimate_json TEXT NOT NULL,
                    request_summary_json TEXT NOT NULL,
                    engine_result_json TEXT,
                    provider_error TEXT
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(analysis_jobs)").fetchall()
            }
            if "engine_result_json" not in columns:
                connection.execute("ALTER TABLE analysis_jobs ADD COLUMN engine_result_json TEXT")
            if "provider_error" not in columns:
                connection.execute("ALTER TABLE analysis_jobs ADD COLUMN provider_error TEXT")

    def put(
        self,
        *,
        job_id: str,
        provider: str,
        provider_job_id: str,
        status: str,
        cost_estimate: dict[str, Any],
        request_summary: dict[str, Any],
        engine_result: dict[str, Any] | None = None,
        provider_error: str | None = None,
    ) -> AnalysisJob:
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_jobs (
                    job_id, provider, provider_job_id, status, created_at, updated_at,
                    cost_estimate_json, request_summary_json, engine_result_json,
                    provider_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    cost_estimate_json=excluded.cost_estimate_json,
                    request_summary_json=excluded.request_summary_json,
                    engine_result_json=excluded.engine_result_json,
                    provider_error=excluded.provider_error
                """,
                (
                    job_id,
                    provider,
                    provider_job_id,
                    status,
                    now,
                    now,
                    json.dumps(cost_estimate, separators=(",", ":"), sort_keys=True),
                    json.dumps(request_summary, separators=(",", ":"), sort_keys=True),
                    (
                        json.dumps(engine_result, separators=(",", ":"), sort_keys=True)
                        if engine_result is not None
                        else None
                    ),
                    provider_error,
                ),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> AnalysisJob:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return AnalysisJob(
            job_id=row["job_id"],
            provider=row["provider"],
            provider_job_id=row["provider_job_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            cost_estimate=json.loads(row["cost_estimate_json"]),
            request_summary=json.loads(row["request_summary_json"]),
            engine_result=(
                json.loads(row["engine_result_json"])
                if row["engine_result_json"] is not None
                else None
            ),
            provider_error=row["provider_error"],
        )

    def list_recent(self, limit: int = 20) -> list[AnalysisJob]:
        safe_limit = max(1, min(int(limit), 100))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id FROM analysis_jobs ORDER BY created_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [self.get(row["job_id"]) for row in rows]

    def update_status(self, job_id: str, status: str) -> AnalysisJob:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE analysis_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (status, time.time(), job_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)
        return self.get(job_id)

    def update_from_provider(
        self,
        job_id: str,
        *,
        status: str,
        engine_result: dict[str, Any] | None = None,
        provider_error: str | None = None,
    ) -> AnalysisJob:
        encoded_result = (
            json.dumps(engine_result, separators=(",", ":"), sort_keys=True)
            if engine_result is not None
            else None
        )
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, updated_at = ?, engine_result_json = ?, provider_error = ?
                WHERE job_id = ?
                """,
                (status, time.time(), encoded_result, provider_error, job_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)
        return self.get(job_id)

    @staticmethod
    def public_dict(job: AnalysisJob) -> dict[str, Any]:
        data = asdict(job)
        # Provider identifiers, raw results and provider diagnostics are retained
        # server-side only. Public clients receive a stable, sanitized contract.
        data.pop("provider_job_id", None)
        data.pop("engine_result", None)
        data.pop("provider_error", None)
        data["has_result"] = job.engine_result is not None
        data["has_error"] = job.provider_error is not None
        return data
