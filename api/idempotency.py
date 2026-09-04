from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class IdempotencyPendingError(RuntimeError):
    """Raised when another request already owns the same in-flight submission."""


class IdempotencyStore:
    """Durable SQLite idempotency guard for paid submissions.

    The important property is not only replay caching: ``reserve`` atomically
    claims a key *before* the external GPU request is sent. Concurrent retries
    therefore cannot both launch a paid job. If the process crashes after the
    provider accepted a request but before we persist the response, the key stays
    pending and retries fail closed instead of risking a second charge.

    SQLite is appropriate for the current single-host prototype. A multi-host
    deployment should move the same reservation semantics to shared Postgres or
    another transactional store.
    """

    def __init__(
        self,
        ttl_seconds: int = 24 * 60 * 60,
        max_entries: int = 5000,
        path: str | None = None,
    ):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self.ttl_seconds = int(ttl_seconds)
        self.max_entries = int(max_entries)
        self.path = path or os.getenv(
            "IDEMPOTENCY_DB_PATH", "/tmp/football-scout-idempotency.sqlite3"
        )
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialise()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_submissions (
                    key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('pending', 'completed')),
                    response_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_idempotency_created_at "
                "ON idempotency_submissions(created_at)"
            )

    @staticmethod
    def fingerprint(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    def _purge_locked(self, connection: sqlite3.Connection, now: float) -> None:
        expiry = now - self.ttl_seconds
        # Completed entries may expire normally. Pending entries are deliberately
        # retained for twice the TTL because deleting an uncertain paid request too
        # early could permit an accidental duplicate charge.
        connection.execute(
            "DELETE FROM idempotency_submissions "
            "WHERE (state='completed' AND created_at < ?) "
            "OR (state='pending' AND created_at < ?)",
            (expiry, now - (2 * self.ttl_seconds)),
        )
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM idempotency_submissions"
        ).fetchone()["count"]
        excess = int(count) - self.max_entries
        if excess > 0:
            # Evict completed records first; never evict a recent pending record just
            # to satisfy cache size because safety matters more than cache compactness.
            connection.execute(
                "DELETE FROM idempotency_submissions WHERE key IN ("
                "SELECT key FROM idempotency_submissions WHERE state='completed' "
                "ORDER BY created_at ASC LIMIT ?)",
                (excess,),
            )

    def get(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        now = time.time()
        fingerprint = self.fingerprint(payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._purge_locked(connection, now)
                row = connection.execute(
                    "SELECT * FROM idempotency_submissions WHERE key = ?", (key,)
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise ValueError("Idempotency key was already used with a different payload")
        if row["state"] == "pending":
            raise IdempotencyPendingError(
                "A submission with this idempotency key is already in progress"
            )
        return json.loads(row["response_json"])

    def reserve(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Atomically claim a submission key before contacting a paid provider.

        Returns a completed cached response when this is a safe replay, ``None``
        when the caller successfully acquired the reservation, and raises when the
        same key belongs to another payload or is already in progress.
        """
        now = time.time()
        fingerprint = self.fingerprint(payload)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._purge_locked(connection, now)
                row = connection.execute(
                    "SELECT * FROM idempotency_submissions WHERE key = ?", (key,)
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO idempotency_submissions "
                        "(key, fingerprint, state, response_json, created_at, updated_at) "
                        "VALUES (?, ?, 'pending', NULL, ?, ?)",
                        (key, fingerprint, now, now),
                    )
                    connection.commit()
                    return None
                if row["fingerprint"] != fingerprint:
                    raise ValueError(
                        "Idempotency key was already used with a different payload"
                    )
                if row["state"] == "pending":
                    raise IdempotencyPendingError(
                        "A submission with this idempotency key is already in progress"
                    )
                response = json.loads(row["response_json"])
                connection.commit()
                return response
            except Exception:
                connection.rollback()
                raise

    def put(self, key: str, payload: dict[str, Any], response: dict[str, Any]) -> None:
        """Mark a reserved request completed and persist its replay response."""
        now = time.time()
        fingerprint = self.fingerprint(payload)
        response_json = json.dumps(response, sort_keys=True, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._purge_locked(connection, now)
                row = connection.execute(
                    "SELECT fingerprint FROM idempotency_submissions WHERE key = ?", (key,)
                ).fetchone()
                if row is not None and row["fingerprint"] != fingerprint:
                    raise ValueError(
                        "Idempotency key was already used with a different payload"
                    )
                connection.execute(
                    """
                    INSERT INTO idempotency_submissions
                        (key, fingerprint, state, response_json, created_at, updated_at)
                    VALUES (?, ?, 'completed', ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        state='completed',
                        response_json=excluded.response_json,
                        updated_at=excluded.updated_at
                    """,
                    (key, fingerprint, response_json, now, now),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
